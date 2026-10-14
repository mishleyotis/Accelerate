"""A capability held as uniformly scored is ROUTED, and can be honestly cleared.

AAA Western and Central New York (2026-10-14): every pillar's critic had
PASSED and every cell was scored when the SCORING gate blocked on
`no_differentiation`. The scorer brief hands only unscored rows and critic
moves, and a PASSED pillar got no critic lane, so the term reached nobody;
rounds 3-5 dispatched nothing and the stall guard stopped the stage.
"""
import json
from pathlib import Path

import pytest

from engine import assessment as A
from engine import brief
from engine.assessment import ScoringRefusal

from fixtures import researched_run as _researched, score_cell as _score

NOTE = ("Re-derived every P1 row against its rubric descriptor and the counter-source; "
        "ceilings hold and nothing flatters.")
ATTEST = ("Each cell re-derived from its own rows: every one shows the same single T3 "
          "source and the same M2 descriptor, so the identical scores are honest.")


def _uniform(tmp_path):
    run, wb, cells, ev = _researched(tmp_path, n=6, absent=0)
    A.open_stage(wb, run.qa_dir)
    for cell in cells:
        _score(wb, cell, ev[cell], score=2.5)            # every cell identical
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic", note=NOTE)
    caps = A.differentiation(wb)["no_differentiation"]
    assert caps, "the fixture must reproduce the uniform capability"
    return run, wb, cells, ev, caps


def test_a_passed_pillar_with_a_uniform_capability_gets_a_critic_lane(tmp_path):
    run, wb, cells, ev, caps = _uniform(tmp_path)
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "c", critic=True)
    rows = json.loads(Path(b["batch"]).read_text())
    assert [r["label"] for r in rows] == ["scoring-critic-P1"], \
        "the gate's no_differentiation term must reach the pillar's critic"
    text = json.dumps(rows) + "".join(
        Path(v).read_text() for r in rows for v in r.values()
        if isinstance(v, str) and v.endswith((".json", ".md")) and Path(v).is_file())
    assert all(c in text for c in caps)
    assert "attest-uniform" in text


def test_an_independent_attestation_clears_the_block_and_is_disclosed(tmp_path):
    run, wb, cells, ev, caps = _uniform(tmp_path)
    for cap in caps:
        A.attest_uniform(wb, cap=cap, actor="scoring-critic", note=ATTEST)
    d = A.differentiation(wb)
    assert not d["no_differentiation"]
    assert set(caps) <= set(d["attested"]) and set(caps) <= set(d["low_differentiation"])
    v = A.gate(wb, run.qa_dir)
    assert "no_differentiation" not in v["blocking"]
    assert set(caps) <= set(v["differentiation_attested"])
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "c2", critic=True)
    assert b["lanes"] == 0 or "scoring-critic-P1" not in \
        [r["label"] for r in json.loads(Path(b["batch"]).read_text())]


def test_attestation_is_refused_from_the_scorer_short_or_when_nothing_is_uniform(tmp_path):
    run, wb, cells, ev, caps = _uniform(tmp_path)
    with pytest.raises(ScoringRefusal, match="cannot attest"):
        A.attest_uniform(wb, cap=caps[0], actor="scoring-p1-producer", note=ATTEST)
    with pytest.raises(ScoringRefusal, match="rubber stamp"):
        A.attest_uniform(wb, cap=caps[0], actor="scoring-critic", note="same scores, fine")
    with pytest.raises(ScoringRefusal, match="nothing to attest"):
        A.attest_uniform(wb, cap="P1C9.9", actor="scoring-critic", note=ATTEST)


def test_rescoring_a_cell_lapses_the_attestation(tmp_path):
    run, wb, cells, ev, caps = _uniform(tmp_path)
    cap = caps[0]
    A.attest_uniform(wb, cap=cap, actor="scoring-critic", note=ATTEST)
    in_cap = [c for c in cells if c.rsplit(".", 1)[0] == cap]
    _score(wb, in_cap[0], ev[in_cap[0]], score=2.0)
    _score(wb, in_cap[0], ev[in_cap[0]], score=2.5)      # same scores, but the book
    assert cap in A.differentiation(wb)["attested"]      # still matches what was attested
    for c in in_cap:
        _score(wb, c, ev[c], score=2.0)                  # uniform again, at a NEW score
    assert cap in A.differentiation(wb)["no_differentiation"], \
        "an attestation is bound to the scores it saw"
