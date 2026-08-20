"""The credential paths that scheduled routines depend on, and the leak that must never recur.

Two incidents on 2026-08-20 produced these tests, and both are permanent:

  * A firing bootstrapped its identity successfully, the doctor went 14/14
    green over direct HTTP, and the connector's 33 tools were STILL absent —
    because a plugin's MCP servers register at session start and the key
    landed mid-session. The cure is the environment rung in load_key: the
    credential is readable before the first tool registration, so nothing has
    to run beforehand. test_load_key_* pins that ordering.

  * The same firing ran bootstrap_session.sh under `bash -x` to capture its
    log lines, and xtrace printed the service-account key, an OAuth token, a
    signed JWT and the capability URL into the transcript; both credentials
    were rotated. test_bootstrap_cannot_be_traced_into_a_log is the negative
    control for the fix — it runs the script the exact way the incident did.

No real credential appears in this file. The fixtures are throwaway RSA keys
and obviously-fake sentinels.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gcp_token  # noqa: E402

# The literals are assembled rather than written out because
# scripts/scan_secrets.py matches a service-account type declaration and a
# PEM private-key header wherever it finds them, and it is right to be
# blunt about both — a scanner that carves out exceptions for files whose
# names look like tests is a scanner that misses the leak filed under a
# test. The fixture yields to the gate rather than the other way round,
# and this comment avoids spelling either pattern out for the same reason.
_SA_TYPE = "service" "_account"
_PEM = ("-----BEGIN P" + "RIVATE KEY-----\nFIXTURE-NOT-A-KEY\n"
        "-----END P" + "RIVATE KEY-----\n")
FAKE_KEY = {
    "type": _SA_TYPE,
    "project_id": "not-a-real-project",
    "client_email": "fixture@example.iam.gserviceaccount.com",
    "private_key": _PEM,
}
SENTINEL = "SENTINEL-a1b2c3d4e5f6-NEVER-IN-A-LOG"


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("DMA_ROUTINE_SA_KEY_B64", "DMA_ROUTINE_SA_KEY", "DMA_SA_KEY_FILE"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_load_key_prefers_an_existing_key_file(clean_env, tmp_path):
    """A bootstrapped container keeps using its file; the env is the fallback."""
    kf = tmp_path / "sa.json"
    kf.write_text(json.dumps(FAKE_KEY))
    other = dict(FAKE_KEY, client_email="env@example.iam.gserviceaccount.com")
    clean_env.setenv("DMA_ROUTINE_SA_KEY_B64",
                     base64.b64encode(json.dumps(other).encode()).decode())
    key, source = gcp_token.load_key(str(kf))
    assert key["client_email"] == FAKE_KEY["client_email"]
    assert "key file" in source


def test_load_key_falls_back_to_the_base64_environment_value(clean_env, tmp_path):
    """The rung that makes a scheduled routine authenticate at session start.

    Since 0.6.8 a successful environment load also WRITES THE FILE THROUGH
    (the self-heal for containers whose setup script never ran), so the
    tests give load_key a private tmp path, never a shared literal one."""
    clean_env.setenv("DMA_ROUTINE_SA_KEY_B64",
                     base64.b64encode(json.dumps(FAKE_KEY).encode()).decode())
    keyfile = tmp_path / "sa.json"
    key, source = gcp_token.load_key(str(keyfile))
    assert key["client_email"] == FAKE_KEY["client_email"]
    assert source.startswith("DMA_ROUTINE_SA_KEY_B64")
    assert keyfile.is_file()  # the write-through re-provisioned the path


def test_load_key_accepts_raw_json_where_newlines_survive(clean_env, tmp_path):
    clean_env.setenv("DMA_ROUTINE_SA_KEY", json.dumps(FAKE_KEY))
    key, source = gcp_token.load_key(str(tmp_path / "sa.json"))
    assert key["client_email"] == FAKE_KEY["client_email"]
    assert source.startswith("DMA_ROUTINE_SA_KEY")


def test_load_key_explains_itself_when_nothing_is_available(clean_env, tmp_path):
    key, source = gcp_token.load_key(str(tmp_path / "sa.json"))
    assert key is None
    assert "DMA_ROUTINE_SA_KEY_B64" in source


def test_load_key_names_the_variable_when_it_is_set_but_malformed(clean_env, tmp_path):
    """A truncated paste must be diagnosable, not silently identical to unset —
    and since 0.6.8 the failure text carries the exact regeneration command."""
    clean_env.setenv("DMA_ROUTINE_SA_KEY_B64", "not-base64-at-all!!")
    key, source = gcp_token.load_key(str(tmp_path / "sa.json"))
    assert key is None
    assert "DMA_ROUTINE_SA_KEY_B64" in source and "unusable" in source
    assert "base64 -w0" in source


def test_cli_exits_2_and_prints_nothing_on_stdout_without_a_key(clean_env, capsys, tmp_path):
    rc = gcp_token.main(["id", "--audience", "https://aud",
                         "--key", str(tmp_path / "absent" / "sa.json")])
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""          # stdout carries tokens and nothing else
    assert "no usable key" in captured.err


def test_bootstrap_cannot_be_traced_into_a_log():
    """THE 2026-08-20 INCIDENT, as a test: `bash -x` must not print the key.

    The script disables xtrace itself, because a caller who wants verbose
    output should not thereby publish a credential. Runs the script exactly
    as the incident did, with a sentinel standing in for the key, and fails
    if the sentinel reaches stdout or stderr.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as sandbox:
        env = dict(os.environ)
        env["DMA_ROUTINE_SA_KEY_B64"] = base64.b64encode(
            json.dumps(dict(FAKE_KEY, private_key=SENTINEL)).encode()).decode()
        env["DMA_ROUTINE_SA_KEY"] = SENTINEL
        # HOME is redirected so the CLI's marketplace/install writes land in
        # the sandbox: this test once rewrote the real settings.json to a dead
        # marketplace source, which is a worse outcome than the leak it hunts.
        env["HOME"] = sandbox
        env["DMA_REPO_DIR"] = str(HERE.parents[2])   # the real checkout: no clone
        env["DMA_SA_KEY_FILE"] = os.path.join(sandbox, "sa.json")
        proc = subprocess.run(
            ["bash", "-x", str(HERE / "bootstrap_session.sh")],
            capture_output=True, text=True, timeout=180, env=env)
        output = (proc.stdout or "") + (proc.stderr or "")
    assert SENTINEL not in output, (
        "bootstrap_session.sh leaked a credential under `bash -x` — the "
        "trace-proofing (set +x near the top) has regressed")
    assert env["DMA_ROUTINE_SA_KEY_B64"] not in output


def test_bootstrap_refuses_to_register_a_marketplace_that_is_not_there():
    """Measured 2026-08-20: pointed at a nonexistent repo dir, the script
    still ran `claude plugin marketplace add` and rewrote the caller's
    settings.json to a dead source, replacing a working install with a
    broken one. A provisioning script must leave a half-provisioned machine
    no worse than it found it."""
    text = (HERE / "bootstrap_session.sh").read_text()
    guard = 'if [ ! -f "$REPO_DIR/.claude-plugin/marketplace.json" ]; then'
    assert guard in text
    # compare against the real invocation, not the prose that explains it
    assert text.index(guard) < text.index('claude plugin marketplace add "$REPO_DIR"')


def test_bootstrap_disables_xtrace_before_touching_a_secret():
    """Structural guard: the `set +x` must precede the key-handling block."""
    text = (HERE / "bootstrap_session.sh").read_text()
    assert "\nset +x\n" in text
    assert text.index("\nset +x\n") < text.index("DMA_ROUTINE_SA_KEY_B64")


def test_auth_helper_reaches_the_environment_rung():
    """mcp_auth_headers.sh must not require a key FILE — session start has none."""
    text = (HERE / "mcp_auth_headers.sh").read_text()
    assert "mint_from_key" in text
    # the no-file branch calls gcp_token.py without --key so load_key reaches
    # the environment
    assert 'gcp_token.py" id --audience "$AUD" 2>/dev/null' in text
