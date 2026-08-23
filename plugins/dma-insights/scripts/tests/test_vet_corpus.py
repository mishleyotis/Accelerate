"""The refusal rate is a measurement, so the instrument gets tested first.

Owner, 2026-08-23: "Did you really fix the detection and ensure at least 70%
of the client would commence synthesis and not get rejected? ... no guessing."

An instrument that quietly reports a flattering number is worse than no
instrument, so the properties pinned here are the ones that would let it lie:
the denominator it chooses, what it counts as a refusal, and whether a
package that CRASHED the vetter can be mistaken for one that passed.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import vet_corpus as vc  # noqa: E402


def _rows(*verdicts):
    return [{"package": f"p{i}", "verdict": v, "refusals": [], "warns": [],
             "pins": [], "exit": 0} for i, v in enumerate(verdicts)]


def _measure(monkeypatch, tmp_path, verdicts, refusals=None):
    """Drive `measure` over synthetic packages without running the vetter."""
    for i in range(len(verdicts)):
        (tmp_path / f"p{i}").mkdir()
    plan = dict(zip([f"p{i}" for i in range(len(verdicts))], verdicts))
    ref = refusals or {}

    def fake_vet(package, timeout=900):
        return {"package": package.name, "verdict": plan[package.name],
                "refusals": ref.get(package.name, []), "warns": [],
                "pins": [], "exit": 0}

    monkeypatch.setattr(vc, "vet", fake_vet)
    return vc.measure(tmp_path)


# ── the denominator, which is the arguable part ───────────────────────────

def test_a_package_that_was_never_an_input_is_not_counted_as_rejected(
        monkeypatch, tmp_path):
    """A briefing-only folder carries no scores. It cannot "commence
    synthesis" and it was never refused — counting it would let a corpus of
    briefing folders drag a healthy vetter below any floor."""
    m = _measure(monkeypatch, tmp_path,
                 ["PRODUCIBLE", "PRODUCIBLE", "NOT_AN_INPUT"])
    assert m["considered"] == 2
    assert m["producible_rate"] == 1.0
    assert m["counts"]["NOT_AN_INPUT"] == 1, "still reported, never hidden"


def test_the_rate_is_producible_over_packages_that_carry_scores(
        monkeypatch, tmp_path):
    m = _measure(monkeypatch, tmp_path,
                 ["PRODUCIBLE"] * 7 + ["REFUSE"] * 3)
    assert m["considered"] == 10
    assert m["producible_rate"] == pytest.approx(0.70)


def test_no_denominator_reports_unmeasurable_rather_than_a_number(
        monkeypatch, tmp_path):
    """Zero producible and zero refused is not 0% and it is not 100%. A
    rate invented from an empty set is the failure this whole exercise is
    about."""
    m = _measure(monkeypatch, tmp_path, ["NOT_AN_INPUT", "NOT_AN_INPUT"])
    assert m["producible_rate"] is None
    assert "NOT MEASURABLE" in vc.render(m)


# ── a crash must never read as a pass ─────────────────────────────────────

def test_a_timeout_is_neither_producible_nor_refused(monkeypatch, tmp_path):
    m = _measure(monkeypatch, tmp_path, ["PRODUCIBLE", "TIMEOUT"])
    assert m["counts"]["TIMEOUT"] == 1
    assert m["considered"] == 1, (
        "a package whose vetting never finished is not evidence either way")
    assert "TIMEOUT" in vc.render(m)


def test_the_vetter_crashing_is_recorded_not_swallowed(tmp_path,
                                                       monkeypatch):
    """`vet` catches OSError so one bad package cannot end the sweep — but
    the catch must produce a row, not a silent skip."""
    monkeypatch.setattr(vc.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    row = vc.vet(tmp_path)
    assert row["verdict"] == "ERROR" and "boom" in row["detail"]


def test_a_timed_out_vetter_produces_a_row(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="vet", timeout=1)
    monkeypatch.setattr(vc.subprocess, "run", _boom)
    row = vc.vet(tmp_path, timeout=1)
    assert row["verdict"] == "TIMEOUT" and "1s" in row["detail"]


# ── what counts as a refusal ──────────────────────────────────────────────

def test_warnings_alone_are_producible(monkeypatch, tmp_path):
    """The vetter exits 1 for ANY finding, warnings included. Reading exit
    status as the verdict would call every warned package rejected — and
    almost every real package carries a warning."""
    (tmp_path / "p").mkdir()
    monkeypatch.setattr(vc.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": "=== findings\n"
                  "[WARN] a column is named oddly\n[PIN] 10 evidence stores\n",
                  "stderr": ""})())
    row = vc.vet(tmp_path / "p")
    assert row["verdict"] == "PRODUCIBLE"
    assert row["warns"] and row["pins"] and not row["refusals"]


def test_a_refuse_line_is_a_refusal(monkeypatch, tmp_path):
    (tmp_path / "p").mkdir()
    monkeypatch.setattr(vc.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": "=== findings\n"
                  "[REFUSE] 26 score(s) outside 1.0-5.0\n", "stderr": ""})())
    assert vc.vet(tmp_path / "p")["verdict"] == "REFUSE"


def test_exit_two_is_not_an_input_not_a_refusal(monkeypatch, tmp_path):
    (tmp_path / "p").mkdir()
    monkeypatch.setattr(vc.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 2, "stdout": "",
                  "stderr": "no scoring workbook found"})())
    assert vc.vet(tmp_path / "p")["verdict"] == "NOT_AN_INPUT"


# ── the causes, which are what gets fixed ─────────────────────────────────

def test_causes_cluster_across_differing_counts(monkeypatch, tmp_path):
    """"26 score(s) outside 1.0-5.0" and "4 score(s) outside 1.0-5.0" are one
    cause. Ranked separately, the thing refusing most packages never rises to
    the top of the list."""
    m = _measure(monkeypatch, tmp_path, ["REFUSE", "REFUSE"], refusals={
        "p0": ["26 score(s) outside 1.0-5.0 in P1_Detail"],
        "p1": ["4 score(s) outside 1.0-5.0 in P1_Detail"]})
    assert len(m["refusal_causes"]) == 1
    assert m["refusal_causes"][0][1] == 2


def test_distinct_causes_stay_distinct(monkeypatch, tmp_path):
    m = _measure(monkeypatch, tmp_path, ["REFUSE", "REFUSE"], refusals={
        "p0": ["26 score(s) outside 1.0-5.0"],
        "p1": ["no research workbook found"]})
    assert len(m["refusal_causes"]) == 2


def test_the_render_names_every_refused_package(monkeypatch, tmp_path):
    m = _measure(monkeypatch, tmp_path, ["REFUSE"], refusals={
        "p0": ["no research workbook found"]})
    text = vc.render(m)
    assert "p0" in text and "no research workbook found" in text


# ── the floor ─────────────────────────────────────────────────────────────

def test_the_floor_fails_below_and_passes_at(monkeypatch, tmp_path, capsys):
    plan = ["PRODUCIBLE"] * 7 + ["REFUSE"] * 3
    for i in range(len(plan)):
        (tmp_path / f"p{i}").mkdir()
    names = {f"p{i}": v for i, v in enumerate(plan)}
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": names[p.name], "refusals": [],
        "warns": [], "pins": [], "exit": 0})
    assert vc.main(["--root", str(tmp_path), "--floor", "0.70"]) == 0
    assert vc.main(["--root", str(tmp_path), "--floor", "0.71"]) == 1


def test_an_unmeasurable_rate_fails_a_floor_rather_than_passing_it(
        monkeypatch, tmp_path):
    """The dangerous direction. A sweep that measured nothing must not clear
    a floor by having no counter-evidence."""
    (tmp_path / "p0").mkdir()
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": "NOT_AN_INPUT", "refusals": [],
        "warns": [], "pins": [], "exit": 0})
    assert vc.main(["--root", str(tmp_path), "--floor", "0.70"]) == 1


def test_no_floor_reports_without_judging(monkeypatch, tmp_path):
    (tmp_path / "p0").mkdir()
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": "REFUSE", "refusals": ["x"],
        "warns": [], "pins": [], "exit": 1})
    assert vc.main(["--root", str(tmp_path)]) == 0


def test_a_missing_package_root_is_an_error_not_an_empty_pass(tmp_path):
    assert vc.main(["--root", str(tmp_path / "nope"), "--floor", "0.7"]) == 2


def test_json_output_round_trips(monkeypatch, tmp_path):
    (tmp_path / "p0").mkdir()
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": "PRODUCIBLE", "refusals": [],
        "warns": [], "pins": [], "exit": 0})
    out = tmp_path / "m.json"
    vc.main(["--root", str(tmp_path), "--json", str(out)])
    assert json.loads(out.read_text())["counts"]["PRODUCIBLE"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the manifest, which is what makes "the last 60" a real denominator ────

def test_a_manifest_scopes_the_measurement(monkeypatch, tmp_path):
    """A rate quoted against a named set must be computed over exactly that
    set — not over whatever else is on disk beside it."""
    for name in ("in-scope-a", "in-scope-b", "not-in-scope"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": "PRODUCIBLE", "refusals": [],
        "warns": [], "pins": [], "exit": 0})
    m = vc.measure(tmp_path, manifest=["in-scope-a", "in-scope-b"])
    assert m["packages"] == 2
    assert {r["package"] for r in m["rows"]} == {"in-scope-a", "in-scope-b"}


def test_a_manifest_entry_not_on_disk_is_missing_not_dropped(monkeypatch,
                                                             tmp_path):
    """A package that could not be pulled shrinks the sample, and a shrunken
    sample must say so — silently measuring 58 of 60 and quoting it as 60 is
    the lie this flag exists to prevent."""
    (tmp_path / "here").mkdir()
    monkeypatch.setattr(vc, "vet", lambda p, timeout=900: {
        "package": p.name, "verdict": "PRODUCIBLE", "refusals": [],
        "warns": [], "pins": [], "exit": 0})
    m = vc.measure(tmp_path, manifest=["here", "never-pulled"])
    assert m["counts"].get("MISSING") == 1
    assert m["considered"] == 1, "MISSING is not evidence either way"
    assert "MISSING" in vc.render(m)


def test_an_empty_manifest_refuses_rather_than_measuring_nothing(tmp_path):
    (tmp_path / "p").mkdir()
    empty = tmp_path / "manifest.txt"
    empty.write_text("\n")
    assert vc.main(["--root", str(tmp_path), "--manifest", str(empty)]) == 2
