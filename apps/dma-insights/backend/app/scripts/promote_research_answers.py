"""Promote validated research-worker answers into the evidence store.

Closes the deploy autopilot loop (route_empty_surfaces → research_worker →
HERE): every ``pending_review`` answer whose sources carry substantive
cited excerpts becomes citable ``evidence_index`` rows with crawler
provenance — tier graded by source kind (investor 2 · report 3 · news 4 ·
interview 5 · web 6), content-hashed, subcap-linked when the queue row
named one, ``published_date`` set ONLY under a strict full-date parse.
G2 timeline-date answers additionally repair the named timeline event's
``event_date`` under the same strict gate (full month-day-year in the
excerpt, applied only when the parse also names the event's own words).

Idempotent three ways: a promoted-keys ledger
(``benchmarks/research_promoted.jsonl``) skips processed answers, the
``(run_id, e_id)`` unique key upserts rather than duplicates, and
re-promoting identical content re-derives the same content_hash. Offline
deploy: no answers file → 0 promoted, exit 0. Never fails the chain.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from collections import Counter

from sqlalchemy import text

from app.database import get_sessionmaker
from app.scripts.research_worker import (
    DEFAULT_ANSWERS,
    DEFAULT_QUEUE,
    _source_kind,
    is_nav_debris,
)
from app.services.evidence_dedup import compute_content_hash

_BENCH = os.path.dirname(DEFAULT_ANSWERS)
DEFAULT_PROMOTED = os.path.join(_BENCH, "research_promoted.jsonl")

_TIER_BY_KIND = {"investor": 2, "report": 3, "news": 4, "interview": 5, "web": 6}
_SUBCAP_RE = re.compile(r"^P\d+C\d+")
_MIN_EXCERPT = 60

# Strict full-date parses only — a bare year or "Q3" NEVER sets a date.
_MONTHS = ("january|february|march|april|may|june|july|august|september|"
           "october|november|december")
_DATE_RES = (
    # March 4, 2024 · Sept. 4, 2024 (abbrev with optional dot)
    re.compile(rf"\b({_MONTHS}|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
               rf"\.?\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", re.I),
    # 4 March 2024
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS})\s+(20\d{{2}})\b", re.I),
    # 2024-03-04
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
)
_MONTH_NO = {m: i + 1 for i, m in enumerate(_MONTHS.split("|"))}
_MONTH_NO.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
                  "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})


def parse_strict_date(text_: str) -> dt.date | None:
    """First full calendar date in the text, or None. Full dates only."""
    s = str(text_ or "")
    for i, rx in enumerate(_DATE_RES):
        m = rx.search(s)
        if not m:
            continue
        try:
            if i == 0:
                mo = _MONTH_NO.get(m.group(1).lower().rstrip("."))
                return dt.date(int(m.group(3)), mo, int(m.group(2))) if mo else None
            if i == 1:
                mo = _MONTH_NO.get(m.group(2).lower())
                return dt.date(int(m.group(3)), mo, int(m.group(1))) if mo else None
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None


def _e_id(key: str, url: str) -> str:
    import hashlib
    h = hashlib.sha256(f"{key}|{url}".encode()).hexdigest()[:10]
    return f"WEB-{h}"  # 14 chars — fits VARCHAR(16)


_TL_Q_RE = re.compile(
    r"timeline event '([^']{8,})", re.I)


async def _apply_timeline_date(session, entity_id: str, question: str,
                               date: dt.date, e_id: str) -> bool:
    """Strict-gated repair of the timeline event the G2 names."""
    m = _TL_Q_RE.search(question or "")
    if not m:
        return False
    prefix = m.group(1).rstrip("…. ")[:60]
    row = (await session.execute(text(
        "SELECT id::text tid FROM timeline_events "
        "WHERE entity_id = CAST(:e AS uuid) AND title LIKE :p LIMIT 1"),
        {"e": entity_id, "p": prefix + "%"})).first()
    if row is None:
        return False
    await session.execute(text(
        "UPDATE timeline_events SET event_date = :d, date_precision = 'day', "
        "evidence_e_ids = array_append("
        "  array_remove(COALESCE(evidence_e_ids, '{}'), :eid), :eid) "
        "WHERE id = CAST(:t AS uuid)"),
        {"d": date, "eid": e_id, "t": row.tid})
    return True


def _load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


async def main_async(args) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    answers = _load_jsonl(args.answers)
    queue_by_key = {r.get("key"): r for r in _load_jsonl(args.queue)}
    done = {r.get("key") for r in _load_jsonl(args.promoted)}
    tally: Counter = Counter()
    ledger: list[dict] = []
    sm = get_sessionmaker()
    async with sm() as session:
        # display_id → (entity_id, active run_id), resolved once
        ent = {r.display_id: (r.eid, r.rid) for r in (await session.execute(text(
            "SELECT e.display_id, e.id::text eid, r.id::text rid "
            "FROM entities e JOIN runs r ON r.entity_id = e.id "
            "WHERE r.status='ACTIVE' AND e.status='ACTIVE'"))).all()}
        for a in answers:
            key = a.get("key")
            if not key or key in done:
                tally["skipped_done"] += 1
                continue
            if a.get("status") not in (None, "pending_review"):
                tally["skipped_status"] += 1
                continue
            ids = ent.get(a.get("entity"))
            if not ids:
                tally["no_active_run"] += 1
                continue
            eid_ent, rid = ids
            q = queue_by_key.get(key) or {}
            # Focus-area answers are semester VALIDATION material for the
            # focus contract (deepen), not evidence: objective-shaped web
            # prose is exactly where same-name entities, stale articles
            # and industry think-pieces slip past lexical gates (measured
            # live: an interview-prep page, a 2021 article and a
            # different 'Cathay' all passed). They stay pending_review.
            if (q.get("surface") or "") == "focus_area":
                tally["held_validation"] += 1
                continue
            subcap = (q.get("subcap_id") or "").strip()
            linked = [subcap] if _SUBCAP_RE.match(subcap) else []
            promoted_eids: list[str] = []
            timeline_fixed = False
            for src in (a.get("sources") or [])[:2]:
                url = (src.get("url") or "").strip()
                excerpt = (src.get("excerpt") or "").strip()
                title = (src.get("title") or "").strip()
                if not url or len(excerpt) < _MIN_EXCERPT:
                    tally["thin_source"] += 1
                    continue
                if is_nav_debris(excerpt):
                    tally["debris_source"] += 1
                    continue
                kind = _source_kind(url, title)
                e_id = _e_id(key, url)
                pub = parse_strict_date(excerpt)
                await session.execute(text(
                    """
                    INSERT INTO evidence_index (run_id, entity_id, e_id, tier,
                        excerpt, source_name, source_url, claim_type,
                        published_date, linked_subcap_ids, content_hash,
                        created_at)
                    VALUES (CAST(:rid AS uuid), CAST(:eid AS uuid), :e, :t,
                        :exc, :sn, :su, 'web_research', :pd,
                        CAST(:ls AS varchar(32)[]), :ch, NOW())
                    ON CONFLICT (run_id, e_id) DO UPDATE SET
                        excerpt = EXCLUDED.excerpt,
                        source_name = EXCLUDED.source_name,
                        source_url = EXCLUDED.source_url,
                        published_date = EXCLUDED.published_date,
                        linked_subcap_ids = EXCLUDED.linked_subcap_ids,
                        content_hash = EXCLUDED.content_hash
                    """),
                    {"rid": rid, "eid": eid_ent, "e": e_id,
                     "t": _TIER_BY_KIND.get(kind, 6), "exc": excerpt[:1500],
                     "sn": (title or kind)[:200] or "web research",
                     "su": url[:500], "pd": pub, "ls": linked,
                     "ch": compute_content_hash(
                         source_url=url, claim_type="web_research",
                         excerpt=excerpt)})
                promoted_eids.append(e_id)
                tally[f"tier_{_TIER_BY_KIND.get(kind, 6)}"] += 1
                # G2 timeline-date repair rides the FIRST dated source
                if (not timeline_fixed and pub
                        and a.get("ground") == "G2"
                        and "timeline event" in (a.get("question") or "")):
                    timeline_fixed = await _apply_timeline_date(
                        session, eid_ent, a.get("question") or "", pub, e_id)
                    if timeline_fixed:
                        tally["timeline_dated"] += 1
            if promoted_eids:
                tally["promoted"] += 1
                ledger.append({"key": key, "entity": a.get("entity"),
                               "e_ids": promoted_eids,
                               "timeline_dated": timeline_fixed,
                               "promoted_at":
                                   dt.datetime.now(dt.UTC).isoformat()})
            else:
                tally["no_usable_source"] += 1
        await session.commit()
    if ledger:
        os.makedirs(os.path.dirname(args.promoted), exist_ok=True)
        with open(args.promoted, "a", encoding="utf-8") as fh:
            for row in ledger:
                fh.write(json.dumps(row) + "\n")
    print(f"# promote_research_answers: answers={len(answers)} "
          f"outcomes={dict(tally)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--answers", default=DEFAULT_ANSWERS)
    ap.add_argument("--queue", default=DEFAULT_QUEUE)
    ap.add_argument("--promoted", default=DEFAULT_PROMOTED)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
