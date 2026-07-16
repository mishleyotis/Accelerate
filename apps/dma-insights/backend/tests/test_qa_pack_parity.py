"""Unit tests for the qa_pack_parity diff engine — pure synthetic dicts, no
DB and no app boot. The differ is the load-bearing part of the regen-chain
gate (`export_startup_pages → qa_pack_parity --strict`), so every rule gets a
pinned case: key-set diff both directions, id-aligned lists, positional
lists, ε boundary on score keys, non-score numeric tolerance, volatile-key
ignore, deterministic sampling.
"""
from __future__ import annotations

from app.scripts.export_startup_pages import prune_stale_client_entries
from app.scripts.qa_coverage_contract import PAGE_FILES
from app.scripts.qa_pack_parity import _SURFACE_ROUTES, diff_surface, stratified_sample


def test_identical_payloads_have_no_findings():
    doc = {"overall_score": 2.4, "cards": [{"id": "a", "fit_score": 80.5}]}
    assert diff_surface(doc, dict(doc)) == ([], [])


def test_key_set_diff_both_directions():
    pack = {"a": 1, "cards": [{"id": "x", "fit_score": 1.0, "old_field": 1}]}
    live = {"a": 1, "new_field": 2, "cards": [{"id": "x", "fit_score": 1.0}]}
    structural, drift = diff_surface(pack, live)
    assert "missing_in_pack:new_field" in structural
    assert "missing_in_live:cards[id=x].old_field" in structural
    assert drift == []


def test_numeric_drift_only_on_score_keys_with_epsilon():
    pack = {"overall_score": 2.40, "peer_median": 3.0, "issue_count": 4,
            "pillars": {"P1": 2.2}}
    live = {"overall_score": 2.42, "peer_median": 3.005, "issue_count": 9,
            "pillars": {"P1": 2.5}}
    structural, drift = diff_surface(pack, live, eps=0.01)
    paths = {d["path"] for d in drift}
    assert "overall_score" in paths          # .02 > ε
    assert "pillars.P1" in paths             # pillar map drift
    assert "peer_median" not in paths        # .005 ≤ ε
    assert "issue_count" not in paths        # not a score key
    assert structural == []


def test_id_aligned_lists_and_positional_lists():
    pack = {"cells": [{"id": "P1", "score": 2.0}, {"id": "P2", "score": 3.0}]}
    live = {"cells": [{"id": "P2", "score": 3.5}, {"id": "P1", "score": 2.0}]}
    structural, drift = diff_surface(pack, live)
    assert structural == []                  # same ids, order-independent
    assert [d["path"] for d in drift] == ["cells[id=P2].score"]
    # positional fallback when elements carry no id
    pack = {"vals": [{"score": 1.0}, {"score": 2.0}]}
    live = {"vals": [{"score": 1.0}]}
    structural, drift = diff_surface(pack, live)
    assert "list_len:vals:2!=1" in structural
    assert drift == []


def test_type_mismatch_is_structural_but_int_float_is_not():
    structural, _ = diff_surface({"x": None}, {"x": 1.5})
    assert structural == ["type:x:NoneType!=float"]
    structural, drift = diff_surface({"fit_score": 80}, {"fit_score": 80.0})
    assert structural == [] and drift == []


def test_volatile_keys_ignored():
    structural, _ = diff_surface({"last_refreshed_at": "a"},
                                 {"last_refreshed_at": "b", "generated_at": "c"})
    assert structural == []


def test_stratified_sample_deterministic_and_bounded():
    ids = [f"c-{i:03}" for i in range(94)]
    s1 = stratified_sample(ids, 8)
    assert s1 == stratified_sample(list(reversed(ids)), 8)  # order-insensitive
    assert len(s1) == 8 and len(set(s1)) == 8
    assert s1[0] == "c-000"
    assert stratified_sample(ids[:3], 8) == sorted(ids[:3])  # k ≥ n → all


def test_every_pack_page_surface_has_a_route():
    for surface in PAGE_FILES:
        assert surface in _SURFACE_ROUTES, surface
        assert "{d}" in _SURFACE_ROUTES[surface]


def test_prune_stale_client_entries_removes_superseded_dirs(tmp_path):
    """The 2026-07-07 pack-parity incident: the committed pack carries a
    stale ``ccu-0001`` dir superseded by ``consumers-credit-union-0001``.
    Pruning must drop the stale dir (and stale flat file) while keeping every
    ACTIVE client — else qa_pack_parity samples the ghost dir and fails."""
    clients = tmp_path / "clients"
    clients.mkdir()
    # active client (freshly exported) + its first-paint flat file
    (clients / "consumers-credit-union-0001").mkdir()
    (clients / "consumers-credit-union-0001" / "overview.json").write_text("{}")
    (clients / "consumers-credit-union-0001.json").write_text("{}")
    # stale superseded slug — dir AND flat file
    (clients / "ccu-0001").mkdir()
    (clients / "ccu-0001" / "overview.json").write_text("{}")
    (clients / "ccu-0001.json").write_text("{}")

    removed = prune_stale_client_entries(clients, {"consumers-credit-union-0001"})

    assert sorted(removed) == ["ccu-0001", "ccu-0001.json"]
    assert (clients / "consumers-credit-union-0001").is_dir()
    assert (clients / "consumers-credit-union-0001.json").exists()
    assert not (clients / "ccu-0001").exists()
    assert not (clients / "ccu-0001.json").exists()


def test_prune_stale_client_entries_noop_when_all_active(tmp_path):
    """Idempotent: nothing removed when every dir is in the active set."""
    clients = tmp_path / "clients"
    clients.mkdir()
    for did in ("a-bank-0001", "b-bank-0001"):
        (clients / did).mkdir()
    removed = prune_stale_client_entries(clients, {"a-bank-0001", "b-bank-0001"})
    assert removed == []
    assert (clients / "a-bank-0001").is_dir()
    assert (clients / "b-bank-0001").is_dir()
