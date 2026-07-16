"""Evidence extraction from non-canonical package layouts.

A QA sweep found 8 production packages whose evidence index shipped under
a name/location the canonical chain missed, leaving the EvidenceDrawer
empty for those clients (ANB Texas, Cathay, Compeer, Farm Credit
Mid-America, Guaranteed Rate, Interactive Brokers, LPL, Payments Canada).
The parser now:

  * tolerates a dict-keyed `evidence_items` map (Compeer),
  * aliases the per-row keys these packages use (`date_published` /
    `pub_date` / `date`, `source_title`, `summary` / `finding` /
    `key_fact`, `maps_to` / `subcap_mapping`, `ers_score`,
    `claim_label`), and
  * discovers evidence under case-mismatched 01_evidence names plus the
    `08_appendices`, `02_research_workbook`, and `01_Research/**`
    locations — only when the canonical chain yielded nothing.

These tests lock the behaviour. The pure-logic shape tests always run;
the real-corpus assertion skips when the committed batch corpus is
absent (CI sandbox without fixtures).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.dma_package import (
    _evidence_rows_from_json,
    parse_package,
)


def _write(tmp_path: Path, name: str, payload: str) -> Path:
    p = tmp_path / name
    p.write_text(payload, encoding="utf-8")
    return p


def test_dict_keyed_evidence_items_compeer_shape(tmp_path: Path) -> None:
    """`evidence_items` keyed by E-ID (Compeer) flattens, key → e_id."""
    payload = """
    {"evidence_items": {
        "E-027": {"source": "Built In job posting", "tier": "T4",
                  "date": "2024",
                  "finding": "Compeer uses Power BI for reporting.",
                  "subcap_mapping": ["P4C2", "P4C3"], "claim_label": "FACT"},
        "E-028": {"source": "Press release", "tier": "T2",
                  "date": "2025", "finding": "Core conversion announced.",
                  "subcap_mapping": ["P1C1"], "claim_label": "FACT"}
    }}
    """
    rows = _evidence_rows_from_json(_write(tmp_path, "c.json", payload), [])
    assert len(rows) == 2
    by_id = {r.e_id: r for r in rows}
    assert set(by_id) == {"E-027", "E-028"}
    r = by_id["E-027"]
    assert r.source_name == "Built In job posting"
    assert r.excerpt.startswith("Compeer uses Power BI")
    assert r.publish_date == "2024"
    assert r.subcap_mappings == ["P4C2", "P4C3"]
    assert r.signal_direction == "FACT"


def test_lpl_checkpoint_aliases(tmp_path: Path) -> None:
    """LPL: `source_title` / `pub_date` / `summary` aliases resolve."""
    payload = """
    {"evidence_items": [
        {"e_id": "E-001", "source_title": "LPL newsroom",
         "source_url": "https://www.lpl.com/news", "pub_date": "2025-09-01",
         "summary": "Record advisor count.", "ers_score": 3.2,
         "claim_label": "POSITIVE"}
    ]}
    """
    rows = _evidence_rows_from_json(_write(tmp_path, "l.json", payload), [])
    assert len(rows) == 1
    r = rows[0]
    assert r.e_id == "E-001"
    assert r.source_name == "LPL newsroom"
    assert r.source_url == "https://www.lpl.com/news"
    assert r.publish_date == "2025-09-01"
    assert r.excerpt == "Record advisor count."
    assert r.signal_direction == "POSITIVE"


def test_payments_canada_register_aliases(tmp_path: Path) -> None:
    """Payments Canada register: `id` / `source` / `date` / `key_fact` /
    `maps_to`. A free-text date *range* survives as a string (the persist
    layer coerces it to NULL — never crashes)."""
    payload = """
    {"items": [
        {"id": "PC-1", "source": "Payments Canada 2026 SUMMIT",
         "tier": "T2", "date": "2026-03-19 to 2026-05-07",
         "key_fact": "Real-time rail go-live slips.",
         "maps_to": ["P1C1", "P3C2"]}
    ]}
    """
    rows = _evidence_rows_from_json(_write(tmp_path, "p.json", payload), [])
    assert len(rows) == 1
    r = rows[0]
    assert r.e_id == "PC-1"
    assert r.source_name == "Payments Canada 2026 SUMMIT"
    assert r.excerpt.startswith("Real-time rail")
    assert r.subcap_mappings == ["P1C1", "P3C2"]
    assert r.publish_date == "2026-03-19 to 2026-05-07"


def test_cathay_enhanced_evidence_date_published(tmp_path: Path) -> None:
    """Cathay enhanced_evidence: `date_published` alias → publish_date."""
    payload = """
    {"items": [
        {"evidence_id": "E-1", "source_name": "BusinessWire",
         "source_url": "https://www.businesswire.com/x", "tier": "T2",
         "date_published": "2025-01-22"}
    ]}
    """
    rows = _evidence_rows_from_json(_write(tmp_path, "e.json", payload), [])
    assert len(rows) == 1
    assert rows[0].publish_date == "2025-01-22"
    assert rows[0].source_url.startswith("https://www.businesswire.com")


def test_noncanonical_discovery_does_not_fire_when_canonical_present(
    tmp_path: Path,
) -> None:
    """Guard: the new fallbacks fire ONLY when canonical 01_evidence
    yielded rows of zero — a package with a populated canonical index must
    NOT be overridden by an 08_appendices file."""
    root = tmp_path / "Acme - DMA"
    (root / "01_evidence").mkdir(parents=True)
    (root / "08_appendices").mkdir(parents=True)
    # canonical index: 1 row
    (root / "01_evidence" / "evidence_index.json").write_text(
        '{"items": [{"evidence_id": "CANON-1", "source_name": "canon",'
        ' "url": "https://x", "tier": "T2"}]}',
        encoding="utf-8",
    )
    # decoy 08_appendices file with MORE rows — must be ignored.
    (root / "08_appendices" / "enhanced_evidence.json").write_text(
        '{"items": [{"evidence_id": "DECOY-1", "source_name": "d", "tier": 2},'
        ' {"evidence_id": "DECOY-2", "source_name": "d", "tier": 2}]}',
        encoding="utf-8",
    )
    pkg = parse_package(root)
    eids = {e.e_id for e in (pkg.evidence or [])}
    assert "CANON-1" in eids
    assert "DECOY-1" not in eids and "DECOY-2" not in eids


# ── Real-corpus assertion — the 8 packages that regressed ──────────────
_CORPUS = (
    Path(__file__).resolve().parent / "fixtures" / "dma_packages_batches"
)

# (batch-relative client dir, minimum evidence rows expected after dedup)
_EIGHT = [
    ("batch_13/American National Bank of Texas - DMA", 20),
    ("batch_09/Cathay Bank - DMA", 20),
    ("batch_12/Compeer Financial - DMA", 20),
    ("batch_15/Farm Credit Mid America - DMA", 50),
    ("batch_06/Guaranteed Rate - DMA", 50),
    ("batch_15/Interactive Brokers - DMA", 40),
    ("batch_08/LPL Financials - DMA", 50),
    ("batch_13/Payments Canada - DMA", 5),
]

_CANON = ("01_evidence", "00_entity_profile", "01_Research")


def _find_root(base: Path) -> Path:
    if any((base / s).is_dir() for s in _CANON):
        return base
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if any((d / s).is_dir() for s in _CANON):
            return d
    return base


@pytest.mark.skipif(
    not _CORPUS.is_dir(), reason="batch corpus not present on this runner"
)
@pytest.mark.parametrize("rel,floor", _EIGHT)
def test_eight_noncanonical_packages_yield_evidence(
    rel: str, floor: int
) -> None:
    base = _CORPUS / rel
    if not base.is_dir():
        pytest.skip(f"fixture absent: {rel}")
    pkg = parse_package(_find_root(base))
    n = len(pkg.evidence or [])
    assert n >= floor, f"{rel}: expected >= {floor} evidence rows, got {n}"


# ── CSV A1 inventory in 08_appendices / 02_research_workbook ────────────
# The 2026-06-26 depth audit found the CSV evidence-variant fallback searched
# ONLY 01_evidence, so packages shipping `A1_Evidence_Inventory.csv` under
# 08_appendices (Acuity, Bank of Utah) had their E-ID<->subcap map dropped ->
# why-now / findings rendered with zero traceable evidence. The fallback now
# also searches 08_appendices + 02_research_workbook.
_A1_APPENDIX = [
    ("batch_14/Acuity Insurance - DMA", 30),
]


@pytest.mark.skipif(
    not _CORPUS.is_dir(), reason="batch corpus not present on this runner"
)
@pytest.mark.parametrize("rel,floor", _A1_APPENDIX)
def test_a1_inventory_in_appendices_yields_subcap_linked_evidence(
    rel: str, floor: int
) -> None:
    base = _CORPUS / rel
    if not base.is_dir():
        pytest.skip(f"fixture absent: {rel}")
    pkg = parse_package(_find_root(base))
    ev = pkg.evidence or []
    linked = [e for e in ev if e.subcap_mappings]
    assert len(ev) >= floor, f"{rel}: {len(ev)} evidence rows (< {floor})"
    # the A1 inventory carries `subcaps_supported` on (nearly) every row, so
    # the recovered evidence must be overwhelmingly subcap-traceable.
    assert len(linked) >= 0.8 * len(ev), (
        f"{rel}: only {len(linked)}/{len(ev)} evidence rows subcap-linked"
    )
