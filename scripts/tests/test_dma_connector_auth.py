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
    monkeypatch.setattr(C, "_gcloud", lambda args: _Sub())
    with pytest.raises(RuntimeError, match="could not mint an identity token"):
        C._mint_identity_token()
