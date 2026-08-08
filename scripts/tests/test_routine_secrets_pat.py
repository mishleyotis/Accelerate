"""The PAT was validated by counting its characters. An expired token has
exactly as many as a live one, so the check could not fail. These tests pin
the replacement: spend the token on GET /user, read the expiry GitHub reports
back, and refuse anything that will not outlive the firing interval.
"""
import io
import json
import time
import urllib.error

import pytest

import routine_secrets as R

PAT = "github_pat_" + "x" * 71          # a plausible shape; never printed


def _hdrs(expiry=None):
    import email.message
    m = email.message.Message()
    if expiry is not None:
        m["github-authentication-token-expiration"] = expiry
    return m


class _Resp(io.BytesIO):
    def __init__(self, body, headers):
        super().__init__(body)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _pat(monkeypatch):
    monkeypatch.setattr(R, "github_pat", lambda: PAT)


def _github(monkeypatch, *, expiry=None, code=None, login="octocat"):
    seen = {}

    def fake(req, *a, **kw):
        seen["headers"] = dict(req.headers)
        seen["url"] = req.full_url
        if code:
            raise urllib.error.HTTPError(req.full_url, code, "no", {},
                                         io.BytesIO(b""))
        return _Resp(json.dumps({"login": login}).encode(), _hdrs(expiry))

    monkeypatch.setattr(R.urllib.request, "urlopen", fake)
    return seen


def _in(seconds):
    t = time.gmtime(time.time() + seconds)
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", t)


def test_a_live_pat_with_a_long_horizon_passes(monkeypatch):
    seen = _github(monkeypatch, expiry=_in(30 * 3600))
    st = R.github_pat_status()
    assert st["ok"] and st["verdict"] == "OK"
    assert st["login"] == "octocat"
    assert seen["url"].endswith("/user"), "did not actually call GitHub"


def test_an_expired_pat_fails(monkeypatch):
    """The measured defect: this token printed 'OK resolved, 93 chars'."""
    _github(monkeypatch, expiry=_in(-60))
    st = R.github_pat_status()
    assert not st["ok"] and st["verdict"] == "FAIL"
    assert "EXPIRED" in st["detail"]


def test_a_pat_dying_inside_the_firing_interval_fails(monkeypatch):
    """Cron is `50 */3 * * *`. A token with two hours left is a token this
    firing outlives — the run finishes and the push at the end does not."""
    _github(monkeypatch, expiry=_in(2 * 3600))
    st = R.github_pat_status(min_seconds=3 * 3600)
    assert not st["ok"] and st["verdict"] == "FAIL"
    assert "firing interval" in st["detail"]


def test_a_pat_outliving_the_firing_interval_passes(monkeypatch):
    _github(monkeypatch, expiry=_in(4 * 3600))
    assert R.github_pat_status(min_seconds=3 * 3600)["ok"]


def test_github_rejecting_the_pat_fails(monkeypatch):
    _github(monkeypatch, code=401)
    st = R.github_pat_status()
    assert not st["ok"] and "401" in st["detail"]


def test_length_alone_never_decides(monkeypatch):
    """Same token, same length, opposite verdicts — the length carries no
    information and the check must not read it as if it did."""
    _github(monkeypatch, expiry=_in(-1))
    dead = R.github_pat_status()
    _github(monkeypatch, expiry=_in(30 * 3600))
    live = R.github_pat_status()
    assert dead["ok"] is False and live["ok"] is True


def test_no_verdict_ever_carries_the_token_or_a_prefix(monkeypatch):
    for expiry, code in ((_in(-1), None), (_in(3600), None), (None, 403),
                         (_in(30 * 3600), None)):
        _github(monkeypatch, expiry=expiry, code=code)
        blob = json.dumps(R.github_pat_status())
        assert PAT not in blob
        assert PAT[:12] not in blob, "leaked a prefix of the token"


@pytest.mark.parametrize("raw", [
    "2026-08-08 10:15:28 UTC",
    "2026-08-08 10:15:28 +0000",
    "2026-08-08T10:15:28+00:00",
])
def test_expiry_header_shapes_parse(raw):
    d = R._parse_gh_expiry(raw)
    assert d is not None and d.tzinfo is not None
    assert d.timestamp() == 1786184128.0     # 2026-08-08 10:15:28 UTC


def test_an_unparseable_expiry_warns_rather_than_silently_passing(monkeypatch):
    _github(monkeypatch, expiry="sometime next week")
    st = R.github_pat_status()
    assert st["verdict"] == "WARN" and st["ok"] is True
