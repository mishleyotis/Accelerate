"""A column that is null by construction must be answerable — by someone.

TWO OF THIS REPO'S OWN CHECKS DISAGREED, and a producer was caught between
them. `scripts/audit_promoted_client.py`'s C-DROP check BLOCKS a column that
is null on every row unless the payload states the basis in one of nine
carrier keys. None of those nine is in the section contract for
`overview.sentiment`, `overview.leadership` or `techstack.techstack`, so
CG-04 refuses the producer that writes one:

    CG-04  leadership.enrichment_status
           field 'enrichment_status' is not in the overview.leadership contract

The producer's only remaining moves were to fill a column that has nothing
to fill it with, or to ship a blocker and call it known. Measured on Logix
run d7ed1d90 on 2026-08-19: four blockers, all four unattributable —
`trend_vs_prior` on a first assessment, `phone` the contact enrichment never
returned, and the two peer columns no peer technographic pass has been run
for.

The carrier is therefore SERVER-SIDE, in `enrichment_status`, which the API
already injects and which C-DROP already recognises. These tests pin the
three properties that make that true and keep it true:

  1. it is computed from the rows, so a run that fills the column loses the
     note without anyone editing a file — a declaration that outlived its
     truth is exactly the sentinel invariant 9 refuses;
  2. every column named in the register is spelled the way the payload
     spells it, because a typo here reads as "no such absence" and blocks;
  3. the audit's own attribution predicate accepts what this produces —
     asserted against the real function, not a copy of its rules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from dma_api import computed  # noqa: E402

REGISTER = json.loads(
    (ROOT / "packages" / "shared" / "enrichment_register.json").read_text())
SURFACES = REGISTER["surfaces"]

# The four columns this landed for, and the surface each belongs to.
MEASURED = [
    ("overview", "leadership", "roster", "phone"),
    ("overview", "sentiment", "bars", "trend_vs_prior"),
    ("techstack", "techstack", "items", "peer_coverage"),
    ("techstack", "techstack", "items", "peer_deployments"),
]


def _status(page, section, rows_key, rows):
    data = {rows_key: rows}
    computed.enrichment_status(data, page, section)
    return data.get("enrichment_status") or {}


@pytest.mark.parametrize("page,section,rows_key,col", MEASURED)
def test_a_column_null_on_every_row_is_answered(page, section, rows_key, col):
    st = _status(page, section, rows_key, [{col: None}, {col: None}])
    assert col in (st.get("absent_columns") or {}), \
        f"{page}.{section}.{col} is null on every row and says nothing"
    assert len(st["absent_columns"][col]) > 40, \
        "a reason short enough to be a status word is not a reason"


@pytest.mark.parametrize("page,section,rows_key,col", MEASURED)
def test_one_row_carrying_a_value_silences_the_note(page, section, rows_key, col):
    """The self-healing half, and the reason this is computed at all. A
    static declaration would go on claiming the column is empty for ever."""
    st = _status(page, section, rows_key, [{col: None}, {col: "a value"}])
    assert col not in (st.get("absent_columns") or {}), \
        f"{page}.{section}.{col} carries a value on a row and still claims " \
        "the column is structurally absent"


def test_no_rows_at_all_claims_nothing():
    """An empty section is a thin section, which `thin` already reports. It
    is not evidence that any particular column is structurally absent."""
    st = _status("overview", "leadership", "roster", [])
    assert "absent_columns" not in st


def test_every_declared_column_is_named_by_the_section_contract():
    """A typo here does not fail loudly. It reads as "no such absence", the
    note never renders, and C-DROP blocks on a column the register believes
    it has already answered — the register would be lying quietly, which is
    the only kind of lie this build cannot see.

    Checked against the contract's own row documentation, so a column that
    was renamed in the contract takes this test red rather than taking the
    attribution silently offline."""
    contracts = json.loads(
        (ROOT / "apps" / "mcp" / "dma_mcp" / "contracts_data.json").read_text())
    missing = []
    for key, spec in SURFACES.items():
        cols = spec.get("absent_columns") or {}
        if not cols:
            continue
        page, section = key.split(".", 1)
        fields = contracts[page][section]["fields"]
        rows_field = fields.get(spec.get("counts") or "")
        doc = json.dumps(rows_field or fields)
        for col in cols:
            if col != col.strip().lower() or " " in col:
                missing.append(f"{key}.{col} (malformed)")
            elif col not in doc:
                missing.append(f"{key}.{col} (not named by the contract)")
    assert missing == [], (
        "the register declares a column the contract does not name, so the "
        "note it writes can never match a real payload key:\n  "
        + "\n  ".join(missing))


def test_the_audit_predicate_accepts_what_this_produces():
    """Asserted against the audit's OWN function. A test that re-implemented
    its rules would pass while the two drifted, which is the failure this
    whole file exists to end."""
    import audit_promoted_client as audit

    st = _status("overview", "sentiment", "bars", [{"trend_vs_prior": None}])
    body = {"sentiment": {"data": {"bars": [{"trend_vs_prior": None}],
                                   "enrichment_status": st}}}
    assert audit._absence_attributed(
        body, ".sentiment.data.bars[].trend_vs_prior", "trend_vs_prior"), \
        "the audit does not recognise the carrier the server just wrote"


def test_the_carrier_is_one_the_audit_looks_in():
    """`enrichment_status` is the only carrier available on these sections,
    because no basis key is in their contracts. If it ever leaves the audit's
    list, every column below goes back to blocking with nowhere to answer."""
    import audit_promoted_client as audit
    assert "enrichment_status" in audit._BASIS_KEYS


def test_an_undeclared_column_still_blocks():
    """The negative control. This mechanism must not become a way to make
    any perfect null column go quiet — only the ones a human declared."""
    import audit_promoted_client as audit
    st = _status("overview", "leadership", "roster", [{"phone": None}])
    body = {"leadership": {"data": {"roster": [{"phone": None, "salary": None}],
                                    "enrichment_status": st}}}
    assert not audit._absence_attributed(
        body, ".leadership.data.roster[].salary", "salary"), \
        "an undeclared null column was treated as attributed"
