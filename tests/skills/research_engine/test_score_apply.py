"""The scoring arithmetic has one owner: `engine.assessment apply`.

Measured 28-09-2026 (QA audit F-F14-029): three independent scorers of
P1C1.1.1 agreed on the rule, the band and the label and disagreed on the
number — 2.5 / 2.7 / 2.7 — because each did raw − adjustments, the caps
and the quarter-point by hand; one wrote "3.0 − 0.3 = 2.5". `apply` takes
the inputs and returns the final, the band, the level and the arithmetic
as one string; `score --raw --adj --cap` calls it, so a scorer never
supplies the result.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import assessment as A
from engine import contract as C
from engine.assessment import ScoringRefusal

from fixtures import (RATIONALE, researched_run as _researched,
                      score_cell as _score)

ENGINE = Path(__file__).resolve().parents[3] / "plugins/dma-insights/skills/dma-research"


def test_the_audits_three_inputs_give_one_answer():
    """raw 3.0, the −0.3 staleness adjustment, a T3 ceiling of 4.0: three
    scorers wrote 2.5, 2.7 and 2.7. The engine says one thing, three times."""
    outs = [A.apply("3.0", ceiling=4.0, adjustments=["ADJ_STALE:-0.3"]) for _ in range(3)]
    assert {o["final"] for o in outs} == {2.5}
    assert {o["band"] for o in outs} == {"Building"} and {o["level"] for o in outs} == {"M3"}
    assert len({o["arithmetic"] for o in outs}) == 1
    a = outs[0]["arithmetic"]
    assert "raw 3" in a and "-0.3 (ADJ_STALE) = 2.7" in a and "to the quarter, down: 2.5" in a


def test_an_adjustment_never_rounds_up_and_the_floor_is_one():
    assert A.apply(3.0, ceiling=5.0, adjustments=[("ADJ_X", -0.3)])["final"] == 2.5
    assert A.apply(3.0, ceiling=5.0, adjustments=[("ADJ_X", -0.5)])["final"] == 2.5
    assert A.apply(2.7, ceiling=5.0)["final"] == 2.5
    assert A.apply(1.0, ceiling=5.0, adjustments=[("ADJ_X", -0.3)])["final"] == 1.0


def test_the_ceiling_and_the_caps_bound_and_are_named():
    out = A.apply(4.0, ceiling=3.0, caps=["CAP_S2:3.0"])
    assert out["final"] == 3.0 and out["bounded_by"] == "evidence ceiling"
    assert "evidence ceiling" in out["caps_applied"]
    out = A.apply(4.0, ceiling=5.0, caps=["CAP_S3:2.0", "CAP_SS:3.0"])
    assert out["final"] == 2.0 and out["bounded_by"] == "cap CAP_S3"
    assert out["caps_applied"] == "CAP_S3"
    assert A.apply(2.5, ceiling=5.0)["caps_applied"] == "none applied"


def test_the_band_is_the_contracts_band_of_the_final():
    for raw in (1.0, 1.75, 2.0, 2.75, 3.0, 3.75, 4.0, 5.0):
        out = A.apply(raw, ceiling=5.0)
        assert out["band"] == C.band_of(out["final"])


@pytest.mark.parametrize("bad", [
    dict(raw=0.5, ceiling=5.0), dict(raw=3.0, ceiling=6.0),
    dict(raw=3.0, ceiling=5.0, adjustments=["ADJ_UP:+0.5"]),
    dict(raw=3.0, ceiling=5.0, adjustments=["-0.3"]),
    dict(raw=3.0, ceiling=5.0, caps=["CAP_X:7"]),
])
def test_bad_inputs_are_refused_by_name(bad):
    with pytest.raises(ScoringRefusal):
        A.apply(bad.pop("raw"), **bad)


def test_score_takes_the_inputs_and_records_the_working(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    out = _score(wb, cells[0], ev[cells[0]], score=None, raw="3.0",
                 adjustments=["ADJ_STALE:-0.3"])
    assert out["score"] == 2.5 and out["band"] == "Building" and out["raw"] == 3.0
    row = wb.scoring_row(cells[0])
    assert float(row["Score"]) == 2.5
    assert "-0.3 (ADJ_STALE)" in str(row["Caps_Applied"]), "the working is on the row"
    log = [r for r in wb.rows("Caps_Applied_Log") if r["subcap_id"] == cells[0]]
    assert log and "ADJ_STALE" in str(log[0]["caps_applied"])


def test_score_refuses_the_arithmetic_done_twice_or_not_at_all(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    with pytest.raises(ScoringRefusal, match="not both"):
        _score(wb, cells[0], ev[cells[0]], score=2.5, raw="3.0")
    with pytest.raises(ScoringRefusal, match="needs --score, or --raw"):
        _score(wb, cells[0], ev[cells[0]], score=None)


def test_a_raw_above_the_rows_ceiling_lands_at_the_ceiling(tmp_path):
    """The evidence ceiling bounds the derived final rather than refusing
    the raw: the refusal was for a FINAL typed above the ceiling."""
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    row = wb.scoring_row(cells[0])
    ceil, _why = A.ceiling_for(wb, row)
    out = _score(wb, cells[0], ev[cells[0]], score=None, raw="5.0")
    assert out["score"] == min(5.0, ceil)


def test_the_cli_apply_reads_the_rows_ceiling(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    r = subprocess.run([sys.executable, "-m", "engine.assessment", "apply",
                        "--run", run.run_id, "--root", str(run.root),
                        "--subcap", cells[0], "--raw", "3.0", "--adj", "ADJ_STALE:-0.3"],
                       cwd=ENGINE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["final"] == 2.5 and out["band"] == "Building" and out["ceiling_why"]
    assert out["subcap"] == cells[0]
