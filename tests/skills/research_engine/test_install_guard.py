"""A run cannot start on an install that is not what the checkout ships.

RC-1 (2026-09-03): this container bound plugin cache 0.9.12 (47 agents)
while the checkout published 1.16.0 (73 agents); nothing refused, so a run
started here ran none of the gates the checkout carries. Two guards now sit
in front of `engine.cli start`, and the owner's decision that the plugin
runs BOTH as a marketplace checkout and as a Cowork zip means both are
needed: the cache-vs-repo comparison (`plugin_version.compare`) and the
install judging ITSELF (`template.zip_guard`: its manifest version against
the plugin version its pinned templates were pinned for).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import cli, template as T  # noqa: E402


# ── the cache guard ───────────────────────────────────────────────────────

@pytest.mark.parametrize("status", sorted(cli.REFUSING_INSTALL_STATES))
def test_a_refusing_install_state_refuses_the_start(monkeypatch, status):
    monkeypatch.setattr(cli, "install_state",
                        lambda: {"ok": False, "status": status,
                                 "_summary": f"{status}: installed 0.9.12 vs published 1.17.0"})
    text = cli.refuse_on_stale_install()
    assert text and text.startswith("REFUSED")
    assert "doctor.py --heal" in text and status in text


@pytest.mark.parametrize("state", [
    None,                                            # a repo checkout / CI: not judged
    {"ok": True, "status": "OK"},
    {"ok": False, "status": "UPDATED_MID_SESSION"},  # disk fixed; fresh children bind it
    {"ok": False, "status": "NOT_INSTALLED"},
    {"ok": False, "status": "MISSING"},
])
def test_states_that_are_not_refusals(monkeypatch, state):
    monkeypatch.setattr(cli, "install_state", lambda: state)
    assert cli.refuse_on_stale_install() is None


def test_start_stops_before_it_reads_the_preflight(monkeypatch, tmp_path, capsys):
    """The refusal is the FIRST thing `start` does — before the preflight,
    before a folder, before a workbook — so nothing is created on a stale
    install that a later session would have to clean up."""
    monkeypatch.setattr(cli, "refuse_on_stale_install",
                        lambda: "REFUSED: this container's dma-insights install is STALE …")

    def boom(*_a, **_k):
        raise AssertionError("the preflight was read on a refused install")
    from engine import preflight
    monkeypatch.setattr(preflight, "require", boom)
    rc = cli.main(["start", "--run", "R-STALE", "--entity", "X", "--entity-id", "x",
                   "--root", str(tmp_path), "--reference-date", "2026-08-29",
                   "--preflight", str(tmp_path / "pf.json")])
    assert rc == 1
    assert "REFUSED" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.xlsx"))


def test_the_waiver_flag_is_spelled_and_lets_the_start_proceed_to_the_preflight(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "refuse_on_stale_install", lambda: "REFUSED: STALE")
    seen = {}
    from engine import preflight

    def require(path):
        seen["path"] = path
        raise preflight.PreflightRefusal("no preflight at that path (fixture)")
    monkeypatch.setattr(preflight, "require", require)
    rc = cli.main(["start", "--run", "R-W", "--entity", "X", "--entity-id", "x",
                   "--root", str(tmp_path), "--reference-date", "2026-08-29",
                   "--preflight", str(tmp_path / "pf.json"),
                   "--allow-stale-install"])
    assert rc == 1 and seen["path"]           # got past the guard, to the preflight
    assert "no preflight" in capsys.readouterr().err


# ── the zip guard: the install judges itself ──────────────────────────────

def _install(tmp_path, manifest_version, requires):
    man = tmp_path / ".claude-plugin" / "plugin.json"
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"name": "dma-insights", "version": manifest_version}))
    tdir = tmp_path / "references" / "templates"
    tdir.mkdir(parents=True)
    (tdir / "report_templates.json").write_text(
        json.dumps({"pinned_at": "2026-09-03", "requires_plugin_version": requires}))
    return man, tdir


def test_a_zip_older_than_its_templates_is_refused(tmp_path):
    man, tdir = _install(tmp_path, "1.16.0", "1.17.0")
    g = T.zip_guard(man, tdir)
    assert g["ok"] is False and g["status"] == "PREDATES_TEMPLATES"
    assert "1.16.0" in g["fix"] and "1.17.0" in g["fix"] and "package_plugin.py" in g["fix"]


def test_a_zip_at_or_past_its_templates_passes(tmp_path):
    for v in ("1.17.0", "1.18.2", "2.0.0"):
        man, tdir = _install(tmp_path / v, v, "1.17.0")
        assert T.zip_guard(man, tdir)["status"] == "OK", v


def test_an_unreadable_manifest_fails_open_and_says_so(tmp_path):
    g = T.zip_guard(tmp_path / "nope.json", tmp_path)
    assert g["ok"] is True and g["status"] == "UNREADABLE"


def test_this_checkout_passes_its_own_zip_guard():
    """The pin and the manifest move together: a bump to one without the
    other is what the guard exists to catch, and it would catch it HERE."""
    g = T.zip_guard()
    assert g["status"] == "OK", g
    assert g["installed"] == g["required"], (
        "bump requires_plugin_version in report_templates.json with the manifest")


def test_the_zip_guard_refuses_the_start(monkeypatch):
    monkeypatch.setattr(T, "zip_guard",
                        lambda *a, **k: {"ok": False, "status": "PREDATES_TEMPLATES",
                                         "installed": "1.16.0", "required": "1.17.0",
                                         "fix": "re-upload the zip"})
    monkeypatch.setattr(cli, "install_state", lambda: None)
    text = cli.refuse_on_stale_install()
    assert text and "PREDATES its own templates" in text and "re-upload the zip" in text


def test_the_binding_records_the_plugin_version_it_was_made_under(tmp_path):
    from fixtures import new_run
    run = new_run(tmp_path, n=2)
    doc = json.loads((run.root / "00_entity_profile" / "template_binding.json").read_text())
    assert doc["plugin_version"] == T.installed_manifest_version()
    assert doc["requires_plugin_version"] == T.templates_require()


# ── the session brief carries the same verdict ───────────────────────────

def test_the_session_brief_names_a_zip_that_predates_its_templates(monkeypatch):
    import importlib.util
    import types
    PLUGIN = Path(__file__).resolve().parents[2].parent / "plugins" / "dma-insights"
    spec = importlib.util.spec_from_file_location(
        "session_brief", PLUGIN / "scripts" / "hooks" / "session_brief.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    monkeypatch.setattr(T, "zip_guard",
                        lambda *a, **k: {"ok": False, "status": "PREDATES_TEMPLATES",
                                         "installed": "1.16.0", "required": "1.17.0",
                                         "fix": "re-upload the zip"})
    fake = types.SimpleNamespace(compare=lambda: {"ok": True, "status": "OK"},
                                 summary=lambda v: "OK")
    monkeypatch.setitem(sys.modules, "plugin_version", fake)
    text = sb.install_warning()
    assert "PREDATES ITS OWN TEMPLATES" in text and "IS REFUSED" in text
    monkeypatch.setattr(T, "zip_guard", lambda *a, **k: {"ok": True, "status": "OK"})
    assert sb.install_warning() == ""
