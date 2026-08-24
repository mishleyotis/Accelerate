"""The connector's write path is the only write path.

Cloud Run authorises at the edge: without an audience-scoped identity token
every call is a 403 and the connector — the sole writer of serving content —
writes nothing. These tests pin the header onto the request and pin the cache
to the token's real expiry, because a synthesis run outlives one hour and a
mint-once cache loses the connector mid-flight.
"""
import io
import json
import time
import urllib.error

import pytest

import dma_connector as C


def _jwt(exp, email="routine@digital-maturity-assessor.iam.gserviceaccount.com"):
    """A syntactically real JWT — unsigned, since nothing here verifies it."""
    import base64

    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'RS256'})}.{seg({'exp': exp, 'email': email})}.sig"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(C, "_idtok_cache", None, raising=False)
    monkeypatch.setattr(C, "_URL", "https://mcp.invalid/mcp/path-token",
                        raising=False)
    yield
    C._idtok_cache = None


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch, payload=None):
    """Record the request the client builds, and answer it successfully."""
    seen = {}
    body = json.dumps(payload or {
        "jsonrpc": "2.0", "id": 1,
        "result": {"content": [{"type": "text", "text": '{"ok": true}'}]}})

    def fake_urlopen(req, *a, **kw):
        seen["headers"] = dict(req.headers)
        seen["url"] = req.full_url
        return _Resp(body.encode())

    monkeypatch.setattr(C.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_call_sends_a_bearer_identity_token(monkeypatch):
    """The measured defect: no Authorization header, therefore a 403.

    raising=False so this fails on the ASSERTION against a client that has no
    minting step at all, rather than on the patch.
    """
    monkeypatch.setattr(C, "_mint_identity_token",
                        lambda: _jwt(time.time() + 3600), raising=False)
    seen = _capture(monkeypatch)

    assert C.call("get_run_progress", run_id="r") == {"ok": True}

    auth = seen["headers"].get("Authorization")
    assert auth is not None, "no Authorization header — Cloud Run answers 403"
    assert auth.startswith("Bearer ey"), auth[:16]


def test_identity_token_is_reminted_before_it_expires(monkeypatch):
    """A run longer than an hour must not carry a dead token into a promote."""
    minted = []

    def mint():
        minted.append(_jwt(time.time() + 3600))
        return minted[-1]

    monkeypatch.setattr(C, "_mint_identity_token", mint)

    first = C.identity_token()
    assert C.identity_token() is first, "re-minted a token that was still fresh"
    assert len(minted) == 1

    # Rewind the cached expiry to inside the refresh margin.
    C._idtok_cache = (first, time.time() + C.TOKEN_REFRESH_MARGIN - 1)
    second = C.identity_token()
    assert second != first, "held a token that was about to expire"
    assert len(minted) == 2


def test_expiry_comes_from_the_token_not_from_a_guess(monkeypatch):
    tok = _jwt(1893456000.0)
    assert C._expiry(tok) == 1893456000.0
    # An unreadable token errs towards re-minting, never towards forever.
    assert C._expiry("not-a-jwt") < time.time() + 3600


def test_a_refused_call_raises_and_names_the_grant(monkeypatch):
    """An unauthenticated/unauthorised call must be REFUSED and explain itself,
    not shrug. The measured defect graded exactly this as a warning."""
    who = "routine@digital-maturity-assessor.iam.gserviceaccount.com"
    monkeypatch.setattr(C, "_mint_identity_token",
                        lambda: _jwt(time.time() + 3600, email=who),
                        raising=False)

    def forbidden(req, *a, **kw):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b""))

    monkeypatch.setattr(C.urllib.request, "urlopen", forbidden)

    with pytest.raises(RuntimeError) as ei:
        C.call("get_run_progress", run_id="r")
    msg = str(ei.value)
    assert "403" in msg
    assert who in msg, "named the wrong identity for the refusal"
    assert "roles/run.invoker" in msg
    assert f"serviceAccount:{who}" in msg


def test_principal_is_read_from_the_token_not_from_gcloud_config(monkeypatch):
    """`gcloud config get-value account` names an account that may have no
    credential behind it; the token names the identity that was actually used."""
    called = []
    monkeypatch.setattr(C, "_gcloud",
                        lambda args: called.append(args) or _Sub())
    who = "someone@example.com"
    assert C.principal(_jwt(time.time() + 60, email=who)) == who
    assert called == [], "shelled out to gcloud when the token already said who"


class _Sub:
    returncode = 0
    stdout = ""
    stderr = ""


def test_mint_failure_is_an_error_not_an_empty_token(monkeypatch):
    """Both rungs empty is an error. Stubbing gcloud alone is no longer
    enough: since 2026-08-24 the service-account key is tried FIRST, and on a
    provisioned container that rung answers — this test passed a stubbed
    gcloud and then minted a real token off the key, which is the opposite of
    what it claims to assert."""
    monkeypatch.setattr(C, "_gcp_token", lambda: None)
    monkeypatch.setattr(C, "_gcloud", lambda args: _Sub())
    with pytest.raises(RuntimeError, match="could not mint an identity token"):
        C._mint_identity_token()


# ── the routine image has no gcloud, and that is the normal case ───────
#
# Measured 2026-08-24 on a routine container: `command -v gcloud` finds
# nothing and /opt/google-cloud-sdk does not exist. The watchdog Routine is
# told in its own prompt that it carries no mcp__* tools and must reach the
# connector "over HTTP through scripts/dma_connector.py" — so while both
# credentials came only from gcloud, that Routine could not perform its
# function on the image it actually runs on, and every firing failed at the
# token rather than reporting a missing SDK.
def test_service_account_key_is_tried_before_gcloud(monkeypatch):
    """The key is what a routine container has; gcloud is what a workstation
    has. Order is the fix, so it is pinned."""
    calls = []
    monkeypatch.setattr(C, "_gcloud",
                        lambda args: calls.append(args) or _Sub())

    class _Mod:
        @staticmethod
        def load_key(path=None):
            return {"client_email": "x", "private_key": "y"}, "test key"

        @staticmethod
        def mint_assertion(key, extra):
            assert extra == {"target_audience": C._MCP_HOST}, \
                "minted for the wrong audience — Cloud Run 403s on that"
            return "assertion"

        @staticmethod
        def exchange(assertion):
            return {"id_token": "TOKEN"}

    monkeypatch.setattr(C, "_gcp_token", lambda: _Mod)
    assert C._mint_identity_token() == "TOKEN"
    assert calls == [], "shelled out to gcloud while the key rung was working"


def test_a_missing_gcloud_binary_is_a_result_not_an_exception(monkeypatch):
    """`_find_gcloud` falls back to a bare name "so it fails with gcloud's own
    error" — but a bare name absent from PATH raises FileNotFoundError out of
    Popen, which no caller reads as a returncode. That exception escaped the
    fallback ladder and crashed the routine with a stack trace instead of the
    error naming what to set.

    THE BINARY IS REMOVED, NOT ASSUMED ABSENT. The first cut of this test read
    `C._gcloud(["version"])` on the bare machine and asserted a non-zero
    returncode, with the comment "no gcloud on this image" — true of the
    routine container it was written on, false of the CI runner, which ships
    the SDK. It went red on GitHub within the hour. A test that asserts what
    the MACHINE holds tests the machine; this one points the module at a path
    that cannot exist, so it exercises the code path on any host.
    """
    monkeypatch.setattr(C, "_GCLOUD", "/nonexistent/dir/gcloud")
    r = C._gcloud(["version"])
    assert r.returncode != 0
    assert "gcloud" in r.stderr
    assert r.stdout == ""


def test_mint_failure_names_the_variable_that_fixes_it(monkeypatch):
    """An unattended firing's error message is the whole bug report."""
    monkeypatch.setattr(C, "_gcp_token", lambda: None)
    monkeypatch.setattr(C, "_gcloud", lambda args: _Sub())
    with pytest.raises(RuntimeError) as ei:
        C._mint_identity_token()
    msg = str(ei.value)
    assert "DMA_ROUTINE_SA_KEY_B64" in msg
    assert "bootstrap_session.sh" in msg


# ── finding gcloud when PATH has already reset ─────────────────────────
#
# Measured 2026-08-16: `_GCLOUD = os.environ.get("GCLOUD_BIN", "gcloud")` was
# evaluated once at import time against whatever PATH the CURRENT shell
# happened to have. In this harness shell state does not survive between
# Bash invocations — an `export PATH=...` in one call is gone in the next —
# so a call that worked minutes earlier died with FileNotFoundError as soon
# as a fresh shell picked the module up. `doctor.py` and `setup_routines.py`
# both already search fixed install locations for exactly this reason; this
# script had the same problem and none of the fix.
def test_GCLOUD_BIN_ENV_VAR_STILL_WINS(monkeypatch):
    monkeypatch.setenv("GCLOUD_BIN", "/custom/gcloud")
    assert C._find_gcloud() == "/custom/gcloud"


def test_falls_back_to_a_fixed_install_location_when_PATH_has_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("GCLOUD_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    fake_home = tmp_path / "home"
    fake_sdk = fake_home / "google-cloud-sdk" / "bin" / "gcloud"
    fake_sdk.parent.mkdir(parents=True)
    fake_sdk.write_text("#!/bin/sh\n")
    fake_sdk.chmod(0o755)
    monkeypatch.setenv("HOME", str(fake_home))
    assert C._find_gcloud() == str(fake_sdk)


def test_a_bare_name_that_resolves_on_PATH_is_still_honoured(monkeypatch):
    monkeypatch.delenv("GCLOUD_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gcloud")
    assert C._find_gcloud() == "/usr/bin/gcloud"


def test_NEVER_RAISES_WHEN_NOTHING_IS_FOUND(monkeypatch):
    """gcloud missing everywhere must fail with gcloud's own error at the call
    site, not with an import-time crash that blocks every other tool call
    including ones that need no credential."""
    monkeypatch.delenv("GCLOUD_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    # Not just an empty HOME: this container genuinely has gcloud installed at
    # one of the fixed fallback paths, so the search has to be denied there
    # too or the test proves nothing on this machine.
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    monkeypatch.setenv("HOME", "/nonexistent-for-this-test")
    assert C._find_gcloud() == "gcloud"


# ── large payloads should not have to be re-typed into a shell argument ─
#
# A contract-complete page payload runs 1-1.6MB. Measured on the Logix
# producer run: ~12 of 50 minutes went to re-typing a payload into a tool-call
# argument, and a one-field repair after a verdict cost a full retransmission
# because there was no cheaper way to resubmit. `--file` is the fix: write the
# payload once, reference it by path, edit and resubmit without retyping.
def test_a_json_string_argument_still_works():
    assert C._cli_args(['{"run_id": "abc"}']) == {"run_id": "abc"}


def test_no_arguments_is_an_empty_call():
    assert C._cli_args([]) == {}


def test_FILE_FORM_READS_THE_SAME_SHAPE_A_STRING_WOULD(tmp_path):
    p = tmp_path / "payload.json"
    p.write_text('{"run_id": "abc", "payload": {"a": [1, 2, 3]}}')
    assert C._cli_args(["--file", str(p)]) == {
        "run_id": "abc", "payload": {"a": [1, 2, 3]}}


def test_file_form_with_no_path_is_a_clean_error_not_an_IndexError():
    with pytest.raises(SystemExit):
        C._cli_args(["--file"])


def test_a_LARGE_payload_survives_the_file_path_intact(tmp_path):
    """The whole reason for the flag: something too big to comfortably retype
    as a shell argument must round-trip byte-for-byte through a file."""
    big = {"run_id": "abc", "payload": {"cells": [
        {"id": f"C{i}", "text": "x" * 200} for i in range(2000)]}}
    p = tmp_path / "big.json"
    p.write_text(json.dumps(big))
    assert C._cli_args(["--file", str(p)]) == big
