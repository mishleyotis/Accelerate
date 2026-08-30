"""A dropped connection on submit is a question, not an answer.

Measured 2026-08-22 submitting the 2.7MB T. Rowe Price heatmap. The 35 parts
were accepted, then:

    http.client.RemoteDisconnected: Remote end closed connection without
    response

and the submission HAD SUCCEEDED — get_run_progress showed heatmap PASS at
submission 8203526d, written while the client was reading a socket that was
no longer there. Cloud Run allows 900s and the client waits 900s, so neither
is the ceiling; something between them gave up during a validation pass that
runs V4 embeddings over 876 evidence rows and 595 cells.

THE DANGER IS NOT THE DROP. It is the obvious next move. Resending re-opens
an upload, re-sends every part, and re-runs the most expensive validation in
the system to produce a second submission of a payload already accepted — and
on a section that APPENDS rather than replaces, it duplicates content. The
same script that turned three thought-leadership entries into six did it by
being run again after something that looked like a failure.

So the rule these tests hold: a transport error resolves by ASKING whether
the submission id moved. A server-raised refusal is never retried, because
that is the server speaking and the answer arrived.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dma_connector as dc                                          # noqa: E402

RUN, PAGE = "run-1", "heatmap"


class Fake:
    """Stands in for `call`, scripted per invocation."""

    def __init__(self, submits, ids):
        self.submits = list(submits)      # what submit_page_payload does
        self.ids = list(ids)              # what progress reports, in order
        self.calls = []

    def __call__(self, tool, **kw):
        self.calls.append(tool)
        if tool == "get_run_progress":
            sid = self.ids.pop(0) if self.ids else None
            return {"pages": {PAGE: {"submission_id": sid, "status": "PASS"}}}
        if tool == "submit_page_payload":
            out = self.submits.pop(0)
            if isinstance(out, Exception):
                raise out
            return out
        if tool == "get_validation_verdict":
            return {"verdict": {"status": "pass"}, "from": "verdict-lookup"}
        raise AssertionError(f"unexpected tool {tool}")


@pytest.fixture
def patched(monkeypatch):
    def use(fake):
        monkeypatch.setattr(dc, "call", fake)
        return fake
    return use


DROP = ConnectionError("Remote end closed connection without response")


def test_the_happy_path_is_one_submit(patched):
    f = patched(Fake(submits=[{"verdict": {"status": "pass"}}], ids=["old"]))
    out = dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert out["verdict"]["status"] == "pass"
    assert f.calls.count("submit_page_payload") == 1


def test_a_drop_whose_submission_landed_is_not_resent(patched):
    """The real 2026-08-22 case. The id moved, so the payload is in — asking
    is what turns a lost answer into a known one."""
    f = patched(Fake(submits=[DROP], ids=["old", "8203526d"]))
    out = dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert out["from"] == "verdict-lookup"
    assert f.calls.count("submit_page_payload") == 1, "it must NOT resend"


def test_a_drop_whose_submission_did_not_land_is_resent(patched):
    f = patched(Fake(submits=[DROP, {"verdict": {"status": "pass"}}],
                     ids=["old", "old"]))
    out = dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert out["verdict"]["status"] == "pass"
    assert f.calls.count("submit_page_payload") == 2


def test_a_page_that_never_lands_raises_and_says_it_is_real(patched):
    f = patched(Fake(submits=[DROP, DROP, DROP],
                     ids=["old", "old", "old", "old"]))
    with pytest.raises(RuntimeError) as e:
        dc.submit_confirmed(RUN, PAGE, attempts=3, upload_id="u1")
    assert "real failure" in str(e.value)
    assert "not a dropped response" in str(e.value)
    assert f.calls.count("submit_page_payload") == 3


def test_a_first_ever_submission_is_recognised_by_the_id_appearing(patched):
    """A page with no prior submission has id None. The id "moving" is None
    -> a real id, which must count as landed or every first submit on a heavy
    page gets sent twice."""
    f = patched(Fake(submits=[DROP], ids=[None, "brand-new"]))
    out = dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert out["from"] == "verdict-lookup"
    assert f.calls.count("submit_page_payload") == 1


def test_a_server_refusal_is_never_retried(patched):
    """A RuntimeError from `call` is the SERVER speaking — a failed verdict, a
    refused gate. The answer arrived. Retrying it would re-run the most
    expensive validation in the system to be told the same thing, and on an
    appending section would corrupt the payload while doing it."""
    f = patched(Fake(submits=[RuntimeError("CG-26: entry 3 cites the same document")],
                     ids=["old"]))
    with pytest.raises(RuntimeError) as e:
        dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert "CG-26" in str(e.value)
    assert f.calls.count("submit_page_payload") == 1


def test_transport_errors_are_the_narrow_set():
    """Widening this to Exception would swallow server refusals into the
    retry path, which is the one thing that must not happen."""
    assert dc.TRANSPORT_ERRORS == (ConnectionError, TimeoutError, OSError)
    assert not issubclass(RuntimeError, dc.TRANSPORT_ERRORS)


def test_the_baseline_id_is_read_before_submitting_not_after(patched):
    """Reading it afterwards would compare the new id with itself and call
    every landed submission a failure."""
    f = patched(Fake(submits=[{"verdict": {"status": "pass"}}], ids=["old"]))
    dc.submit_confirmed(RUN, PAGE, upload_id="u1")
    assert f.calls[0] == "get_run_progress"
    assert f.calls[1] == "submit_page_payload"
