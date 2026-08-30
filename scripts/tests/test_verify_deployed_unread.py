"""An unreadable service is not a service that is up to date.

MEASURED 2026-08-30. This container had no gcloud. `verify_deployed.py
--quick` printed COULD NOT READ for all three services and then:

    No service has unshipped commits touching its source.
    exit=0

Production was six days old at that moment. dmai-web was four commits
behind — one of them the fix for a register row rendering a live button
onto a page that reports it does not exist — and dmai-mcp three.

The mechanism is small and worth naming, because it is the shape that
recurs: an unread row was stored with `built_at: ""`, and
`changed_since("")` returns `[]` because there is no timestamp to compare
from. Empty then means the same thing as "nothing changed since the
build". One bucket, two meanings, and the reassuring one won.

The script's own docstring already said exit 2 was for "the comparison
could not be made — which is NOT a pass, and says so". Every path obeyed
that except the one that mattered.

These tests drive main() with GCLOUD pointed at nothing, which is exactly
what the no-SDK container looked like.
"""
import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_deployed.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_deployed", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(monkeypatch, *argv):
    m = _module()
    monkeypatch.setattr(m, "GCLOUD", "/definitely/not/a/real/gcloud")
    monkeypatch.setattr(sys, "argv", ["verify_deployed.py", *argv])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = m.main()
    return rc, buf.getvalue()


def test_unreadable_services_are_not_a_pass(monkeypatch):
    rc, out = _run(monkeypatch, "--quick")
    assert rc == 2, (
        f"exit {rc} for a run that read NOTHING. 0 would say production is "
        f"current when nothing was compared, which is the defect measured on "
        f"2026-08-30 — six days and seven commits stale behind a green exit")
    assert "NOT a pass" in out


def test_the_report_names_which_services_went_unread(monkeypatch):
    _, out = _run(monkeypatch, "--quick")
    for svc in ("dmai-web", "dmai-api", "dmai-mcp"):
        assert svc in out, (
            f"{svc} was not named. 'some services could not be read' sends "
            f"the reader hunting; the whole value here is saying which")


def test_it_never_claims_nothing_is_unshipped_when_it_read_nothing(monkeypatch):
    """The exact sentence that was printed over a six-day-old production."""
    _, out = _run(monkeypatch, "--quick")
    assert "No service has unshipped commits" not in out


def test_the_non_quick_path_is_also_not_a_pass(monkeypatch):
    """--quick was the measured case; the full path must not be the next one."""
    rc, _ = _run(monkeypatch)
    assert rc != 0, "the bundle comparison cannot pass on services it never read"


def test_changed_since_still_returns_empty_for_a_missing_timestamp():
    """Pin the mechanism, so a future reader sees WHY the guard is needed.

    This behaviour is correct on its own — with no build time there is no
    window to search. It is only dangerous when its result is read as
    'nothing changed'. If this ever stops being empty, the guard above is
    load-bearing for a different reason and someone should re-read both.
    """
    assert _module().changed_since("", ["apps/web"]) == []
