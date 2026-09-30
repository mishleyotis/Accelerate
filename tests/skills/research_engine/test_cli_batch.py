"""`engine.cli batch`: many writes, one load, one lock, one save.

Measured 2026-09-30 on a live multi-LOB run: one `engine.cli` write took
~10 s and every writer shares one lock, so 76 research batches would have
held it ~5.7 hours — concurrency past a few agents only queued them.
"""
from __future__ import annotations

import json

from engine import cli, runstate
from engine.brief import capability_of
from fixtures import new_run


def _run(tmp_path):
    run = new_run(tmp_path, n=5, prelim=False)
    cells = run.open().selected_subcaps()
    sibs = [c for c in cells if capability_of(c) == capability_of(cells[0])]
    return run, sibs


def _batch(run, tmp_path, lines, capsys):
    f = tmp_path / "ops.txt"
    f.write_text("\n".join(lines))
    rc = cli.main(["batch", "--run", run.run_id, "--root", str(run.root), "--file", str(f)])
    return rc, json.loads(capsys.readouterr().out)


def test_every_command_lands_and_the_workbook_is_saved_once(tmp_path, capsys, monkeypatch):
    run, sibs = _run(tmp_path)
    saves = []
    real = runstate.Run.open

    def counting(self):
        wb = real(self)
        orig = wb.save
        wb.save = lambda: (saves.append(1), orig())[1]
        return wb
    monkeypatch.setattr(runstate.Run, "open", counting)
    lines = ["# one capability's volley, logged together"] + [
        f"search --subcap {c} --facet works --tool web_search --query 'probe {i} {c}' "
        f"--hits 3 --kept 1 --actor research-p1c1-producer" for i, c in enumerate(sibs)]
    rc, out = _batch(run, tmp_path, lines, capsys)
    assert rc == 0 and out["applied"] == len(sibs) and out["refused"] == 0, out
    assert len(saves) == 1, f"{len(saves)} saves for one batch"
    rows = [r for r in real(run).rows("Search_Log") if str(r.get("Query") or "").startswith("probe")]
    assert len(rows) == len(sibs)


def test_a_refused_command_is_reported_and_the_rest_still_apply(tmp_path, capsys):
    run, sibs = _run(tmp_path)
    good = (f"search --subcap {sibs[0]} --facet works --tool web_search "
            f"--query 'kept one' --hits 1 --kept 1 --actor research-p1c1-producer")
    rc, out = _batch(run, tmp_path, [good, "search --facet works --tool web_search "
                                     "--query 'no cell' --hits 1 --kept 1", "gate --category P1C1",
                                     good.replace("kept one", "x") + " --run DMA-RES-OTHER-0001",
                                     "python3 -m engine.cli " + good.replace("kept one", "same run")
                                     + f" --run {run.run_id} --root {run.root}"], capsys)
    assert rc == 1
    oks = [r["ok"] for r in out["results"]]
    assert oks == [True, False, False, False, True], out
    assert "not a batchable write" in out["results"][2]["error"]
    assert "another run" in out["results"][3]["error"]
