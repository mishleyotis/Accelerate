"""The dma-research skill's prose reads its vocabularies from their owners.

Measured 28-09-2026 (QA audit F-L11-042 / prompt-craft scorecard): the
skill file carried three eras of "how" at once — a six-batch protocol that
waited for "continue", a JSON index appended beside the run, Moody's as a
mandatory second source, `J | Score` beside the contract's column D, an
18/36-month recency ladder beside the engine's 12/24/36/48 — and 80 hard
rules of which three carried a reason. These tests hold the rewritten skill
to its owners: the contract's columns, ladder and labels, the assessment
module's ceilings, the retired-writer list, and the absence of every
batch-era token the audit named.
"""
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
RESEARCH = PLUGIN / "skills" / "dma-research"
sys.path.insert(0, str(RESEARCH))
from engine import assessment, contract as C  # noqa: E402

SKILL = (RESEARCH / "SKILL.md").read_text(encoding="utf-8")
SPEC = (RESEARCH / "references" / "research_workbook_spec.md").read_text(encoding="utf-8")
PROTOCOL = (RESEARCH / "references" / "RESEARCH-PROTOCOL.md").read_text(encoding="utf-8")


def test_the_recency_ladder_in_prose_is_the_contracts():
    words = [w for w, _ in C.RECENCY_LADDER] + [C.RECENCY_ARCHIVAL, C.RECENCY_UNVERIFIED]
    assert words == ["CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL", "UNVERIFIED"], (
        "QA Report B-09: the ladder is CURRENT · RECENT · DATED · STALE · ARCHIVAL")
    line = re.search(r"CURRENT \(<(\d+)\) · RECENT \(<(\d+)\) · DATED \(<(\d+)\) · STALE \(<(\d+)\) · ARCHIVAL", SKILL)
    assert line, "the skill states the ladder in the contract's words"
    assert [int(x) for x in line.groups()] == [hi for _, hi in C.RECENCY_LADDER]
    assert "LEGACY" not in SKILL


def test_the_tier_ceilings_in_prose_are_the_assessment_modules():
    for tier, ceil in assessment.TIER_CEILING.items():
        row = re.search(rf"^\| {tier} \|[^\n]*", SKILL, re.M)
        assert row, tier
        assert f"| {ceil} |" in row.group(0), (tier, row.group(0))


def test_the_claim_labels_in_prose_are_the_contracts():
    for label in C.CLAIM_LABELS:
        assert re.search(rf"^\| {label} \|", SKILL, re.M), label
    assert "`contract.CLAIM_LABELS`" in SKILL


def test_the_workbook_spec_column_table_is_the_contracts():
    rows = re.findall(r"^\| ([A-Z]{1,2}) \| `(\w+)` \|", SPEC, re.M)
    assert [name for _, name in rows] == list(C.PILLAR_COLUMNS)
    assert rows[C.PILLAR_COLUMNS.index("Score")][0] == "D"
    assert "J | Score" not in SPEC and "Column U" not in SPEC


def test_engine_cli_columns_prints_the_contract():
    r = subprocess.run([sys.executable, "-m", "engine.cli", "columns"], cwd=RESEARCH,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    names = [l.split("\t")[1] for l in r.stdout.strip().splitlines()]
    assert names == list(C.PILLAR_COLUMNS)
    assert r.stdout.splitlines()[C.PILLAR_COLUMNS.index("Score")].startswith("D\t")


def test_every_retired_script_is_listed_as_retired_and_no_live_one_is():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("audit_skills", PLUGIN / "scripts" / "audit_skills.py")
    mod = module_from_spec(spec); spec.loader.exec_module(mod)
    research_retired = [w for w in mod.RETIRED_WRITERS if (RESEARCH / "scripts" / w).exists()]
    assert len(research_retired) == 7
    for w in research_retired:
        assert re.search(rf"`scripts/{re.escape(w)}` \| \*\*RETIRED\*\*", SKILL), w


def test_the_batch_era_is_gone_from_the_skill_and_its_references():
    stale = re.compile(r"06_handoff|/home/claude/|Moody|P1C1-P1C5|safeguard_gates\.md|"
                       r"evidence_index\.json|[Ww]ait for .?continue|18\s*mo\b|\bLEGACY\b|"
                       r"\bweb_fetch\b|Batch [1-6]\b|BATCH [1-6]\b|PARAMETER LOCK|"
                       r"DMA_Client_Profile_Research_Template")
    hits = []
    for f in [RESEARCH / "SKILL.md"] + sorted((RESEARCH / "references").glob("*.md")):
        if f.name == "CHANGELOG.md":
            continue  # history, by name
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if stale.search(line) and "retired" not in line.lower():
                hits.append(f"{f.name}:{n}: {line.strip()[:90]}")
    assert hits == [], hits
    for gone in ("batch_execution_protocol.md", "context_window.md",
                 "safeguard_gates.md", "deliverables_spec.md"):
        assert not (RESEARCH / "references" / gone).exists(), gone


def test_the_tools_rule_is_stated_once_and_pointed_at():
    assert PROTOCOL.count("## Tools: first choice, fallback, and what you emit") == 1
    assert "§ *Tools: first choice, fallback, and what you emit*" in re.sub(r"\s+", " ", SKILL)
    # no percentage split survives anywhere in the research prose
    assert not re.search(r"70\s*%\s*of|PRIMARY", SKILL)
    assert not re.search(r"≥\s*70%|70% of", PROTOCOL)


def test_every_rule_carries_its_reason():
    """The scorecard's L-02: 80 hard rules, 3 with a reason. The rules table
    is now two columns, Rule and Why, and every row fills both."""
    table = SKILL.split("## Rules", 1)[1].split("## Evidence tiers", 1)[0]
    rows = [l for l in table.splitlines() if re.match(r"^\| \d+ \|", l)]
    assert len(rows) >= 12
    for r in rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        assert len(cells) == 3 and len(cells[2]) >= 40, r[:80]
