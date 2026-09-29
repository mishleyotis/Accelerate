"""The dispatch brief states what to hand back and what to do when a question
cannot be answered (prompt-craft scorecard rewrite 2, 29-09-2026).

Measured: a headless `claude -p` lane reads the packet and the session hook,
not RESEARCH-PROTOCOL.md, and the packet ended on its numbered rules —
nothing in it said what to return, and NOT_RUN appeared only as a gate
default. The JSON carries the block and the markdown renders it, from one
object, so they cannot disagree.
"""
from engine import brief

from .test_capability_grain import _full_run


def test_the_packet_carries_the_return_contract_and_the_markdown_renders_it(tmp_path):
    run = _full_run(tmp_path)
    packet = brief.dispatch(run.open(), "P1C1", run=run)
    block = packet["done_and_ambiguity"]
    text = " ".join(block)
    assert "engine.cli gate" in block[0] and "--require-synthesis" in block[0]
    assert "engine.brief handback" in block[0] and "search_requests" in block[0]
    assert "the relay fires them" in block[0]
    assert "NOT_RUN: <reason>" in text and "NO_FINDING after <n> searches" in text
    assert "leave it, say so" in text
    assert packet["packet_chars"] <= packet["packet_ceiling"], "the block rides inside the ceiling"
    assert "trust `orient`" in text
    assert "Bash calls per card" in text
    md = brief.as_markdown(packet)
    assert "### When you are done, and when you cannot decide" in md
    assert md.index("### Rules") < md.index("### When you are done")
    for line in block:
        assert f"- {line}" in md
