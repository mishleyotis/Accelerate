"""A Routine that fails silently is indistinguishable from one with nothing
to do.

WHY THESE EXIST. On 2026-08-30 a `list_triggers` call found two of the six
live Routines unhealthy, one of them for six days, with nothing anywhere
reporting either. The watchdog watches RUNS; nothing watched the ROUTINES.
Both failures are one field of one API response away from being visible, and
neither is visible from inside a run.

The two measured causes are encoded as diagnoses rather than status words,
because the next move differs completely:

  FAILED     the one measured instance was a SPEND LIMIT, which no change to
             this repo can fix
  ABANDONED  the one measured instance was BLOCKED on a connector permission
             prompt that the plugin's own hook allows — so the hook did not
             run, which is a stale install, which a session cannot heal
             because hooks bind once at session start
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = HERE / "routine_health.py"
sys.path.insert(0, str(HERE))
import routine_health as RH                                  # noqa: E402

_NO_CANON = pathlib.Path("/dev/null")

NOW = datetime(2026, 8, 30, 6, 20, tzinfo=timezone.utc)


def _t(name, status=None, fired=None, nxt=None, enabled=True, **kw):
    row = {"name": name, "id": f"trig_{name}", "enabled": enabled,
           "cron_expression": kw.pop("cron", "0 * * * *"),
           "next_run_at": nxt, **kw}
    if status:
        row["last_run"] = {"status": status, "fired_at": fired,
                           "session_id": f"cse_{name}"}
    return row


def test_a_succeeded_routine_is_healthy():
    r = RH.assess(_t("ok", "ROUTINE_RUN_STATUS_SUCCEEDED",
                     "2026-08-30T05:23:00Z"), NOW)
    assert r["verdict"] == "HEALTHY"


def test_a_failed_routine_names_the_spend_limit_before_a_code_defect():
    """The measured instance was not a defect at all, and a report that sent
    somebody looking for one would have cost a day."""
    r = RH.assess(_t("rect", "ROUTINE_RUN_STATUS_FAILED",
                     "2026-08-24T13:20:22Z"), NOW)
    assert r["verdict"] == "FAILED"
    assert "spend limit" in r["detail"].lower()
    assert r["stale_hours"] > 130
    assert r["session_id"] == "cse_rect", "the session is where the reason is"


def test_an_abandoned_routine_points_at_the_hook_that_did_not_run():
    r = RH.assess(_t("drift", "ROUTINE_RUN_STATUS_ABANDONED",
                     "2026-08-29T15:05:16Z"), NOW)
    assert r["verdict"] == "ABANDONED"
    assert "pending_action" in r["detail"]
    assert "bind once at session start" in r["detail"]


# ── in flight is not sick ────────────────────────────────────────────────

def test_a_firing_inside_its_own_interval_is_in_flight():
    """An hourly Routine is PENDING for part of every hour. Calling that
    unhealthy would make the check cry wolf on every run, and a check that
    cries wolf is one nobody reads."""
    r = RH.assess(_t("intake", "ROUTINE_RUN_STATUS_PENDING",
                     "2026-08-30T05:59:00Z", nxt="2026-08-30T06:59:00Z"), NOW)
    assert r["verdict"] == "IN_FLIGHT"
    assert "running, not stuck" in r["detail"]


def test_a_pending_firing_past_two_intervals_is_stuck():
    r = RH.assess(_t("intake", "ROUTINE_RUN_STATUS_PENDING",
                     "2026-08-30T02:00:00Z", nxt="2026-08-30T03:00:00Z"), NOW)
    assert r["verdict"] == "PENDING"
    assert "outlived the schedule" in r["detail"]


def test_the_interval_comes_from_the_routines_own_schedule():
    """A weekly Routine gets a week of slack and an hourly one gets an hour,
    without this script parsing cron."""
    weekly = RH.assess(_t("weekly", "ROUTINE_RUN_STATUS_PENDING",
                          "2026-08-30T02:00:00Z",
                          nxt="2026-09-06T02:00:00Z", cron="0 2 * * 1"), NOW)
    assert weekly["verdict"] == "IN_FLIGHT"


# ── the shapes that are not faults ───────────────────────────────────────

def test_a_disabled_routine_is_reported_but_not_a_fault():
    r = RH.assess(_t("paused", "ROUTINE_RUN_STATUS_SUCCEEDED",
                     "2026-08-01T00:00:00Z", enabled=False), NOW)
    assert r["verdict"] == "DISABLED"
    assert "not doing anything" in r["detail"]


def test_a_routine_with_no_recorded_run_is_distinguished():
    r = RH.assess(_t("fresh"), NOW)
    assert r["verdict"] == "NO_RUN"


# ── the report, and the exit code CI would read ──────────────────────────

def test_the_report_counts_and_orders_by_what_needs_attention():
    doc = {"triggers": [
        _t("a", "ROUTINE_RUN_STATUS_SUCCEEDED", "2026-08-30T05:00:00Z"),
        _t("b", "ROUTINE_RUN_STATUS_FAILED", "2026-08-24T13:00:00Z"),
        _t("c", "ROUTINE_RUN_STATUS_ABANDONED", "2026-08-29T15:00:00Z"),
    ]}
    out = RH.report(doc, NOW, canon=_NO_CANON)
    assert out["total"] == 3 and out["healthy"] == 1
    assert [r["name"] for r in out["unhealthy"]] == ["b", "c"]
    assert out["routines"][-1]["name"] == "a", "healthy sorts last"


def test_strict_exits_one_when_a_routine_needs_attention(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"triggers": [
        _t("b", "ROUTINE_RUN_STATUS_FAILED", "2026-08-24T13:00:00Z")]}))
    empty = tmp_path / "canon.md"
    empty.write_text("")
    r = subprocess.run([sys.executable, str(SCRIPT), "--file", str(p),
                        "--strict", "--canon", str(empty)],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout
    assert "spend limit" in r.stdout.lower()

    p.write_text(json.dumps({"triggers": [
        _t("a", "ROUTINE_RUN_STATUS_SUCCEEDED", "2026-08-30T05:00:00Z")]}))
    r = subprocess.run([sys.executable, str(SCRIPT), "--file", str(p),
                        "--strict", "--canon", str(empty)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_it_reads_the_response_shape_the_api_actually_returns(tmp_path):
    """`list_triggers` wraps its rows, and a caller pasting the raw response
    should not have to unwrap it first."""
    for doc in ({"triggers": [_t("a", "ROUTINE_RUN_STATUS_SUCCEEDED",
                                 "2026-08-30T05:00:00Z")]},
                [_t("a", "ROUTINE_RUN_STATUS_SUCCEEDED",
                    "2026-08-30T05:00:00Z")],
                {"data": [_t("a", "ROUTINE_RUN_STATUS_SUCCEEDED",
                             "2026-08-30T05:00:00Z")]}):
        assert RH.report(doc, NOW, canon=_NO_CANON)["total"] == 1


def test_a_declared_routine_that_does_not_exist_is_MISSING(tmp_path):
    """The failure this closes, measured 2026-08-30: an account carrying NO
    Routines answered `0/0 routine(s) healthy` and exit 0, and the readiness
    board's routines lane went green on an empty schedule while the canon
    declared six LIVE. Absence has to be a verdict; a table with no rows is
    the same silence a deleted Routine leaves."""
    canon = tmp_path / "ROUTINES.md"
    canon.write_text(
        "### 2a \u00b7 dma-synthesis-sequence-a \u2014 `8 */12 * * *` "
        "\u00b7 LIVE (`trig_x`, enabled)\n\n"
        "### 2z \u00b7 dma-retired-thing \u2014 every 12h "
        "\u00b7 DELETED in the routines UI\n")

    out = RH.report({"data": []}, NOW, canon=canon)
    assert out["missing"] == ["dma-synthesis-sequence-a"], out["missing"]
    assert out["declared"] == 1
    assert len(out["unhealthy"]) == 1, "a MISSING routine must need attention"

    # A DELETED section is history, not a requirement — rebuilding a Routine
    # somebody deliberately removed is not what this check is for.
    assert "dma-retired-thing" not in out["missing"]


def test_a_present_routine_is_not_reported_missing(tmp_path):
    canon = tmp_path / "ROUTINES.md"
    canon.write_text("### 2a \u00b7 keeper \u2014 `0 1 * * *` "
                     "\u00b7 LIVE (`trig_x`, enabled)\n")
    out = RH.report({"data": [_t("keeper", "ROUTINE_RUN_STATUS_SUCCEEDED",
                                 "2026-08-30T05:00:00Z")]}, NOW, canon=canon)
    assert out["missing"] == []
    assert out["unhealthy"] == []


def test_strict_fails_on_an_empty_account_against_the_real_canon(tmp_path):
    """End to end through the CLI, against the canon this plugin ships."""
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"data": []}))
    r = subprocess.run([sys.executable, str(SCRIPT), "--file", str(p),
                        "--strict"], capture_output=True, text=True)
    assert r.returncode == 1, r.stdout
    assert "MISSING" in r.stdout
    assert "declared LIVE in the canon" in r.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
