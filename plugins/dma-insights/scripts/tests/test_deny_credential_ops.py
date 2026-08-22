"""The credential guard: deterministic policy where a classifier once stood.

Measured 2026-08-20: a fired synthesis session invented a "GitHub PAT
instruction", committed repo edits outside its writer scope and tried to
push them; the harness classifier blocked it, but a probabilistic block
teaches nothing and invites rephrasing. The hook makes the boundary policy
and puts the sanctioned path in the denial text. Tokens in these tests are
CONSTRUCTED, never literal — the secret scanner is right to be blunt.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "deny_credential_ops.py"
FAKE_PAT = "ghp_" + "x" * 30
FAKE_FG = "github_pat_" + "y" * 24


def _run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, str(HOOK)], input=raw,
                       capture_output=True, text=True)
    assert r.returncode == 0  # the guard never errors a call, it decides
    return json.loads(r.stdout) if r.stdout.strip() else None


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def _is_deny(out):
    return (out or {}).get("hookSpecificOutput", {}).get(
        "permissionDecision") == "deny"


def test_pat_literal_is_denied_with_the_sanctioned_path():
    out = _run(_bash(f"git push https://{FAKE_PAT}@github.com/o/r main"))
    assert _is_deny(out)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "push-ledger" in reason and "rectifier" in reason
    assert "spurious" in reason  # the invented-instruction lesson, verbatim


def test_fine_grained_token_is_denied():
    assert _is_deny(_run(_bash(f"curl -H 'Authorization: token {FAKE_FG}' x")))


def test_embedded_credential_url_is_denied_without_any_token_shape():
    assert _is_deny(_run(_bash(
        "git remote set-url origin https://user:pw@github.com/o/r.git")))


def test_x_access_token_form_is_denied():
    assert _is_deny(_run(_bash(
        "git push https://x-access-token:t@github.com/o/r")))


def test_credential_helper_write_is_denied():
    assert _is_deny(_run(_bash("git config --global credential.helper store")))


def test_google_docs_shell_fetch_is_denied():
    assert _is_deny(_run(_bash(
        "curl -sL https://docs.google.com/document/d/ANYID/export?format=txt")))


def test_the_sanctioned_operations_pass_silently():
    for cmd in (
        "git push -u origin claude/dma-insights-onboarding-0ryrd0",
        "git commit -m 'x' && git push -u origin claude/rectifier-cycle-01",
        "git status && git log --oneline -3",
        "python3 plugins/dma-insights/scripts/drive_fetch.py pull --client x",
        "python3 plugins/dma-insights/scripts/drive_fetch.py push-ledger "
        "--file fixtures/match_feedback.json --session 20260820-synthesis",
        "curl -sf https://www.googleapis.com/drive/v3/files/abc?alt=media",
        "gcloud auth print-identity-token --audiences=https://x",
    ):
        assert _run(_bash(cmd)) is None, cmd


def test_malformed_stdin_fails_open():
    assert _run("this is not json") is None


def test_other_tools_are_not_the_guards_business():
    assert _run({"tool_name": "Read",
                 "tool_input": {"command": f"https://{FAKE_PAT}@github.com"}}
                ) is None
