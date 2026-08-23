"""Caps live wherever the assessment kept them, and none is an answer.

Owner, 2026-08-23, verbatim: "Caps applied may even exist in the scoring and
research workbook and usually relate to the issue log or issues raised in the
client research report, or an issue log in csv or any other format. If no
caps were applied, then there were no issues."

What it cost before the rule existed: a vetter refused three consecutive
packages in one firing for a missing `Caps_Applied_Log` SHEET. The routine
spent its client slot and its whole reserve list and produced nobody. Then
the first package it had refused was re-scanned across every format and
found to carry 1,035 cap records in 10 sources — 73, 168, 44 and 95 of them
in a `caps_applied` COLUMN on the four scoring-detail sheets, present the
entire time.

So both halves are pinned here: the scan finds caps in every shape a package
writes them, and an empty result is reported as a state rather than a defect.
"""
import json
import sys
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")
HERE = Path(__file__).resolve().parents[2]   # plugins/dma-insights
sys.path.insert(0, str(HERE / "skills" / "dma-surface-production" / "scripts"))
sys.path.insert(0, str(HERE / "scripts"))
import vet_workbooks as vw  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_findings():
    vw.findings.clear()
    yield
    vw.findings.clear()


def _book(path: Path, sheets: dict):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


def _pm(**over):
    base = {"governance": [], "other": [], "evidence_tables": [], "reports": []}
    base.update(over)
    return base


# ── the shapes a package writes caps in ───────────────────────────────────

def test_caps_in_a_column_are_found(tmp_path):
    """THE MEASURED CASE. The refused package had no Caps_Applied_Log sheet
    and 380 capped rows across four scoring sheets' `caps_applied` column."""
    book = _book(tmp_path / "scoring.xlsx", {
        "P1_Subcap_Scoring": [["SubCap_ID", "Score", "Caps_Applied"],
                              ["P1C1.1", 3, "T3_EVIDENCE_CEILING"],
                              ["P1C1.2", 4, "None"],
                              ["P1C1.3", 2, "CROSS_PILLAR"]],
        "P2_Subcap_Scoring": [["SubCap_ID", "Score", "Caps_Applied"],
                              ["P2C1.1", 3, "T4_CEILING"]]})
    caps = vw.scan_caps(tmp_path, _pm(), [book])
    assert caps["records"] == 3, (
        "two real caps on P1 and one on P2; 'None' is not a cap")
    assert any("P1_Subcap_Scoring" in s for s in caps["sources"])


def test_caps_in_a_sheet_are_found(tmp_path):
    book = _book(tmp_path / "scoring.xlsx", {
        "Caps_Applied_Log": [["Cap_ID", "SubCap_ID", "Reason"],
                             ["C1", "P1C1.1", "no evidence above T3"],
                             ["C2", "P2C1.1", "contradiction unresolved"]]})
    caps = vw.scan_caps(tmp_path, _pm(), [book])
    assert caps["records"] == 2


def test_caps_in_a_csv_are_found(tmp_path):
    (tmp_path / "07_governance").mkdir()
    (tmp_path / "07_governance" / "caps_applied_log.csv").write_text(
        "cap_id,subcap_id,reason\nC1,P1C1.1,thin\nC2,P1C1.2,thin\n")
    caps = vw.scan_caps(
        tmp_path, _pm(governance=["07_governance/caps_applied_log.csv"]), [])
    assert caps["records"] == 2


def test_caps_in_json_are_found(tmp_path):
    (tmp_path / "issue_log.json").write_text(json.dumps(
        {"issues": [{"id": "I1"}, {"id": "I2"}, {"id": "I3"}]}))
    caps = vw.scan_caps(tmp_path, _pm(other=["issue_log.json"]), [])
    assert caps["records"] == 3


def test_a_jsonl_issue_ledger_is_found(tmp_path):
    (tmp_path / "issues.jsonl").write_text(
        '{"id": "I1"}\n{"id": "I2"}\n')
    caps = vw.scan_caps(tmp_path, _pm(other=["issues.jsonl"]), [])
    assert caps["records"] == 2


def test_the_research_workbook_is_searched_too(tmp_path):
    """The owner named BOTH workbooks. A scan that opens only the scoring one
    reproduces the original defect on a package that logged caps beside its
    evidence."""
    scoring = _book(tmp_path / "scoring.xlsx", {"Summary": [["a"], [1]]})
    research = _book(tmp_path / "research.xlsx", {
        "Issue_Log": [["ID", "Issue"], ["I1", "vendor unconfirmed"]]})
    caps = vw.scan_caps(tmp_path, _pm(), [scoring, research])
    assert caps["records"] == 1
    assert any("research.xlsx" in s for s in caps["sources"])


# ── the sentinels ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["", "  ", "-", "N/A", "na", "None",
                                   "NONE", "no", "nil", "0", "False"])
def test_a_no_cap_sentinel_is_not_a_cap(tmp_path, value):
    """A `Caps_Applied` column is populated on every scored row; most rows say
    "no cap" in whichever dialect that package chose. Counting those makes
    every package look maximally capped."""
    book = _book(tmp_path / f"s{abs(hash(value))}.xlsx", {
        "P1_Subcap_Scoring": [["SubCap_ID", "Caps_Applied"], ["P1C1.1", value]]})
    assert vw.scan_caps(tmp_path, _pm(), [book])["records"] == 0


# ── the rule that cost a firing ───────────────────────────────────────────

def test_no_caps_anywhere_is_reported_as_a_state_not_a_defect(tmp_path):
    book = _book(tmp_path / "scoring.xlsx", {
        "P1_Subcap_Scoring": [["SubCap_ID", "Score"], ["P1C1.1", 3]]})
    caps = vw.scan_caps(tmp_path, _pm(), [book])
    assert caps["records"] == 0
    vw.report_caps(caps)
    levels = {lvl for lvl, _ in vw.findings}
    assert "REFUSE" not in levels, (
        "an absent caps log must never be a refusal — this is the exact "
        "finding that burned a firing's client slot and both reserves")
    body = " ".join(m for _, m in vw.findings)
    assert "NO CAPS APPLIED" in body and "NEVER" in body
    assert "no issues" in body, (
        "the report must state the OWNER'S REASON, not merely the absence: "
        "no caps applied means the assessment raised no issues")


def test_report_caps_never_refuses_whatever_it_is_given(tmp_path):
    """Belt and braces on the one property that matters. There is no input
    to this reporter that should stop a package entering the system."""
    for caps in ({"records": 0, "sources": [], "checked": [], "prose": []},
                 {"records": 0, "sources": [], "checked": ["a", "b"],
                  "prose": ["04_reports/issues.docx"]},
                 {"records": 9, "sources": ["x: 9 row(s)"], "checked": ["x"],
                  "prose": []}):
        vw.findings.clear()
        vw.report_caps(caps)
        assert "REFUSE" not in {lvl for lvl, _ in vw.findings}


def test_where_it_looked_is_reported_when_it_finds_nothing(tmp_path):
    """"I found no caps" and "I did not look for caps" must stay
    distinguishable — the same rule the refresh queue's 403 taught."""
    book = _book(tmp_path / "scoring.xlsx", {
        "Caps_Applied_Log": [["Cap_ID", "Reason"]]})       # header only
    caps = vw.scan_caps(tmp_path, _pm(), [book])
    assert caps["records"] == 0
    assert caps["checked"], "an empty sheet was still a place that was checked"
    vw.report_caps(caps)
    assert "looked in" in " ".join(m for _, m in vw.findings)


def test_a_prose_issue_report_is_named_and_never_parsed(tmp_path):
    caps = vw.scan_caps(
        tmp_path, _pm(reports=["04_reports/Client_Issue_Review.docx"]), [])
    assert caps["prose"] == ["04_reports/Client_Issue_Review.docx"]
    assert caps["records"] == 0, "a docx is where a human reads, not a row count"
    vw.report_caps(caps)
    body = " ".join(m for _, m in vw.findings)
    assert "Client_Issue_Review.docx" in body


# ── the rule is written where the agent reads it ──────────────────────────

def test_the_vetter_agent_carries_the_absent_caps_rule():
    """The script reports; the AGENT decides. A rule that lives only in
    Python is a rule the deciding agent never sees."""
    md = (HERE / "agents" / "orchestration" / "package-vetter.md").read_text()
    assert "If no caps were applied, then there were no issues" in md
    assert "never a REFUSE" in md.lower() or "never a refuse" in md.lower()


def test_the_governance_audit_no_longer_calls_an_absent_cap_log_critical():
    doc = (HERE / "skills" / "dma-governance" / "references" /
           "audit_checks.md").read_text()
    iv05 = next(ln for ln in doc.splitlines() if ln.startswith("| IV-05"))
    assert "ABSENT IS A PASS" in iv05
    assert not iv05.rstrip().endswith("CRITICAL |")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the closed refusal list ───────────────────────────────────────────────
#
# The caps defect was one rule refusing wrongly. The class behind it is an
# agent that may refuse for any reason it can articulate: a live session
# refused a package for "103 cell names mismatched against the catalogue",
# a condition no check in this repository raises. Fixing checks one at a
# time cannot bound that; a closed list can.

def test_every_refusal_the_script_raises_carries_a_listed_code():
    """A REFUSE with no code, or a code not on the list, must be impossible
    to write — `note` raises rather than accepting it."""
    import re as _re
    src = Path(vw.__file__).read_text()
    calls = _re.findall(r'note\(\s*"REFUSE".*?\)\s*$', src, _re.S | _re.M)
    assert calls, "no refusals found — the extraction has broken"
    for call in calls:
        m = _re.search(r'code="(V\d+)"', call)
        assert m, f"refusal with no code:\n{call[:200]}"
        assert m.group(1) in vw.SCRIPT_REFUSALS, (
            f"{m.group(1)} is not in SCRIPT_REFUSALS")


def test_an_unlisted_code_cannot_be_emitted():
    with pytest.raises(ValueError, match="refusal without a listed code"):
        vw.note("REFUSE", "something a rule invented", code="V99")
    with pytest.raises(ValueError):
        vw.note("REFUSE", "no code at all")


def test_a_warning_needs_no_code():
    """Only refusals are bounded. Findings must stay cheap to write, or the
    pressure is to upgrade them to refusals to say anything at all."""
    vw.note("WARN", "a column is named oddly")
    assert vw.findings == [("WARN", "a column is named oddly")]


def test_every_script_code_has_a_call_site():
    """A listed code nothing raises advertises a protection that does not
    exist — the same defect as a guard that checks nothing. V6 was removed
    for exactly this reason."""
    src = Path(vw.__file__).read_text()
    for code in vw.SCRIPT_REFUSALS:
        assert f'code="{code}"' in src, (
            f"{code} is listed but never raised — either wire it up or "
            f"retire the number")


def test_the_two_groups_do_not_overlap():
    assert not (set(vw.SCRIPT_REFUSALS) & set(vw.AGENT_REFUSALS))
    assert set(vw.REFUSALS) == set(vw.SCRIPT_REFUSALS) | set(vw.AGENT_REFUSALS)


def test_v6_stays_retired():
    """A retired code must never be reused: a code that changes meaning is
    worse than a gap in the numbering."""
    assert "V6" not in vw.REFUSALS
    assert "no excerpt column found" in Path(vw.__file__).read_text()


def test_the_agent_doc_lists_exactly_the_registry():
    """The script reports and the AGENT decides, so the list has to be in
    front of the agent. A list that lives only in Python bounds nothing."""
    md = (HERE / "agents" / "orchestration" / "package-vetter.md").read_text()
    for code, criterion in vw.REFUSALS.items():
        assert code in md, f"{code} is in the registry and not in the agent doc"
    import re as _re
    in_doc = set(_re.findall(r"\b(V\d+)\b", md))
    assert in_doc <= set(vw.REFUSALS) | {"V6"}, (
        f"the agent doc names codes the registry does not: "
        f"{sorted(in_doc - set(vw.REFUSALS))}")
