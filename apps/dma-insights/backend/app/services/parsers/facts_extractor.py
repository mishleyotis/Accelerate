"""Derive D5 Context timeline events from evidence `facts[]` — NLP pipeline.

The DMA bot's `01_evidence/evidence_index.json` carries, per E-ID, a
`facts[]` list ({fact_id, text, claim_label, specificity_score}) plus a
parent-level `publish_date` / `signal_direction`. The 2026-06 context
audit measured what the first regex+excerpt derivation produced across
1,097 events: 88% defaulted dates (26 dots piled on one publish date for
one client), 51% garbage titles (verbatim 140-300-char excerpts with
subcap prefixes and ALL-CAPS researcher headers), negation misses
("NEGATIVE SEARCH RESULT: No formal enforcement…" rendered as a
regulatory event), and 66 cross-source duplicates.

This module is the rebuilt pure (no-DB) derivation on the shared NLP
platform (plan Part 8.2):

  1. **Negation/absence gate** (`nlp.polarity.is_negated_absence`) —
     researcher negative-search rows are SUPPRESSED from the timeline
     (they record that nothing happened). :func:`extract_regulatory_standing`
     converts the strongest regulatory absence into ONE explicit
     clean-standing signal for the D5 regulatory block instead.
  2. **Event-vs-description gate** — a fact is promoted only when it has
     an event verb (appointed/acquired/fined/…) or an in-text date on an
     M&A/leadership/regulatory frame; obligations ("MUST maintain
     BSA/AML"), hypotheticals ("actively seeking", "would enable"),
     internal-alternative notes and resume/baseline descriptions are
     dropped.
  3. **Real event dates** (`nlp.dates.resolve_event_date`) — textual
     date in the claim > quarter > fiscal > `publish_date` fallback,
     ALWAYS labelled with `date_precision` so the frontend can
     jitter/cluster fallback pile-ups honestly.
  4. **Titles** (`nlp.titlecraft.make_title`) — ≤60-char subject-verb-
     object display titles; the verbatim excerpt moves to `body`.
  5. **Native `signal`** (`nlp.polarity.signal`) — polarity classified
     from the claim itself, never inferred from `kind`.
  6. **`subcap_ids[]` / `evidence_e_ids[]`** — capability references and
     E-ID citations present in the text (plus the parent E-ID).
  7. **Cross-source dedup** (`nlp.similarity.near_duplicates`) — near-
     duplicate events within a quarter are merged, keeping the more
     precise date and unioning evidence anchors.

Provenance: the events are tier `DERIVED` (deterministic classification
over EXTRACTED evidence) — never LLM-synthesised.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.schemas.package import EvidenceRow, TimelineEventCandidate
from app.services.nlp import dates as nlp_dates
from app.services.nlp import polarity
from app.services.nlp.segment import sentences
from app.services.nlp.similarity import near_duplicates
from app.services.nlp.titlecraft import make_title

# publish_date sentinels that carry no usable date.
_BAD_DATE_TOKENS = frozenset(
    {"", "n/a", "na", "none", "null", "unknown", "current",
     "ongoing", "tbd", "present", "-", "—"}
)

# claim_labels that are anti-facts (absence / removed / negative search) —
# never promote to a timeline event.
_EXCLUDED_CLAIM_LABELS = frozenset(
    {"REMOVED", "NO_EVIDENCE", "NEGATIVE_SEARCH", "ABSENCE"}
)

# Lower plausibility bound for an event year (digital-era DMAs).
_MIN_YEAR = 1990

# Facts that are NEGATIVE/absence statements are never timeline events —
# nlp.polarity.is_negated_absence is the primary gate; this keeps the
# legacy corpus-specific phrasings that predate the shared lexicon.
_ANTI_MARKERS = re.compile(
    r"negative evidence|not listed|no evidence|absence of|no record of",
    re.IGNORECASE,
)

# "acquisition" is overwhelmingly used in the NON-M&A sense across the
# corpus (talent / customer / user / data acquisition). Reject those.
_NON_MA_ACQUISITION = re.compile(
    r"\b(talent|customers?|clients?|users?|data|dtc|deposits?|loans?|"
    r"mortgages?|digital|lead|audience|member)\s+acquisition",
    re.IGNORECASE,
)

# Ordered (kind, pattern). First match wins. Patterns are deliberately
# verb-anchored and NARROW: this classifier is deterministic (DERIVED tier),
# so it must favour PRECISION over recall — a sparse-but-accurate analyst
# timeline beats a dense one polluted by corporate-value words ("we value
# Collaboration"), resume phrasing ("led the 0-1 launch of …"), and generic
# compliance text.
_KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pat, re.IGNORECASE))
    for kind, pat in (
        (
            "acquisition",
            r"\bacquired\b|\bacquisition of\b|\bmerg(?:er|ed)\b|"
            r"\bbuyout\b|\btakeover\b|\btook over\b",
        ),
        (
            "leadership",
            # an appointment/departure verb within 45 chars of an exec
            # title, in either order. Background/resume facts ("Co-founder
            # and CPO at …", "Led end-to-end development") lack the verb and
            # so are excluded. 2026-07 audit: the title lexicon must cover
            # VP/SVP/EVP/AVP/vice president/manager(-ing director) in BOTH
            # alternations — "VP Marketing hired Dec 2025", "SVP Strategic
            # Risk Officer hired", and "EVP Technology Soma Bulusu joined
            # Feb 2024" (IBKR's critical inflection point) fell through to
            # milestone/regulatory.
            r"\b(appoint\w*|named|hired|hires|joins?|joined|promot\w*|"
            r"stepped down|steps down|resign\w*|depart\w*|succeed\w*|"
            r"replac\w*)\b.{0,45}\b(ceo|cfo|cto|cio|cdo|coo|cmo|cro|ciso|"
            r"chro|cpo|chief|"
            r"president|chair(?:man|person)?|head of|director|officer|"
            r"s?vp|evp|avp|vice president|manag(?:er|ing director))\b"
            r"|\b(ceo|cfo|cto|cio|cdo|coo|cmo|cro|ciso|chro|cpo|"
            r"chief\s+\w+\s+officer|chief|"
            r"president|chair(?:man|person)?|head of|director|officer|"
            r"s?vp|evp|avp|vice president|manag(?:er|ing director))\b"
            r".{0,45}\b(appoint\w*|named|hired|hires|"
            r"joined|promot\w*|stepped down|resign\w*|depart\w*|succeed\w*)\b",
        ),
        (
            "regulatory",
            # 2026-07 audit: enforcement-shaped LEGAL events (criminal
            # indictment, class-action/lawsuit, data breach → AG
            # notifications, court-appointed administrator, regulator
            # settlements) were falling through to 'milestone'.
            r"consent order|enforcement action|cease and desist|\bfined\b|"
            r"monetary penalty|regulatory penalty|sanctioned by|"
            r"\bindict(?:ed|ment)s?\b|\blawsuits?\b|\blitigation\b|"
            r"\bclass[-\s]action\b|\bdata\s+breach(?:es)?\b|court-appointed|"
            r"regulatory\s+settlement|settlement\s+with\s+(?:the\s+)?"
            r"(?:regulat\w+|attorneys?\s+general)|"
            r"\bcharter (?:granted|approved)\b",
        ),
    )
)

# Event VERBS (past-tense occurrences). A noun frame alone ("merger of six
# credit unions") is NOT an event unless it also carries an in-text date —
# this kills the resume/oversight-description class ("Darcy oversaw complex
# integration following the merger of six credit unions").
_EVENT_VERB_RE = re.compile(
    r"\b(?:launched|completed|hired|appointed|named|joined|promoted|"
    r"stepped down|resigned|departed|succeeded|acquired|closed|announced|"
    r"fined|sanctioned|migrated|deployed|opened|merged|partnered|signed|"
    r"raised|crossed|granted|rolled out|went live)\b",
    re.IGNORECASE,
)
# Verb → deterministic kind for facts the narrow classifier passed on but
# the strict `is_event` gate accepted (dated occurrence). acquired/merged
# are intentionally absent — the M&A path is owned by _KIND_PATTERNS with
# the non-M&A guard. 2026-07 audit: hired/appointed/joined/promoted and the
# departure verbs had NO mapping, dumping 112 leadership hires into
# 'milestone'; 'named' stays out (award phrasing — "named Best Bank" — is
# not a personnel move; named+title is owned by _KIND_PATTERNS).
_VERB_KIND: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:launched|deployed|rolled out|went live)\b", re.I), "product"),
    (re.compile(r"\b(?:partnered|signed)\b", re.I), "partnership"),
    (re.compile(r"\b(?:fined|sanctioned)\b", re.I), "regulatory"),
    (re.compile(r"\b(?:hired|appointed|joined|promoted|stepped\s+down|"
                r"resigned|departed)\b", re.I), "leadership"),
)

# Regulators as ACTORS (2026-07-06 tightening): "OSFI launched new
# Supervisory Framework" / "FINRA CORE launched in 2025" are regulatory-
# landscape events, not the entity's own product launches — the classifier
# was chipping them "tech launch" on the D5 timeline. A regulator named
# BEFORE the event verb makes the event regulatory.
_REGULATOR_NAME_RE = re.compile(
    r"\b(?:FINRA|SEC|CFTC|OCC|FDIC|CFPB|NCUA|OSFI|FINTRAC|FHFA|NAIC|"
    r"ESMA|IIROC|CIRO|OSC|BCSC|Federal\s+Reserve|MAS|APRA|"
    r"FCA)\b",
)
# join/hire verbs + executive titles — the staff-hire noise gate.
_JOIN_VERB_RE = re.compile(r"\b(?:joined|joins|hired|hires)\b", re.IGNORECASE)
_EXEC_TITLE_RE = re.compile(
    r"\b(?:ceo|cfo|cto|cio|cdo|coo|ciso|cro|cmo|chro|chief|president|"
    r"chair(?:man|person)?|head of|director|officer|founder|evp|svp|vp)\b",
    re.IGNORECASE,
)


def _regulator_is_actor(text: str) -> bool:
    """True when a regulator is named BEFORE the first event verb — the
    regulator did the launching/announcing, not the assessed entity."""
    m = _EVENT_VERB_RE.search(text)
    scope = text[: m.start()] if m else text
    return bool(_REGULATOR_NAME_RE.search(scope))


def _is_staff_hire_note(text: str) -> bool:
    """True for individual staffing notes ("Sara A. Business Data Analyst
    joined Dec 2024") — a join/hire verb with NO executive title. Real
    leadership changes carry an exec title and classify upstream; a
    non-executive job start is researcher roster bookkeeping, not a
    company timeline event (precision-over-recall contract)."""
    return bool(_JOIN_VERB_RE.search(text)) and not _EXEC_TITLE_RE.search(text)

# Descriptions that must never be promoted even when verb-shaped:
# obligations/baselines, hypotheticals/strategy intent, analyst inference.
_OBLIGATION_RE = re.compile(
    r"\b(?:must|shall|is\s+required\s+to|are\s+required\s+to|obligated\s+to|"
    r"is\s+subject\s+to\s+ongoing)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL_RE = re.compile(
    r"\b(?:would|could|might|hypothetical(?:ly)?|plans?\s+to|intends?\s+to|"
    r"expect(?:s|ed)?\s+to|aims?\s+to|considering|exploring|actively\s+seeking|"
    r"seeking\s+to|pursuing|proposes?\s+to|if\b)",
    re.IGNORECASE,
)
_ANALYST_NOTE_RE = re.compile(
    r"\b(?:analyst\s+note|we\s+believe|we\s+assess|in\s+our\s+view|our\s+view|"
    r"internal\s+alternative|likely\s+(?:to|reflects?)|appears\s+to|"
    r"may\s+(?:be|indicate|suggest))\b",
    re.IGNORECASE,
)
_NEGATOR_RE = re.compile(r"\b(?:no|not|never|without|none)\b", re.IGNORECASE)

# Peer-precedent / cautionary-example framings — the researcher citing what
# happened to ANOTHER institution ("NYDFS enforcement precedent: Gemini
# Trust fined $37M"). 2026-07 audit: these landed on the CLIENT's timeline
# as its own regulatory events. Entity-scoping gate: reject the whole fact.
_PEER_PRECEDENT_RE = re.compile(
    r"\b(?:enforcement|regulatory|supervisory|industry|nydfs|occ|cfpb|fdic|"
    r"ncua|sec|finra)\s+precedents?\b|\bprecedents?\s*:|"
    r"\bpeer\s+(?:institutions?|banks?|credit\s+unions?|examples?|"
    r"precedents?)\b|\bcautionary\s+(?:tale|example)\b",
    re.IGNORECASE,
)

# Capability references + E-ID citations inside a fact's text.
_SUBCAP_ID_RE = re.compile(r"\bP[1-4]C\d+(?:\.\d+){1,3}(?:[Tt]\d)?\b")
_E_ID_RE = re.compile(r"\bE-?(\d{2,4})\b")

# Regulatory-absence terms — used by extract_regulatory_standing to find
# the clean-standing signal among the suppressed negated absences.
_REG_BAD_RE = re.compile(
    r"enforcement|consent\s+order|cease\s+and\s+desist|monetary\s+penalt|"
    r"penalt(?:y|ies)|fines?\b|\bfined\b|sanction|MRA\b|formal\s+agreement|"
    r"regulatory\s+action",
    re.IGNORECASE,
)


def parse_event_date(raw: Any, *, today: date | None = None) -> date | None:
    """Normalise a messy `publish_date` string to a `date`, or None.

    Handles YYYY-MM-DD, YYYY-Qn, YYYY-MM, and bare YYYY (the start year of
    a range / open-ended `YYYY-current`). Rejects sentinels and years
    outside [_MIN_YEAR, this year + 1].
    """
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in _BAD_DATE_TOKENS:
        return None
    today = today or date.today()
    max_year = today.year + 1

    def _ok_year(y: int) -> bool:
        return _MIN_YEAR <= y <= max_year

    # Full ISO date.
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if _ok_year(y) and 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    # Quarter: YYYY-Qn / YYYY Qn.
    m = re.match(r"(\d{4})[-\s]?q([1-4])", s)
    if m:
        y, q = int(m[1]), int(m[2])
        if _ok_year(y):
            return date(y, (q - 1) * 3 + 1, 1)
    # YYYY-MM (guard month range so range-tails like 2020-2022 fall through).
    m = re.match(r"(\d{4})-(\d{1,2})(?!\d)", s)
    if m:
        y, mo = int(m[1]), int(m[2])
        if _ok_year(y) and 1 <= mo <= 12:
            return date(y, mo, 1)
    # Bare / leading year (range start, YYYY-current, plain YYYY).
    m = re.match(r"(\d{4})", s)
    if m:
        y = int(m[1])
        if _ok_year(y):
            return date(y, 1, 1)
    return None


def classify_fact_kind(text: str) -> str | None:
    """Map a fact's text to a timeline `kind`, or None when it is a static
    description (the common case) that should not appear on a timeline."""
    if not text:
        return None
    if polarity.is_negated_absence(text) or _ANTI_MARKERS.search(text):
        return None
    for kind, pat in _KIND_PATTERNS:
        if pat.search(text):
            if kind == "acquisition" and _NON_MA_ACQUISITION.search(text):
                continue
            return kind
    return None


def _fact_field(fact: Any, name: str) -> Any:
    """Read a field from either a FactItem model or a raw dict."""
    if isinstance(fact, dict):
        return fact.get(name)
    return getattr(fact, name, None)


def _trim_title(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(" .,;:") + "…"


def _has_event_verb(text: str) -> bool:
    """A past-tense occurrence verb, not negated in its lookback window."""
    m = _EVENT_VERB_RE.search(text)
    if not m:
        return False
    lookback = text[max(0, m.start() - 24) : m.start()]
    return not _NEGATOR_RE.search(lookback)


def _is_description(text: str) -> bool:
    """Obligation / hypothetical / analyst-note gate (never an event)."""
    return bool(
        _OBLIGATION_RE.search(text)
        or _HYPOTHETICAL_RE.search(text)
        or _ANALYST_NOTE_RE.search(text)
    )


def _verb_kind(text: str) -> str:
    for pat, kind in _VERB_KIND:
        if pat.search(text):
            return kind
    return "milestone"


def claim_segments(text: str) -> list[str]:
    """Part 8.2 step 1 — claim segmentation over a fact's text.

    Researcher facts pack several claims into one string ("Capital Bank
    acquired 2011 (Albany region); Canal Bank launched 2024 (Buffalo)").
    Each sentence (nlp.segment) is further split on ';' so classification,
    dating, titling and framing operate on ONE claim at a time; segments
    under 20 chars are noise.
    """
    segs: list[str] = []
    for sent in sentences(text or ""):
        for part in sent.split(";"):
            part = part.strip()
            if len(part) >= 20:
                segs.append(part)
    return segs or ([text.strip()] if text and len(text.strip()) >= 20 else [])


def event_title(text: str) -> str:
    """≤60-char display title via titlecraft; trimmed-text fallback."""
    title = make_title(text, 60)
    if len(title) >= 12:
        return title
    return _trim_title(text, 60)


def extract_refs(text: str) -> tuple[list[str], list[str]]:
    """(subcap_ids, e_ids) referenced in a fact's text, deduped in order."""
    subcaps: list[str] = []
    for m in _SUBCAP_ID_RE.finditer(text or ""):
        sid = m.group(0)
        if sid not in subcaps:
            subcaps.append(sid)
    e_ids: list[str] = []
    for m in _E_ID_RE.finditer(text or ""):
        eid = f"E-{m.group(1)}"
        if eid not in e_ids:
            e_ids.append(eid)
    return subcaps[:6], e_ids[:6]


_PRECISION_RANK = {"day": 0, "month": 1, "quarter": 2, "year": 3,
                   "publish_fallback": 4, "none": 5}


def dedup_events(
    events: list[TimelineEventCandidate],
    *,
    threshold: float = 0.75,
    window_days: int = 100,
) -> list[TimelineEventCandidate]:
    """Merge near-duplicate events across sources (audit: 66 dupes).

    Pairs whose title+body cosine ≥ ``threshold`` AND whose dates fall
    within ``window_days`` collapse into one event — the survivor is the
    one with the more precise date (day > month > … > publish_fallback),
    and evidence/subcap anchors are unioned. Order is preserved.
    """
    if len(events) < 2:
        return events

    def _text(ev: TimelineEventCandidate) -> str:
        return f"{ev.title} {ev.body or ''}"

    drop: dict[int, int] = {}  # dropped index → survivor index
    for i, j, _score in near_duplicates(events, key=_text, threshold=threshold):
        a, b = events[i], events[j]
        if abs((a.event_date - b.event_date).days) > window_days:
            continue
        ra = _PRECISION_RANK.get(a.date_precision or "none", 5)
        rb = _PRECISION_RANK.get(b.date_precision or "none", 5)
        keep, lose = (i, j) if ra <= rb else (j, i)
        # Follow survivor chains so A→B→C unions into one row.
        while keep in drop:
            keep = drop[keep]
        if keep == lose:
            continue
        drop[lose] = keep
        kev, lev = events[keep], events[lose]
        for eid in lev.evidence_e_ids:
            if eid not in kev.evidence_e_ids:
                kev.evidence_e_ids.append(eid)
        for sid in lev.subcap_ids:
            if sid not in kev.subcap_ids:
                kev.subcap_ids.append(sid)
        if kev.e_id is None:
            kev.e_id = lev.e_id
        if kev.source_url is None:
            kev.source_url = lev.source_url
    return [ev for idx, ev in enumerate(events) if idx not in drop]


def extract_timeline_events(
    evidence_rows: list[EvidenceRow],
    *,
    today: date | None = None,
    cap: int = 60,
) -> list[TimelineEventCandidate]:
    """Derive deduped, capped, precision-flagged timeline events.

    Promotion contract per CLAIM SEGMENT (plan Part 8.2; facts are first
    segmented so one multi-claim string yields per-claim events):
      - negated absences, obligations, hypotheticals, analyst notes → out;
      - peer-precedent framings ("NYDFS enforcement precedent: X fined…")
        are another institution's events → out;
      - an event needs a non-negated occurrence VERB, or an in-text date
        (day/month/quarter) on an M&A/leadership/regulatory frame;
      - the event date resolves from the CLAIM text first;
        ``publish_date`` is only a flagged fallback;
      - title is titlecraft-compressed, the verbatim claim moves to body;
      - `signal` is polarity-classified from the claim itself.
    Most-recent first; near-duplicates merged; capped at `cap`.
    """
    today = today or date.today()
    max_year = today.year + 1
    out: list[TimelineEventCandidate] = []
    seen: set[tuple[str, date, str]] = set()
    for ev in evidence_rows:
        publish = parse_event_date(getattr(ev, "publish_date", None), today=today)
        for fact in getattr(ev, "facts", None) or []:
            label = _fact_field(fact, "claim_label")
            if label and str(label).upper() in _EXCLUDED_CLAIM_LABELS:
                continue
            fact_text = (_fact_field(fact, "text") or "").strip()
            if len(fact_text) < 20:
                continue
            if polarity.is_negated_absence(fact_text) or _ANTI_MARKERS.search(fact_text):
                continue  # nothing happened — never a timeline dot
            if _PEER_PRECEDENT_RE.search(fact_text):
                continue  # another institution's event — not this timeline
            for text in claim_segments(fact_text):
                if polarity.is_negated_absence(text) or _ANTI_MARKERS.search(text):
                    continue
                if _PEER_PRECEDENT_RE.search(text):
                    continue
                if _is_description(text):
                    continue  # baseline / hypothetical / analyst inference
                resolved, precision = nlp_dates.resolve_event_date(text, publish)
                if resolved is None or precision == "none":
                    continue
                if not (_MIN_YEAR <= resolved.year <= max_year):
                    # Implausible in-text year — retreat to the publish date.
                    if publish is None:
                        continue
                    resolved, precision = publish, "publish_fallback"
                kind = classify_fact_kind(text)
                has_verb = _has_event_verb(text)
                if kind is None:
                    # Not an M&A/leadership/regulatory frame: only strictly
                    # dated occurrences (verb + in-text date) are promoted.
                    if not (has_verb and precision in {"day", "month", "quarter", "year"}):
                        continue
                    if _is_staff_hire_note(text):
                        continue  # non-executive job start — roster noise
                    kind = _verb_kind(text)
                    if kind != "regulatory" and _regulator_is_actor(text):
                        # "OSFI launched new Supervisory Framework" — the
                        # regulator acted; never the entity's tech launch.
                        kind = "regulatory"
                elif not has_verb and precision not in {"day", "month", "quarter"}:
                    # Noun-only frame ("merger of six credit unions") without
                    # a real in-text date is a description, not an occurrence.
                    continue
                title = event_title(text)
                key = (kind, resolved, title.lower())
                if key in seen:
                    continue
                seen.add(key)
                subcap_ids, cited = extract_refs(fact_text)
                e_id = getattr(ev, "e_id", None)
                evidence_e_ids = ([e_id] if e_id else []) + [
                    c for c in cited if c != e_id
                ]
                out.append(
                    TimelineEventCandidate(
                        event_date=resolved,
                        kind=kind,
                        title=title,
                        # The SEGMENT is the claim — the full fact rides in
                        # body only when it adds context beyond the claim.
                        body=fact_text,
                        source_url=getattr(ev, "source_url", None),
                        e_id=e_id,
                        signal=polarity.signal_for_kind(text, kind),
                        date_precision=precision,
                        evidence_e_ids=evidence_e_ids,
                        subcap_ids=subcap_ids,
                    )
                )
    out = dedup_events(out)
    out.sort(key=lambda c: (c.event_date, c.kind), reverse=True)
    return out[:cap]


def extract_regulatory_standing(
    evidence_rows: list[EvidenceRow],
) -> dict[str, Any] | None:
    """ONE clean-standing signal from the suppressed regulatory absences.

    The timeline suppresses negated-absence rows ("NEGATIVE SEARCH RESULT:
    No formal enforcement orders…"); this converts the strongest of them
    (facts first, excerpt fallback) into an explicit positive signal for
    the D5 regulatory block: ``{label, note, e_id, as_of}`` (``as_of`` is
    the source's publish date when parseable — the "verified as of" date).
    Returns None when the corpus records no regulatory absence — never
    fabricated.
    """
    best: dict[str, Any] | None = None
    for ev in evidence_rows:
        texts = [
            (_fact_field(f, "text") or "").strip()
            for f in (getattr(ev, "facts", None) or [])
        ]
        texts.append((getattr(ev, "excerpt", None) or "").strip())
        for text in texts:
            if len(text) < 20:
                continue
            if not polarity.is_negated_absence(text):
                continue
            if not _REG_BAD_RE.search(text):
                continue
            note = _trim_title(text, 220)
            published = parse_event_date(getattr(ev, "publish_date", None))
            candidate = {
                "label": "Clean regulatory standing",
                "note": note,
                "e_id": getattr(ev, "e_id", None),
                "as_of": published.isoformat() if published else None,
            }
            # Prefer the candidate that names enforcement most explicitly.
            if best is None or (
                "enforcement" in text.lower()
                and "enforcement" not in str(best["note"]).lower()
            ):
                best = candidate
    return best
