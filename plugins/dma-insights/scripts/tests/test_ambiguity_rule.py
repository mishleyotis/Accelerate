"""Every per-surface producer states what it does when the inputs are
ambiguous: it returns `blocked` with a reason, not a section built on a
guess. Measured 28-09-2026 (QA audit F-C03-040): the research lanes had
stated paths (declared absence, search_requests, deferred questions); the
per-surface producers had "return section JSON" and nothing else.
"""
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
PRODUCERS = sorted((PLUGIN / "agents" / "production").rglob("*.md"))


def _section(text, heading):
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def test_there_are_per_surface_producers_to_hold_the_rule():
    assert len([p for p in PRODUCERS if p.name != "README.md"]) >= 24


def test_every_producer_with_an_output_contract_states_the_ambiguity_action():
    missing = []
    for p in PRODUCERS:
        text = p.read_text(encoding="utf-8")
        if "## Output contract" not in text:
            continue
        body = _section(text, "Output contract")
        if '{"blocked"' not in body or "F-C03-040" not in body:
            missing.append(str(p.relative_to(PLUGIN)))
    assert missing == [], missing


def test_the_rule_names_what_settles_it_and_forbids_a_guess():
    p = PLUGIN / "agents/production/heatmap/heatmap-evidence-producer.md"
    body = _section(p.read_text(encoding="utf-8"), "Output contract")
    assert "what would settle it" in body and "do not pick one" in body
