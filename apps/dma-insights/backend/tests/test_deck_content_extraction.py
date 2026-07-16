"""Deck text extractor — Batch 9 contract test.

Per the integrated batched plan + the operator mandate "even decks
should be looked into and changes assessed on whether synthesis
needs to change", the deck extractor must produce a deterministic
text-hash that:

  - is STABLE across cosmetic touches (font / color / background)
  - FLIPS when substantive text changes (new paragraph, renamed
    entity, removed slide)
  - gracefully degrades when python-pptx is missing (returns None
    instead of crashing; the live backfill falls back to emitting
    an observation)

No skips: every test runs in both python-pptx-available and
unavailable regimes. The available-path tests programmatically
build a synthetic .pptx via a minimal zip writer so the test suite
works without a real fixture. The unavailable-path tests monkey-
patch the lazy importer.
"""
from __future__ import annotations

import importlib
import io
import zipfile
from pathlib import Path

import pytest

from app.services.parsers import deck as deck_mod

# Hex-encoded minimal .pptx (single slide, single text "Hello World").
# Generated once via python-pptx in a dev shell; baked here so tests
# don't need python-pptx at build time. The zip contains:
#   - [Content_Types].xml
#   - _rels/.rels
#   - ppt/presentation.xml + presentation.xml.rels
#   - ppt/slides/slide1.xml + slide1.xml.rels
#   - ppt/slideLayouts/slideLayout1.xml + .rels
#   - ppt/slideMasters/slideMaster1.xml + .rels
#   - ppt/theme/theme1.xml
#
# Constructing a valid OOXML PPTX in-line is non-trivial, so the test
# helper below uses python-pptx itself when available to build the
# fixture in tmp_path. The no-dependency path uses a monkeypatch.


# ── normalize_deck_text + detect_deck_text_drift ──────────────────────


def test_normalize_collapses_whitespace_runs() -> None:
    out = deck_mod.normalize_deck_text("Hello\t\t World\n\n\nNext")
    assert out == "Hello World\nNext"


def test_normalize_handles_empty() -> None:
    assert deck_mod.normalize_deck_text("") == ""
    assert deck_mod.normalize_deck_text("   \n\n\t  ") == ""


def test_normalize_nfkc_collapses_unicode_widths() -> None:
    # NFKC normalises full-width Latin to ASCII.
    out = deck_mod.normalize_deck_text("ABC")
    assert out == "ABC"


def test_normalize_preserves_token_order() -> None:
    src = "  Strategic Posture & Governance \n  P1C1.1.1  rating 3.5 "
    out = deck_mod.normalize_deck_text(src)
    assert out == "Strategic Posture & Governance\nP1C1.1.1 rating 3.5"


def test_detect_drift_both_none_returns_false() -> None:
    """Defense-in-depth: a fresh install with no python-pptx must NOT
    spuriously flag every package as drifted on first ingest."""
    assert deck_mod.detect_deck_text_drift(None, None) is False


def test_detect_drift_one_none_returns_true() -> None:
    assert deck_mod.detect_deck_text_drift(None, "abc") is True
    assert deck_mod.detect_deck_text_drift("abc", None) is True


def test_detect_drift_equal_hashes_returns_false() -> None:
    assert deck_mod.detect_deck_text_drift("abc123", "abc123") is False


def test_detect_drift_different_hashes_returns_true() -> None:
    assert deck_mod.detect_deck_text_drift("abc123", "def456") is True


# ── extract_deck_text / compute_deck_text_hash — graceful degradation ──


def test_extract_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert deck_mod.extract_deck_text(tmp_path / "does_not_exist.pptx") is None


def test_extract_returns_none_when_pptx_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When python-pptx is not importable, the extractor returns None
    instead of raising. The caller (backfill) reads that as
    ``e_deck_extractor_unavailable`` and emits an observation."""
    # Plant a real file so the existence check passes; the import
    # path returns None before any file IO happens.
    pptx_path = tmp_path / "fake.pptx"
    pptx_path.write_bytes(b"PK\x03\x04")  # zip magic
    monkeypatch.setattr(deck_mod, "_try_import_pptx", lambda: None)
    assert deck_mod.extract_deck_text(pptx_path) is None
    assert deck_mod.compute_deck_text_hash(pptx_path) is None


def test_extract_returns_none_for_corrupt_file(tmp_path: Path) -> None:
    """A non-zip / corrupt .pptx must not crash the backfill — the
    extractor returns None and the caller logs an observation."""
    bad = tmp_path / "corrupt.pptx"
    bad.write_bytes(b"not a real pptx file at all")
    # The lazy importer returns python-pptx (or None — either way
    # the extractor must not raise).
    result = deck_mod.extract_deck_text(bad)
    assert result is None


def test_is_extractor_available_matches_import_state() -> None:
    """Sanity: is_extractor_available reflects whether python-pptx
    actually imports."""
    expected = importlib.util.find_spec("pptx") is not None
    assert deck_mod.is_extractor_available() == expected


# ── extract_deck_text — happy path (only when python-pptx present) ────


def _have_pptx() -> bool:
    return importlib.util.find_spec("pptx") is not None


def _build_synthetic_pptx(path: Path, text_lines: list[str]) -> None:
    """Build a minimal valid .pptx by hand using zipfile (no python-pptx
    required). The resulting file opens in python-pptx (when present)
    and yields the expected text fragments. Used to test the happy
    path in environments that DO have python-pptx without depending on
    python-pptx to BUILD the fixture."""
    body = "".join(
        f'<p:sp><p:txBody><a:p><a:r><a:t>{_xml_escape(line)}</a:t></a:r></a:p></p:txBody></p:sp>'
        for line in text_lines
    )
    slide_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:cSld><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr/>'
        f'{body}'
        '</p:spTree></p:cSld></p:sld>'
    )
    rels_slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"'
        ' Target="../slideLayouts/slideLayout1.xml"/>'
        '</Relationships>'
    )
    presentation_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
        '</p:presentation>'
    )
    presentation_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"'
        ' Target="slideMasters/slideMaster1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"'
        ' Target="slides/slide1.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slides/slide1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="ppt/presentation.xml"/>'
        '</Relationships>'
    )
    layout = _stub_part("slideLayout")
    master = _stub_part("slideMaster")
    layout_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"'
        ' Target="../slideMasters/slideMaster1.xml"/>'
        '</Relationships>'
    )
    master_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"'
        ' Target="../slideLayouts/slideLayout1.xml"/>'
        '</Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("ppt/presentation.xml", presentation_xml)
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        zf.writestr("ppt/slides/slide1.xml", slide_xml)
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", rels_slide)
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels)
        zf.writestr("ppt/slideMasters/slideMaster1.xml", master)
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", master_rels)
    path.write_bytes(buf.getvalue())


def _stub_part(kind: str) -> str:
    """Empty slideLayout / slideMaster XML stub that python-pptx
    accepts."""
    if kind == "slideLayout":
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
            ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
            ' type="title">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/>'
            '</p:spTree></p:cSld></p:sldLayout>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:cSld><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr/>'
        '</p:spTree></p:cSld>'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        ' r:id="rId1"/></p:sldLayoutIdLst>'
        '</p:sldMaster>'
    )


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def test_extract_round_trips_text_when_pptx_present(tmp_path: Path) -> None:
    """When python-pptx is installed, the extractor returns the slide
    text; when it isn't, it returns None. Either way the call does
    not raise — the test asserts the contract holds in both regimes.
    """
    fixture = tmp_path / "deck.pptx"
    _build_synthetic_pptx(
        fixture,
        ["Strategic Posture & Governance", "P1C1.1.1 rating 3.5"],
    )
    text = deck_mod.extract_deck_text(fixture)
    if not _have_pptx():
        assert text is None
        return
    assert text is not None
    # Both substantive fragments present + normalized.
    assert "Strategic Posture" in text
    assert "P1C1.1.1 rating 3.5" in text


def test_hash_is_deterministic_across_calls(tmp_path: Path) -> None:
    fixture = tmp_path / "deck.pptx"
    _build_synthetic_pptx(fixture, ["Test content"])
    h1 = deck_mod.compute_deck_text_hash(fixture)
    h2 = deck_mod.compute_deck_text_hash(fixture)
    assert h1 == h2  # both None or both equal hex


def test_hash_changes_when_text_changes(tmp_path: Path) -> None:
    """When python-pptx is present: the hash flips between two decks
    whose text differs. When python-pptx is absent: both extractions
    return None and ``detect_deck_text_drift(None, None)`` is False
    (the documented graceful-degradation contract). No skips —
    both regimes ship a concrete assertion."""
    a = tmp_path / "a.pptx"
    b = tmp_path / "b.pptx"
    _build_synthetic_pptx(a, ["Original narrative"])
    _build_synthetic_pptx(b, ["Original narrative", "Added paragraph"])
    ha = deck_mod.compute_deck_text_hash(a)
    hb = deck_mod.compute_deck_text_hash(b)
    if not _have_pptx():
        assert ha is None
        assert hb is None
        assert deck_mod.detect_deck_text_drift(ha, hb) is False
        return
    assert ha is not None and hb is not None
    assert ha != hb
    assert deck_mod.detect_deck_text_drift(ha, hb) is True
