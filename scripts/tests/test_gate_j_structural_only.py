"""Gate J's CLI blocks on structure only — owner decision B (2026-10-04).

The CLI shares CG-PAR's rules (apps/mcp/dma_mcp/parity.py), and the exit
code is what an operator and CI branch on. Before this change any gap —
a list half the gold's length, a member filled on fewer rows — exited 1, so
the CLI refused exactly what the promote gate was found refusing wrongly:
counts. Now it exits 1 only on a structural gap, prints counts and fill
ratios as warnings, leaves a gold run out of its own reference set, and
prefers gold of the target's sub-vertical.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import parity  # noqa: E402

CLI = ROOT / "scripts" / "gate_j_surface_parity.py"
GOLD = ROOT / "fixtures" / "surface_gold.json"


def run(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, timeout=120)


def _thin(node):
    if isinstance(node, dict):
        if "n" in node:
            node["n"] = min(node["n"], 1)
            if node.get("rows"):
                node["rows"] = node["rows"][:1]
        for v in node.values():
            _thin(v)
    return node


def _write_dir(tmp_path, pages):
    for page, body in pages.items():
        (tmp_path / f"{page}.json").write_text(json.dumps(body))
    return tmp_path


def test_a_thinner_target_exits_clean_with_warnings(tmp_path):
    gold = parity.load_gold(GOLD)
    pages = {p: _thin(copy.deepcopy(s))
             for p, s in parity.gold_runs(gold)["gold-c1351d25"].items()}
    r = run("--gold", GOLD, "--target-dir", _write_dir(tmp_path, pages),
            "--sub-vertical", "CU")
    assert r.returncode == 0, r.stdout[-1500:]
    assert "(warning) [list_len]" in r.stdout, r.stdout[-1500:]
    assert "no structural gap" in r.stdout


def test_a_gold_run_is_left_out_of_its_own_reference(tmp_path):
    gold = parity.load_gold(GOLD)
    pages = parity.gold_runs(gold)["gold-40971653"]
    r = run("--gold", GOLD, "--target-dir", _write_dir(tmp_path, pages),
            "--run-id", "40971653-aa3e-4373-9163-a967c57a9305",
            "--sub-vertical", "CU")
    assert r.returncode == 0, r.stdout[-1500:]
    assert "left out: gold-40971653" in r.stdout, r.stdout[:600]
    assert "against the gold (gold-c1351d25, gold-d7ed1d90)" in r.stdout, \
        r.stdout[-600:]


def test_client_against_client_a_count_is_a_warning(tmp_path):
    bar = {"source": "s", "rating": 4.1, "scale": "1-5", "n": 10}
    ref = {"sections": {"sentiment": {"data": {"bars": [bar] * 7,
                                               "themes": [{"theme": "t"}]}}}}
    tgt = {"sections": {"sentiment": {"data": {"bars": [bar],
                                               "themes": [{"theme": "t"}]}}}}
    (tmp_path / "r.json").write_text(json.dumps(ref))
    (tmp_path / "t.json").write_text(json.dumps(tgt))
    r = run("--reference-file", tmp_path / "r.json",
            "--target-file", tmp_path / "t.json", "--page", "overview")
    assert r.returncode == 0, r.stdout
    assert "(warning) [list_len] overview.sentiment.bars" in r.stdout


def test_the_thin_fixture_still_exits_1_on_its_structural_gaps():
    r = run("--gold", GOLD, "--target-file",
            ROOT / "fixtures" / "parity" / "target-thin-overview.json",
            "--page", "overview", "--sub-vertical", "CU")
    assert r.returncode == 1, r.stdout
    assert "[held_beyond_cap] overview.firmographics.fields" in r.stdout
    assert "[key_absent] overview.sentiment.gap_analysis" in r.stdout
    assert "(warning) [stated_share] overview.firmographics.fields" in r.stdout
