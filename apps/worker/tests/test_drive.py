

import sys
from pathlib import Path

# This file's own path setup, rather than a sibling's. Until
# 2026-08-20 it passed ONLY inside the full suite: an
# alphabetically-earlier module inserted apps/worker on sys.path at
# import time, and this one inherited it. Alone — which is what
# `pytest --lf`, a single-file re-run and every `git bisect` over
# worker code do — it died on ModuleNotFoundError: dma_worker, a
# failure with nothing to do with the code under test.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def test_a_long_run_re_mints_rather_than_outliving_its_token():
    """The measured failure: `40 ingested, 114 failed, 1 quarantined`, every
    failure HTTPError 401. main() minted ONE token and passed the string to
    every download for the whole execution; a Drive token lives an hour and a
    full-tree scan of 154 packages does not fit in one."""
    from dma_worker import drive

    minted = []
    clock = {"t": 1_000_000.0}

    def fake_mint(scope):
        minted.append(scope)
        return f"tok-{len(minted)}", clock["t"] + 3600.0

    orig_mint, orig_time = drive._mint, drive.time.time
    drive._mint = fake_mint
    drive.time.time = lambda: clock["t"]
    try:
        get = drive.token_provider()
        assert get() == "tok-1"
        assert get() == "tok-1", "a live token is reused, not re-minted per call"
        # Fifty-five minutes later, inside the 5-minute refresh margin.
        clock["t"] += 55 * 60
        assert get() == "tok-2", (
            "a token inside its refresh margin must be replaced before it is "
            "spent — this is the whole defect")
        assert len(minted) == 2
    finally:
        drive._mint, drive.time.time = orig_mint, orig_time


def test_a_401_re_mints_once_and_retries_rather_than_failing_the_package():
    """A refresh margin removes almost every expiry, but not one landing
    between the check and the call. A 401 must cost one retry, not a package."""
    import urllib.error
    from dma_worker import drive

    seen = []

    def token(force=False):
        seen.append(force)
        return "fresh" if force else "stale"

    calls = []

    class _Body:
        def __init__(self, payload): self.payload = payload
        def read(self): return self.payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        auth = req.headers.get("Authorization")
        calls.append(auth)
        if auth == "Bearer stale":
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return _Body(b"ok")

    orig = drive.urllib.request.urlopen
    drive.urllib.request.urlopen = fake_open
    try:
        assert drive._get(token, "https://example.invalid/x", 10) == b"ok"
    finally:
        drive.urllib.request.urlopen = orig

    assert calls == ["Bearer stale", "Bearer fresh"]
    assert seen == [False, True], "the retry must FORCE a new token, not reuse the dead one"


def test_a_plain_string_token_still_works_and_does_not_retry():
    """Call sites and tests that pass a string keep working — and a string
    cannot be re-minted, so a 401 on one must surface rather than loop."""
    import urllib.error
    import pytest
    from dma_worker import drive

    def fake_open(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    orig = drive.urllib.request.urlopen
    drive.urllib.request.urlopen = fake_open
    try:
        with pytest.raises(urllib.error.HTTPError):
            drive._get("a-plain-string", "https://example.invalid/x", 10)
    finally:
        drive.urllib.request.urlopen = orig
