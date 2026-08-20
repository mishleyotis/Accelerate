"""The API-key enrichment floor: configured, absent-and-named, never silent.

What must hold: every service resolves its own Secret Manager slot; an
absent key produces the exact fix command, not a vague failure; auth
headers are built per service style; and no code path prints a key.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import enrich_api  # noqa: E402


def test_every_service_has_a_secret_slot_and_auth_style():
    for name, cfg in enrich_api.SERVICES.items():
        assert cfg["secret"].startswith("dmai-") and cfg["secret"].endswith("-api-key")
        header, template = cfg["auth"]
        assert "{key}" in template and header
        assert "search_url" in cfg or "base" in cfg


def test_headers_carry_each_services_own_style():
    h = enrich_api._headers("exa", "K1")
    assert h == {"x-api-key": "K1"}
    h = enrich_api._headers("tavily", "K2")
    assert h == {"Authorization": "Bearer K2"}


def test_missing_key_names_service_state_and_fix(monkeypatch):
    monkeypatch.setattr(enrich_api, "_secret", lambda n, a: (None, "empty"))
    with pytest.raises(SystemExit) as e:
        enrich_api._key_for("exa", "access")
    msg = str(e.value)
    assert "exa" in msg and "empty" in msg
    assert "gcloud secrets versions add dmai-exa-api-key" in msg


def test_unshared_secret_is_distinguishable_from_empty(monkeypatch):
    monkeypatch.setattr(enrich_api, "_secret", lambda n, a: (None, "unshared"))
    with pytest.raises(SystemExit) as e:
        enrich_api._key_for("clay", "access")
    assert "unshared" in str(e.value)


def test_search_routes_query_through_the_service_shape(monkeypatch):
    seen = {}
    monkeypatch.setattr(enrich_api, "_access_token", lambda: "acc")
    monkeypatch.setattr(enrich_api, "_secret", lambda n, a: ("KEY", "ok"))
    monkeypatch.setattr(enrich_api, "_post",
                        lambda url, headers, payload: seen.update(
                            url=url, headers=headers, payload=payload) or {"ok": 1})
    out = enrich_api.search("tavily", "model registry vendor", num=3)
    assert out == {"ok": 1}
    assert seen["url"].startswith("https://api.tavily.com")
    assert seen["payload"]["query"] == "model registry vendor"
    assert seen["payload"]["max_results"] == 3
    assert "KEY" in seen["headers"]["Authorization"]


def test_generic_call_requires_a_rooted_path(monkeypatch):
    monkeypatch.setattr(enrich_api, "_access_token", lambda: "acc")
    monkeypatch.setattr(enrich_api, "_secret", lambda n, a: ("KEY", "ok"))
    with pytest.raises(SystemExit):
        enrich_api.call("clay", "no-slash", {})


def test_check_degrades_and_never_hard_fails(monkeypatch, capsys):
    monkeypatch.setattr(enrich_api, "_access_token", lambda: "acc")
    monkeypatch.setattr(enrich_api, "_secret", lambda n, a: (None, "empty"))
    assert enrich_api.check() == 0
    out = capsys.readouterr().out
    assert "degraded" in out and "not-run" in out and "fabricated" in out


def test_no_key_value_reaches_stdout_on_check(monkeypatch, capsys):
    monkeypatch.setattr(enrich_api, "_access_token", lambda: "acc")
    monkeypatch.setattr(enrich_api, "_secret",
                        lambda n, a: ("SUPERSECRETVALUE123", "ok"))
    enrich_api.check()
    assert "SUPERSECRETVALUE123" not in capsys.readouterr().out
