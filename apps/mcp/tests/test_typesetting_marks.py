"""CG-35 — a manuscript mark is not a sentence.

Reported 2026-08-22 from the focus-area drilldown as "invalid characters".
Four pilcrows had reached the served page inside `source_document`:

    "T. Rowe Price press release — T. Rowe Price Announces Creation of Global
     Strategy Function (¶4 of the release (Sharps quote), immediately after
     ¶3's introduction of Andrew Reich)"

The provenance was true and the placement was useful to whoever wrote it. It
is still not a document title, and `¶` is a mark most readers cannot name.

It arrived by a route worth remembering: the same annotation was FIRST written
into `source_page`, an INTEGER column, where it broke promotion outright with
a Postgres type error. Moving it to the nearest string field made the promote
succeed and put the annotation on a client's page. This gate is the second
half of that repair — the first half only stopped it reaching a number column.

THE LIST IS DELIBERATELY NARROW. `§` is not in it: "12 CFR § 1026.36" is real
work in this corpus, and a gate that refused a regulatory citation would be
refusing correct output. What is listed either marks up a manuscript, is
invisible and therefore un-auditable, or is already evidence of a decode that
failed upstream.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                # noqa: E402
from dma_mcp.validation import (_BAD_CHARS,                    # noqa: E402
                                _check_no_typesetting_marks as marks)

REAL = ("T. Rowe Price press release — T. Rowe Price Announces Creation of "
        "Global Strategy Function (¶4 of the release (Sharps quote), "
        "immediately after ¶3's introduction of Andrew Reich)")


# ── the defect ──


def test_the_real_source_document_is_refused():
    out = marks("focus_areas", {"focus_areas": [{"source_document": REAL}]})
    assert len(out) == 1
    r = out[0]
    assert r["path"] == "focus_areas.focus_areas[0].source_document"
    assert "PILCROW" in r["message"]
    assert "¶4 of the release" in r["message"], (
        "the refusal must show the text around the mark, or the producer has "
        "to go hunting for it")


def test_every_listed_mark_is_caught_wherever_it_hides():
    for ch in _BAD_CHARS:
        body = {"a": {"b": [{"c": f"before{ch}after"}]}}
        out = marks("s", body)
        assert len(out) == 1, f"{ch!r} ({_BAD_CHARS[ch]}) was not caught"
        assert out[0]["path"] == "s.a.b[0].c"


def test_the_invisible_ones_matter_most():
    """A zero-width space changes nothing on screen and breaks every search,
    comparison and dedup that touches the field. Nobody reports it; it just
    makes two identical strings stop matching."""
    out = marks("techstack", {"items": [{"vendor": "Sales​force"}]})
    assert len(out) == 1
    assert "ZERO WIDTH" in out[0]["message"]


def test_a_replacement_character_is_a_decode_that_already_failed():
    out = marks("overview", {"headline": "T� Rowe Price"})
    assert len(out) == 1
    assert "REPLACEMENT" in out[0]["message"]


# ── what must NOT be refused ──


def test_a_regulatory_citation_passes():
    """`§` is real work. A gate that refused it would refuse correct output —
    which is why the character list is narrow rather than "non-ASCII"."""
    body = {"rows": [{"citation": "12 CFR § 1026.36(d)(1)",
                      "note": "Regulation Z § 1026 applies."}]}
    assert marks("regulatory_standing", body) == []


def test_ordinary_typography_passes():
    """Em dashes, curly quotes, ellipses and accents are all over this corpus
    and all correct."""
    body = {"text": "The board — chaired by Renée — said “we are ready”… "
                    "and the 2026 report agrees."}
    assert marks("overview", body) == []


def test_a_clean_payload_is_silent():
    assert marks("focus_areas", {"focus_areas": [
        {"source_document": "T. Rowe Price Announces Creation of Global "
                            "Strategy Function"}]}) == []


def test_non_dict_bodies_are_ignored():
    assert marks("s", None) == [] and marks("s", []) == []


# ── registered and wired ──


def test_the_gate_is_registered_and_blocks():
    assert "CG-35" in GATES
    assert GATES["CG-35"][-1] == "block"
    assert "§" not in GATES["CG-35"][2], (
        "the rule text must not imply the section sign is refused")


def test_the_check_is_wired_into_the_dispatch():
    """Every test above calls the check directly and would stay green with it
    unwired. Asserted over the AST — the name appears in its own def and
    docstring, so a substring check would pass on an unwired file."""
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation.py").read_text(encoding="utf-8")
    called = {getattr(n.func, "id", None) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call)}
    assert "_check_no_typesetting_marks" in called
