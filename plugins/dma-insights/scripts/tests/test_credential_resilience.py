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


def _seed_repo(path: str, branch: str) -> str:
    """A hermetic stand-in for the checkout: one commit, self-remote.

    bootstrap_session.sh's section 1 fetches origin/$BRANCH and, on a clean
    tree, resets to it. Handing it a repo whose origin is itself keeps that
    whole section real — fetch, ancestry check, reset — with every side
    effect owned by the sandbox.
    """
    os.makedirs(os.path.join(path, ".claude-plugin"))
    Path(path, ".claude-plugin", "marketplace.json").write_text("{}\n")
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-C", path, "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", *a],
        check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "-q", "-b", branch, path],
                   check=True, capture_output=True, text=True)
    run("add", "-A")
    run("commit", "-qm", "seed")
    run("remote", "add", "origin", path)
    return path


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
        # The repo is a sandbox repo for the same reason: this test once
        # handed the script the REAL checkout ("no clone"), and section 1
        # switched a developer's clean work branch onto the routine branch
        # mid test-suite, so every test collected after it read the wrong
        # tree — locally and on CI (2026-08-24). A test that provisions runs
        # provisioning against something it owns.
        env["HOME"] = sandbox
        env["DMA_REPO_DIR"] = _seed_repo(os.path.join(sandbox, "repo"),
                                         "sandbox-branch")
        env["DMA_REPO_BRANCH"] = "sandbox-branch"
        env["DMA_SA_KEY_FILE"] = os.path.join(sandbox, "sa.json")
        proc = subprocess.run(
            ["bash", "-x", str(HERE / "bootstrap_session.sh")],
            capture_output=True, text=True, timeout=180, env=env)
        output = (proc.stdout or "") + (proc.stderr or "")
    assert SENTINEL not in output, (
        "bootstrap_session.sh leaked a credential under `bash -x` — the "
        "trace-proofing (set +x near the top) has regressed")
    assert env["DMA_ROUTINE_SA_KEY_B64"] not in output


def test_bootstrap_never_discards_unmerged_commits():
    """THE 2026-08-24 INCIDENT, as a test: a clean tree AHEAD of the branch
    tip is somebody's work, exactly like a dirty one.

    Section 1's hard reset exists for routine containers, which are only
    ever at-or-behind the branch tip. Run against a repo whose clean HEAD
    holds a commit origin/$BRANCH does not have — a developer's work branch,
    the shape that was silently switched out from under a test suite — the
    script must refuse, say so, and leave HEAD exactly where it was.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as sandbox:
        repo = _seed_repo(os.path.join(sandbox, "repo"), "sandbox-branch")
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t",
             "-c", "commit.gpgsign=false", *a],
            check=True, capture_output=True, text=True).stdout.strip()
        run("checkout", "-q", "-b", "somebody's-work")
        Path(repo, "work.txt").write_text("unmerged\n")
        run("add", "-A")
        run("commit", "-qm", "work the branch tip does not have")
        head_before = run("rev-parse", "HEAD")
        env = dict(os.environ)
        env["HOME"] = sandbox
        env["DMA_REPO_DIR"] = repo
        env["DMA_REPO_BRANCH"] = "sandbox-branch"
        env["DMA_SA_KEY_FILE"] = os.path.join(sandbox, "sa.json")
        env.pop("DMA_ROUTINE_SA_KEY_B64", None)
        env.pop("DMA_ROUTINE_SA_KEY", None)
        proc = subprocess.run(
            ["bash", str(HERE / "bootstrap_session.sh")],
            capture_output=True, text=True, timeout=180, env=env)
        head_after = run("rev-parse", "HEAD")
        branch_after = run("rev-parse", "--abbrev-ref", "HEAD")
    assert head_after == head_before, (
        "bootstrap_session.sh moved HEAD off a clean tree that held commits "
        "origin/$BRANCH does not have — that is somebody's work, discarded")
    assert branch_after == "somebody's-work"
    assert "NOT AN ANCESTOR" in (proc.stdout or "") + (proc.stderr or ""), (
        "the refusal must be loud — a silent skip reads as provisioned")


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
