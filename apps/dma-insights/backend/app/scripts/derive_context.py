"""Context/timeline derive (pipeline stage; Part 8.2 NLP re-derivation).

Two responsibilities:

1. **Timeline re-derivation (default)** — the 2026-06 audit measured the
   ingested `timeline_events` at 88% defaulted dates, 51% garbage titles,
   negation misses and 66 duplicates. This stage re-runs the rebuilt NLP
   event pipeline (`facts_extractor.extract_timeline_events` — event gate,
   negated-absence suppression, real event dates + `date_precision`,
   titlecraft titles with the verbatim claim in `body`, native polarity
   `signal`, `subcap_ids`/`evidence_e_ids`, cross-source dedup) over each
   entity's package evidence (`01_evidence/evidence_index.json`, the only
   facts carrier), falling back to the Client Profile DOCX "Digital
   Evolution Timeline" when no dated facts produced events (same ladder as
   ingest), and REPLACES the entity's timeline rows. Deterministic and
   idempotent: same corpus in → same rows out.

2. **Fill-if-empty** — entities whose package carries no timeline-bearing
   rows at all get a small set of **grounded** milestones (never
   fabricated): the founding year from `parsed_facts.founded`
   (`date_precision='year'`) and the DMA assessment itself on its real
   assessment date (`date_precision='day'`); both `signal='neutral'`.

Pure SQL + the shared NLP platform; no LLM, no fabrication.

Usage:
  DATABASE_URL=... [DMA_SEED_CORPUS_DIR=...] \
      python -m app.scripts.derive_context [--fill-only]
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker

_CORPUS = (os.environ.get("DMA_CONTEXT_CORPUS_DIR")
           or os.environ.get("DMA_SEED_CORPUS_DIR")
           or "tests/fixtures/dma_packages_batches")

_CANON = ("01_evidence", "00_entity_profile", "01_Research", "07_governance",
          "04_reports")

# Part 8.2/8.6 residual guards (2026-07-02).
# Negated-absence titles that slip past the extractor's suppressor must never
# persist as timeline dots (mirrors qa_coverage_contract._TITLE_NEG_RE so the
# context_negation_title_pct counter reaches 0).
_NEG_TITLE_RE = re.compile(
    r"\bNEGATIVE SEARCH\b|\bNO\s+(?:formal|evidence|M&A|actions?|enforcement)\b|"
    r"\bNOT\s+named\b|^no\b",
    re.IGNORECASE,
)
# kinds whose events carry a discoverable evidence anchor (founding / DMA-
# assessment milestones are legitimately evidence-free and are left alone).
_ATTACH_KINDS = ("acquisition", "leadership", "regulatory", "regulatory_standing")
_TOKEN_STOP = frozenset(
    "the a an of and for to in on at with from bank corp inc llc lp na company "
    "co group holdings financial services credit union trust completed announced "
    "acquired acquisition merger merges new named launches launched".split())
_WORD_RE = re.compile(r"[a-z]{4,}")


def _content_tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _TOKEN_STOP}


def _is_negation_title(title: str) -> bool:
    return bool(title) and bool(_NEG_TITLE_RE.search(title.strip()))


def _norm_name(s: str) -> str:
    """Folder/entity name → comparable token string (lowercased alnum)."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _package_index() -> dict[str, str]:
    """{normalized client-dir name → package root} over the corpus."""
    idx: dict[str, str] = {}
    if not os.path.isdir(_CORPUS):
        return idx
    for batch in sorted(glob.glob(os.path.join(_CORPUS, "*"))):
        if not os.path.isdir(batch):
            continue
        for client in sorted(glob.glob(os.path.join(batch, "*"))):
            if not os.path.isdir(client):
                continue
            root = client
            for sub in [client, *[d for d in glob.glob(os.path.join(client, "*"))
                                  if os.path.isdir(d)]]:
                if any(os.path.isdir(os.path.join(sub, c)) for c in _CANON):
                    root = sub
                    break
            idx.setdefault(_norm_name(os.path.basename(client)), root)
    return idx


def _match_root(pkg_idx: dict[str, str], name: str, dfid: str | None) -> str | None:
    key = _norm_name((dfid or "").split("local:", 1)[-1] if "local:" in (dfid or "")
                     else name)
    root = pkg_idx.get(key)
    if root:
        return root
    kt = set(key.split())
    for k, v in pkg_idx.items():
        if kt and (kt <= set(k.split()) or set(k.split()) <= kt):
            return v
    return None


def _load_evidence_rows(root: str) -> list:
    """EvidenceRow list from `01_evidence/evidence_index.json` (facts carrier).

    Mirrors the orchestrator's JSON branch — tolerant of tier drift and
    malformed facts. Returns [] when the package ships no JSON index (the
    CSV variants carry no `facts[]`, so there is nothing to re-derive from).
    """
    from app.schemas.package import EvidenceRow

    p = Path(root) / "01_evidence" / "evidence_index.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    rows: list = []
    for raw in d.get("items", []) if isinstance(d, dict) else []:
        if not isinstance(raw, dict):
            continue
        t = re.match(r"\s*(\d+)", str(raw.get("tier", "5")).strip().lstrip("Tt"))
        try:
            rows.append(EvidenceRow(
                e_id=str(raw.get("evidence_id") or raw.get("e_id") or "E?")[:16],
                source_name=str(raw.get("source_name") or "(unnamed)"),
                source_url=raw.get("url") or raw.get("source_url"),
                tier=max(1, min(8, int(t.group(1)))) if t else 5,
                publish_date=str(raw.get("publish_date") or "") or None,
                excerpt=str(raw.get("excerpt") or ""),
                facts=raw.get("facts") if isinstance(raw.get("facts"), list) else [],
            ))
        except Exception:
            continue
    return rows


def _docx_timeline_events(root: str) -> tuple[list, list]:
    """(timeline_events, acquisition_events) from the Client Profile DOCX."""
    from app.services.parsers.client_profile import parse_client_profile_path

    reports = Path(root) / "04_reports"
    if not reports.is_dir():
        return [], []
    cands = [
        f for f in sorted(reports.glob("*.docx"))
        if re.search(r"client.?profile|profile.?research", f.name, re.IGNORECASE)
    ]
    for f in cands:
        try:
            res = parse_client_profile_path(f)
        except Exception:
            continue
        if res.timeline_events or res.acquisition_events:
            return list(res.timeline_events), list(res.acquisition_events)
    return [], []


async def _replace_events(session, eid: str, events: list) -> None:
    await session.execute(
        text("DELETE FROM timeline_events WHERE entity_id = CAST(:eid AS uuid)"),
        {"eid": eid},
    )
    # Citation-validity floor (2026-07-11 parity audit; mirrors
    # section_routing + apply_startup_data_fixes): DOCX-parsed events cite
    # prose E-IDs that may have no evidence_index row — a dangling id is a
    # dead drawer chip, and the pack fixer prunes it from the baked pack, so
    # the DB row must not carry it either or qa_pack_parity diffs pack vs
    # live. Empty evidence set (hollow package) disables the filter — the
    # fixer's exact guard.
    known = {
        r.e_id for r in (await session.execute(text(
            "SELECT DISTINCT ei.e_id FROM evidence_index ei "
            "JOIN runs r ON r.id = ei.run_id "
            "WHERE r.entity_id = CAST(:eid AS uuid)"
        ), {"eid": eid})).all()
    }
    for ev in events:
        await session.execute(text(
            """
            INSERT INTO timeline_events
                (entity_id, event_date, kind, title, body, source_url, e_id,
                 signal, date_precision, evidence_e_ids, subcap_ids, created_at)
            VALUES (CAST(:eid AS uuid), :d, :k, :t, :b, :url, :e,
                    :sig, :prec, :eids, :sids, NOW())
            """
        ), {
            "eid": eid, "d": ev.event_date, "k": ev.kind[:32],
            "t": ev.title[:300], "b": ev.body,
            "url": getattr(ev, "source_url", None),
            "e": (ev.e_id or "")[:16] or None,
            "sig": (getattr(ev, "signal", None) or "")[:10] or None,
            "prec": (getattr(ev, "date_precision", None) or "")[:20] or None,
            "eids": [e for e in (getattr(ev, "evidence_e_ids", None) or [])
                     if not known or e in known],
            "sids": list(getattr(ev, "subcap_ids", None) or []),
        })


async def _attach_timeline_evidence(session, eid: str, events: list) -> int:
    """Attach ``evidence_e_ids`` to attachment-eligible events that carry no
    anchor, by matching each event's title/body against the entity's own
    ``evidence_index`` excerpts. Grounded SEMANTICALLY (2026-07-09 NLP
    hardening): the MiniLM bi-encoder ranks the excerpts and an event only
    binds its best excerpt at relevance ≥ 0.30 — raw token counting bound
    ~16% of events to excerpts they don't actually describe (shared generic
    tokens like the bank's name). Degrades to the ≥2-content-token overlap
    match when the tier is cold. Mutates the candidates in place; returns
    the number attached."""
    need = [ev for ev in events
            if ev.kind in _ATTACH_KINDS
            and not (ev.e_id or getattr(ev, "evidence_e_ids", None))]
    if not need:
        return 0
    rows = (await session.execute(text(
        """
        SELECT e_id, excerpt FROM evidence_index
        WHERE entity_id = CAST(:eid AS uuid)
          AND e_id IS NOT NULL AND length(COALESCE(excerpt, '')) > 40
        LIMIT 400
        """
    ), {"eid": eid})).all()
    if not rows:
        return 0
    attached = 0
    from app.services.nlp.semantic import SemanticIndex, model_available
    if model_available():
        idx = SemanticIndex()
        idx.fit([(r.e_id, r.excerpt) for r in rows])
        for ev in need:
            q = f"{ev.title} {ev.body or ''}".strip()
            if len(q) < 12:
                continue
            hits = idx.top_k(q, 1, min_score=0.30)
            if hits:
                ev.evidence_e_ids = [hits[0][0]]
                attached += 1
        return attached
    # cold tier — the original ≥2-shared-content-token match.
    ev_toks = [(r.e_id, _content_tokens(r.excerpt)) for r in rows]
    for ev in need:
        q = _content_tokens(f"{ev.title} {ev.body or ''}")
        if len(q) < 2:
            continue
        best_eid, best_n = None, 1
        for e_id, toks in ev_toks:
            n = len(q & toks)
            if n > best_n:
                best_eid, best_n = e_id, n
        if best_eid:
            ev.evidence_e_ids = [best_eid]
            attached += 1
    return attached


async def _apply_issue_register_polarity(session, eid: str, events: list) -> int:
    """Cross-reference the client's OPEN issue register (operator mandate
    2026-07-06: "check the issue register for each client").

    A NEUTRAL timeline event whose subcaps fall under a high/critical OPEN
    *client* issue is a step taken inside a known problem area, so it is
    reclassified ``signal='negative'`` — this is what surfaces the client's
    real trouble spots as red dots on the digital-evolution timeline. Only
    ``kind='client'`` issues count: the ``assessment_qa`` rows are internal
    report-QA notes ("citations below target", "weights not summing to 1.0"),
    never the client's own difficulty. Explicit positives/negatives are left
    untouched (a launch in a weak area stays a positive step). Subcap match is
    dotted-prefix aware so a category-level issue (``P4C4``) governs its
    subcaps (``P4C4.1.2``). Mutates events in place; returns the count flipped.
    """
    neutral = [ev for ev in events
               if (getattr(ev, "signal", None) or "neutral") == "neutral"
               and getattr(ev, "subcap_ids", None)]
    if not neutral:
        return 0
    rows = (await session.execute(text(
        """
        SELECT DISTINCT unnest(linked_subcap_ids) AS code
        FROM issue_register
        WHERE entity_id = CAST(:eid AS uuid)
          AND kind = 'client'
          AND COALESCE(status, 'OPEN') = 'OPEN'
          AND severity IN ('high', 'critical')
          AND linked_subcap_ids IS NOT NULL
        """
    ), {"eid": eid})).all()
    codes = {(r.code or "").strip() for r in rows if (r.code or "").strip()}
    if not codes:
        return 0

    def _under_issue(sc: str) -> bool:
        sc = (sc or "").strip()
        return any(
            sc == c or sc.startswith(c + ".") or c.startswith(sc + ".")
            for c in codes
        )

    flipped = 0
    for ev in neutral:
        if any(_under_issue(sc) for sc in (ev.subcap_ids or [])):
            ev.signal = "negative"
            flipped += 1
    return flipped


async def _rederive(session) -> tuple[int, int]:
    """NLP re-derivation over the corpus → (entities_rederived, events).

    Also persists ONE ``kind='regulatory_standing'`` row per entity whose
    evidence records a verified regulatory absence ("NEGATIVE SEARCH: no
    formal enforcement orders…"): the timeline suppresses those claims
    (Part 8.2 step 3), and the context router lifts this row OUT of the
    timeline into the D5 regulatory block's clean-standing signal. The
    negated absences live in evidence ``facts[]``, which are not persisted
    to ``evidence_index`` — ``timeline_events`` is this stage's own table,
    so the write stays wave-safe.
    """
    from datetime import date as _date

    from app.schemas.package import TimelineEventCandidate
    from app.services.parsers.facts_extractor import (
        dedup_events,
        extract_regulatory_standing,
        extract_timeline_events,
    )

    pkg_idx = _package_index()
    if not pkg_idx:
        print(f"# derive_context: corpus dir not found ({_CORPUS}) — "
              "re-derivation skipped, fill-if-empty only", flush=True)
        return 0, 0
    rows = (await session.execute(text(
        """
        SELECT e.id::text AS eid, e.display_id, e.name,
               e.drive_folder_id AS dfid
        FROM entities e
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()
    rederived = inserted = 0
    for ent in rows:
        root = _match_root(pkg_idx, ent.name, ent.dfid)
        if not root:
            continue
        evidence = _load_evidence_rows(root)
        events = extract_timeline_events(evidence) if evidence else []
        docx_events, docx_acqs = _docx_timeline_events(root)
        if not events and docx_events:
            events = docx_events
        # The report's dedicated Acquisition History table is authoritative
        # for kind='acquisition' — merge (near-dup aware) like ingest does.
        if docx_acqs:
            events = dedup_events(events + docx_acqs)
        # Drop negated-absence titles that slipped past the extractor's
        # suppressor ("No CFPB enforcement actions found …") — they are not
        # timeline dots; the clean-standing signal is carried separately by the
        # regulatory_standing row appended below.
        events = [ev for ev in events if not _is_negation_title(ev.title)]
        standing = extract_regulatory_standing(evidence) if evidence else None
        if not events and standing is None:
            continue
        events.sort(key=lambda c: c.event_date, reverse=True)
        events = events[:60]
        # Broaden evidence attachment: acquisition/leadership/regulatory events
        # that carry no e_id get one from the entity's own evidence when a row
        # clearly discusses the same event (grounded, ≥2 shared content tokens).
        await _attach_timeline_evidence(session, ent.eid, events)
        # Operator mandate 2026-07-06: check each client's issue register so
        # events inside a known high/critical problem area classify negative.
        await _apply_issue_register_polarity(session, ent.eid, events)
        if standing is not None:
            as_of = standing.get("as_of")
            events.append(TimelineEventCandidate(
                event_date=(_date.fromisoformat(as_of) if as_of
                            else _date.today()),
                kind="regulatory_standing",
                title=str(standing["label"])[:300],
                body=str(standing["note"]) or None,
                e_id=standing.get("e_id"),
                signal="positive",
                date_precision="publish_fallback",
                evidence_e_ids=[standing["e_id"]] if standing.get("e_id") else [],
            ))
        await _replace_events(session, ent.eid, events)
        rederived += 1
        inserted += len(events)
    return rederived, inserted


async def _fill_if_empty(session) -> tuple[int, int]:
    """Grounded milestones for entities with ZERO timeline events."""
    rows = (await session.execute(text(
        """
        SELECT e.id::text AS eid, e.display_id, e.name,
               COALESCE(r.assessment_date, r.started_at::date) AS asm_date,
               ar.overall_score,
               f.parsed_facts->>'founded' AS founded
        FROM entities e
        JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
        LEFT JOIN firmographics f ON f.entity_id = e.id
        LEFT JOIN LATERAL (
            SELECT ROUND(AVG(s.score)::numeric, 2) AS overall_score
            FROM subcap_scores s WHERE s.run_id = r.id AND s.score IS NOT NULL
        ) ar ON TRUE
        WHERE e.status = 'ACTIVE'
          AND NOT EXISTS (SELECT 1 FROM timeline_events te WHERE te.entity_id = e.id)
        ORDER BY e.display_id
        """
    ))).all()

    filled = inserted = 0
    for r in rows:
        # (date, kind, title, body, precision) — signal is always neutral:
        # these are grounded milestones, not polarity-classified claims.
        events: list[tuple[date, str, str, str, str]] = []
        if r.founded and r.founded.isdigit() and 1700 <= int(r.founded) <= 2030:
            events.append((
                date(int(r.founded), 1, 1), "milestone", "Founded",
                f"{r.name} was established in {int(r.founded)}.", "year",
            ))
        if r.asm_date is not None:
            score_txt = (f" Overall digital maturity scored {r.overall_score}/5.0."
                         if r.overall_score is not None else "")
            events.append((
                r.asm_date, "milestone",
                "DMA digital maturity assessment completed",
                f"Zennify completed a Digital Maturity Assessment of {r.name}."
                f"{score_txt}",
                "day",
            ))
        if not events:
            continue
        for ev_date, kind, title, body, precision in events:
            await session.execute(text(
                """
                INSERT INTO timeline_events
                    (entity_id, event_date, kind, title, body,
                     signal, date_precision, created_at)
                VALUES (CAST(:eid AS uuid), :d, :k, :t, :b,
                        'neutral', :prec, NOW())
                """
            ), {"eid": r.eid, "d": ev_date, "k": kind, "t": title, "b": body,
                "prec": precision})
            inserted += 1
        filled += 1
    return filled, inserted


async def _fill_regulatory(session) -> int:
    """Part 8.6 license/jurisdiction fill.

    Computes ``license_type`` + ``jurisdictions`` from the entity's own
    firmographics (prose patterns + the grounded regulator-class fallback) and
    PERSISTS them into ``firmographics.parsed_facts`` as structured keys — the
    context router is out of this stage's write scope, so persisting is what
    lets its unchanged ``regulatory_view`` read them back (25 → ~89 clients
    carry both). Honest-null (no write) when neither prose nor regulator
    determines the field. Idempotent: only fills a key that is still absent.
    """
    from app.services.context_extras import financials_view, regulatory_view

    rows = (await session.execute(text(
        """
        SELECT e.id::text AS eid, f.primary_regulator, f.narrative_md,
               f.parsed_facts, f.financial_highlights
        FROM firmographics f JOIN entities e ON e.id = f.entity_id
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()
    filled = 0
    for r in rows:
        pf = dict(r.parsed_facts or {})
        fin = financials_view(r.financial_highlights)
        reg = regulatory_view(pf, r.narrative_md, (fin or {}).get("lines"),
                              primary_regulator=r.primary_regulator)
        updates: dict[str, object] = {}
        if reg.get("license_type") and not _present_key(pf, ("license_type",
                "license", "charter_type", "charter")):
            updates["license_type"] = reg["license_type"]
        if reg.get("jurisdictions") and not _present_key(pf, ("jurisdictions",
                "operating_states", "footprint", "geography", "states")):
            updates["jurisdictions"] = reg["jurisdictions"]
        if not updates:
            continue
        pf.update(updates)
        await session.execute(text(
            "UPDATE firmographics SET parsed_facts = CAST(:pf AS jsonb) "
            "WHERE entity_id = CAST(:eid AS uuid)"
        ), {"pf": json.dumps(pf), "eid": r.eid})
        filled += 1
    return filled


async def _fill_acquisition_count(session) -> int:
    """Persist the acquisitions COUNT into ``firmographics.parsed_facts`` so the
    overview firmographics "Acquisitions" row renders a number (0 when none) —
    never a bare true/false (2026-07-06 operator report). Uses the SAME frame
    validator the D5 context router uses (`acquisitions_from_timeline`), so the
    overview count and the context AcquisitionsCard can never disagree. A
    Gemini-enriched acquisitions LIST in parsed_facts always wins. Writes 0 for
    entities with no verifiable acquisition frame. Returns rows updated."""
    from collections import defaultdict
    from types import SimpleNamespace

    from app.services.context_extras import acquisitions_from_timeline

    ent_rows = (await session.execute(text(
        "SELECT e.id::text AS eid, e.name FROM entities e "
        "JOIN firmographics f ON f.entity_id = e.id WHERE e.status = 'ACTIVE'"
    ))).all()
    names = {r.eid: r.name for r in ent_rows}
    ev: dict[str, list] = defaultdict(list)
    for r in (await session.execute(text(
        """
        SELECT e.id::text AS eid, te.id::text AS tid, te.event_date, te.kind,
               te.title, te.body, te.source_url, te.e_id, te.evidence_e_ids
        FROM entities e JOIN timeline_events te ON te.entity_id = e.id
        WHERE e.status = 'ACTIVE' AND lower(COALESCE(te.kind, '')) = 'acquisition'
        """
    ))).all():
        ev[r.eid].append(SimpleNamespace(
            id=r.tid, event_date=r.event_date, kind=r.kind, title=r.title,
            body=r.body, source_url=r.source_url, e_id=r.e_id,
            evidence_e_ids=list(r.evidence_e_ids or [])))
    filled = 0
    for eid, name in names.items():
        try:
            count = len(acquisitions_from_timeline(ev.get(eid, []), entity_name=name))
        except Exception:
            count = 0
        pf_row = (await session.execute(text(
            "SELECT parsed_facts FROM firmographics WHERE entity_id = CAST(:eid AS uuid)"
        ), {"eid": eid})).first()
        pf = dict((pf_row[0] if pf_row and pf_row[0] else {}) or {})
        if isinstance(pf.get("acquisitions"), list) and pf["acquisitions"]:
            continue  # Gemini-enriched structured list wins
        if pf.get("acquisitions") == count:
            continue
        pf["acquisitions"] = count
        await session.execute(text(
            "UPDATE firmographics SET parsed_facts = CAST(:pf AS jsonb) "
            "WHERE entity_id = CAST(:eid AS uuid)"
        ), {"pf": json.dumps(pf), "eid": eid})
        filled += 1
    return filled


def _present_key(pf: dict, keys: tuple[str, ...]) -> bool:
    for k in keys:
        v = pf.get(k)
        if (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v):
            return True
    return False


def _source_tenure_map(root: str | None) -> dict[str, int]:
    """{normalized-name → tenure_months} mined from the package's leadership
    registers (A7/leadership CSVs + entity_profile ``leadership_snapshot``).
    Verbatim appointment dates only — never fabricated."""
    from app.services.context_extras import tenure_months_from_text

    out: dict[str, int] = {}
    if not root:
        return out
    for f in glob.glob(os.path.join(root, "**", "entity_profile.json"), recursive=True):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        snap = (data or {}).get("leadership_snapshot") or {}
        if not isinstance(snap, dict):
            continue
        for person in snap.values():
            if not isinstance(person, dict) or not person.get("name"):
                continue
            blob = " ".join(str(person.get(k) or "") for k in
                            ("tenure_started_role", "tenure", "title", "background"))
            tm = tenure_months_from_text(blob)
            if tm is not None:
                out.setdefault(_norm_name(person["name"]), tm)
    import csv as _csv
    import io as _io
    for f in glob.glob(os.path.join(root, "**", "*.csv"), recursive=True):
        b = os.path.basename(f).lower()
        if not ("leader" in b or "executive" in b or "entity_profile" in b):
            continue
        try:
            reader = _csv.DictReader(_io.StringIO(
                Path(f).read_text(encoding="utf-8", errors="replace")))
            rows = list(reader)
        except (OSError, UnicodeError, _csv.Error):
            continue
        for raw in rows:
            nm = {(k or "").strip().lower(): (v or "").strip()
                  for k, v in raw.items() if k}
            name = next((nm[k] for k in ("name", "full name", "full_name",
                                         "executive") if nm.get(k)), "")
            if not name:
                continue
            blob = " ".join(v for k, v in nm.items() if any(
                t in k for t in ("tenure", "start", "since", "appoint", "title",
                                 "role", "background", "date")))
            tm = tenure_months_from_text(blob)
            if tm is not None:
                out.setdefault(_norm_name(name), tm)
    return out


async def _fill_tenure(session) -> tuple[int, int]:
    """Part 8.6 leadership tenure fill.

    Fills ``tenure_months`` on ``firmographics.leadership`` rows from (1) the
    row's own title/background appointment phrasing and (2) the package's
    leadership registers, matched by name. The corpus records an appointment
    date for only ~13% of leaders (8/95 entities ship a register) — the rest
    stay honest-null. Lifts the served leadership_tenure counter from 0.4% to
    that ~13% ceiling. Returns (entities_touched, leaders_filled).
    """
    from app.services.context_extras import tenure_months_from_text

    pkg_idx = _package_index()
    rows = (await session.execute(text(
        """
        SELECT e.id::text AS eid, e.name, e.drive_folder_id AS dfid, f.leadership
        FROM firmographics f JOIN entities e ON e.id = f.entity_id
        WHERE e.status = 'ACTIVE'
        ORDER BY e.display_id
        """
    ))).all()
    ent_touched = leaders_filled = 0
    for r in rows:
        roster = r.leadership
        if isinstance(roster, str):
            try:
                roster = json.loads(roster or "[]")
            except json.JSONDecodeError:
                roster = []
        if not isinstance(roster, list) or not roster:
            continue
        root = _match_root(pkg_idx, r.name, r.dfid)
        src = _source_tenure_map(root)
        changed = False
        for p in roster:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            if p.get("tenure_months") is not None:
                continue
            own = tenure_months_from_text(" ".join(
                str(p.get(k) or "") for k in ("tenure", "title", "background")))
            tm = own if own is not None else src.get(_norm_name(p["name"]))
            if tm is not None:
                p["tenure_months"] = tm
                changed = True
                leaders_filled += 1
        if changed:
            await session.execute(text(
                "UPDATE firmographics SET leadership = CAST(:l AS jsonb) "
                "WHERE entity_id = CAST(:eid AS uuid)"
            ), {"l": json.dumps(roster), "eid": r.eid})
            ent_touched += 1
    return ent_touched, leaders_filled


async def _upgrade_fallback_dates(session) -> tuple[int, int]:
    """Upgrade ``publish_fallback`` event dates from real textual dates.

    The ingest extractor resolves dates over the fact slice it saw; the
    persisted title+body — and the event's own cited evidence excerpts —
    often carry the explicit date it missed ("June 2025 Crossfuze
    webinar"). Re-run the same ``resolve_event_date`` ladder over both,
    in that order, and upgrade date + precision on a hit. Events with no
    textual date anywhere keep the publish fallback: that publish date is
    the best REAL anchor, and inventing sharper precision would be a
    fabrication. Idempotent (upgraded rows leave the fallback set).
    Returns (upgraded, honestly_kept)."""
    from app.services.nlp.dates import resolve_event_date
    rows = (await session.execute(text(
        """
        SELECT te.id, te.title, COALESCE(te.body, '') AS b,
               COALESCE(string_agg(ev.excerpt, ' '), '') AS ex
        FROM timeline_events te
        LEFT JOIN evidence_index ev
          ON ev.entity_id = te.entity_id
         AND (ev.e_id = te.e_id
              OR ev.e_id = ANY(COALESCE(te.evidence_e_ids, ARRAY[]::text[])))
        WHERE te.date_precision = 'publish_fallback'
        GROUP BY te.id, te.title, te.body
        """))).all()
    upgraded = 0
    for r in rows:
        d, prec = resolve_event_date(f"{r.title}. {r.b}")
        if prec in ("none", "publish_fallback"):
            d, prec = resolve_event_date(r.ex or "")
        if prec in ("none", "publish_fallback") or d is None:
            ent = (await session.execute(text(
                "SELECT display_id FROM entities WHERE id = "
                "(SELECT entity_id FROM timeline_events WHERE id = :i)"),
                {"i": r.id})).scalar()
            if ent:
                from app.services.research_queue import file_clarification
                file_clarification(
                    entity=str(ent), surface="timeline", ground="G2",
                    question=(f"Real event date needed for timeline event "
                              f"'{str(r.title)[:80]}' — no textual date in "
                              f"its prose or cited evidence"),
                    # body/excerpt head gives the research tier query
                    # terms when the title alone is a stub
                    context=(f"{r.b} {r.ex}".strip()[:300] or None),
                    filed_by="derive_context")
            continue
        await session.execute(text(
            "UPDATE timeline_events SET event_date = :d, date_precision = :p "
            "WHERE id = :i"), {"d": d, "p": prec, "i": r.id})
        upgraded += 1
    return upgraded, len(rows) - upgraded


async def _amain(argv: list[str]) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    fill_only = "--fill-only" in argv
    sm = get_sessionmaker()
    rederived = re_events = filled = fill_events = 0
    # Bank the timeline re-derivation + grounded fill-if-empty FIRST, in their
    # own transaction, so a downstream secondary-fill failure can never roll
    # them back (2026-07-06: a single client's None financial series was
    # aborting the whole derive → empty context page for most clients).
    async with sm() as session:
        if not fill_only:
            rederived, re_events = await _rederive(session)
        filled, fill_events = await _fill_if_empty(session)
        await session.commit()

    async def _guarded(label: str, fn):
        try:
            async with sm() as session:
                res = await fn(session)
                await session.commit()
                return res
        except Exception as exc:  # one client's data must not nuke the derive
            print(f"# derive_context: {label} fill skipped "
                  f"({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
            return None

    reg_filled = await _guarded("regulatory", _fill_regulatory) or 0
    tenure_ents, tenure_leaders = (await _guarded("tenure", _fill_tenure)
                                   or (0, 0))
    acq_filled = await _guarded("acq_count", _fill_acquisition_count) or 0
    dates_up, dates_kept = (await _guarded("fallback_dates",
                                           _upgrade_fallback_dates) or (0, 0))

    print(f"# derive_context: entities_rederived={rederived} "
          f"events_rederived={re_events} entities_filled={filled} "
          f"events_filled={fill_events} reg_license_juris_filled={reg_filled} "
          f"tenure_entities={tenure_ents} tenure_leaders_filled={tenure_leaders} "
          f"acq_count_filled={acq_filled} "
          f"fallback_dates_upgraded={dates_up} fallback_dates_kept={dates_kept} "
          f"(NLP timeline re-derivation + grounded fill-if-empty + "
          f"license/jurisdiction + leadership tenure + acquisition count)",
          flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
