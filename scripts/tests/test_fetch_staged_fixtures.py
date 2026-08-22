"""The fixture fetcher must reassemble a chunked section byte-for-byte.

`fetch_staged_fixtures.py` exists because the six whole-payload cases in
`tests/skills/test_check_payload_false_positives.py` need a real passing run
and a real passing run may not be committed — it carries the un-redacted
internal record of a named institution. The script is therefore the only route
those six cases have to ever run, which makes its reassembly the load-bearing
part: a chunked section rebuilt wrong writes a fixture that looks whole and is
not, and the tests it feeds would report on a payload nobody submitted.

The heatmap section that forced chunked transport into existence is 1.36 MB
against a 64 KB inline budget — 22 parts — so "it worked on the small one" is
not evidence about the case that matters.

No connector is reached here; `call` is replaced with a recorder that answers
exactly as `apps/mcp/dma_mcp/staged.py` does.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "fetch_staged_fixtures.py"
INLINE = 64 * 1024


def _load(monkeypatch, responder):
    """Import the script with `dma_connector.call` already replaced."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import dma_connector
    monkeypatch.setattr(dma_connector, "call", responder)
    spec = importlib.util.spec_from_file_location("fetch_staged", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "call", responder)
    return mod


def _blob(v):
    return json.dumps(v, separators=(",", ":"), default=str)


def fake_connector(payload):
    """`get_staged_payload`'s three answers, over one page's real payload."""
    def call(tool, **kw):
        assert tool == "get_staged_payload"
        section, part = kw.get("section", ""), kw.get("part", 0)
        if not section:
            return {"sections": {name: {"bytes": len(_blob(body)),
                                        "inline": len(_blob(body)) <= INLINE}
                                 for name, body in payload.items()}}
        body = payload[section]
        blob = _blob(body)
        total = max(1, -(-len(blob) // INLINE))
        if part:
            lo = (part - 1) * INLINE
            return {"section": section, "part": part, "parts": total,
                    "chunk": blob[lo:lo + INLINE]}
        if len(blob) > INLINE:
            return {"section": section, "error": "section_too_large",
                    "bytes": len(blob), "parts": total}
        return {"section": section, "data": body, "bytes": len(blob)}
    return call


# A section far over the budget, with the shape that actually broke: many
# cells, unicode in the prose, and a nesting the byte split cuts mid-token.
BIG = {"cells": [{"subcap_id": f"P1C1.{i}.1",
                  "synthesis": "The institution's own site does not serve its "
                               "pages to a non-browser client — the ladder is "
                               f"kept in place for cell {i}. ünïcode ✓",
                  "e_ids": [f"E-CC-{i}"], "thin": True}
                 for i in range(1, 900)]}
SMALL = {"produced_at": "2026-08-17T00:00:00Z", "arc_shape": "STEADY_INVESTMENT"}


def test_a_chunked_section_comes_back_byte_for_byte(monkeypatch):
    payload = {"cell_evidence": BIG, "timeline": SMALL}
    assert len(_blob(BIG)) > INLINE, "the big section must exceed the budget"
    mod = _load(monkeypatch, fake_connector(payload))
    got = mod.fetch_page("run-1", "heatmap")
    assert got == payload
    assert got["cell_evidence"]["cells"][-1]["synthesis"].endswith("ünïcode ✓")


def test_more_than_one_part_is_actually_fetched(monkeypatch):
    """The control on the control: a single-part read would pass the test
    above by accident if the budget were mis-stated."""
    seen = []
    inner = fake_connector({"cell_evidence": BIG})

    def recording(tool, **kw):
        seen.append(kw.get("part", 0))
        return inner(tool, **kw)

    mod = _load(monkeypatch, recording)
    mod.fetch_page("run-1", "heatmap")
    assert max(seen) > 1, f"never chunked: parts requested were {sorted(set(seen))}"


def test_an_inline_section_is_taken_from_data_not_reassembled(monkeypatch):
    mod = _load(monkeypatch, fake_connector({"timeline": SMALL}))
    assert mod.fetch_page("run-1", "context") == {"timeline": SMALL}


def test_a_missing_chunk_raises_rather_than_writing_a_short_fixture(monkeypatch):
    """A truncated payload that looks whole is the failure mode the connector's
    own chunked read was built to prevent. The fetcher may not reintroduce it."""
    inner = fake_connector({"cell_evidence": BIG})

    def lossy(tool, **kw):
        got = inner(tool, **kw)
        if got.get("part") == 2:
            return {"section": kw["section"], "error": "no_such_part"}
        return got

    mod = _load(monkeypatch, lossy)
    with pytest.raises(RuntimeError, match="part 2"):
        mod.fetch_page("run-1", "heatmap")


def test_a_page_with_no_staged_submission_names_the_page(monkeypatch):
    mod = _load(monkeypatch, lambda tool, **kw: {
        "error": "no_staged_submission", "hint": "produce the page."})
    with pytest.raises(RuntimeError, match="techstack.*no_staged_submission"):
        mod.fetch_page("run-1", "techstack")


def test_the_payloads_it_writes_are_gitignored():
    """The reason this script exists at all: what it writes may not be
    committed. If the ignore rule is ever dropped, the next `git add -A` in a
    fixture-refresh session publishes a client's internal record."""
    import subprocess
    probe = "fixtures/staged_runs/logix/overview.json"
    r = subprocess.run(["git", "check-ignore", "-q", probe],
                       cwd=ROOT, capture_output=True)
    assert r.returncode == 0, f"{probe} is NOT gitignored"
