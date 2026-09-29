"""The taxonomy drift check catches the prose defects the audit measured.

Measured 28-09-2026 (QA audit F-L14-041): the shipped skills carried the
deck's 1.50 / 2.50 / 3.50 band cut-offs, the retired fifth-band hex, an
"M5 | Transformational" rubric row, "17 rollups" and "~72 capabilities" —
and `check_taxonomy_drift.py` reported 0 findings, because its band rules
wanted a band word on the same line. These tests plant each defect in a
scratch plugin tree and expect the rule to fire, and plant the three kinds
of legitimate line (lineage, prohibition, deprecated code) and expect
silence. The last test is the point: the shipped plugin scans clean.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_taxonomy_drift",
                                               SCRIPTS / "check_taxonomy_drift.py")
ctd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctd)


def _plant(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text + "\n")


def _literals(root):
    return sorted(h["literal"] for h in ctd.scan(root))


@pytest.mark.parametrize("line, literal", [
    ("| M5 | Transformational | 4.5–5.0 | Industry-leading |", "Transformational"),
    ("label: \"Transformational\"", "Transformational"),
    ("Score ranges: 0.00–1.49 Activating, 1.50–2.49 Building", "1.50 / 2.50 / 3.50 band cut-offs"),
    ("| Differentiating | 3.50–5.00 | #139F94 |", "1.50 / 2.50 / 3.50 band cut-offs"),
    ("Score→Level: 2.50–3.49=Competing", "1.50 / 2.50 / 3.50 band cut-offs"),
    ("Differentiating renders as #185F60 on the strip", "#185F60"),
    # the batch era (QA audit F-L11-042, 29-09-2026)
    ("├── 06_handoff/                # Batch 6 (research_handoff.json)", "06_handoff"),
    ("/home/claude/dma_output/{RUN_ID}/", "/home/claude/"),
    ("web_search FIRST, then Moody's connector — web_search is PRIMARY", "Moody's"),
    ("MANDATORY PROXY RULE for Governance & Strategy subcaps (P1C1-P1C5):", "P1C1-P1C5"),
    ("| `references/safeguard_gates.md` | Batch 4 | 16 safeguard gates |", "safeguard_gates.md"),
    ("append to `evidence_index.json` on disk using this pattern", "evidence_index.json"),
    ("6 batches. Stop after each. Wait for \"continue\". Checkpoint after each batch.", "wait for continue"),
    ("Recency tags: CURRENT (<18mo), RECENT (18-36mo)", "18-month recency"),
    ("recency_tag: CURRENT|RECENT|LEGACY|UNVERIFIED", "LEGACY (recency)"),
    ("One `web_fetch` → 20+ subcap facts.", "web_fetch"),
    ('    "accent":     "185F60",', "#185F60"),
    ("export_category_summary.csv    # 17 rollups with weighted scores", "17 rollups"),
    ("### Capability Micro-Loop (repeat for each ~72 capabilities)", "~72 capabilities"),
    ("the catalogue holds 17 categories", "17 categories"),
])
def test_each_measured_defect_fires_its_rule(tmp_path, line, literal):
    _plant(tmp_path, "skills/x/SKILL.md", line)
    assert _literals(tmp_path) == [literal]


def test_a_lineage_line_a_prohibition_and_deprecated_code_are_not_drift(tmp_path):
    _plant(tmp_path, "skills/x/a.md",
           "v5.0 workbooks carried 17 categories and a Transformational row")
    _plant(tmp_path, "skills/x/b.md",
           "Never write Transformational: there is no fifth band")
    _plant(tmp_path, "skills/x/c.md",
           "Any occurrence of `M5` or `Transformational` is a defect")
    _plant(tmp_path, "skills/x/scripts/deprecated/old.py",
           "LEVEL = 'Transformational'  # 185F60")
    assert ctd.scan(tmp_path) == []


def test_the_batch_era_rules_spare_the_legitimate_lines(tmp_path):
    """A retired script's legacy body, a line saying Moody's is NOT wired, the
    LEGACY_ANCHORED arc shape and a legacy core system are not drift."""
    _plant(tmp_path, "skills/x/scripts/calculate_ers.py",
           "parser.add_argument('evidence_index', help='Path to evidence_index.json')")
    _plant(tmp_path, "skills/x/a.json", '"connector": "moodys", "status": "declared, not wired"')
    _plant(tmp_path, "skills/x/b.md", "arc_shape: STEADY_INVESTMENT | LEGACY_ANCHORED | RECENT_ACCELERATION")
    _plant(tmp_path, "skills/x/c.md", "a legacy core system the estate still runs on")
    assert ctd.scan(tmp_path) == []


def test_a_score_scale_range_is_not_a_band_claim(tmp_path):
    _plant(tmp_path, "skills/x/a.md", "| 2 | Developing | 1.50 – 2.49 | #C7D3EC |")
    _plant(tmp_path, "skills/x/b.md", "ceiling: M1-M5 or null")
    _plant(tmp_path, "skills/x/c.md",
           "Subcap→Capability verification: 72 capabilities tested, 72 within ±0.01")
    assert ctd.scan(tmp_path) == []


def test_the_shipped_plugin_scans_clean():
    assert ctd.scan() == []
