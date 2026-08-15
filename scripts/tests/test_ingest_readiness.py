"""The census ratchet, without needing the corpus.

`ingest_readiness.py` runs against a gigabytes-large corpus that does not live
in this repo, so its comparison logic is what a test can reach — and the
comparison is the part that decides whether a run passes.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "ingest_readiness", ROOT / "scripts" / "ingest_readiness.py")
ir = importlib.util.module_from_spec(_spec)
sys.modules["ingest_readiness"] = ir
_spec.loader.exec_module(ir)

BASE = {"packages": 154, "parse_failures": 0, "zero_cell_packages": 7,
        "duplicate_ids_remaining": 0, "subvertical_unresolved": 7,
        "packages_without_identity": 6}


def test_an_unchanged_run_passes():
    assert ir.compare(dict(BASE), BASE) == []


def test_improvement_passes():
    better = dict(BASE, zero_cell_packages=3, subvertical_unresolved=0)
    assert ir.compare(better, BASE) == []


def test_each_one_sided_metric_regresses_on_its_own():
    """Every ratcheted metric must be checked, not just the first."""
    for key in ir._ONE_SIDED:
        worse = dict(BASE)
        worse[key] = BASE[key] + 1
        bad = ir.compare(worse, BASE)
        assert any(key in b for b in bad), f"{key} regressed and nothing said so"


def test_a_shrunken_corpus_is_itself_a_regression():
    """Fewer packages means fewer chances to fail, so every count below would
    improve for the wrong reason. That must not read as a pass."""
    smaller = dict(BASE, packages=40)
    bad = ir.compare(smaller, BASE)
    assert bad and "packages" in bad[0]


def test_a_metric_absent_from_the_baseline_is_not_invented():
    """An older baseline predating a metric must not fail every run: absent
    means unknown, and unknown is not a regression."""
    old = {k: v for k, v in BASE.items() if k != "duplicate_ids_remaining"}
    assert ir.compare(dict(BASE, duplicate_ids_remaining=99), old) == []


def test_observation_counts_are_not_ratcheted():
    """A parser that starts recording something it used to miss is an
    IMPROVEMENT that shows up as more observations. Ratcheting those would
    punish it, so they are reported and never compared."""
    assert "observations_total" not in ir._ONE_SIDED
    assert "observation_kinds" not in ir._ONE_SIDED
