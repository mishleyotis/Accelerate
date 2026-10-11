

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


def _scripted_urlopen(drive, codes):
    """urlopen that raises each HTTP code in `codes` in turn, then answers."""
    import urllib.error

    calls = []

    class _Body:
        def read(self): return b"ok"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        calls.append(req.headers.get("Authorization"))
        if len(calls) <= len(codes):
            code = codes[len(calls) - 1]
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return _Body()

    return fake_open, calls


def test_a_transient_drive_500_backs_off_and_retries_rather_than_killing_the_scan():
    """The measured failure: dmai-worker-mpm6d (2026-10-10 19:00 UTC) and
    -rpwdv (2026-10-11 09:00 UTC) both exited 1 on one `HTTP Error 500` from
    files.list mid-walk — a Drive-side fault failed the whole package scan."""
    from dma_worker import drive

    fake_open, calls = _scripted_urlopen(drive, [500, 503, 429])
    slept = []
    orig_open, orig_sleep = drive.urllib.request.urlopen, drive.time.sleep
    drive.urllib.request.urlopen = fake_open
    drive.time.sleep = slept.append
    try:
        assert drive._get("tok", "https://example.invalid/x", 10) == b"ok"
    finally:
        drive.urllib.request.urlopen, drive.time.sleep = orig_open, orig_sleep

    assert len(calls) == 4
    assert slept == list(drive._BACKOFF_S), "each retry must wait, longer each time"


def test_a_transient_fault_that_outlasts_every_wait_still_surfaces():
    """Backoff is bounded: a Drive outage must fail the run, not hang it."""
    import urllib.error
    import pytest
    from dma_worker import drive

    tries = len(drive._BACKOFF_S) + 1
    fake_open, calls = _scripted_urlopen(drive, [500] * (tries + 5))
    orig_open, orig_sleep = drive.urllib.request.urlopen, drive.time.sleep
    drive.urllib.request.urlopen = fake_open
    drive.time.sleep = lambda s: None
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            drive._get("tok", "https://example.invalid/x", 10)
    finally:
        drive.urllib.request.urlopen, drive.time.sleep = orig_open, orig_sleep

    assert e.value.code == 500
    assert len(calls) == tries


def test_a_client_error_is_not_retried():
    """A 404 or 403 is a real answer about the request; retrying it only
    delays the failure the scan must report."""
    import urllib.error
    import pytest
    from dma_worker import drive

    for code in (403, 404):
        fake_open, calls = _scripted_urlopen(drive, [code])
        slept = []
        orig_open, orig_sleep = drive.urllib.request.urlopen, drive.time.sleep
        drive.urllib.request.urlopen = fake_open
        drive.time.sleep = slept.append
        try:
            with pytest.raises(urllib.error.HTTPError):
                drive._get("tok", "https://example.invalid/x", 10)
        finally:
            drive.urllib.request.urlopen, drive.time.sleep = orig_open, orig_sleep
        assert len(calls) == 1 and slept == [], code


def test_a_401_then_a_500_re_mints_once_and_still_backs_off():
    """The two recoveries compose: a stale token and a Drive blip in the same
    call both recover, and the re-mint is not repeated on the 5xx retry."""
    from dma_worker import drive

    forced = []
    state = {"tok": "stale"}

    def token(force=False):
        forced.append(force)
        if force:
            state["tok"] = "fresh"
        return state["tok"]

    fake_open, calls = _scripted_urlopen(drive, [401, 500])
    orig_open, orig_sleep = drive.urllib.request.urlopen, drive.time.sleep
    drive.urllib.request.urlopen = fake_open
    drive.time.sleep = lambda s: None
    try:
        assert drive._get(token, "https://example.invalid/x", 10) == b"ok"
    finally:
        drive.urllib.request.urlopen, drive.time.sleep = orig_open, orig_sleep

    assert calls == ["Bearer stale", "Bearer fresh", "Bearer fresh"]
    assert forced == [False, True, False], "only the call after the 401 forces a mint"


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
