"""Pure transforms for the D5 Context extras (B-2/B-3/B-4 + plan Part 8).

Kept LLM-free and DB-free so they unit-test cleanly; the context router
feeds DB rows / JSONB in and serialises the results onto ``ContextResponse``.

- ``to_issue_register`` — ingested ``issue_register`` rows → DTOs, deriving
  OPEN/RESOLVED from ``resolved_on`` for the D5 issue Gantt.
- ``acquisitions_from_timeline`` — Part 8.3 acquisition FRAME extraction:
  a timeline row of kind='acquisition' surfaces on the acquisitions panel
  only when it carries a real M&A frame (event verb + ORG target, scoped
  to the entity), populating {target, acquirer, amount, status,
  announced_on/closed_on, details, e_id}. Strategy intent ("actively
  seeking"), complaints, negated absences and third-party/peer M&A are
  rejected (the audit measured 36% false positives).
- ``financials_view`` — Part 8.4: year-keys count ONLY when the key is a
  year (nlp.quantities.extract_year_series guard kills the
  [2022, 2025]→[2023, 87.5] harvest class); labelled per-metric series
  {metric, unit, fy[], values[]} with explicit unit/scale; prose fragments
  routed to ``lines[]`` — never rendered as metric keys.
- ``sentiment_view`` — Part 8.5: structured per-source rows {source, kind,
  value, max, n, polarity, themes[], drilldown, evidence_e_id}; merges
  rating+review-count fragments into one row.
- ``leadership_view`` — Part 8.6 (view-time): tenure_months from date
  phrases (nlp.dates), parentheticals stripped into ``note``, garbled
  non-person rows dropped or converted to explicit gap rows,
  critical-role/recent-hire flags.
- ``regulatory_view`` — license_type/charter + jurisdictions extracted
  from firmographics prose/parsed_facts (verbatim spans; honest-null).
- ``derive_trend_md`` — composes a grounded 1-2 sentence trend paragraph
  from the REAL financial series when the assessment report shipped none.

Never fabricates: every emitted field is a verbatim span or an arithmetic
consequence of parsed values.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.schemas.context import AcquisitionOut, IssueRegisterOut, TimelineEventOut
from app.services.nlp import dates as nlp_dates
from app.services.nlp import entities as nlp_entities
from app.services.nlp import polarity as nlp_polarity
from app.services.nlp.quantities import extract_year_series
from app.services.nlp.segment import clip_excerpt_verbatim

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_NUM_RE = re.compile(r"-?\$?\s*([\d,]+(?:\.\d+)?)\s*([BMK%]?)", re.I)
_MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "": 1.0, "%": 1.0}
_E_ID_RE = re.compile(r"\bE-?(\d{2,4})\b")


# Inline evidence citations as written by derive_issues / the analyst
# ("Observed in the research evidence [E-032]: …", "[E-020,E-042,E-052]")
# — bracketed only, so bare prose mentions of an E-ID ("Add E-NNN
# citations") never become anchors. Bracket groups may carry several ids.
_ISSUE_EID_GROUP_RE = re.compile(r"\[((?:E-\d{2,4}[,;\s]*)+)\]")
_ISSUE_EID_RE = re.compile(r"E-\d{2,4}")


def to_issue_register(rows: list[Any]) -> list[IssueRegisterOut]:
    out: list[IssueRegisterOut] = []
    for r in rows:
        resolved = getattr(r, "resolved_on", None)
        rationale = getattr(r, "rationale", None)
        # Read-time mining of the rationale's own [E-###] citations →
        # drawer-openable evidence anchors (order-preserving, deduped).
        e_ids: list[str] = []
        for grp in _ISSUE_EID_GROUP_RE.finditer(rationale or ""):
            for m in _ISSUE_EID_RE.finditer(grp.group(1)):
                if m.group(0) not in e_ids:
                    e_ids.append(m.group(0))
        # A rationale that merely repeats the title adds nothing in the
        # drilldown (title renders directly above it) — honest None.
        if rationale and rationale.strip() == (r.title or "").strip():
            rationale = None
        # Rationale reaches AEs verbatim in the drilldown — scrub internal
        # jargon / run-ids / raw subcap codes the same way narrative bodies
        # are (2026-07-14 vet: a rockland rationale carried a run-id +
        # "[P3C1.6.1] Score 1.0 (M1)"). E-ID anchors are mined ABOVE from the
        # raw text, and scrub_md preserves bracketed [E-###] citations, so the
        # drawer chips are unaffected.
        if rationale:
            from app.services.text_hygiene import scrub_md as _scrub_md
            rationale = _scrub_md(rationale)
        # Stored canonical status wins (a register can say SETTLED with
        # no resolution date — before 2026-07-06 that rendered OPEN
        # forever: 0/662 resolved across the whole pack); resolved_on
        # presence is the fallback for legacy rows.
        stored_status = getattr(r, "status", None)
        if stored_status in ("OPEN", "RESOLVED"):
            status = stored_status
        else:
            status = "RESOLVED" if resolved is not None else "OPEN"
        caps_raw = getattr(r, "caps", None) or {}
        caps: dict[str, float] = {}
        if isinstance(caps_raw, dict):
            for k, v in caps_raw.items():
                try:
                    caps[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
        # Issue titles reach AEs verbatim — run them through the same
        # deterministic polish the narrative fields get (S14 accusatory-
        # title class: deficit leads rewritten; validated-absence wording
        # and E-ID/number anchors preserved by the rewrite validator).
        from app.services.narrative_polish import polish_narrative
        title = polish_narrative(
            r.title, target_kind="section",
            target_id=f"{r.id}:issue-title",
        ) or r.title
        out.append(
            IssueRegisterOut(
                id=str(r.id),
                issue_id=r.issue_id,
                title=title,
                severity=r.severity,
                rationale=rationale,
                opened_on=getattr(r, "opened_on", None),
                resolved_on=resolved,
                status=status,
                linked_subcap_ids=list(getattr(r, "linked_subcap_ids", None) or []),
                evidence_e_ids=e_ids[:4],
                kind=getattr(r, "kind", None) or "client",
                dma_impact=getattr(r, "dma_impact", None),
                caps=caps,
            )
        )
    return out


_REG_ISSUE_RE = re.compile(
    r"regulat|complian|enforc|consent|licen[cs]|bsa|aml|cfpb|sanction",
    re.IGNORECASE,
)


def has_open_regulatory_issue(issues: list[IssueRegisterOut]) -> bool:
    """True when the run's issue register carries an OPEN regulatory item.

    Gates the clean-standing signal (Part 8.2 step 3): the corpus's
    negative-search notes must never claim clean standing while an open
    enforcement/compliance issue exists in the same package.
    """
    return any(
        i.status == "OPEN" and _REG_ISSUE_RE.search(f"{i.issue_id} {i.title}")
        for i in issues
    )


# ── Part 8.3 · Acquisition frames ──────────────────────────────────────────

_ACQ_VERB_RE = re.compile(
    r"\bacquired\b|\bacquisition of\b|\bmerger of\b|\bmerged with\b|"
    r"\bmerger with\b|\btook over\b|\btakeover of\b|\bbuyout of\b|"
    r"\bpurchased\b|\bcompleted (?:the )?(?:acquisition|merger)\b",
    re.IGNORECASE,
)
_ACQ_REJECT_RE = re.compile(
    r"\bactively\s+seeking|\bseeking\s+to\b|\bexplor(?:e|ing)\b|"
    r"\bconsider(?:ing)?\b|\bplans?\s+to\b|\bintends?\s+to\b|\bwould\b|"
    r"\bcould\b|\bpotential\b|\bhypothetical|\bcomplain\w*|\breviews?\b|"
    r"\brating\b|\bsentiment\b|app\s+store|glassdoor|\bbbb\b|"
    r"\banalogous\b|pattern\s+to|different\s+entity|\bpeer\b|\be\.g\.",
    re.IGNORECASE,
)
_ACQ_STATUS_CLOSED_RE = re.compile(
    r"\b(?:completed|closed|finali[sz]ed|legal\s+merger|fully\s+integrated|"
    r"became\s+effective)\b",
    re.IGNORECASE,
)
_ACQ_STATUS_INTEGRATING_RE = re.compile(r"\bintegrat(?:ion|ing)\b", re.IGNORECASE)
_ACQ_STATUS_ANNOUNCED_RE = re.compile(
    r"\bannounced\b|definitive\s+agreement|agreement\s+to|\bsigned\b|"
    r"intent\s+to|\bapproved\b|member\s+vote",
    re.IGNORECASE,
)
# Generic FSI words that carry no identity — excluded from entity tokens.
_GENERIC_NAME_TOKENS = frozenset({
    "bank", "banks", "bancorp", "bancshares", "credit", "union", "unions",
    "financial", "finance", "trust", "company", "corporation", "corp", "inc",
    "group", "holdings", "federal", "national", "association", "the", "of",
    "and", "limited", "ltd", "llc", "co", "cu", "fcu", "n.a", "na",
})
# A bare-ORG title (curated DOCX Acquisition-History rows): short, no verb,
# and actually organisation-shaped (FSI suffix) — "Interlake Insurance",
# "Carpathia Credit Union", "Hudson Valley CU branches".
_ORG_TITLE_RE = re.compile(
    r"^[A-Z][\w&.'-]*(?:\s+[A-Za-z][\w&.'-]*){0,5}$"
)
_ORG_SUFFIX_RE = re.compile(
    r"\b(?:Bank|Bancorp|Bancshares|Credit\s+Union|CU|FCU|Financial|Insurance|"
    r"Holdings|Trust|Capital|Partners|Mortgage|Leasing|Wealth|Advisors?|"
    r"Group|Inc\.?|Corp\.?|LLC|Ltd\.?|branches)\b"
)


def _bare_target(title: str) -> str:
    """Strip trailing M&A verb tails from a bare-org title ("Capital Bank
    acquired 2011" → "Capital Bank") so the target is the organisation."""
    return re.sub(
        r"\s+(?:acquired|acquisition|merged?|merger|purchased|buyout|"
        r"takeover)\b.*$",
        "", title, flags=re.IGNORECASE,
    ).strip(" ,–—-")  # noqa: RUF001


def _org_shaped_title(title: str) -> bool:
    t = (title or "").strip()
    if not t or len(t) > 60 or not _ORG_TITLE_RE.match(t):
        return False
    if _ORG_SUFFIX_RE.search(t):
        return True
    # spaCy tier: an ORG span covering most of the title.
    orgs = _org_spans(t)
    return any((o["end"] - o["start"]) >= 0.6 * len(t) for o in orgs)


def _entity_tokens(entity_name: str | None) -> set[str]:
    if not entity_name:
        return set()
    words = re.findall(r"[A-Za-z][\w'-]*", entity_name)
    tokens = {
        w.lower() for w in words
        if len(w) >= 3 and w.lower() not in _GENERIC_NAME_TOKENS
    }
    # Acronym ("American Airlines Federal Credit Union" → AAFCU) + the
    # name itself when it already IS an acronym.
    if len(words) >= 2:
        tokens.add("".join(w[0] for w in words).lower())
    if len(words) == 1:
        tokens.add(words[0].lower())
    return tokens


def _mentions_entity(text: str, tokens: set[str]) -> bool:
    if not tokens:
        return True  # can't scope without a name — frame check must carry it
    low = text.lower()
    if any(re.search(rf"\b{re.escape(t)}\b", low) for t in tokens):
        return True
    # Acronym/compact forms: reports write "APGFCU" for "APG Federal
    # Credit Union" — the 2026-07-04 deep search found real M&A frames
    # rejected because the compact form never token-matches. A candidate
    # whose compacted letters START with a distinctive (≥3-char) entity
    # token is the same institution ("apgfcu".startswith("apg")).
    compact = re.sub(r"[^a-z0-9]", "", low)
    return bool(compact) and any(
        len(t) >= 3 and compact.startswith(t) for t in tokens)


def _org_spans(text: str) -> list[dict]:
    # Money spans mis-tagged ORG ("~$420M") carry no identity — drop them.
    return [
        o for o in nlp_entities.extract(text).get("orgs", [])
        if "$" not in o["text"]
    ]


# Capitalized-phrase fallback for participants NER misses ("merger of
# Access + Noventis + Sunova CUs" — bare names carry no ORG suffix).
_CAPS_PHRASE_RE = re.compile(
    r"[A-Z][\w&.'-]*(?:\s+(?:[A-Z][\w&.'-]*|CUs?|branches))*"
)
_PARTICIPANT_STOP_RE = re.compile(r"[(;:.]| in | on | from | for ")


def _caps_participants_after(text: str, pos: int, window: int = 90) -> list[dict]:
    """ORG-shaped pseudo-spans from capitalized phrases after ``pos``."""
    segment = text[pos : pos + window]
    stop = _PARTICIPANT_STOP_RE.search(segment)
    if stop:
        segment = segment[: stop.start()]
    out: list[dict] = []
    for m in _CAPS_PHRASE_RE.finditer(segment):
        phrase = m.group(0).strip(" ,+&")
        if not phrase or phrase.lower() in _GENERIC_NAME_TOKENS:
            continue
        out.append({
            "text": phrase, "start": pos + m.start(),
            "end": pos + m.start() + len(phrase), "norm": phrase,
        })
    return out


def _nearest_org(orgs: list[dict], *, before: int | None = None,
                 after: int | None = None, window: int = 70) -> dict | None:
    best: dict | None = None
    best_gap = window + 1
    for org in orgs:
        if before is not None and org["end"] <= before:
            gap = before - org["end"]
        elif after is not None and org["start"] >= after:
            gap = org["start"] - after
        else:
            continue
        if gap < best_gap:
            best, best_gap = org, gap
    return best


def _verb_clause(text: str) -> str:
    """The clause containing the M&A verb — frames must not cross ';'/'.'
    boundaries ("Capital Bank acquired 2011; Canal Bank launched 2024"
    must not read Canal Bank as the target). Parentheticals (stock
    tickers, region notes) are stripped FIRST so a ';' inside "(TSX:GIB.A;
    NYSE:GIB)" cannot shear the subject off its verb."""
    text = re.sub(r"\([^()]{0,80}\)", " ", text)
    for seg in re.split(r"(?<=[;.])\s+|;", text):
        if _ACQ_VERB_RE.search(seg):
            return re.sub(r"\s+", " ", seg).strip()
    return re.sub(r"\s+", " ", text).strip()


# "X acquired 2011" — researcher shorthand meaning X WAS acquired then.
_PASSIVE_SHORTHAND_RE = re.compile(
    r"\b(?:acquired|purchased)\s*(?:in\s+)?(?:(?:19|20)\d{2}\b|$)", re.IGNORECASE,
)


def _acq_frame(
    text: str, entity_name: str | None, tokens: set[str],
) -> tuple[str | None, str | None] | None:
    """(acquirer, target) when ``text`` carries a real M&A frame, else None."""
    text = _verb_clause(text)
    verb = _ACQ_VERB_RE.search(text)
    if not verb:
        return None
    orgs = _org_spans(text)
    verb_text = verb.group(0).lower()

    # "acquisition of Y (by X)" / "merger of A + B" — participants follow.
    if verb_text.startswith(("acquisition of", "merger of", "takeover of",
                             "buyout of")):
        after = [o for o in orgs if o["start"] >= verb.end()
                 and o["start"] - verb.end() <= 90]
        if not after:
            # NER misses bare capitalized participants — caps-phrase tier.
            after = _caps_participants_after(text, verb.end())
        if not after:
            return None
        by = re.search(r"\bby\s+", text[verb.end():])
        acquirer: str | None = None
        target_orgs = after
        if by:
            by_pos = verb.end() + by.end()
            by_org = _nearest_org(orgs, after=by_pos, window=40)
            if by_org:
                acquirer = by_org["norm"] or by_org["text"]
                target_orgs = [o for o in after if o is not by_org]
        if verb_text.startswith("merger of") and acquirer is None:
            own = [o for o in target_orgs
                   if _mentions_entity(o["text"], tokens) and tokens]
            if own:
                acquirer = own[0]["norm"] or own[0]["text"]
                target_orgs = [o for o in target_orgs if o is not own[0]]
        target = " + ".join(
            (o["norm"] or o["text"]) for o in target_orgs[:3]
        ) or None
        return (acquirer, target) if target else None

    # "X acquired/merged with/took over/purchased Y".
    before_org = _nearest_org(orgs, before=verb.start())
    after_org = _nearest_org(orgs, after=verb.end())
    acquirer = (before_org["norm"] or before_org["text"]) if before_org else None
    target = (after_org["norm"] or after_org["text"]) if after_org else None
    if acquirer is None:
        # Caps-phrase tier for a subject NER missed ("Capital Bank acquired…").
        m = re.search(r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})\s*$",
                      text[: verb.start()])
        if m and m.group(1).lower() not in _GENERIC_NAME_TOKENS:
            acquirer = m.group(1)
    if target is None:
        caps_after = _caps_participants_after(text, verb.end(), window=60)
        if caps_after:
            target = caps_after[0]["norm"]
    if target is None:
        # Passive shorthand ("Capital Bank acquired 2011") — the named org
        # WAS acquired; the entity is the implied acquirer unless the org
        # is the entity itself.
        if (
            acquirer is not None
            and _PASSIVE_SHORTHAND_RE.search(text[verb.start():])
            and not (tokens and _mentions_entity(acquirer, tokens))
        ):
            return (entity_name, acquirer)
        return None
    if acquirer is None:
        # Implied subject ("Acquired Interlake Insurance subsidiary in 2024")
        # — the report speaks about the entity itself. The prefix must carry
        # NO capitalized token (an unrecognized proper noun there means the
        # subject is someone else, not the entity).
        clause_start = max(text.rfind(".", 0, verb.start()),
                           text.rfind(";", 0, verb.start()))
        prefix = text[clause_start + 1 : verb.start()].strip(" —–-")  # noqa: RUF001
        if len(prefix.split()) <= 3 and not re.search(r"\b[A-Z][\w.]*", prefix):
            acquirer = entity_name
    return (acquirer, target)


def _acq_status(text: str) -> str | None:
    if _ACQ_STATUS_CLOSED_RE.search(text):
        return "closed"
    if _ACQ_STATUS_INTEGRATING_RE.search(text):
        return "integrating"
    if _ACQ_STATUS_ANNOUNCED_RE.search(text):
        return "announced"
    return None


def _acq_amount(text: str) -> str | None:
    """Verbatim deal-size string near ANY M&A verb occurrence, else None."""
    money = nlp_entities.extract(text).get("money", [])
    if not money:
        return None
    verb_positions = [m.start() for m in _ACQ_VERB_RE.finditer(text)]
    if verb_positions:
        near = [
            m for m in money
            if any(abs(m["start"] - p) <= 90 for p in verb_positions)
        ]
        if near:
            return near[0]["text"].strip()
        return None
    return money[0]["text"].strip()


def acquisitions_from_timeline(
    timeline: list[TimelineEventOut],
    entity_name: str | None = None,
) -> list[AcquisitionOut]:
    """Timeline kind='acquisition' rows → structured, frame-validated ACQ rows.

    Requires an acquisition frame (M&A event verb + ORG target via
    ``nlp.entities``) scoped to the entity; curated bare-ORG rows (the
    Client-Profile "Acquisition History" table emits just the target name)
    are kept with the entity as implied acquirer. Everything else —
    negated absences, strategy intent, complaints, peer/vendor M&A —
    is rejected. Audit target: FP < 5%.
    """
    tokens = _entity_tokens(entity_name)
    out: list[AcquisitionOut] = []
    for t in timeline:
        if (t.kind or "").strip().lower() != "acquisition":
            continue
        text = f"{t.title}. {t.body}" if t.body else (t.title or "")
        if not text.strip():
            continue
        if nlp_polarity.is_negated_absence(text):
            continue
        if _ACQ_REJECT_RE.search(text):
            continue
        frame = _acq_frame(text, entity_name, tokens)
        if frame is not None:
            acquirer, target = frame
            if tokens and acquirer is None:
                # Unattributable subject — cannot claim it for this entity.
                continue
            # Third-party/peer M&A: a frame that never involves the entity
            # is not THIS client's acquisition history.
            if tokens and acquirer is not None and acquirer != entity_name \
                    and not (_mentions_entity(str(acquirer), tokens)
                             or _mentions_entity(str(target or ""), tokens)):
                continue
        elif _org_shaped_title(_bare_target(t.title or "")):
            # Curated Acquisition-History table row: title IS the target.
            acquirer, target = entity_name, _bare_target(t.title.strip())
        else:
            continue  # no frame → not a verifiable acquisition
        status = _acq_status(text)
        evidence = list(getattr(t, "evidence_e_ids", None) or [])
        e_id = evidence[0] if evidence else t.e_id
        out.append(
            AcquisitionOut(
                id=t.id,
                event_date=t.event_date,
                title=t.title,
                body=t.body,
                source_url=t.source_url,
                e_id=e_id,
                target=target,
                acquirer=acquirer,
                amount=_acq_amount(text),
                status=status,
                announced_on=t.event_date if status == "announced" else None,
                closed_on=t.event_date if status == "closed" else None,
                # Verbatim mandate: drop whole trailing sentences only
                # (ellipsis-marked) — never a mid-claim cut.
                details=clip_excerpt_verbatim(t.body or "", 500) or None,
            )
        )
    return out


# ── Part 8.4 · Financials ──────────────────────────────────────────────────

def _coerce_number(raw: str) -> float | None:
    m = _NUM_RE.search(raw)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return val * _MULT.get(m.group(2).lower(), 1.0)


def _is_prose_fragment(key: str, value: Any) -> bool:
    """True when a metrics pair is a shredded prose sentence, not a metric.

    The audit's 12 prose-keys ("b_asset_threshold_crossing_appears_
    achievable_within_1", "a-driven_scale-up_2022", "member_cagr" →
    "7.0% | Net Income Growth…") come from upstream sentence-splitting on
    ':' — they are defended here (the parse path is D1-owned) and routed
    to ``lines[]``.
    """
    k = str(key)
    if len(k) > 28:
        return True
    if len(re.findall(r"[a-z0-9]+", k.lower())) >= 5:
        return True
    if isinstance(value, str):
        v = value.strip()
        if len(v) > 60 or v.count(" ") >= 9:
            return True
        if "|" in v or "\u2014" in v:  # em-dash marks prose tails
            return True
        if v.endswith((":", "+", "-")):
            return True
    return False


# Canonical metric-name + unit inference from suffixed keys
# ("Total_Assets_B" → total_assets/usd_b, "NIM_Pct" → nim/pct).
_METRIC_SUFFIX_UNITS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"_b$", re.I), "usd_b"),
    (re.compile(r"_m$", re.I), "usd_m"),
    (re.compile(r"_k$", re.I), "usd_k"),
    (re.compile(r"_pct$|_percent$", re.I), "pct"),
)
_COUNT_METRIC_RE = re.compile(
    r"branch|member|employee|customer|user|location|office|atm|advisor|fte",
    re.IGNORECASE,
)
_METRIC_VALUE_YEAR_RE = re.compile(
    r"^([\-+]?[\d,]+(?:\.\d+)?)\s*\+?\s*\(((?:19|20)\d{2})\)$"
)


def _canon_metric(key: str) -> tuple[str, str | None]:
    """("Total_Assets_B") → ("total_assets", "usd_b"); unit None if unknown."""
    unit: str | None = None
    name = str(key).strip()
    for pat, u in _METRIC_SUFFIX_UNITS:
        if pat.search(name):
            unit = u
            name = pat.sub("", name)
            break
    canon = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if unit is None and _COUNT_METRIC_RE.search(canon):
        unit = "count"
    return canon, unit


def _infer_series_label(
    series: dict[int, float], metrics: dict[str, Any],
) -> tuple[str, str]:
    """Label an anonymous year series by matching a `<num> (<year>)` metric.

    Sunflower's ``series`` {2026: 20.4} matches ``Total_Assets_B``
    "20.4 (2026)" → (total_assets, usd_b). Falls back to ("value",
    "unknown") — the chart still renders, honestly unlabelled.
    """
    for key, raw in metrics.items():
        if not isinstance(raw, str):
            continue
        m = _METRIC_VALUE_YEAR_RE.match(raw.strip())
        if not m:
            continue
        try:
            val, year = float(m.group(1).replace(",", "")), int(m.group(2))
        except ValueError:
            continue
        got = series.get(year)
        if got is not None and abs(got - val) <= max(0.005 * abs(val), 1e-9):
            canon, unit = _canon_metric(key)
            return canon, unit or "unknown"
    # Absolute-USD series (year-keyed "$1.2B" strings normalise to 1.2e9).
    if series and all(abs(v) >= 1e5 for v in series.values()):
        return "value", "usd"
    return "value", "unknown"


_CARD_UNIT_TO_LABELED = {"B": "usd_b", "M": "usd_m", "K": "usd_k"}


def _mine_prose_series(financial_highlights: dict | None) -> list[dict[str, Any]]:
    """Prose-mined labelled series via the D1 trajectory engine.

    ``overview_cards.financial_trajectory_card`` already extracts aligned
    year→$ series out of highlight PROSE ("grew from $2.286B in 2021 to
    $3.209B in 2025") — reuse it verbatim (one engine, two surfaces) and
    reshape its ``{fy[], series{metric: values}}`` into the Part 8.4
    ``[{metric, unit, fy[], values[]}]`` contract. Per-metric fy axes are
    trimmed to the years that metric actually has (no null bars). Money
    units map B/M/K → usd_b/usd_m/usd_k; ``*_pct`` metrics label as pct."""
    from app.services.overview_cards import financial_trajectory_card

    card = financial_trajectory_card(financial_highlights)
    if not card or not card.get("fy") or not card.get("series"):
        return []
    fy = card["fy"]
    unit = _CARD_UNIT_TO_LABELED.get(str(card.get("unit") or "").upper(), "usd_b")
    out: list[dict[str, Any]] = []
    for metric, values in card["series"].items():
        # A metric whose value list is None/empty (a card can carry a metric
        # key with no aligned series) must be skipped — not fed to zip(), which
        # would raise TypeError and abort the whole context derive (2026-07-06:
        # this crash was silently rolling back timeline/regulatory/acquisition
        # persistence, leaving the context page empty for most clients).
        if not isinstance(values, list | tuple):
            continue
        pairs = [(y, v) for y, v in zip(fy, values, strict=False) if v is not None]
        if len(pairs) < 2:
            continue
        out.append({
            "metric": metric,
            "unit": "pct" if str(metric).endswith("_pct") else unit,
            "fy": [y for y, _ in pairs],
            "values": [v for _, v in pairs],
        })
    return out


def financials_view(financial_highlights: dict | None) -> dict | None:
    """Shape the flat highlights dict into a renderable financial view.

    Output: ``{years, series, series_labeled, metrics, lines}`` — all
    optional; ``years``/``series`` keep the legacy shape for older
    consumers, ``series_labeled`` is the Part 8.4 contract
    ``[{metric, unit, fy[], values[]}]``. Year alignment goes through
    ``nlp.quantities.extract_year_series`` so a year is a series point
    ONLY when the KEY is a year — the spurious [2022, 2025] → [2023,
    87.5] harvest class cannot recur. Prose fragments route to ``lines``.
    Returns None when there is nothing to show (honest skeleton).
    """
    if not financial_highlights:
        return None

    fh = dict(financial_highlights)
    lines: list[str] = list(fh.pop("lines", None) or [])
    fh.pop("derived_from", None)  # provenance, not a metric
    # The guarded trajectory is NEVER a kv metric (it rendered as the
    # literal string "[object Object]" in the D5 kv-grid, 2026-07-06
    # deploy review) — it is the PRIMARY chart axis, lifted below.
    traj = fh.pop("trajectory", None)
    traj_labeled: list[dict[str, Any]] = []
    if isinstance(traj, dict) and isinstance(traj.get("series"), dict):
        fy_years = [int(str(f)[2:]) for f in (traj.get("fy") or [])
                    if str(f)[2:].isdigit()]
        for key, metric, unit in (("total_assets", "total_assets", "usd_b"),
                                  ("net_income_m", "net_income", "usd_m")):
            vals = traj["series"].get(key)
            if not isinstance(vals, list):
                continue
            pairs = [(y, v) for y, v in zip(fy_years, vals, strict=False)
                     if isinstance(v, int | float)]
            if len(pairs) >= 2:   # per-metric axis trimmed — no null bars
                traj_labeled.append({
                    "metric": metric, "unit": unit,
                    "fy": [y for y, _ in pairs],
                    "values": [float(v) for _, v in pairs],
                })

    # Pre-structured series wins for the year axis; remaining top-level
    # year-fullmatch keys feed it too (guarded — keys only).
    year_to_val: dict[int, float] = {}
    pre = fh.pop("series", None) or fh.pop("by_year", None)
    if isinstance(pre, dict) and pre:
        year_to_val.update(extract_year_series(pre))
    top_level = extract_year_series(fh)
    for y, v in top_level.items():
        year_to_val.setdefault(y, v)
    year_keys = {k for k in fh if re.fullmatch(r"(?:FY\s?)?(?:19|20)\d{2}",
                                               str(k).strip())}

    metrics: dict[str, Any] = {}
    prose_pairs: list[str] = []
    for k, v in fh.items():
        if k in year_keys:
            continue
        if _is_prose_fragment(k, v):
            prose_pairs.append(f"{str(k).replace('_', ' ')}: {v}")
            continue
        metrics[k] = v

    view: dict[str, Any] = {}
    series_labeled: list[dict[str, Any]] = []
    if traj_labeled:
        # D5 charts the SAME guarded series the D1 Overview card renders
        # (wave 2): the trajectory axis is outlier-dropped/unit-rescued at
        # derive time, so it always wins over re-mining the raw keys.
        series_labeled = traj_labeled
        view["years"] = traj_labeled[0]["fy"]
        view["series"] = {"value": traj_labeled[0]["values"]}
    elif year_to_val:
        years = sorted(year_to_val)
        values = [year_to_val[y] for y in years]
        view["years"] = years
        view["series"] = {"value": values}
        metric, unit = _infer_series_label(year_to_val, metrics)
        series_labeled.append(
            {"metric": metric, "unit": unit, "fy": years, "values": values}
        )
    if not any(len(s["fy"]) >= 2 for s in series_labeled):
        # Shared engine with the D1 FinancialTrajectoryCard (Part 8.4):
        # most packs carry the multi-year series only as PROSE ("Total
        # assets grew from $2.286B in 2021 to $3.209B in 2025") — the
        # all-94 rendered sweep found 81 clients whose context chart was
        # empty while D1 charted the same highlights. Mine the prose
        # with the same extractor so both surfaces agree.
        mined = _mine_prose_series(financial_highlights)
        if mined:
            series_labeled = mined
            first = mined[0]
            view["years"] = first["fy"]
            view["series"] = {"value": first["values"]}
    if series_labeled:
        view["series_labeled"] = series_labeled
    if isinstance(traj, dict):
        view["trajectory"] = traj   # headline/anomalies for the trend tier
    if metrics:
        view["metrics"] = metrics
    if not lines and prose_pairs:
        # The shredded source sentence is not otherwise represented —
        # surface it as narrative lines rather than losing it.
        lines = prose_pairs
    if lines:
        view["lines"] = lines

    return view or None


# ── Part 8.5 · Sentiment ───────────────────────────────────────────────────

_RATING_SLASH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
_RATING_STARS_RE = re.compile(r"(\d+(?:\.\d+)?)[\s-]*stars?\b", re.IGNORECASE)
_RATING_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_BARE_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
_N_RE = re.compile(r"(\d[\d,]*)\s*\+?\s*(?:reviews?|ratings?|complaints?|responses?)",
                   re.IGNORECASE)
_FRAGMENT_SUFFIX_RE = re.compile(
    r"\s+(rating|reviews?|review\s+count|score|volume)$", re.IGNORECASE,
)
_SOURCE_KIND: tuple[tuple[re.Pattern[str], str], ...] = (
    # NPS is its own metric kind — a -100..+100 index, never an n or a /5
    # score (Compeer's tile rendered "Net Promoter · n=22"; 2026-07-06).
    (re.compile(r"\bnps\b|\benps\b|net\s+promoter", re.I), "nps"),
    (re.compile(r"glassdoor|indeed|comparably", re.I), "employee"),
    (re.compile(r"app\s*store|google\s*play|mobile", re.I), "mobile"),
    (re.compile(r"bbb|better\s+business|cfpb|complaint|trustpilot|"
                r"deposit\s*accounts", re.I), "customer"),
    (re.compile(r"bauer|weiss|s&p|moody|fitch|a\.?m\.?\s*best", re.I), "industry"),
    (re.compile(r"linkedin|twitter|facebook|social", re.I), "social"),
)
_NPS_VALUE_RE = re.compile(r"^\s*([+-]?\d{1,3}(?:\.\d{1,2})?)\s*$")
_COUNTABLE_SRC_RE = re.compile(r"complaint|reviews?\b", re.I)
_POS_TOKEN_RE = re.compile(r"\bpositive|improving|superior|strong\b", re.IGNORECASE)
_NEG_TOKEN_RE = re.compile(r"\bnegative|declining|weak|poor\b", re.IGNORECASE)


def _source_kind(source: str) -> str:
    for pat, kind in _SOURCE_KIND:
        if pat.search(source):
            return kind
    return "other"


def _parse_rating(raw: str) -> tuple[float | None, float | None]:
    """A rating string → (value, max); (None, None) when not a rating."""
    s = (raw or "").strip()
    if not s:
        return None, None
    m = _RATING_SLASH_RE.search(s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _RATING_STARS_RE.search(s)
    if m:
        return float(m.group(1)), 5.0
    m = _RATING_PCT_RE.search(s)
    if m:
        return float(m.group(1)), 100.0
    m = _BARE_NUM_RE.match(s)
    if m:
        v = float(m.group(1))
        if v <= 5:
            return v, 5.0
        return None, None  # bare large number — count, not a rating
    return None, None


def _clean_drilldown(raw: str) -> str | None:
    s = re.sub(r"\s+", " ", raw or "").strip()
    # Shredded leading fragments ("g: 12 consecutive years…").
    s = re.sub(r"^[a-z]{1,2}[:;,]\s*", "", s)
    if len(s) < 12:
        return None
    # Verbatim mandate: a long drilldown keeps whole sentences (ellipsis
    # marks the dropped tail) — never a mid-claim word cut.
    return clip_excerpt_verbatim(s, 260)


def sentiment_view(sentiment: dict | None) -> dict | None:
    """Normalise the firmographics.sentiment JSONB to structured rows.

    ``{sources: [{source, kind, value, max, n, polarity, themes[],
    drilldown, evidence_e_id}], derived_from?}``. Rating+review-count
    fragments ("Glassdoor Rating" 3.8 + "Glassdoor Reviews" 59) merge
    into one row (value 3.8/5, n=59). Unparseable rating strings stay
    honest: value None, raw text preserved in the drilldown.
    """
    if not sentiment:
        return None
    raw_sources = sentiment.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        return None

    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        source_full = str(raw.get("source") or "").strip()
        if not source_full:
            continue
        base = _FRAGMENT_SUFFIX_RE.sub("", source_full).strip() or source_full
        key = base.lower()
        row = merged.get(key)
        if row is None:
            row = {
                "source": base, "kind": _source_kind(base),
                "value": None, "max": None, "n": None, "polarity": None,
                "themes": [], "drilldown": None, "evidence_e_id": None,
            }
            merged[key] = row
            order.append(key)

        rating_raw = str(raw.get("rating") or "").strip()
        is_count_fragment = bool(
            _FRAGMENT_SUFFIX_RE.search(source_full)
            and re.search(r"reviews?|count|volume", source_full, re.I)
        )
        if row["kind"] == "nps" or raw.get("kind") == "nps":
            # the bare/signed index IS the value — before wave 2 it fell
            # into the bare-number branch and rendered as the sample size.
            row["kind"] = "nps"
            m = _NPS_VALUE_RE.match(rating_raw)
            if (m and row["value"] is None and abs(float(m.group(1))) <= 100
                    and not _RATING_SLASH_RE.search(rating_raw)):
                row["value"], row["max"] = float(m.group(1)), None
            elif rating_raw and row["value"] is None:
                v2, m2 = _parse_rating(rating_raw)   # "9.7/10"-style rating
                if v2 is not None and m2 in (5.0, 10.0):
                    row["value"], row["max"] = v2, m2
        else:
            value, vmax = _parse_rating(rating_raw)
            if value is not None and not is_count_fragment and row["value"] is None:
                row["value"], row["max"] = value, vmax
            elif rating_raw and value is None or is_count_fragment:
                # A bare integer is the sample size ONLY on a count-shaped
                # fragment ("…Reviews") or a countable source (complaints)
                # — an unparsed RATING must never masquerade as n.
                m = _BARE_NUM_RE.match(rating_raw)
                if m and row["n"] is None and (
                        is_count_fragment or _COUNTABLE_SRC_RE.search(base)):
                    n = float(m.group(1))
                    if n > 5 or is_count_fragment:
                        row["n"] = int(n)

        prose_bits = [str(raw.get(k) or "") for k in ("signal", "drilldown", "notes")]
        prose = " ".join(b for b in prose_bits if b).strip()
        volume = str(raw.get("volume") or "")
        for hay in (volume, prose):
            if row["n"] is None and hay:
                m = _N_RE.search(hay)
                if m:
                    row["n"] = int(m.group(1).replace(",", ""))
        if row["value"] is None and prose:
            # e.g. "Glassdoor rating of 3.8/5 across 310+ reviews" in prose.
            v2, m2 = _parse_rating(prose)
            if v2 is not None and m2 == 5.0:
                row["value"], row["max"] = v2, m2

        themes_raw = str(raw.get("themes") or "")
        if themes_raw:
            for theme in re.split(r"[;•|]", themes_raw):
                theme = theme.strip()
                if theme and theme not in row["themes"]:
                    row["themes"].append(theme)
        row["themes"] = row["themes"][:4]

        if row["drilldown"] is None:
            row["drilldown"] = _clean_drilldown(prose)
        if row["evidence_e_id"] is None:
            m = _E_ID_RE.search(prose)
            if m:
                row["evidence_e_id"] = f"E-{m.group(1)}"

        trend = str(raw.get("trend") or "")
        tone_hay = " ".join([trend, rating_raw, themes_raw])
        if row["polarity"] is None:
            if _NEG_TOKEN_RE.search(tone_hay):
                row["polarity"] = "negative"
            elif _POS_TOKEN_RE.search(tone_hay):
                row["polarity"] = "positive"
        if trend and not row.get("trend"):
            row["trend"] = trend

    out_rows: list[dict[str, Any]] = []
    for key in order:
        row = merged[key]
        if row["polarity"] is None:
            hay = " ".join([*row["themes"], row["drilldown"] or ""])
            row["polarity"] = nlp_polarity.signal(hay) if hay.strip() else "neutral"
        out_rows.append(row)
    if not out_rows:
        return None
    view: dict[str, Any] = {"sources": out_rows}
    if sentiment.get("derived_from"):
        view["derived_from"] = sentiment["derived_from"]
    return view


# ── Part 8.6 · Leadership (view-time) ──────────────────────────────────────

_PAREN_RE = re.compile(r"\s*\(([^()]{1,60})\)")
_ROLE_TOKEN_RE = re.compile(
    r"\b(CEO|CFO|CTO|CIO|CISO|CDO|COO|CRO|CMO|CHRO|president|chief|chair|"
    r"director|officer|head\b|EVP|SVP|VP)\b",
    re.IGNORECASE,
)
_CRITICAL_ROLE_RE = re.compile(
    r"\b(CISO|CTO|CIO|CDO)\b|chief\s+(information\s+security|technology|"
    r"information|data|digital)\s+officer",
    re.IGNORECASE,
)
_GARBLE_RE = re.compile(
    r"\b(not\s+yet|confirmed|identified|via|per\b|proxy|search|recent|"
    r"within|months?|unknown|n/?a|none|pending|transition)\b",
    re.IGNORECASE,
)
_TENURE_PHRASE_RE = re.compile(
    r"\b(?:joined|hired|appointed|since|started|named|promoted)\b[^.;]{0,40}",
    re.IGNORECASE,
)
_TENURE_NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(years?|yrs?|months?|mos?)\b", re.IGNORECASE,
)
# "N-year veteran", "19-year", "30+ year" tenure phrasing (not "N years old").
_TENURE_NYEAR_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*[-\s]?(?:year|yr)s?\b(?![-\s]old)", re.I)
# bare appointment date the verb-anchored phrase RE misses: "(Aug 2024)",
# "(since 1991)", a leading "Aug 2024)" background clip, or a bare "(2019)".
_APPT_DATE_RE = re.compile(
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+((?:19|20)\d{2})"
    r"|\((?:since\s+|appointed\s+|est\.?\s+)?((?:19|20)\d{2})\)",
    re.I,
)
_GAP_ROLES_RE = re.compile(r"\b(CISO|CTO|CIO|CDO|CFO|COO|CEO)\b")


def tenure_months_from_text(text: str, today: date | None = None) -> int | None:
    """Months of tenure from any date/duration phrase in free text.

    Ladder (first hit wins, never fabricates): verb-anchored appointment
    dates ("joined/since/appointed … 2019" via nlp.dates) → "N-year"/"30+
    year" veteran phrasing → bare month-year / "(1991)" appointment clips.
    Used by ``leadership_view`` (serve-time) and the derive_context tenure
    fill (source-register mining) so both share one grounded interpreter.
    """
    today = today or date.today()
    if not text:
        return None
    tm = _tenure_from_text(text, today)
    if tm is not None:
        return tm
    m = _TENURE_NYEAR_RE.search(text)
    if m:
        n = int(m.group(1))
        if 0 < n <= 60:
            return n * 12
    for m in _APPT_DATE_RE.finditer(text):
        yr = int(m.group(1) or m.group(2))
        if 1950 <= yr <= today.year:
            return max(0, (today.year - yr) * 12)
    return None


def _person_like(name: str) -> bool:
    n = (name or "").strip()
    if not n or len(n) > 40 or any(ch.isdigit() for ch in n):
        return False
    if _GARBLE_RE.search(n):
        return False
    words = n.split()
    if not 2 <= len(words) <= 5:
        return False
    return all(w[0].isupper() or w[0] in "'-" or w.rstrip(".").isupper()
               for w in words if w)


def _tenure_from_text(text: str, today: date) -> int | None:
    """Months of tenure from a date phrase ("joined May 2026", "since 2019")."""
    if not text:
        return None
    for m in _TENURE_PHRASE_RE.finditer(text):
        resolved, precision = nlp_dates.resolve_event_date(m.group(0))
        if resolved is None or precision in {"none", "publish_fallback"}:
            continue
        if resolved > today:
            continue
        return max(0, (today.year - resolved.year) * 12
                   + (today.month - resolved.month))
    return None


def _tenure_from_value(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return int(raw) if raw >= 0 else None
    m = _TENURE_NUM_RE.search(str(raw))
    if not m:
        return None
    n = float(m.group(1))
    return round(n * 12) if m.group(2).lower().startswith("y") else round(n)


def leadership_view(
    rows: list | None, *, today: date | None = None,
) -> list[dict[str, Any]]:
    """Clean + enrich leadership rows for the D5 leadership panel.

    - parentheticals stripped from names into ``note``;
    - garbled non-person rows dropped, or converted to explicit ``gap_flag``
      rows when they name missing critical roles ("NO NAMED CDO CTO CISO");
    - ``tenure_months`` from explicit numbers or date phrases (nlp.dates);
    - ``critical_role`` (security/data/technology seats), ``recent_hire``
      (≤ 6 months) flags.
    Never fabricates: rows without a derivable tenure keep ``None``.
    """
    today = today or date.today()
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        title = str(raw.get("title") or "").strip()
        note_bits: list[str] = []
        m = _PAREN_RE.search(name)
        if m:
            note_bits.append(m.group(1).strip())
            name = _PAREN_RE.sub("", name).strip(" ,–—-")  # noqa: RUF001
        if not _person_like(name):
            roles = _GAP_ROLES_RE.findall(f"{name} {title}".upper())
            if roles:
                seen: list[str] = []
                for r in roles:
                    if r not in seen:
                        seen.append(r)
                out.append({
                    "name": None, "title": " / ".join(seen),
                    "gap_flag": True, "critical_role": True,
                    "tenure_months": None,
                    "note": "Not confirmed from public evidence.",
                })
            continue
        background = str(raw.get("background") or "").strip() or None
        # Part 8.6 (2026-07-02): mine title too — many rosters carry the
        # appointment in the title ("Chairman & CEO (since 1991)") or a
        # "19-year veteran" clip in the background, which the prior
        # tenure/background-only, verb-anchored mining missed (0.4% → ~13%,
        # the honest ceiling — the corpus records tenure for ~13% of leaders).
        tenure = (
            _tenure_from_value(raw.get("tenure_months"))
            or _tenure_from_value(raw.get("tenure"))
            or tenure_months_from_text(" ".join(
                s for s in (str(raw.get("tenure") or ""), title, background or "") if s
            ), today)
        )
        row: dict[str, Any] = {
            "name": name,
            "title": title or None,
            "tenure_months": tenure,
            "background": background,
            "critical_role": bool(_CRITICAL_ROLE_RE.search(title)),
            "recent_hire": tenure is not None and tenure <= 6,
        }
        if note_bits:
            row["note"] = "; ".join(note_bits)
        for passthrough in ("clay", "evidence", "id"):
            if raw.get(passthrough) is not None:
                row[passthrough] = raw[passthrough]
        out.append(row)
    return out


# ── Part 8.6 · Regulatory (license/charter + jurisdictions) ───────────────

_LICENSE_RE = re.compile(
    r"\b("
    r"(?:federally|state|provincially|nationally)[- ]chartered"
    r"(?:\s+[a-z]+){0,3}?(?:\s+(?:bank|credit\s+union|trust\s+company|"
    r"savings\s+bank|institution))?"
    r"|national\s+bank(?:\s+charter)?"
    r"|federal\s+(?:savings\s+bank|credit\s+union|charter|thrift)"
    r"|state\s+(?:member\s+bank|savings\s+bank|charter|trust\s+company)"
    r"|schedule\s+i+\s+bank"
    r"|national\s+association"
    r"|trust\s+company\s+charter"
    r"|industrial\s+(?:bank|loan\s+company)"
    r"|consumer\s+(?:lending|finance)\s+licen[cs]e[sd]?"
    r"|licen[cs]ed\s+(?:as\s+)?(?:an?\s+)?[a-z][a-z ]{3,40}?"
    r"(?:lender|bank|insurer|trust|credit\s+union)"
    r")\b",
    re.IGNORECASE,
)
_US_STATES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    "Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    "Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    "Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    "New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    "Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
    "Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia"
)
_CA_PROVINCES = (
    "Alberta|British Columbia|Manitoba|New Brunswick|Newfoundland|"
    "Nova Scotia|Ontario|Prince Edward Island|Quebec|Saskatchewan"
)
_REGION_RE = re.compile(rf"\b({_US_STATES}|{_CA_PROVINCES})\b")
_FOOTPRINT_CUE_RE = re.compile(
    r"(?:operates|operating|serving|serves|branches|locations|offices|"
    r"footprint|presence|markets?|across|headquartered)\b",
    re.IGNORECASE,
)
_N_STATES_RE = re.compile(r"\b(\d{1,2})[\s-]+states?\b", re.IGNORECASE)

# Part 8.6 (2026-07-02): the primary_regulator determines the charter/licence
# CLASS as a matter of regulatory fact — a grounded fallback when the prose
# never spells the charter out (25 → 89 clients with both fields).
_REGULATOR_LICENSE: tuple[tuple[re.Pattern[str], str], ...] = (
    # NCUA (incl. its full name "National Credit Union Administration") must be
    # tested before the generic state-charter rule so it is not misread as a
    # state "credit union administration".
    (re.compile(r"\bNCUA\b|national credit union", re.I), "Credit union (NCUA-regulated)"),
    (re.compile(r"state\s+(?:dfi|department of financial|banking department|"
                r"corporation commission|financial institutions)|"
                r"credit union administration", re.I),
     "State-chartered institution"),
    (re.compile(r"\bOCC\b|comptroller of the currency", re.I), "National bank charter (OCC)"),
    (re.compile(r"farm credit", re.I), "Farm Credit System institution (FCA-chartered)"),
    (re.compile(r"\bOSFI\b|superintendent of financial", re.I),
     "Federally regulated financial institution (OSFI, Canada)"),
    (re.compile(r"deposit guarantee corporation|\bDGCM\b", re.I),
     "Provincially chartered credit union"),
    (re.compile(r"ontario securities|\bOSC\b|\bBCSC\b|securities commission", re.I),
     "Provincially registered securities firm"),
    (re.compile(r"investment advisers act|registered investment advis|\bRIA\b", re.I),
     "SEC-registered investment adviser"),
    (re.compile(r"insurance depart|bureau of insurance|\bDOI\b|\bNAIC\b", re.I),
     "State-licensed insurer"),
    (re.compile(r"federal reserve|\bFRS\b|\bFRB\b", re.I), "Federal Reserve-regulated bank"),
    (re.compile(r"\bESMA\b|\bASIC\b|\bMAS\b|\bSFC\b|\bFCA\b\s*\(uk\)", re.I),
     "Internationally regulated broker-dealer"),
    (re.compile(r"\bSEC\b", re.I), "SEC-registered"),
    (re.compile(r"\bCFPB\b|\bFTC\b|\bFCA\b", re.I), "Licensed consumer lender"),
    (re.compile(r"\bFDIC\b", re.I), "FDIC-insured bank"),
)
_US_STATE_ABBR = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_HQ_STATE_ABBR_RE = re.compile(
    r"(?:headquartered in|\bHQ\b[:\s]|based in|located in|operates? (?:from|in))"
    r"[^.\n]{0,70}?,\s*([A-Z]{2})\b")
_CITY_STATE = {
    "chicago": "Illinois", "nyc": "New York", "manhattan": "New York",
    "brooklyn": "New York", "queens": "New York", "astoria": "New York",
    "boston": "Massachusetts", "san francisco": "California",
    "los angeles": "California", "atlanta": "Georgia", "seattle": "Washington",
    "denver": "Colorado", "miami": "Florida", "philadelphia": "Pennsylvania",
}
_CITY_HQ_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _CITY_STATE) + r")\b[- ]?(?:head|hq|based|,)",
    re.I)
# a national/federal charter implies national jurisdiction (grounded); a plain
# regional FDIC/NCUA charter does NOT — those stay honest-null.
_NATIONAL_LICENSE_RE = re.compile(
    r"national bank(?:\s+charter)?|^SEC-registered|OSFI|Internationally regulated", re.I)
_NATIONAL_PROSE_RE = re.compile(r"\ball 50 states\b|\bnationwide\b|\bnational(?:ly)?\b", re.I)


def _license_from_regulator(regulator: str | None) -> str | None:
    for rx, label in _REGULATOR_LICENSE:
        if regulator and rx.search(regulator):
            return label
    return None


def _jurisdictions_from_context(
    hay: str, regulator: str | None, license_type: str | None,
) -> list[str] | None:
    m = _HQ_STATE_ABBR_RE.search(hay)
    if m and m.group(1) in _US_STATE_ABBR:
        return [_US_STATE_ABBR[m.group(1)]]
    if regulator:
        fm = _REGION_RE.search(regulator)
        if fm:
            return [fm.group(1)]
    cm = _CITY_HQ_RE.search(hay)
    if cm:
        return [_CITY_STATE[cm.group(1).lower()]]
    if license_type and (_NATIONAL_LICENSE_RE.search(license_type)
                         or _NATIONAL_PROSE_RE.search(hay)):
        if "OSFI" in license_type:
            return ["Canada (national)"]
        if "Internationally" in license_type:
            return ["International"]
        return ["United States (national)"]
    return None


def regulatory_view(
    parsed_facts: dict | None,
    narrative_md: str | None,
    lines: list[str] | None = None,
    primary_regulator: str | None = None,
) -> dict[str, Any]:
    """Extract license_type/charter + jurisdictions from existing prose.

    Verbatim spans first (patterns over parsed_facts values, the
    firmographics narrative and financial lines); then a grounded regulator-
    class fallback when ``primary_regulator`` is supplied (the derive_context
    fill passes it, then persists the result to parsed_facts so the serve-time
    call reads it back as a structured key). Honest-null when neither the
    prose nor the regulator determines the field. Structured parsed_facts keys
    win over pattern mining.
    """
    pf = parsed_facts or {}
    out: dict[str, Any] = {"license_type": None, "jurisdictions": None}

    for key in ("license_type", "license", "charter_type", "charter"):
        v = pf.get(key)
        if isinstance(v, str) and v.strip():
            out["license_type"] = v.strip()
            break

    hay_parts = [narrative_md or ""]
    hay_parts.extend(str(v) for v in pf.values() if isinstance(v, str))
    hay_parts.extend(lines or [])
    hay = "\n".join(p for p in hay_parts if p)

    if out["license_type"] is None and hay:
        m = _LICENSE_RE.search(hay)
        if m:
            span = re.sub(r"\s+", " ", m.group(1)).strip()
            out["license_type"] = span[0].upper() + span[1:]
    if out["license_type"] is None:
        out["license_type"] = _license_from_regulator(primary_regulator)

    juris: list[str] = []
    for key in ("jurisdictions", "operating_states", "footprint", "geography",
                "states"):
        v = pf.get(key)
        if isinstance(v, list) and v:
            juris = [str(x).strip() for x in v if str(x).strip()][:8]
            break
        if isinstance(v, str) and v.strip():
            juris = [s.strip() for s in re.split(r"[;,·|]", v) if s.strip()][:8]
            break
    if not juris and hay:
        for sentence in re.split(r"(?<=[.;])\s+", hay):
            if not _FOOTPRINT_CUE_RE.search(sentence):
                continue
            for m in _REGION_RE.finditer(sentence):
                if m.group(1) not in juris:
                    juris.append(m.group(1))
        if not juris:
            m = _N_STATES_RE.search(hay)
            if m:
                juris = [f"{m.group(1)} states"]
    if juris:
        out["jurisdictions"] = juris[:8]
    else:
        out["jurisdictions"] = _jurisdictions_from_context(
            hay, primary_regulator, out["license_type"])
    return out


# ── Part 8.6 · Derived trend narrative ─────────────────────────────────────

_TREND_TOKEN_RE = re.compile(
    r"\b(ACCELERATING|IMPROVING|RECOVERING|STABLE|DECLINING|DECELERATING)\b",
    re.IGNORECASE,
)
_CAGR_RE = re.compile(
    r"CAGR[^%\n]{0,40}?([+\-]?\d+(?:\.\d+)?)\s*%"
    r"|([+\-]?\d+(?:\.\d+)?)\s*%[^.\n]{0,20}?CAGR",
    re.IGNORECASE,
)


def _fmt_series_value(value: float, unit: str) -> str:
    if unit == "usd_b":
        return f"${value:,.1f}B"
    if unit == "usd_m":
        return f"${value:,.1f}M"
    if unit == "pct":
        return f"{value:,.1f}%"
    if unit == "usd":
        a = abs(value)
        if a >= 1e9:
            return f"${value / 1e9:,.1f}B"
        if a >= 1e6:
            return f"${value / 1e6:,.1f}M"
        return f"${value:,.0f}"
    return f"{value:,.1f}"


# Part 8.6 broadening (2026-07-02): additional grounded trend sources so the
# 33 clients whose report shipped no trend narrative AND no ≥2-period labelled
# series still derive one (33 → ~4 honest-null). Each tier is verbatim-grounded.
_YEAR_SUFFIX_RE = re.compile(r"^(.*?)[_\s]((?:19|20)\d{2})$")
_GROWTH_KEY_RE = re.compile(r"growth|cagr", re.I)
_PCT_TREND_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)\s*%")
_MONEY_PRIORITY = ("total_assets", "total assets", "assets", "deposits", "aum",
                   "revenue", "net_income", "net income", "loans", "premium",
                   "surplus")
_CLEAN_MONEY_RE = re.compile(r"^\s*\$?~?[\d.,]+\s*[BMK]?\s*$", re.I)
_LINE_TREND_RE = re.compile(
    r"→|->|grown from|grew from|compounded|\bCAGR\b|\bgrowth\b|"
    r"year[- ]over[- ]year|\bYoY\b", re.I)
_LINE_MONEYPCT_RE = re.compile(r"\$|\d+(?:\.\d+)?\s*%|\bbillion\b|\bmillion\b", re.I)
_LINE_GAP_RE = re.compile(r"trend data gap|need [a-z-]+ [\d-]*\s*year|will attempt", re.I)


def _clean_money_span(v: object) -> str | None:
    s = str(v).strip()
    if len(s) > 22 or "(" in s or "|" in s or not re.search(r"\d", s):
        return None
    return s


def _paired_year_clause(metrics: dict) -> str | None:
    """Two same-metric year-suffixed keys (deposits_2024 + deposits_2025)."""
    groups: dict[str, list[tuple[int, object]]] = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            continue
        m = _YEAR_SUFFIX_RE.match(str(k))
        if not m or _GROWTH_KEY_RE.search(m.group(1)):
            continue
        groups.setdefault(m.group(1).strip("_").lower(), []).append((int(m.group(2)), v))
    cand = [(b, sorted(ys)) for b, ys in groups.items() if len({y for y, _ in ys}) >= 2]
    if not cand:
        return None
    cand.sort(key=lambda it: next(
        (i for i, p in enumerate(_MONEY_PRIORITY) if p in it[0]), 99))
    base, ys = cand[0]
    (y1, v1), (y2, v2) = ys[0], ys[-1]
    n1, n2 = _coerce_number(str(v1)), _coerce_number(str(v2))
    s1, s2 = _clean_money_span(v1), _clean_money_span(v2)
    if not (s1 and s2 and n1 is not None and n2 is not None):
        return None
    verb = "grew" if n2 >= n1 else "declined"
    clause = f"{base.replace('_', ' ').capitalize()} {verb} from {s1} ({y1}) to {s2} ({y2})"
    g = metrics.get(f"{base}_growth_yoy") or metrics.get(f"{base}_growth")
    gm = _PCT_TREND_RE.search(str(g)) if g else None
    if gm:
        clause += f" — {gm.group(1)}% YoY"
    return clause + "."


def _trajectory_clause(metrics: dict) -> str | None:
    """The report-prose trajectory block's own grounded headline."""
    tj = metrics.get("trajectory")
    if not isinstance(tj, dict):
        return None
    hl = str(tj.get("headline") or "").strip()
    if not hl or not re.search(r"\d", hl):
        return None
    hl = hl.replace(" · ", " as of ").replace("·", "as of")
    fy = [str(x) for x in (tj.get("fy") or []) if x]
    span = f", within a series tracked {fy[0]} to {fy[-1]}" if len(fy) >= 2 else ""
    return f"Most recent reported financials: {hl}{span}."


def _line_trend_clause(financials: dict) -> str | None:
    """A verbatim corpus line already stating a trend (arrow / growth / CAGR)."""
    for ln in financials.get("lines") or []:
        s = str(ln).strip()
        if not s or _LINE_GAP_RE.search(s):
            continue
        if _LINE_TREND_RE.search(s) and _LINE_MONEYPCT_RE.search(s):
            s = re.split(r"(?<=[.])\s+(?=[A-Z])", s)[0].strip()
            s = re.sub(r"\s*\[E-[^\]]*\]", "", s).strip()  # drop inline E-ID chips
            if len(s) > 240:
                s = s[:237].rstrip() + "…"
            return s if s.endswith((".", "…")) else s + "."
    return None


def _snapshot_clause(metrics: dict) -> str | None:
    """Last resort: the single highest-priority clean money metric, as of the
    latest available period (no invented direction)."""
    best: tuple[int, str, str] | None = None
    for k, v in metrics.items():
        if isinstance(v, dict):
            continue
        kl = str(k).lower()
        pr = next((i for i, p in enumerate(_MONEY_PRIORITY) if p in kl), None)
        if pr is None or not _CLEAN_MONEY_RE.match(str(v).strip()):
            continue
        n = _coerce_number(str(v).strip())
        if n is None:
            continue
        sv = str(v).strip()
        disp = sv if re.search(r"[BMK$]", sv, re.I) else _fmt_series_value(n, "usd")
        if best is None or pr < best[0]:
            best = (pr, k.replace("_", " "), disp)
    if best is None:
        return None
    return f"Latest available financials show {best[1]} of {best[2]}."


def derive_trend_md(financials: dict | None) -> str | None:
    """Grounded 1-2 sentence trend paragraph from the REAL financial view.

    Used only when the assessment report shipped no trend narrative. Tries, in
    order: a ≥2-period labelled series (first→last + CAGR); year-suffixed metric
    pairs; the report-prose trajectory headline; a verbatim corpus trend line;
    a growth/CAGR phrase; then a single-metric snapshot as of the latest period.
    Every tier is verbatim-grounded or an arithmetic consequence of parsed
    values; returns None only when the corpus records no financials at all.
    """
    if not financials:
        return None
    metrics = financials.get("metrics") or {}
    hay = " ".join([
        *(financials.get("lines") or []),
        *(f"{k} {v}" for k, v in metrics.items() if not isinstance(v, dict)),
    ])
    trend_m = _TREND_TOKEN_RE.search(hay)
    trend = trend_m.group(1).upper() if trend_m else None

    sentences: list[str] = []
    labeled = financials.get("series_labeled") or []
    primary = labeled[0] if labeled else None
    if primary and len(primary.get("fy") or []) >= 2:
        fy, values = primary["fy"], primary["values"]
        unit = primary.get("unit") or "unknown"
        metric = str(primary.get("metric") or "value").replace("_", " ")
        first, last = values[0], values[-1]
        span = fy[-1] - fy[0]
        verb = "grew" if last >= first else "declined"
        clause = (
            f"{metric.capitalize()} {verb} from "
            f"{_fmt_series_value(first, unit)} ({fy[0]}) to "
            f"{_fmt_series_value(last, unit)} ({fy[-1]})"
        )
        if first > 0 and last > 0 and span > 0:
            cagr = ((last / first) ** (1 / span) - 1) * 100
            clause += f" — {cagr:,.1f}% CAGR"
        sentences.append(clause + ".")
    if not sentences:
        # the trajectory moved out of metrics (wave 2: it is the chart
        # axis, not a kv metric) — accept it from either location.
        tj_holder = ({"trajectory": financials["trajectory"]}
                     if isinstance(financials.get("trajectory"), dict)
                     else metrics)
        for clause in (
            _paired_year_clause(metrics),
            _trajectory_clause(tj_holder),
            _line_trend_clause(financials),
        ):
            if clause:
                sentences.append(clause)
                break
    if not sentences:
        m = _CAGR_RE.search(hay)
        if m:
            pct = m.group(1) or m.group(2)
            sentences.append(f"The research corpus records a {pct}% CAGR.")
    if not sentences:
        snap = _snapshot_clause(metrics)
        if snap:
            sentences.append(snap)
    if trend:
        sentences.append(f"Trajectory classified {trend} in the research corpus.")
    if not sentences:
        return None
    return " ".join(sentences[:2])
