"""The preflight's contract is one sentence: what it prints and what it exits
with must be the same claim.

The measured defect broke it twice over — a 403 from the connector fell into
a `*)` branch that printed WARN and left FAIL=0, so a routine with no write
path read "PREFLIGHT PASS — proceed", claimed a run, and synthesised for
hours. These tests drive the real script with stubbed `gcloud` and `python3`
so every branch is exercised, and assert the invariant on every scenario.
"""
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "routine_preflight.sh"

GCLOUD_STUB = r"""#!/usr/bin/env bash
# Minimal gcloud, driven by STUB_* env vars. Prints no secret because it holds
# none: `print-access-token` succeeds or fails, and that is the whole check.
case "$*" in
  *"auth print-access-token"*)
    [ "${STUB_CAN_MINT:-1}" = "1" ] || { echo "ERROR: no credentials" >&2; exit 1; }
    echo "ya29.stub-access-token"; exit 0 ;;
  *"auth list"*)
    echo "${STUB_ACCOUNT:-routine@digital-maturity-assessor.iam.gserviceaccount.com}"
    exit 0 ;;
  *"run services describe"*)
    [ "${STUB_SERVICES_UP:-1}" = "1" ] || exit 1
    echo "stub-revision-00001"; exit 0 ;;
  *"--version"*) echo "Google Cloud SDK 000.0.0"; exit 0 ;;
esac
exit 0
"""

PYTHON_STUB = r"""#!/usr/bin/env bash
# Stands in for the two python entrypoints the preflight drives.
case "${1:-}" in
  *routine_secrets.py)
    case "${STUB_SECRETS_EXIT:-0}" in
      0) echo "github pat        OK   accepted by GitHub" ;;
      2) echo "intake folder     WARN listed successfully and is genuinely empty" ;;
      *) echo "github pat        FAIL EXPIRED at 2026-08-08 10:15:28 UTC" ;;
    esac
    exit "${STUB_SECRETS_EXIT:-0}" ;;
  -)
    cat >/dev/null                      # swallow the heredoc
    echo "${STUB_MCP_LINE:-OK}"
    exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def stubs(tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    for name, body in (("gcloud", GCLOUD_STUB), ("python3", PYTHON_STUB)):
        p = d / name
        p.write_text(textwrap.dedent(body))
        p.chmod(0o755)
    return d


def run(stubs, **env):
    e = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
    e.pop("INTAKE_FOLDER_ID", None)
    e.update({k: str(v) for k, v in env.items()})
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                       env=e, timeout=120)
    verdict = [ln for ln in r.stdout.splitlines() if ln.startswith("PREFLIGHT")]
    assert verdict, f"no composite verdict printed:\n{r.stdout}\n{r.stderr}"
    return r.returncode, verdict[-1], r.stdout


# scenario -> (env, expected verdict word)
SCENARIOS = {
    "everything works": ({"INTAKE_FOLDER_ID": "abc123"}, "PASS"),
    "connector 403": ({"STUB_MCP_LINE": "ERR HTTPError: HTTP Error 403: Forbidden"},
                      "FAIL"),
    "connector unreachable": ({"STUB_MCP_LINE": "ERR URLError: connection refused"},
                              "FAIL"),
    "expired pat": ({"STUB_SECRETS_EXIT": 1}, "FAIL"),
    "degraded secrets": ({"STUB_SECRETS_EXIT": 2}, "WARN"),
    "no working credential": ({"STUB_CAN_MINT": 0}, "FAIL"),
    "service not deployed": ({"STUB_SERVICES_UP": 0}, "FAIL"),
    "intake id unset": ({}, "WARN"),
    # A FAIL alongside a WARN must still read FAIL — the harsher verdict wins.
    "expired pat and a warning": ({"STUB_SECRETS_EXIT": 1}, "FAIL"),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_verdict_matches_expectation(stubs, name):
    env, expected = SCENARIOS[name]
    code, verdict, out = run(stubs, **env)
    assert f"PREFLIGHT {expected}" in verdict, out


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_verdict_and_exit_code_never_disagree(stubs, name):
    """The invariant. A run that prints FAIL on one line and exits 0 is worse
    than no preflight at all: the routine reads the exit code."""
    env, _ = SCENARIOS[name]
    code, verdict, out = run(stubs, **env)
    printed_fail = "PREFLIGHT FAIL" in verdict
    assert printed_fail == (code != 0), (
        f"verdict {verdict!r} but exit {code}\n{out}")


def test_a_refused_connector_is_not_downgraded_to_a_warning(stubs):
    """Content enters the app only through the connector. No connector means
    no output, so this can never be 'degraded but workable'."""
    code, verdict, out = run(
        stubs, STUB_MCP_LINE="ERR HTTPError: HTTP Error 403: Forbidden")
    line = [ln for ln in out.splitlines() if ln.startswith("mcp tool call")][0]
    assert " FAIL " in line, line
    assert " WARN " not in line, line
    assert code == 1


def test_warnings_alone_do_not_block_a_run(stubs):
    code, verdict, out = run(stubs, STUB_SECRETS_EXIT=2)
    assert code == 0
    assert "PREFLIGHT WARN" in verdict
    assert "proceed" in verdict


def test_identity_check_survives_a_named_account_with_no_credential(stubs):
    """`gcloud config get-value account` prints a name and exits 0 against an
    emptied credential store. The stub keeps the account name and removes the
    credential; the preflight must still refuse."""
    code, verdict, out = run(stubs, STUB_CAN_MINT=0)
    line = [ln for ln in out.splitlines() if ln.startswith("gcloud identity")][0]
    assert " FAIL " in line, line
    assert code == 1
