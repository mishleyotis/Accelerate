"""A lane nobody measured is not a lane that passed.

WHY THESE EXIST. Every green report this project has been wrong about was
green because something never looked: the doctor counted the checkout's files
on a container carrying a five-agent install; `classification.py` classified
the client profile and nothing read the kind it wrote; two of six Routines
were unhealthy for days because the thing that watches runs does not watch
Routines. In each case the summary line was true about what it measured and
silent about what it did not.

So the property under test here is not "readiness.py runs". It is that a lane
this container cannot see NEVER lands in the ready count, that `--strict`
refuses such a report, and that the standing items no script can close travel
with the answer instead of being remembered by whoever wrote it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = HERE / "readiness.py"
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(HERE))
import readiness as R                                        # noqa: E402


def _stub(monkeypatch, table):
    """Replace the subprocess layer: table maps a script basename to
    (exit_code, output). A name absent from the table returns None, which is
    this file's word for 'never ran'."""
    def fake(argv, cwd=None, timeout=None):
        name = next((pathlib.Path(a).name for a in argv
                     if str(a).endswith(".py")), argv[-1])
        return table.get(name, (None, "not stubbed"))
    monkeypatch.setattr(R, "_run", fake)


ALL_GREEN = {"audit_coverage.py": (0, "0 holes"),
             "audit_autoapprove.py": (0, "124/184 auto-approved"),
             "audit_skills.py": (0, "99/99 scripts"),
             "check_taxonomy_drift.py": (0, "0 stale"),
             "plugin_version.py": (0, "OK"),
             "doctor.py": (0, "all green"),
             "routine_health.py": (0, "6/6 healthy")}


# ── the core invariant ───────────────────────────────────────────────────

def test_an_unmeasured_lane_is_never_counted_as_ready(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "doctor.py": (None, "no network")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    doctor = next(r for r in out["lanes"] if r["lane"] == "connector")
    assert doctor["verdict"] == R.UNMEASURED
    assert doctor not in out["ready"]
    assert len(out["ready"]) + len(out["blocked"]) + len(out["unmeasured"]) \
        == len(out["lanes"])


def test_every_lane_lands_in_exactly_one_bucket(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "audit_coverage.py": (1, "2 holes")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    seen = [r["lane"] for r in out["ready"] + out["blocked"]
            + out["unmeasured"]]
    assert sorted(seen) == sorted(r["lane"] for r in out["lanes"])


# ── the routines lane, which a script cannot measure by itself ───────────

def test_without_a_triggers_file_the_routines_lane_is_unmeasured(monkeypatch):
    _stub(monkeypatch, ALL_GREEN)
    out = R.assess()
    row = next(r for r in out["lanes"] if r["lane"] == "routines")
    assert row["verdict"] == R.UNMEASURED
    assert "list_triggers" in row["detail"] + row["fix"], row


def test_with_a_triggers_file_the_routines_lane_is_measured(monkeypatch,
                                                            tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "routine_health.py": (1, "2 unhealthy")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    row = next(r for r in out["lanes"] if r["lane"] == "routines")
    assert row["verdict"] == R.BLOCKED


# ── a container with no credentials measured its own emptiness ───────────

def test_a_missing_credential_downgrades_the_connector_lane_to_unmeasured(
        monkeypatch, tmp_path):
    """Reporting a SERVING deployment as BLOCKED because this container holds
    no token is as wrong as reporting an unreachable one as ready."""
    _stub(monkeypatch, {**ALL_GREEN,
                        "doctor.py": (1, "  [FAIL] identity token mints"
                                         "  no key file and no gcloud")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    row = next(r for r in out["lanes"] if r["lane"] == "connector")
    assert row["verdict"] == R.UNMEASURED
    assert "no live credential path" in row["detail"]


def test_a_real_connector_failure_still_blocks(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN,
                        "doctor.py": (1, "  [FAIL] connector rejects an "
                                         "unauthenticated call  HTTP 200")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    row = next(r for r in out["lanes"] if r["lane"] == "connector")
    assert row["verdict"] == R.BLOCKED


def test_a_stale_install_is_not_reported_as_a_missing_credential(
        monkeypatch, tmp_path):
    """The measured mistake. The doctor fails on a STALE install, and most of
    its PASSING rows contain the word `token` — so a downgrade keyed on the
    whole output turned an install defect into "no live credential path",
    inventing a reason for its own verdict and hiding a row the install lane
    already owns."""
    doctor = ("DMA Insights — install doctor\n"
              "  [ok] identity token mints  yes, from key file\n"
              "  [FAIL] installed plugin  STALE: 0.9.12 vs 1.9.0\n"
              "  [ok] connector path token  not in this environment\n"
              "14/15 checks passed.")
    _stub(monkeypatch, {**ALL_GREEN, "doctor.py": (1, doctor)})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    row = next(r for r in out["lanes"] if r["lane"] == "connector")
    assert row["verdict"] == R.BLOCKED, row
    assert "installed plugin" in row["detail"], row["detail"]
    assert "no live credential path" not in row["detail"]


def test_offline_leaves_the_connector_unmeasured_rather_than_passing(
        monkeypatch, tmp_path):
    """`--offline` is what CI and `goal_status.py --offline` pass. The lane
    reaches a live service, so skipping it must read as unmeasured — a
    skipped check that reports READY is the whole thing this file refuses."""
    _stub(monkeypatch, ALL_GREEN)
    out = R.assess(triggers=str(tmp_path / "t.json"), offline=True)
    row = next(r for r in out["lanes"] if r["lane"] == "connector")
    assert row["verdict"] == R.UNMEASURED
    assert "--offline" in row["detail"]


def test_offline_does_not_silence_the_other_lanes(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "audit_coverage.py": (1, "1 HOLE")})
    out = R.assess(triggers=str(tmp_path / "t.json"), offline=True)
    assert [r["lane"] for r in out["blocked_in_repository"]] == ["coverage"]


# ── the detail line must carry the decisive row ──────────────────────────

def test_the_detail_is_the_failing_row_not_the_last_three_lines():
    text = ("headline\n  [ok] a\n  [FAIL] the real one\n"
            "  [ok] b\n  [ok] c\n  [ok] d")
    assert "the real one" in R._gist(text)
    assert "[ok] d" not in R._gist(text)


def test_a_clean_run_falls_back_to_its_headline_and_summary():
    text = "0 holes\n  tab -> command -> agent\n  ...\nALL OWNED"
    got = R._gist(text)
    assert "0 holes" in got and "ALL OWNED" in got


def test_a_single_line_output_is_not_repeated():
    assert R._gist("6/6 healthy") == "6/6 healthy"


# ── the exit codes, which are what CI reads ──────────────────────────────

def test_blocked_exits_nonzero_without_strict(monkeypatch, tmp_path,
                                              capsys):
    _stub(monkeypatch, {**ALL_GREEN, "audit_skills.py": (1, "3 broken refs")})
    assert R.main(["--triggers", str(tmp_path / "t.json")]) == 1


def test_unmeasured_exits_zero_without_strict_and_says_so(monkeypatch,
                                                          capsys):
    _stub(monkeypatch, ALL_GREEN)
    rc = R.main([])                       # no --triggers, no --tests
    text = capsys.readouterr().out
    assert rc == 0
    assert "never measured" in text, text


def test_unmeasured_exits_nonzero_under_strict(monkeypatch):
    _stub(monkeypatch, ALL_GREEN)
    assert R.main(["--strict"]) == 1


def test_json_carries_the_buckets_and_the_standing_items(monkeypatch,
                                                          tmp_path, capsys):
    _stub(monkeypatch, ALL_GREEN)
    R.main(["--triggers", str(tmp_path / "t.json"), "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert {"lanes", "ready", "blocked", "unmeasured", "standing_open"} \
        <= set(doc)
    assert doc["standing_open"], "the open items must travel with the answer"


# ── the standing items must stay answerable ──────────────────────────────

def test_every_standing_item_names_an_owner_and_a_document_that_exists():
    """An open item with no owner is a worry, and an open item pointing at a
    document that is not there is worse than none — it reads as specified."""
    for item, detail, owner, doc in R.STANDING_OPEN:
        assert owner.strip(), item
        assert detail.strip(), item
        path = pathlib.Path(R.PLUGIN) / doc
        assert path.exists(), f"{item} points at a missing {doc}"


def test_every_lane_names_a_fix(monkeypatch, tmp_path):
    _stub(monkeypatch, ALL_GREEN)
    for row in R.assess(triggers=str(tmp_path / "t.json"))["lanes"]:
        assert row["fix"].strip(), row["lane"]
        assert row["what"].strip(), row["lane"]


# ── scope: a blocked lane is not one thing ───────────────────────────────

def test_every_lane_declares_what_its_verdict_is_a_property_of(monkeypatch,
                                                                tmp_path):
    _stub(monkeypatch, ALL_GREEN)
    for row in R.assess(triggers=str(tmp_path / "t.json"))["lanes"]:
        assert row["scope"] in (R.REPOSITORY, R.CONTAINER, R.EXTERNAL), row


def test_a_stale_install_does_not_read_as_a_repository_defect(monkeypatch,
                                                               tmp_path):
    """A stale install is true of the CONTAINER the check ran in. It is a
    real blocker — it is what abandoned a live Routine — and it is not
    something a reader of this checkout can fix by editing a file, so a
    caller asking only about the repository must not be handed it."""
    _stub(monkeypatch, {**ALL_GREEN,
                        "plugin_version.py": (1, "STALE: 0.9.12 vs 1.9.0")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    assert out["blocked"], "it still blocks"
    assert not out["blocked_in_repository"], \
        "and it is not the checkout's defect"


def test_a_tool_nobody_ruled_on_blocks_the_approvals_lane(monkeypatch,
                                                          tmp_path):
    """A scheduled firing has nobody to answer a prompt, so an MCP tool in
    neither the read nor the withheld set is a firing that stops — and it
    stops silently, which is why it is a lane rather than a warning."""
    _stub(monkeypatch, {**ALL_GREEN,
                        "audit_autoapprove.py": (1, "1 UNCLASSIFIED")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    assert [r["lane"] for r in out["blocked_in_repository"]] == ["approvals"]


def test_a_coverage_hole_is_a_repository_defect(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "audit_coverage.py": (1, "2 holes")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    assert [r["lane"] for r in out["blocked_in_repository"]] == ["coverage"]


def test_an_unhealthy_routine_is_external_to_both(monkeypatch, tmp_path):
    _stub(monkeypatch, {**ALL_GREEN, "routine_health.py": (1, "2 unhealthy")})
    out = R.assess(triggers=str(tmp_path / "t.json"))
    row = next(r for r in out["lanes"] if r["lane"] == "routines")
    assert row["scope"] == R.EXTERNAL
    assert not out["blocked_in_repository"]


# ── it must actually run ─────────────────────────────────────────────────

def test_the_script_answers_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
