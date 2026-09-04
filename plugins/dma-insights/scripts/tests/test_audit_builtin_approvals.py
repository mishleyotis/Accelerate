"""Every command the manifests and Routines issue passes the built-in hook.

The hook is a grammar, and a grammar is only as good as the corpus it was
checked against. This runs `audit_builtin_approvals.py` — which harvests the
real commands from the agents, the skills and the Routine prompts and feeds
each to the real hook — and fails on any that would prompt. A new manifest
line the grammar does not know fails HERE, before a scheduled firing hangs on
it.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent / "audit_builtin_approvals.py"

sys.path.insert(0, str(HERE.parent))
import audit_builtin_approvals as A  # noqa: E402


def test_the_harvest_finds_the_commands_the_pipeline_actually_runs():
    rows = A.harvest()
    cmds = " || ".join(r["command"] for r in rows)
    assert len(rows) >= 80, f"only {len(rows)} commands harvested — the walk broke"
    for must in ("engine.cli", "engine.assessment", "agent_run.py",
                 "drive_fetch.py", "doctor.py", "ship_page.py"):
        assert must in cmds, f"{must} is not in the harvested corpus"


def test_placeholders_are_normalised_to_what_a_session_types():
    n = A.normalise
    assert "{" not in n("python3 -m engine.gold_standard report <docx> --kind {research|assessment}")
    assert "<" not in n("python scripts/ship_page.py <run_id> <page|all> --sections DIR [--promote]")
    assert n("python3 -m engine.cli orient --run <RUN_ID> --root <ROOT>") == \
        "python3 -m engine.cli orient --run R-1 --root /root/.dma/runs/R-1"


def test_a_sentence_that_starts_with_a_verb_name_is_not_harvested():
    rows = A.harvest()
    assert not any(r["command"].startswith("tail is ") for r in rows)


def test_no_harvested_command_would_prompt():
    r = subprocess.run([sys.executable, str(AUDIT), "--strict"],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "would PROMPT" in r.stdout and " 0 would PROMPT" in r.stdout


def test_a_skill_relative_path_resolves_from_the_skill_directory():
    """`python ../../scripts/inspect_client_folders.py` is how SKILL.md
    writes it, from the skill's own directory. Judged from the repo root it
    resolves to nothing and would read as a prompt."""
    cmd = "python ../../scripts/inspect_client_folders.py --client X"
    skill = A.PLUGIN / "skills" / "dma-surface-production"
    assert A.classify(cmd, str(skill)) == "ALLOWED"
    assert A.classify(cmd, str(A.REPO)) == "PROMPTS"
