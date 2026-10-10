"""The store, offline: round trips, TTL per recency class on a fake clock,
the URL index, atomic writes (no temp file ever left behind), and run-state
updates that keep every increment under concurrent threads."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from evidence_engine import config, store as store_mod
from evidence_engine.store import Store, atomic_write, default_run_state

TEXT = ("Example Federal Credit Union reported total assets of $6.11 billion at June 30, 2026, "
        "up 4.2 percent over the year.")
META = {"url": "https://example-fcu.test/news/q2", "url_key": "example-fcu.test/news/q2",
        "final_url": "https://example-fcu.test/news/q2", "title": "Q2 results",
        "published": "2026-08-15", "published_basis": "json-ld datePublished",
        "content_type": "text/html", "retrieved": "2026-10-10", "url_status": "live",
        "original_url": None, "archive_timestamp": None, "verify_hash": "sha256:abc"}


class FakeClock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def st(tmp_path, clock) -> Store:
    return Store(tmp_path / "store", clock=clock)


def no_temp_files(root: Path) -> bool:
    return not any(p.name.endswith(".tmp") for p in root.rglob("*") if p.is_file())


# ── text ───────────────────────────────────────────────────────────────────

def test_text_round_trip_is_content_addressed(st, clock):
    h = st.put_text(TEXT, META, "CURRENT")
    assert h.startswith("sha256:") and len(h) == 71
    got = st.get_text(h)
    assert got is not None
    text, meta = got
    assert text == TEXT
    assert meta["url"] == META["url"] and meta["published"] == "2026-08-15"
    assert meta["content_hash"] == h and meta["recency_class"] == "CURRENT"
    assert meta["ttl_s"] == config.settings().text_ttl_current_s
    assert st.get_text(h[7:]) is not None                     # bare hex accepted
    assert st.put_text(TEXT, META, "CURRENT") == h             # same bytes, same hash
    assert st.get_text("sha256:" + "0" * 64) is None
    with pytest.raises(ValueError):
        st.get_text("not-a-hash")
    assert (st.root / "text" / f"{h[7:]}.txt").exists()
    assert (st.root / "text" / f"{h[7:]}.json").exists()


@pytest.mark.parametrize("recency, setting", [
    ("CURRENT", "text_ttl_current_s"),
    (None, "text_ttl_undated_s"),
    ("UNVERIFIED", "text_ttl_undated_s"),
    ("RECENT", "text_ttl_older_s"),
    ("ARCHIVAL", "text_ttl_older_s"),
])
def test_text_ttl_by_recency_class(st, clock, recency, setting):
    ttl = getattr(config.settings(), setting)
    h = st.put_text(TEXT + f" [{recency}]", META, recency)
    clock.t += ttl - 1
    assert st.get_text(h) is not None
    clock.t += 1
    assert st.get_text(h) is None
    assert st.text_meta(h) is not None                        # the sidecar is kept for health


def test_text_ttl_classes_are_ordered_current_shortest(st):
    assert st.text_ttl_s("CURRENT") < st.text_ttl_s(None) < st.text_ttl_s("STALE")


def test_url_index_finds_live_text_only(st, clock):
    h = st.put_text(TEXT, META, "CURRENT")
    assert st.find_text_by_url(META["url_key"]) == h
    assert st.find_text_by_url("example-fcu.test/other") is None
    idx = json.loads((st.root / "url_index.json").read_text())
    assert idx[META["url_key"]]["hash"] == h
    clock.t += config.settings().text_ttl_current_s
    assert st.find_text_by_url(META["url_key"]) is None       # expired ⇒ absent
    # re-put refreshes the TTL and the index
    assert st.put_text(TEXT, META, "CURRENT") == h
    assert st.find_text_by_url(META["url_key"]) == h
    # an explicit mapping (an alias URL) is honoured
    st.index_url("example-fcu.test/alias", h)
    assert st.find_text_by_url("example-fcu.test/alias") == h


# ── search ─────────────────────────────────────────────────────────────────

def test_search_round_trip_and_ttl(st, clock):
    results = [{"url": "https://example-fcu.test/a", "title": "A", "rank": 1}]
    st.put_search("searxng|example federal credit union digital banking|works", results)
    assert st.get_search("searxng|example federal credit union digital banking|works") == results
    assert st.get_search("missing") is None
    entry = st.search_entry("searxng|example federal credit union digital banking|works")
    assert entry["stored_at"].startswith("2027-")
    clock.t += config.settings().search_ttl_s
    assert st.get_search("searxng|example federal credit union digital banking|works") is None


def test_search_keys_with_unsafe_characters_do_not_escape_the_directory(st):
    st.put_search("../../etc/passwd", [1])
    files = list((st.root / "search").glob("*.json"))
    assert len(files) == 1 and ".." not in files[0].name
    assert st.get_search("../../etc/passwd") == [1]


# ── cards ──────────────────────────────────────────────────────────────────

def test_cards_round_trip_and_listing(st):
    run_id = "run-example-0001"
    cards = [{"card_id": f"EV-{i:08x}", "item": {"source_url": f"https://example-fcu.test/{i}"}} for i in (3, 1, 2)]
    for c in cards:
        assert st.put_card(run_id, c) == c["card_id"]
    assert st.get_card(run_id, "EV-00000002") == cards[2]
    assert st.get_card(run_id, "EV-missing") is None
    assert [c["card_id"] for c in st.list_cards(run_id)] == ["EV-00000001", "EV-00000002", "EV-00000003"]
    assert st.list_cards("no-such-run") == []
    with pytest.raises(ValueError):
        st.put_card(run_id, {"item": {}})
    assert st.card_ids(run_id) == ["EV-00000001", "EV-00000002", "EV-00000003"]


# ── run state ──────────────────────────────────────────────────────────────

def test_run_state_default_and_save(st, clock):
    assert st.run_state("fresh") == default_run_state()
    st.update_run_state("r1", lambda s: s["queries"].append({"id": "Q-01", "q": "example federal credit union mobile app"}))
    state = st.run_state("r1")
    assert state["queries"][0]["id"] == "Q-01"
    assert state["created_at"] and state["updated_at"]
    # a replacement dict returned by fn is saved as the state
    st.update_run_state("r1", lambda s: {**s, "ladder_rungs": ["regulator"]})
    assert st.run_state("r1")["ladder_rungs"] == ["regulator"]
    assert st.run_state("r1")["queries"]                      # the merge kept the rest


def test_run_state_concurrent_updates_keep_every_increment(st):
    run_id = "run-concurrent"
    threads, errors = [], []

    def worker():
        try:
            for _ in range(10):
                def bump(state):
                    calls = state.setdefault("calls", {})
                    calls["works"] = calls.get("works", 0) + 1
                st.update_run_state(run_id, bump)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    for _ in range(20):
        t = threading.Thread(target=worker)
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert st.run_state(run_id)["calls"]["works"] == 200
    assert no_temp_files(st.root)


# ── health ─────────────────────────────────────────────────────────────────

def test_health_log_is_append_only_jsonl(st):
    st.append_health({"source": "searxng", "state": "open", "last_kind": "captcha"})
    st.append_health({"source": "searxng", "state": "closed"})
    lines = (st.root / "health" / "source_health.jsonl").read_text().splitlines()
    assert len(lines) == 2
    recs = st.health_records()
    assert recs[0]["source"] == "searxng" and recs[0]["at"].startswith("2027-")
    assert st.health_records(limit=1)[0]["state"] == "closed"


# ── atomicity ──────────────────────────────────────────────────────────────

def test_atomic_writes_leave_no_temp_file(st):
    st.put_text(TEXT, META, "CURRENT")
    st.put_search("k", [1])
    st.put_card("r", {"card_id": "EV-1"})
    st.save_run_state("r", {"calls": {}})
    st.append_health({"x": 1})
    assert no_temp_files(st.root)


def test_failed_write_leaves_no_temp_file_and_no_partial_target(tmp_path, monkeypatch):
    target = tmp_path / "d" / "f.json"
    atomic_write(target, b'{"ok": true}')

    def bad_replace(src, dst):
        raise OSError("disk full")

    # the final rename fails: the target keeps its old bytes, no temp remains
    monkeypatch.setattr(store_mod.os, "replace", bad_replace)
    with pytest.raises(OSError):
        atomic_write(target, b"{}")
    monkeypatch.undo()
    assert target.read_bytes() == b'{"ok": true}'
    assert no_temp_files(tmp_path)


def test_unserialisable_card_leaves_no_temp_file(st):
    with pytest.raises(TypeError):
        st.put_card("r", {"card_id": "EV-x", "item": {"when": object()}})
    assert no_temp_files(st.root)
    assert st.get_card("r", "EV-x") is None


# ── settings root and the GCS mirror ──────────────────────────────────────

def test_default_root_is_settings_data_dir_and_process_store_is_cached(tmp_path):
    store_mod.reset_store()
    s = store_mod.store()
    assert s.root == Path(config.settings().data_dir)
    assert str(s.root).startswith(str(tmp_path))               # conftest isolates EE_DATA_DIR
    assert store_mod.store() is s
    store_mod.reset_store()


def test_gcs_mirror_is_local_only_when_the_library_or_bucket_is_absent(tmp_path, clock, monkeypatch):
    s = Store(tmp_path / "s", clock=clock, gcs_bucket="example-bucket-that-is-not-used")
    import builtins
    real_import = builtins.__import__

    def no_gcs(name, *a, **k):
        if name.startswith("google"):
            raise ImportError("no google-cloud-storage here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_gcs)
    h = s.put_text(TEXT, META, "CURRENT")                      # must not raise
    assert s.get_text(h) is not None
    assert s._gcs_bucket() is None and s._bucket_tried is True
