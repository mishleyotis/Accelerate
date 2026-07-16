"""Leadership-roster derive — grounded, no empty states (2026-06).

The D1/D5 leadership panel renders the visible empty state "No public leadership
roster on file for this client yet." for 40/94 entities. Their packages DO ship
the roster — in a structured artifact the ingest's client-profile parser missed
(``08_appendices/A2_Leadership_Register.csv``, ``A1_entity_profile.csv``, or a
profile DOCX under a variant name like ``DMA_Client_Profile_Report_*.docx`` /
``DMA_Client_Profile_Research_*.docx`` rather than the canonical
``*_Client_Profile_Research_Report.docx``).

This sweeps each empty entity's package for any leadership-bearing artifact:
  1. JSON dict-of-roles rosters — ``leadership_snapshot`` (entity_profile.json),
     ``key_leadership`` (research_handoff.json), and role→"Name (Title)" string
     maps — via the same ``extract_leadership`` the ingest path uses (so the
     backfill matches ingest coverage instead of only finding CSV/DOCX).
  2. CSV leadership register — real ``Full Name`` + ``Title`` (+ credentials /
     digital-signal background, appointment-date tenure).
  3. Profile DOCX variants — parsed via the canonical client-profile parser's
     table/paragraph leadership extraction.

Every name/title is verbatim from the package — never invented. Idempotent:
fills only entities whose ``firmographics.leadership`` is empty. Safe on every
deploy (post-deploy-refresh.sh).

Usage: DATABASE_URL=... [DMA_SEED_CORPUS_DIR=...] python -m app.scripts.derive_leadership
"""
from __future__ import annotations

import asyncio
import csv
import glob
import io
import json
import os
import re
from datetime import date, datetime

from sqlalchemy import text

from app.database import get_sessionmaker
from app.scripts.derive_issues import _norm_name, _package_index

_NAME_KEYS = ("full name", "name", "executive", "leader", "full_name")
_TITLE_KEYS = ("title", "role", "position")
_BG_KEYS = ("key digital signal", "credentials", "background", "bio",
            "salesforce relevance", "notes")
_DATE_KEYS = ("appointment date", "start date", "tenure start", "since")

# Many Client-Profile / Assessment reports render the "4.3 Leadership Overview"
# as labelled PROSE — "<Title>: <Full Name> — <description> [E-ID]" / "<Title>:
# <Full Name> (<description>)" (Zions, OneAZ, BOK …) — which the table/JSON
# extractors miss, leaving the panel empty OR (when the ingest grabbed a colon-
# title fragment) showing junk like "CEO: Brandon". This recovers the real
# {name,title}: the title must carry a leadership ROLE keyword and the name must
# pass the canonical person guard, so corporate/product phrases are never
# mistaken for a person.
_ROLE_KW = re.compile(
    r"\b(CEO|CFO|CIO|CTO|CISO|COO|CDO|CMO|CRO|President|Chief|EVP|SVP|VP|Director"
    r"|Head|Chair|Chairman|Chairwoman|Treasurer|Controller|Officer|Founder"
    r"|Managing Partner|Partner|Principal)\b", re.I)
_GAP_KW = re.compile(
    r"\bgap|no identified|none|absent|vacant|unknown|\btbd\b|all filled\b", re.I)
_PROSE_LEAD = re.compile(
    r"^\s*(?P<title>[A-Z][\w&/.,\-' ]{1,55}?)\s*:\s+"
    r"(?P<name>[A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3})")


def _tenure_months(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(str(raw)[:10]).date()
    except ValueError:
        return None
    today = date.today()
    return max(0, (today.year - d.year) * 12 + (today.month - d.month))


def _leaders_from_csv(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(io.StringIO(fh.read()))
    except OSError:
        return []
    out: list[dict] = []
    for raw in reader:
        norm = {(k or "").strip().lower(): (v or "").strip()
                for k, v in raw.items() if k}
        name = next((norm[k] for k in _NAME_KEYS if norm.get(k)), "")
        title = next((norm[k] for k in _TITLE_KEYS if norm.get(k)), "")
        if not name or len(name) > 120 or not any(c.isalpha() for c in name):
            continue
        bg = next((norm[k] for k in _BG_KEYS if norm.get(k)), "") or None
        tenure = _tenure_months(
            next((norm[k] for k in _DATE_KEYS if norm.get(k)), None))
        out.append({"name": name[:120], "title": (title or "")[:120] or None,
                    "tenure": tenure, "background": (bg[:400] if bg else None)})
    return out


def _csv_leadership(root: str) -> list[dict]:
    """Best structured leadership register under the package root."""
    best: list[dict] = []
    for sub in ("08_appendices", "00_entity_profile", "01_evidence",
                "02_research_workbook"):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "**", "*.csv"), recursive=True):
            base = os.path.basename(f).lower()
            if "leadership" in base or "executive" in base or (
                    "entity_profile" in base or "leader" in base):
                rows = _leaders_from_csv(f)
                if len(rows) > len(best):
                    best = rows
    return best


def _json_leadership(root: str) -> list[dict]:
    """JSON dict-of-roles rosters (``leadership_snapshot`` / ``key_leadership``
    / role→"Name (Title)" strings) via the SAME robust extractor the ingest
    path uses, so the in-place backfill matches ingest coverage instead of
    only finding CSV/DOCX rosters. Applies the canonical person-name guard."""
    from pathlib import Path

    from app.services.entity_healing import extract_leadership
    from app.services.parsers.dma_package import _is_person_name
    try:
        people = extract_leadership(Path(root))
    except Exception:
        return []
    # extract_leadership already emits {name,title,tenure,background} — the
    # exact downstream shape; just filter non-people ("No CDO", prose, …).
    return [p for p in people if _is_person_name(p.get("name"))]


def _docx_leadership(root: str) -> list[dict]:
    """Leadership from any profile DOCX variant via the canonical parser."""
    from app.services.parsers.client_profile import parse_client_profile_path

    cands: list[str] = []
    for sub in ("04_reports", "00_entity_profile"):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            for f in glob.glob(os.path.join(d, "**", "*.docx"), recursive=True):
                base = os.path.basename(f).lower()
                if "profile" in base or "leadership" in base or "entity" in base:
                    cands.append(f)
    best: list[dict] = []
    for f in sorted(set(cands)):
        try:
            res = parse_client_profile_path(f)
        except Exception:
            continue
        rows = [{"name": le.name[:120],
                 "title": (getattr(le, "title", "") or "")[:120] or None,
                 "tenure": None,
                 "background": (getattr(le, "background", None) or None)}
                for le in (res.leadership or [])
                if getattr(le, "name", "").strip()]
        if len(rows) > len(best):
            best = rows
    return best


def _entity_dir(root: str) -> str:
    """The entity's package dir — the child of a ``batch_*`` (or corpus) dir on
    the path to ``root``. Many packages ship several version subdirs ("<Entity>
    FINAL", "<Entity> DMA v2.0", "Background Research") as siblings; the canonical
    root may point at one while the leadership prose lives in another. Sweeping
    from the entity dir covers them all WITHOUT crossing into a sibling entity
    (it stops at the batch boundary)."""
    cur = os.path.abspath(root)
    while True:
        parent = os.path.dirname(cur)
        if not parent or parent == cur:
            return root
        pb = os.path.basename(parent).lower()
        if pb.startswith("batch_") or "dma_packages" in pb:
            return cur
        cur = parent


def _prose_leadership(root: str) -> list[dict]:
    """Labelled-prose leadership ("<Role Title>: <Full Name> — …") from any
    profile / assessment / report DOCX — the format the table/JSON extractors
    miss. The title must carry a role keyword and the name must pass the person
    guard, so no corporate/product phrase is ever surfaced as a leader."""
    import docx as _docx

    from app.services.parsers.dma_package import _is_person_name
    # Sweep the whole entity dir (covers sibling version subdirs), not just the
    # canonical root — bounded to the entity so no cross-entity contamination.
    base = _entity_dir(root)
    cands = [f for f in glob.glob(os.path.join(base, "**", "*.docx"), recursive=True)
             if any(k in os.path.basename(f).lower()
                    for k in ("profile", "leadership", "entity", "report"))]
    best: list[dict] = []
    for f in sorted(set(cands)):
        try:
            doc = _docx.Document(f)
        except Exception:
            continue
        out: list[dict] = []
        seen: set[str] = set()
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if not t or len(t) > 220:
                continue
            m = _PROSE_LEAD.match(t)
            if not m:
                continue
            title = m.group("title").strip()
            name = m.group("name").strip().rstrip(".").strip()
            if (not _ROLE_KW.search(title) or _GAP_KW.search(title)
                    or _GAP_KW.search(name) or not _is_person_name(name)):
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            bg = t[m.end():].strip(" —-([,").rstrip("]). ").strip() or None
            out.append({"name": name[:120], "title": title[:120] or None,
                        "tenure": None, "background": (bg[:400] if bg else None)})
        if len(out) > len(best):
            best = out
    return best


# ── Roster enrichment: flags + tenure + explicit GAP rows (plan 4.8) ────────
# The seat matcher resolves FUNCTIONAL / SYNONYM titles, not just the acronym:
# a "Chief Security Officer" (CSO) fills the CISO seat, a "Head of Product
# Strategy, Data and Architecture" (or a "de facto CDO") fills the CDO seat.
# Without this, FCMA minted fabricated CISO (Tiffany Smith, CSO) + CDO (Daniel
# Brittain) gaps although both are FILLED and marked R12-FORBIDDEN.
_CRITICAL_SEATS = (
    ("CISO", re.compile(
        r"\bCISO\b|chief information security|chief security officer|\bCSO\b"
        r"|head of (?:information |cyber ?)?security"
        r"|(?:information |cyber ?)security officer", re.I)),
    ("CTO / CIO", re.compile(
        r"\bCTO\b|\bCIO\b|chief (?:technology|information) officer", re.I)),
    ("CDO", re.compile(
        r"\bCDO\b|chief (?:data|digital) officer"
        r"|de facto CDO|head of (?:data|digital)"
        r"|data\s*(?:and|&|,)\s*architect"          # "Data and Architecture"
        r"|product strategy,?\s*data",              # "Product Strategy, Data …"
        re.I)),
)
# The seat's canonical NAME(s) — used with the FILLED marker below so an
# explicit profile resolution ("Chief Information Security Officer: FILLED —
# Tiffany Smith") suppresses the gap even when the roster title is unusual.
_SEAT_NAME_RE = {
    "CISO": re.compile(
        r"chief information security officer|chief security officer|\bCISO\b|\bCSO\b", re.I),
    "CTO / CIO": re.compile(
        r"chief technology officer|chief information officer|\bCTO\b|\bCIO\b", re.I),
    "CDO": re.compile(r"chief data officer|chief digital officer|\bCDO\b", re.I),
}
# Explicit seat-resolution markers ("… : FILLED — Name", "CONSOLIDATED",
# "FUNCTIONALLY FILLED", "LIKELY FILLED"). A seat so marked is NEVER a gap.
_SEAT_FILLED_MARK = re.compile(
    r"\b(?:functionally\s+|likely\s+)?filled\b|\bconsolidated\b|\bsubsumed\b", re.I)
# R12 forbidden generic-hypothesis phrases ("'Hire a CISO' — FORBIDDEN",
# "'Appoint a CDO' — FORBIDDEN") — an explicit instruction NOT to mint the gap.
_R12_FORBIDDEN = {
    "CISO": re.compile(r"hire a ciso|appoint a ciso|no ciso", re.I),
    "CTO / CIO": re.compile(r"hire a cto|appoint a cto|hire a cio|appoint a cio", re.I),
    "CDO": re.compile(
        r"appoint a cdo|hire a cdo|create a chief data|no digital strategy", re.I),
}
_TENURE_NUM = re.compile(r"(\d{1,2})\s*(?:\+\s*)?(years?|yrs?|months?|mos?)\b", re.I)


def _seat_marked_filled(seat: str, blob: str) -> bool:
    """True when the profile explicitly resolves ``seat`` as FILLED /
    CONSOLIDATED / FUNCTIONALLY FILLED (the R11/R12 leadership-gaps analysis),
    or an R12 forbidden-phrase forbids minting the gap for it."""
    if not blob:
        return False
    if _R12_FORBIDDEN[seat].search(blob):
        return True
    name_re = _SEAT_NAME_RE.get(seat)
    if name_re:
        for m in name_re.finditer(blob):
            # the FILLED/CONSOLIDATED marker must sit right after the seat name
            # ("Chief Information Security Officer: FILLED — Tiffany Smith").
            if _SEAT_FILLED_MARK.search(blob[m.start(): m.end() + 60]):
                return True
    return False


def tenure_months_of(raw: object) -> int | None:
    """tenure string → months: ISO date ('2021-03'), bare year ('2019'),
    'N years'/'N months'. None when unparseable."""
    sv = str(raw or "").strip()
    if not sv:
        return None
    today = date.today()
    m = re.match(r"^((?:19|20)\d{2})(?:-(\d{1,2}))?", sv)
    if m:
        y, mo = int(m.group(1)), int(m.group(2) or 6)
        if 1950 <= y <= today.year:
            return max(0, (today.year - y) * 12 + (today.month - mo))
    m = _TENURE_NUM.search(sv)
    if m:
        n = int(m.group(1))
        return n * 12 if m.group(2).lower().startswith("y") else n
    return None


def enrich_roster(roster: list, entity_evidence_blob: str = "") -> tuple[list, int, int]:
    """Adds critical_role / recent_hire / gap_flag / tenure_months to every
    person row and appends explicit GAP rows for critical seats absent from
    BOTH the roster and the evidence trail (prototype EX-05: 'CISO absent'
    is a row, not silence). Returns (rows, gap_count, enriched_count)."""
    from app.services.startup_enrich import leadership_flags

    out: list[dict] = []
    enriched = 0
    for p in roster or []:
        if not isinstance(p, dict):
            continue
        row = dict(p)
        tm = row.get("tenure_months")
        if tm in (None, "") and row.get("tenure") not in (None, ""):
            tm = tenure_months_of(row.get("tenure"))
            if tm is not None:
                row["tenure_months"] = tm
        flags = leadership_flags(row.get("title"), row.get("tenure_months"), row.get("name"))
        for k, v in flags.items():
            if row.get(k) is None:
                row[k] = v
        enriched += 1
        out.append(row)
    # Roster TITLES + BACKGROUNDS both count toward filling a seat — a "de
    # facto CDO" noted in a background is real coverage, not a gap.
    titles_blob = " ".join(
        f"{p.get('title') or ''} {p.get('background') or ''}" for p in out)
    blob = entity_evidence_blob or ""
    gaps = 0
    for seat, pat in _CRITICAL_SEATS:
        # (1) a roster person functionally holds the seat (synonym-resolved)
        if pat.search(titles_blob):
            continue
        # (2) the profile explicitly marks the seat FILLED / CONSOLIDATED, or
        #     an R12 forbidden-phrase forbids minting the gap
        if _seat_marked_filled(seat, blob):
            continue
        # (3) the seat is otherwise evidenced in the trail (legacy suppression)
        if pat.search(blob):
            continue
        out.append({"name": None, "title": seat, "gap_flag": True,
                    "critical_role": True, "recent_hire": False,
                    "background": f"No {seat} identified in the public roster "
                                  f"or evidence trail — a named ownership gap.",
                    "derived_from": "roster_gap_scan"})
        gaps += 1
        if gaps >= 2:
            break
    return out, gaps, enriched


# ── Thought-leadership deterministic fallback (plan 4.2/4.9) ────────────────
_TL_TYPES = (
    ("podcast", re.compile(r"podcast|episode", re.I)),
    ("webinar", re.compile(r"webinar|web seminar", re.I)),
    ("conference", re.compile(r"conference|summit|keynote|panel(?:ist)?|speaking (?:at|engagement)", re.I)),
    ("linkedin-post", re.compile(r"linkedin (?:post|article|presence|activity)|"
                                  r"posted on linkedin|themed posts|"
                                  r"social media (?:presence|activity|posts)|#[A-Z][a-zA-Z]{3,}", re.I)),
    ("blog", re.compile(r"\bblog\b", re.I)),
    ("article", re.compile(r"article|op-ed|byline|authored|interview(?:ed)?|"
                           r"press release|quoted", re.I)),
)


def tl_from_evidence(ev_rows: list, roster: list, entity_name: str) -> list[dict]:
    """Typed thought-leadership items mined from the entity's OWN evidence:
    rows whose excerpt matches a publication/speaking pattern AND names a
    roster executive (or the entity itself with an executive title word).
    Emits [{type, date, title, excerpt, author, url, e_id}] — every field
    verbatim from the evidence row; nothing invented."""
    from app.services.nlp.titlecraft import make_title

    names = [str(p.get("name")) for p in roster or []
             if isinstance(p, dict) and p.get("name")]
    out: list[dict] = []
    seen: set[str] = set()
    for er in ev_rows:
        exc = er.get("excerpt") or ""
        if len(exc) < 60:
            continue
        src_blob = f"{er.get('source_url') or ''} {er.get('source_name') or ''}"
        tl_type = next((t for t, pat in _TL_TYPES if pat.search(exc)), None)
        if not tl_type:
            if re.search(r"linkedin\.com/(?:posts|pulse)", src_blob, re.I):
                tl_type = "linkedin-post"
            elif re.search(r"youtube|spotify|podcasts?\.apple|soundcloud", src_blob, re.I):
                tl_type = "podcast"
            elif re.search(r"medium\.com|substack", src_blob, re.I):
                tl_type = "blog"
            elif re.search(r"thought leadership|whitepaper|white paper|insights? (?:piece|series)|"
                           r"perspective|fireside|webcast", exc, re.I):
                tl_type = "article"
        if not tl_type:
            continue
        # Negated absences ("no podcast appearances found", "NEGATIVE
        # SEARCH") must never surface as thought-leadership artifacts.
        from app.services.nlp.polarity import is_negated_absence
        if is_negated_absence(exc):
            continue
        # Institutional voice counts too (Part D: "what the client talks
        # about publicly") — author stays None unless an executive matches.
        author = next((n for n in names if n.lower() in exc.lower()), None)
        title = make_title(exc, 70)
        key = title.lower()[:40]
        if not title or key in seen:
            continue
        seen.add(key)
        out.append({
            "type": tl_type,
            "date": er.get("published_date"),
            "title": title,
            "excerpt": exc[:220],
            "author": author,
            "url": er.get("source_url"),
            "e_id": er.get("e_id"),
            "derived_from": "evidence_index",
        })
        if len(out) >= 6:
            break
    return out


_EXEC_BEFORE = re.compile(
    r"\b(CEO|CFO|CIO|CTO|CISO|CDO|COO|CRO|CMO|President|Chair(?:man|woman)?|"
    r"Chief [A-Z][a-z]+(?: [A-Z][a-z]+)? Officer|EVP|SVP)\b[,:]?\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-zA-Z'\-]+)")
_EXEC_AFTER = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-zA-Z'\-]+),?\s+(?:the\s+|its\s+)?"
    r"(CEO|CFO|CIO|CTO|CISO|CDO|COO|CRO|CMO|President|Chief [A-Z][a-z]+"
    r"(?: [A-Z][a-z]+)? Officer)\b")


async def _ner_leadership(session, entity_id: str) -> list[dict]:
    """Final ladder rung (plan 4.8): mine '<TITLE> <Name>' / '<Name>, <TITLE>'
    executive mentions from the entity's persisted sections + evidence
    excerpts. Verbatim, person-guarded, deduped; never invented."""
    from app.services.parsers.dma_package import _is_person_name
    blobs = (await session.execute(text(
        """
        (SELECT body t FROM document_sections ds
          JOIN runs r ON r.id=ds.run_id AND r.status='ACTIVE'
          WHERE ds.entity_id=CAST(:e AS uuid) LIMIT 60)
        UNION ALL
        (SELECT excerpt t FROM evidence_index
          WHERE entity_id=CAST(:e AS uuid)
            AND length(COALESCE(excerpt,''))>80 LIMIT 300)
        """), {"e": entity_id})).scalars().all()
    out: list[dict] = []
    seen: set[str] = set()
    for blob in blobs:
        for pat, name_i, title_i in ((_EXEC_BEFORE, 2, 1), (_EXEC_AFTER, 1, 2)):
            for m in pat.finditer(blob or ""):
                name = m.group(name_i).strip()
                title = m.group(title_i).strip()
                if not _is_person_name(name) or name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append({"name": name[:120], "title": title[:120],
                            "tenure": None, "background": None,
                            "derived_from": "ner:document_sections"})
                if len(out) >= 8:
                    return out
    return out


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        import sys
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    from app.services.parsers.dma_package import _is_person_name
    sm = get_sessionmaker()
    pkg_idx = _package_index()
    filled = csv_src = docx_src = json_src = prose_src = ner_src = 0
    async with sm() as session:
        # Re-derive a roster when it is empty OR contains NO real person — the
        # ingest path sometimes grabs a colon-title fragment ("CEO: Brandon",
        # "Leadership Gaps:") that the export patcher correctly drops, leaving the
        # panel blank. Both states are recoverable from the package prose.
        rows = (await session.execute(text(
            """
            SELECT e.id::text eid, e.name, e.drive_folder_id dfid,
                   r.id::text rid, f.leadership lead
            FROM entities e
            JOIN firmographics f ON f.entity_id = e.id
            JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
            WHERE e.status = 'ACTIVE'
            ORDER BY e.display_id
            """))).all()
        empties = []
        for ent in rows:
            cur = ent.lead
            if isinstance(cur, str):
                try:
                    cur = json.loads(cur or "[]")
                except json.JSONDecodeError:
                    cur = []
            if not [p for p in (cur or []) if _is_person_name((p or {}).get("name"))]:
                empties.append(ent)
        for ent in empties:
            dfid = ent.dfid or ""
            key = _norm_name(dfid.split("local:", 1)[-1] if "local:" in dfid
                             else ent.name)
            root = pkg_idx.get(key)
            if not root:
                kt = set(key.split())
                for k, v in pkg_idx.items():
                    if kt and (kt <= set(k.split()) or set(k.split()) <= kt):
                        root = v
                        break
            root = root or ""
            # Filter EVERY extractor's output through the person guard before
            # accepting it — the structured docx parser sometimes returns the same
            # colon-title junk ("CEO: Brandon") the ingest grabbed, which must not
            # block the fallthrough to the labelled-prose roster.
            def _real(rows: list[dict]) -> list[dict]:
                return [r for r in rows if _is_person_name(r.get("name"))]

            leaders = _real(_json_leadership(root)) if root else []
            src = "json"
            if not leaders and root:
                leaders = _real(_csv_leadership(root))
                src = "csv"
            if not leaders and root:
                leaders = _real(_docx_leadership(root))
                src = "docx"
            if not leaders and root:
                # Labelled-prose roster ("CEO: Brandon Michaels — …") the
                # structured extractors miss — title must be a role + name must
                # pass the person guard, so nothing is fabricated.
                leaders = _real(_prose_leadership(root))
                src = "prose"
            if not leaders:
                # NER over the persisted sections/evidence — the final rung.
                leaders = _real(await _ner_leadership(session, ent.eid))
                src = "ner"
            if not leaders:
                # Genuinely no recoverable roster (the "4.3 Leadership Overview"
                # section is empty, or only states "no identified gaps"). We do
                # NOT guess names — the panel stays honestly empty.
                continue
            # de-dup by name, cap to a legible roster
            seen: set[str] = set()
            uniq: list[dict] = []
            for r in leaders:
                k = r["name"].lower()
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(r)
            # overwrite unconditionally — the selection already proved the current
            # roster carries no real person (empty or all-junk).
            await session.execute(text(
                "UPDATE firmographics SET leadership = CAST(:l AS jsonb) "
                "WHERE entity_id = CAST(:e AS uuid)"
            ), {"l": json.dumps(uniq[:12]), "e": ent.eid})
            filled += 1
            if src == "csv":
                csv_src += 1
            elif src == "docx":
                docx_src += 1
            elif src == "json":
                json_src += 1
            elif src == "prose":
                prose_src += 1
            elif src == "ner":
                ner_src += 1
        # Pass 2 — enrich EVERY roster with flags/tenure + explicit GAP rows.
        flagged = gap_rows = tl_filled = 0
        rows2 = (await session.execute(text(
            """
            SELECT e.id::text eid, e.name, f.leadership lead, f.thought_leadership tl
            FROM entities e
            JOIN firmographics f ON f.entity_id=e.id
            JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
            WHERE e.status='ACTIVE'
            """))).all()
        for ent in rows2:
            roster = ent.lead if isinstance(ent.lead, list) else []
            real = [p for p in roster if isinstance(p, dict)
                    and _is_person_name(p.get("name"))]
            ev_rows = (await session.execute(text(
                """
                SELECT e_id, excerpt, source_url, source_name,
                       published_date::text AS published_date
                FROM evidence_index WHERE entity_id=CAST(:e AS uuid)
                  AND length(COALESCE(excerpt,'')) > 0
                ORDER BY tier ASC LIMIT 400
                """), {"e": ent.eid})).mappings().all()
            ev_blob = " ".join((r.get("excerpt") or "")[:200] for r in ev_rows[:120])
            # The R11/R12 "Leadership Gaps Analysis" seat resolution ("Chief
            # Information Security Officer: FILLED — Tiffany Smith") + the R12
            # forbidden-phrase list live in the report prose — feed them to the
            # gap scan so an explicitly FILLED seat is never re-declared a gap.
            doc_blob = (await session.execute(text(
                "SELECT string_agg(body, ' ') FROM document_sections "
                "WHERE entity_id=CAST(:e AS uuid)"), {"e": ent.eid})).scalar() or ""
            gap_blob = (ev_blob + " " + doc_blob)[:200000]
            if real:
                new_roster, gaps, _n = enrich_roster(real, gap_blob)
                if new_roster != roster:
                    await session.execute(text(
                        "UPDATE firmographics SET leadership=CAST(:l AS jsonb) "
                        "WHERE entity_id=CAST(:e AS uuid)"
                    ), {"l": json.dumps(new_roster), "e": ent.eid})
                    flagged += 1
                    gap_rows += gaps
            # thought-leadership is STRICTLY a Clay-enrichment surface
            # (operator mandate 2026-07-06): the card stays EMPTY until the
            # Clay connector webhook syncs it. The old evidence-typed
            # deterministic fallback mis-typed INTERNAL Zennify-proposal
            # excerpts ("Zennify Proposal Phase 2 …", url:INTERNAL) as the
            # client's public thought leadership on 77/94 clients — removed.
            # (tl_from_evidence retained in nlp for the Clay-side classifier
            #  but never invoked as a derive fallback here.)
        await session.commit()
    print(f"# derive_leadership: flagged={flagged} gap_rows={gap_rows} "
          f"tl_filled={tl_filled} filled={filled} "
          f"(json={json_src} csv={csv_src} docx={docx_src} prose={prose_src} ner={ner_src}) "
          f"(verbatim structured roster from package; idempotent)", flush=True)
    return 0


def main() -> None:
    import sys
    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
