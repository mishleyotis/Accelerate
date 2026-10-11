"""The engine's memory: content-addressed text, search cache, cards, run state.

Why this module exists
----------------------
A card points at `provenance.content_hash` and `excerpt_offsets` into a
cleaned text (CARD-CONTRACT §3); `expand_context` and `verify_cards` must
read back EXACTLY the bytes the card was cut from, so cleaned text is
stored by its sha256 and never rewritten. Search results are cached so a
re-run of a facet within a day costs the backends nothing; cards and the
per-run state (origin clusters seen per facet, calls per facet for
saturation, the query log, the ladder rungs searched) let a stopped run
resume. The source-health log is the breaker history `/health` reports.

The rules
---------
- **TTL by recency class** (config, "cache TTLs"): a search entry expires
  after `settings.search_ttl_s`; a text entry expires after
  `text_ttl_current_s` when it was stored as `CURRENT`, after
  `text_ttl_undated_s` when undated (`UNVERIFIED` / None), else after
  `text_ttl_older_s` — a CURRENT page is re-read sooner than an ARCHIVAL
  one, which does not change. An expired entry reads as absent.
- **Atomic writes**: every file is written to a temp name in the same
  directory and `os.replace`d, so a reader never sees a half-written file
  and a crash never leaves a torn one; a failed write leaves no temp file.
- **Run state is read-modify-write under a per-run lock**
  (`update_run_state(run_id, fn)`), so concurrent collectors in one
  process never lose an increment.
- **Local first, GCS mirror optional**: the store is rooted at
  `settings.data_dir`; when `settings.gcs_bucket` is set, each written
  file is also uploaded (lazy import of `google.cloud.storage`; absent
  library or empty bucket ⇒ local only, never required in tests).

All timestamps come from an injectable clock (epoch seconds). No model,
no network beyond the optional mirror.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import settings

log = logging.getLogger(__name__)

Clock = Callable[[], float]

RECENCY_CURRENT = "CURRENT"
UNDATED_CLASSES = frozenset({"", "UNVERIFIED", "NONE"})
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _hex(h: str) -> str:
    """`sha256:<hex>` or bare hex → hex; refuses anything else."""
    v = (h or "").strip()
    if v.startswith("sha256:"):
        v = v[7:]
    if not re.fullmatch(r"[0-9a-f]{64}", v):
        raise ValueError(f"not a sha256 content hash: {h!r}")
    return v


def _safe(component: str) -> str:
    """A path component that cannot traverse: unsafe characters become `_`
    and an overlong or empty name is hashed."""
    c = _SAFE_RE.sub("_", str(component or ""))
    c = c.strip("._")
    if not c or len(c) > 120:
        return "h_" + hashlib.sha256(str(component).encode("utf-8")).hexdigest()[:32]
    return c


def _iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a temp file in the same directory and
    `os.replace`; a failure removes the temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def _loads(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def default_run_state() -> dict[str, Any]:
    """The shape every run starts with (DISCOVERY §3: saturation is judged
    per facet from origin clusters seen and calls made)."""
    return {"origin_clusters": {}, "calls": {}, "queries": [], "ladder_rungs": [],
            "cards": 0, "created_at": None, "updated_at": None}


class Store:
    """See the module docstring. `root` defaults to `settings.data_dir`;
    `clock` to `time.time`; `gcs_bucket` to `settings.gcs_bucket`."""

    def __init__(self, root: Path | str | None = None, *, clock: Clock | None = None,
                 gcs_bucket: str | None = None) -> None:
        s = settings()
        self.root = Path(root) if root is not None else Path(s.data_dir)
        self._clock: Clock = clock or time.time
        self._bucket_name = gcs_bucket if gcs_bucket is not None else s.gcs_bucket
        self._bucket: Any = None
        self._bucket_tried = False
        self._settings = s
        self._run_locks: dict[str, threading.Lock] = {}
        self._run_locks_guard = threading.Lock()
        self._index_lock = threading.Lock()

    # paths --------------------------------------------------------------
    def _text_path(self, hexhash: str) -> Path:
        return self.root / "text" / f"{hexhash}.txt"

    def _text_meta_path(self, hexhash: str) -> Path:
        return self.root / "text" / f"{hexhash}.json"

    def _search_path(self, key: str) -> Path:
        return self.root / "search" / f"{_safe(key)}.json"

    def _card_path(self, run_id: str, card_id: str) -> Path:
        return self.root / "cards" / _safe(run_id) / f"{_safe(card_id)}.json"

    def _run_state_path(self, run_id: str) -> Path:
        return self.root / "runs" / _safe(run_id) / "state.json"

    @property
    def _url_index_path(self) -> Path:
        return self.root / "url_index.json"

    @property
    def _health_path(self) -> Path:
        return self.root / "health" / "source_health.jsonl"

    # writing ------------------------------------------------------------
    def _write(self, path: Path, data: bytes) -> None:
        atomic_write(path, data)
        self._mirror(path)

    def _gcs_bucket(self) -> Any:
        if self._bucket_tried or not self._bucket_name:
            return self._bucket
        self._bucket_tried = True
        try:
            from google.cloud import storage  # type: ignore  # lazy: optional
            self._bucket = storage.Client().bucket(self._bucket_name)
        except Exception as exc:  # noqa: BLE001 — local only, say so once
            log.warning("gcs mirror disabled (%s): %s", self._bucket_name, exc)
            self._bucket = None
        return self._bucket

    def _mirror(self, path: Path) -> None:
        bucket = self._gcs_bucket()
        if bucket is None:
            return
        rel = path.relative_to(self.root).as_posix()
        try:
            bucket.blob(rel).upload_from_filename(str(path))
        except Exception as exc:  # noqa: BLE001 — the local copy is authoritative
            log.warning("gcs mirror of %s failed: %s", rel, exc)

    def _restore(self, path: Path) -> bool:
        """On a local miss, pull the file from the mirror when there is one."""
        bucket = self._gcs_bucket()
        if bucket is None:
            return False
        rel = path.relative_to(self.root).as_posix()
        try:
            blob = bucket.blob(rel)
            if not blob.exists():
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            blob.download_to_filename(str(tmp))
            os.replace(tmp, path)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("gcs restore of %s failed: %s", rel, exc)
            return False

    def _exists(self, path: Path) -> bool:
        return path.exists() or self._restore(path)

    # TTL ----------------------------------------------------------------
    def text_ttl_s(self, recency_class: str | None) -> int:
        s = self._settings
        rc = (recency_class or "").upper()
        if rc == RECENCY_CURRENT:
            return s.text_ttl_current_s
        if rc in UNDATED_CLASSES:
            return s.text_ttl_undated_s
        return s.text_ttl_older_s

    def _expired(self, meta: dict[str, Any]) -> bool:
        exp = meta.get("expires_at_ts")
        return exp is not None and self._clock() >= float(exp)

    # text ---------------------------------------------------------------
    def put_text(self, text: str, meta: dict[str, Any] | None = None,
                 recency_class: str | None = None) -> str:
        """Store cleaned text by content; returns `sha256:<hex>`. The sidecar
        carries `meta` (url, final_url, title, published, published_basis,
        content_type, retrieved, url_status, original_url,
        archive_timestamp, verify_hash) plus the storage bookkeeping. A
        re-put of the same text refreshes the sidecar and the TTL."""
        data = (text or "").encode("utf-8")
        hexhash = hashlib.sha256(data).hexdigest()
        now = self._clock()
        ttl = self.text_ttl_s(recency_class)
        side = dict(meta or {})
        side.update({"content_hash": "sha256:" + hexhash, "bytes": len(data),
                     "recency_class": recency_class or "UNVERIFIED", "ttl_s": ttl,
                     "stored_at": _iso(now), "stored_at_ts": now,
                     "expires_at": _iso(now + ttl), "expires_at_ts": now + ttl})
        if not self._text_path(hexhash).exists():
            self._write(self._text_path(hexhash), data)
        self._write(self._text_meta_path(hexhash), _dumps(side))
        for key in ("url_key", "url"):
            if side.get(key):
                self._index_url(str(side[key]), "sha256:" + hexhash, now)
                break
        return "sha256:" + hexhash

    def get_text(self, content_hash: str) -> tuple[str, dict[str, Any]] | None:
        """`(text, meta)` or None when absent or expired."""
        hexhash = _hex(content_hash)
        tp, mp = self._text_path(hexhash), self._text_meta_path(hexhash)
        if not (self._exists(tp) and self._exists(mp)):
            return None
        meta = _loads(mp)
        if self._expired(meta):
            return None
        return tp.read_text(encoding="utf-8"), meta

    def text_meta(self, content_hash: str) -> dict[str, Any] | None:
        """The sidecar alone, expired or not (for health and eval)."""
        mp = self._text_meta_path(_hex(content_hash))
        return _loads(mp) if self._exists(mp) else None

    # url index ----------------------------------------------------------
    def _read_index(self) -> dict[str, Any]:
        p = self._url_index_path
        if not self._exists(p):
            return {}
        try:
            return _loads(p)
        except (ValueError, OSError):
            return {}

    def _index_url(self, url_key: str, content_hash: str, now: float) -> None:
        with self._index_lock:
            idx = self._read_index()
            idx[url_key] = {"hash": content_hash, "stored_at": _iso(now)}
            self._write(self._url_index_path, _dumps(idx))

    def index_url(self, url_key: str, content_hash: str) -> None:
        """Map a URL key (`fetch.url_key`) to a stored text."""
        self._index_url(url_key, "sha256:" + _hex(content_hash), self._clock())

    def find_text_by_url(self, url_key: str) -> str | None:
        """The content hash of the live (unexpired) text stored for this
        URL key, else None."""
        entry = self._read_index().get(url_key)
        if not entry:
            return None
        h = entry.get("hash")
        if not h or self.get_text(h) is None:
            return None
        return h

    # search cache -------------------------------------------------------
    def put_search(self, key: str, results: Any) -> None:
        now = self._clock()
        ttl = self._settings.search_ttl_s
        self._write(self._search_path(key), _dumps({
            "key": key, "results": results, "stored_at": _iso(now), "stored_at_ts": now,
            "expires_at": _iso(now + ttl), "expires_at_ts": now + ttl}))

    def get_search(self, key: str) -> Any | None:
        """The cached results, or None when absent or past `search_ttl_s`."""
        p = self._search_path(key)
        if not self._exists(p):
            return None
        entry = _loads(p)
        if self._expired(entry):
            return None
        return entry.get("results")

    def search_entry(self, key: str) -> dict[str, Any] | None:
        p = self._search_path(key)
        return _loads(p) if self._exists(p) else None

    # cards --------------------------------------------------------------
    def put_card(self, run_id: str, card: dict[str, Any]) -> str:
        card_id = str(card.get("card_id") or "")
        if not card_id:
            raise ValueError("card has no card_id")
        self._write(self._card_path(run_id, card_id), _dumps(card))
        return card_id

    def get_card(self, run_id: str, card_id: str) -> dict[str, Any] | None:
        p = self._card_path(run_id, card_id)
        return _loads(p) if self._exists(p) else None

    def list_cards(self, run_id: str) -> list[dict[str, Any]]:
        d = self.root / "cards" / _safe(run_id)
        if not d.is_dir():
            return []
        out = []
        for p in sorted(d.glob("*.json")):
            if p.name.startswith("."):
                continue
            try:
                out.append(_loads(p))
            except ValueError:
                log.warning("unreadable card %s", p)
        return out

    def card_ids(self, run_id: str) -> list[str]:
        return [str(c.get("card_id")) for c in self.list_cards(run_id)]

    # run state ----------------------------------------------------------
    def lock(self, run_id: str) -> threading.Lock:
        """The in-process lock for this run's state (one per run_id)."""
        with self._run_locks_guard:
            lk = self._run_locks.get(run_id)
            if lk is None:
                lk = threading.Lock()
                self._run_locks[run_id] = lk
            return lk

    def run_state(self, run_id: str) -> dict[str, Any]:
        """The run's state; a fresh default when none is saved."""
        p = self._run_state_path(run_id)
        if not self._exists(p):
            return default_run_state()
        try:
            state = _loads(p)
        except ValueError:
            return default_run_state()
        base = default_run_state()
        base.update(state)
        return base

    def save_run_state(self, run_id: str, state: dict[str, Any]) -> None:
        now = self._clock()
        state = dict(state)
        if not state.get("created_at"):
            state["created_at"] = _iso(now)
        state["updated_at"] = _iso(now)
        self._write(self._run_state_path(run_id), _dumps(state))

    def update_run_state(self, run_id: str, fn: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
        """Read-modify-write under the run's lock. `fn(state)` mutates the
        dict in place (or returns a replacement); the result is saved and
        returned."""
        with self.lock(run_id):
            state = self.run_state(run_id)
            ret = fn(state)
            if isinstance(ret, dict):
                state = ret
            self.save_run_state(run_id, state)
            return state

    # health -------------------------------------------------------------
    def append_health(self, record: dict[str, Any]) -> None:
        """Append one JSON line (with `at`) to `health/source_health.jsonl`.
        The file is append-only; a line is small enough to be one write."""
        rec = dict(record)
        rec.setdefault("at", _iso(self._clock()))
        p = self._health_path
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
        self._mirror(p)

    def health_records(self, limit: int | None = None) -> list[dict[str, Any]]:
        p = self._health_path
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
        if limit is not None:
            lines = lines[-limit:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out


_STORE: Store | None = None


def store() -> Store:
    """The process-wide store rooted at `settings.data_dir`."""
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE


def reset_store() -> None:
    """Tests: forget the process-wide store (settings may have changed)."""
    global _STORE
    _STORE = None
