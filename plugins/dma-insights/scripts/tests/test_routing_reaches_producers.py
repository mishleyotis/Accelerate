"""The routing chain resolves — from every entry, for every hop.

AUD-0004, 0005, 0053, 0054, 0055, 0058, 0132 and 0149 all describe one
failure in different places: an unattended producer follows the documented
route and arrives nowhere. These tests walk the route the way an agent would.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
SP = PLUGIN / "skills" / "dma-surface-production"
LIFECYCLE = SP / "05-lifecycle"
HOOKS = PLUGIN / "scripts" / "hooks"


def _run(script, payload):
    return subprocess.run(
        [sys.executable, str(script)], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30)


# ── AUD-0005 · the second hop is not dead ────────────────────────────────

def test_every_rulebook_anchor_in_the_surface_map_resolves():
    text = (LIFECYCLE / "surface-map.md").read_text()
    refs = set(re.findall(r"`?((?:\.\./)?[\w./-]*rulebooks/[a-z]+\.md)", text))
    assert refs, "the map must carry rulebook anchors at all"
    missing = [r for r in refs if not (LIFECYCLE / r).resolve().is_file()]
    assert missing == [], missing


def test_the_client_memory_anchor_resolves_too():
    text = (LIFECYCLE / "client-memory.md").read_text()
    for r in set(re.findall(r"((?:\.\./)?[\w./-]*rulebooks/[a-z]+\.md)", text)):
        assert (LIFECYCLE / r).resolve().is_file(), r


def test_the_broken_reference_ceiling_is_zero_not_todays_defect_count():
    """The ceiling was 8 — exactly the then-current defect count — so the
    check passed while 49 of 53 rows pointed at nothing."""
    src = (PLUGIN / "scripts" / "audit_skills.py").read_text()
    m = re.search(r"^MAX_BROKEN\s*=\s*(\d+)", src, re.M)
    assert m and int(m.group(1)) == 0


def test_audit_skills_reports_no_broken_references():
    r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "audit_skills.py")],
                       capture_output=True, text=True, timeout=300)
    doc = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    assert doc["broken_refs_total"] == 0, doc["broken_refs"]


# ── AUD-0004 / AUD-0054 · the brief reaches every start ──────────────────

@pytest.mark.parametrize("source", ["startup", "clear", "resume", "compact",
                                    "fork"])
def test_the_brief_prints_on_all_five_session_start_sources(source):
    out = _run(HOOKS / "session_brief.py", {"source": source}).stdout
    assert "route before you produce" in out
    assert "routing.md" in out


def test_the_compaction_brief_names_a_destination():
    """'compaction' as a session event did not exist in any of the skill's
    63 files, so an agent that lost the brief had nowhere to route."""
    out = _run(HOOKS / "session_brief.py", {"source": "compact"}).stdout
    assert "After a compaction" in out
    assert "After a compaction" in (LIFECYCLE / "routing.md").read_text()


def test_a_subagent_gets_the_brief_through_the_event_that_reaches_it():
    """SessionStart hooks reach top-level sessions only, and the Routine
    dispatches every producer as an in-process subagent."""
    out = _run(HOOKS / "session_brief.py",
               {"hook_event_name": "SubagentStart",
                "agent_type": "heatmap-grid-producer"}).stdout
    doc = json.loads(out)
    ctx = doc["hookSpecificOutput"]["additionalContexts"][0]
    assert doc["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "route before you produce" in ctx
    assert "do not submit or promote" in ctx


def test_the_plugin_declares_the_subagent_hook():
    d = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert "SubagentStart" in d["hooks"]


def test_the_brief_fails_open_on_a_malformed_event():
    r = subprocess.run([sys.executable, str(HOOKS / "session_brief.py")],
                       input="not json", capture_output=True, text=True)
    assert r.returncode == 0 and "route before you produce" in r.stdout


# ── AUD-0055 · the headless preamble carries routing ─────────────────────

def test_the_dispatch_preamble_carries_the_routing_rule():
    src = (PLUGIN / "scripts" / "agent_run.py").read_text()
    pre = src[src.index("PREAMBLE = "):src.index("--- TASK ---")]
    for token in ("routing.md", "get_memory_digest", "promote",
                  "finding-challenger", "explain_gate"):
        assert token in pre, f"the preamble never mentions {token}"


# ── AUD-0058 · the two routes that used to dead-end ──────────────────────

def test_a_reviewer_rejected_card_routes_in_one_hop():
    """list_reviewer_feedback is keyed by ic_id and carries no JSON path, so
    the table's 'when a note names a JSON path' rule could not resolve it."""
    text = (LIFECYCLE / "routing.md").read_text()
    assert "ic_id" in text
    assert "insights-cards-producer" in text
    for prefix in ("ic_id", "rec_id", "f_id", "fa_id", "ts_id", "wn_id"):
        assert prefix in text, f"{prefix} has no route"


def test_routing_names_the_gate_authorities():
    """routing.md contained zero gate references and never named
    explain_gate, so a repairer had no route from a gate id to its rule."""
    text = (LIFECYCLE / "routing.md").read_text()
    assert "explain_gate" in text and "1-gates.md" in text


# ── AUD-0053 · every gate the connector can emit is documented ───────────

def _emitted_gate_ids():
    out = set()
    base = REPO / "apps" / "mcp" / "dma_mcp"
    for p in list(base.glob("*.py")) + list(base.glob("*.json")):
        out |= set(re.findall(r"\b(?:CG|AG|SG|ET)-[0-9]+\b",
                              p.read_text(errors="ignore")))
    return out


def test_no_gate_the_connector_emits_is_undocumented():
    doc = (LIFECYCLE / "1-gates.md").read_text()
    documented = set(re.findall(r"\b(?:CG|AG|SG|ET)-[0-9]+\b", doc))
    missing = sorted(_emitted_gate_ids() - documented)
    assert missing == [], missing


def test_the_worked_example_gate_is_present():
    assert "CG-30" in (LIFECYCLE / "1-gates.md").read_text()


def test_the_gate_census_is_not_stale():
    r = subprocess.run([sys.executable,
                        str(PLUGIN / "scripts" / "gen_gates_md.py"), "--check"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


# ── AUD-0132 · a manifest works wherever the plugin is installed ─────────

def test_no_agent_manifest_hardcodes_a_checkout_path():
    bad = [str(p.relative_to(PLUGIN)) for p in (PLUGIN / "agents").rglob("*.md")
           if "/home/user/Accelerate" in p.read_text()]
    assert bad == [], bad


def test_plugin_internal_references_use_the_plugin_variable():
    n = sum(p.read_text().count("${CLAUDE_PLUGIN_ROOT}")
            for p in (PLUGIN / "agents").rglob("*.md"))
    assert n > 100, f"only {n} plugin-root references — did a rewrite regress?"


# ── AUD-0101 · the never-cat rule is enforced, not just written ──────────

@pytest.mark.parametrize("cmd", [
    "cat /run/01_evidence/evidence_index.json",
    "cat $RUN/ledger.jsonl",
    "less kg/pack_P1C1.json",
    "cat engagement_set.json | head",
])
def test_a_whole_file_read_of_a_forbidden_path_is_denied(cmd):
    out = _run(HOOKS / "deny_bulk_read.py",
               {"tool_name": "Bash", "tool_input": {"command": cmd}}).stdout
    assert out.strip(), f"not denied: {cmd}"
    d = json.loads(out)["hookSpecificOutput"]
    assert d["permissionDecision"] == "deny"
    assert "Run this instead" in d["permissionDecisionReason"]


@pytest.mark.parametrize("cmd", [
    "grep -c E- /run/01_evidence/evidence_index.json",
    "head -c 400 $RUN/ledger.jsonl",
    "jq '.subcap_records | length' research_handoff.json",
    "wc -l engagement_set.json",
    "cat README.md",
])
def test_a_bounded_read_and_an_unrelated_file_are_allowed(cmd):
    out = _run(HOOKS / "deny_bulk_read.py",
               {"tool_name": "Bash", "tool_input": {"command": cmd}}).stdout
    assert out.strip() == "", f"wrongly denied: {cmd}"


# ── AUD-0062 / 0070 / 0071 · the taxonomy the skills state ───────────────

def test_no_skill_states_a_stale_taxonomy_count():
    r = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "check_taxonomy_drift.py")],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout


def test_the_killed_seventeenth_category_has_no_criteria_block_left():
    """Naming P1C5 to say it is retired is right; carrying a scoring block
    for it is the defect. So the test is on the SECTIONS, not on mentions."""
    for rel, heading in (
            ("skills/dma-assessment/references/capability_criteria.md",
             r"^###\s+(P[1-4]C\d)"),
            ("skills/dma-research/references/diagnostic_questions.md",
             r"^\*\*(P[1-4]C\d)")):
        text = (PLUGIN / rel).read_text()
        sections = re.findall(heading, text, re.M)
        assert "P1C5" not in sections, f"{rel} still scores the retired category"
        assert len(set(sections)) == 16, \
            f"{rel} carries {len(set(sections))} category blocks"


def test_the_fallback_question_bank_states_its_real_coverage():
    """It claimed ~836 questions and holds category-level patterns."""
    text = (PLUGIN / "skills/dma-research/references/"
                     "diagnostic_questions.md").read_text()
    assert "one group of question PATTERNS per" in text
    assert "Grading a closed pattern" in text


# ── AUD-0093 · the credential doc states the reach it actually has ───────

def test_secrets_md_states_the_drive_scope_the_key_mints():
    text = (PLUGIN / "docs" / "secrets.md").read_text()
    assert "auth/drive" in text
    assert "not `drive.readonly`" in text or "not `drive.readonly`" in text


# ── AUD-0032 · the handoff seam reads the workbook, not the JSON ────────

def test_dma_assessment_keys_its_handoff_on_the_workbook():
    """The documented primary mode keyed on `research_handoff.json`'s
    PRESENCE, and the workbook played no role in the handoff at all — so
    the artefact the owner audits and the artefact the pipeline trusted
    could diverge with no gate noticing."""
    text = (PLUGIN / "skills" / "dma-assessment" / "SKILL.md").read_text()
    phase0 = text[text.index("## Phase 0"):text.index("## Phase 1")] \
        if "## Phase 1" in text else text[text.index("## Phase 0"):]
    assert "THE WORKBOOK, not the JSON" in phase0
    assert "Handoff_Lock" in phase0
    assert "catalogue_hash" in phase0
    assert "HARD STOP" in phase0
    assert "the workbook is right" in phase0


def test_the_handoff_json_is_described_as_an_index_not_an_interface():
    # Whitespace-normalised: the sentence wraps in the source, and a test
    # that breaks on a reflow tells you nothing about the rule.
    text = " ".join((PLUGIN / "skills" / "dma-assessment" / "SKILL.md")
                    .read_text().split())
    assert "read-only index over those same sheets" in text
    assert "It is not the interface." in text
    assert "If the two ever disagree, the workbook is right." in text
