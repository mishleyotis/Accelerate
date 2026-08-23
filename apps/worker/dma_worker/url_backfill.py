"""Give a stored evidence row back the URL its package always carried.

WHY THIS EXISTS. Reported 2026-08-23 by opening a drawer: "no URLs on the
T. Rowe evidence". Measured over the complete served set, 757 of 894 items
carry none, against 153 of 154 for the Baxter exemplar.

None of them were ever researched wrong. The package states them:

    03_scoring_workbook/…Evidence_Master   757 rows, 753 with a URL  (99%)
    01_evidence/evidence_index.json        752 rows, 748 with a URL  (99%)

and the worker's own `parse_evidence_master` reads 753 of them correctly
TODAY. The run simply predates the fix: T. Rowe was ingested 2026-08-10 and
the ingest only began writing `source_url` on 2026-08-18 (RC1, 0052bb0).
Every run scanned before that date holds the same hole, and re-scanning is
not available to them — the promoted run is the one serving, and a fresh
scan makes a new run rather than mending this one.

So this is a BACKFILL, deliberately the narrowest one that can work:

  * it only ever fills a NULL. A stored URL is never replaced, because a
    stored URL may have been repaired by hand and this file does not know
    better than a human who looked.
  * it joins on the package-local id, which is exact rather than fuzzy:
    `E-002` in the workbook became `E-TROW-002` in the store, and 751 of
    752 T. Rowe rows still round-trip through `local_id_of_stored` — the
    mint run backwards. Matching on source NAME instead would recover 712
    and quietly mismatch some of them, so it is not used.
  * it never invents. A row the package cannot answer stays NULL and is
    counted, so "we could not fill 6" is a number on the report rather
    than a silence.

What it is NOT: an enrichment pass. Nothing here fetches, searches or
guesses. If the package does not hold the URL, the producer's own ladder
(package -> corpus -> connectors) is where it gets found, and gate M is
what stops the run promoting without it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .evidence_ids import local_id, local_id_of_stored, stored_url

URL_RE = re.compile(r"^https?://", re.I)

#: Where a package states a URL, richest first. The workbook register is the
#: authority the ingest already reads; the JSON index is its twin and carries
#: four URLs the register does not.
_JSON_STORES = ("01_evidence/evidence_index.json", "01_evidence/ledger.jsonl")
_ID_KEYS = ("evidence_id", "e_id", "id")
_URL_KEYS = ("url", "source_url", "url_or_citation", "link")


def _first_url(row: dict) -> str | None:
    for k in _URL_KEYS:
        v = str(row.get(k) or "").strip()
        if URL_RE.match(v):
            return v
    return None


def urls_from_package(package_dir) -> dict:
    """{package-local id -> url} from every JSON evidence store present.

    Keyed by `local_id`, the same normaliser the lander used to mint, so the
    join is the mint run backwards rather than a second guess at it.
    """
    root = Path(package_dir)
    out: dict = {}
    for rel in _JSON_STORES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix == ".jsonl":
                rows = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
            else:
                doc = json.loads(raw)
                rows = doc if isinstance(doc, list) else next(
                    (v for v in doc.values()
                     if isinstance(v, list) and v and isinstance(v[0], dict)),
                    [])
        except Exception:                                       # noqa: BLE001
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = next((str(row[k]) for k in _ID_KEYS if row.get(k)), None)
            url = _first_url(row)
            if not rid or not url:
                continue
            key = local_id(rid)
            # First store wins: the list is ordered richest-first on purpose,
            # and a later store must not quietly overwrite a better answer.
            if key and key not in out:
                out[key] = url
    return out


def plan(stored_rows: list, package_urls: dict) -> dict:
    """What would be filled, without touching anything.

    `stored_rows` are {e_id, source_url} as the store holds them. Returns
    the fills, plus the rows nothing could answer — both counted, because a
    backfill that reports only its successes is how a gap becomes invisible.
    """
    fills, unanswered, already = [], [], 0
    for row in stored_rows:
        eid = row.get("e_id")
        if not eid:
            continue
        if URL_RE.match(str(row.get("source_url") or "").strip()):
            already += 1
            continue
        # STORED ids come in (`E-TROW-002`); the package states LOCAL ones
        # (`E-002`). `local_id_of_stored` is the mint run backwards and is
        # the only key that joins them — `local_id` would return None for
        # every stored id and the backfill would silently fill nothing.
        url = package_urls.get(local_id_of_stored(eid))
        if url:
            fills.append({"e_id": eid, "source_url": stored_url(url)})
        else:
            unanswered.append(eid)
    return {"fills": fills, "unanswered": unanswered,
            "already_had_one": already, "considered": len(stored_rows)}


def apply(cur, fills: list) -> int:
    """Fill NULLs only. The WHERE clause is the safety, not the caller."""
    n = 0
    for f in fills:
        cur.execute(
            """UPDATE evidence_index SET source_url = %s
                WHERE e_id = %s AND (source_url IS NULL OR source_url = '')""",
            (f["source_url"], f["e_id"]))
        n += cur.rowcount or 0
    return n
