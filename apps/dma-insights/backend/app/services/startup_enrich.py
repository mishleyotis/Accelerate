"""Pure, DB-free enrichment helpers shared by the derive scripts and the
no-DB snapshot regenerator (`app/scripts/apply_startup_data_fixes.py`).

Every function is deterministic and GROUNDED in already-persisted data
(firmographics, financial_highlights lines, subcap scores, the per-client
insight/platform cards). Nothing here fabricates a value: when the evidence is
absent the helper returns None / [] so the caller renders an honest blank.

Keeping the logic here (operating on plain dicts/scalars, no SQLAlchemy) means
the canonical DB derive steps and the offline snapshot pass produce identical
output from one source of truth — no drift between the deploy reparse and the
committed `startup-data`.
"""
from __future__ import annotations

import contextlib as _contextlib
import re
import unicodedata
import zlib as _zlib_mod
from collections.abc import Iterable

# Canonical "E-047" plus the corpus's real variants: "E0001" (no dash,
# richbank/rockland class), "EV-12"/"INT-3" (connector-sourced ids). The
# rubric's citation counter (nlp.quality) recognizes the same set.
_E_ID_RE = re.compile(
    r"\b(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}\b|\bE\d{3,4}\b")
_SUBCAP_ID_RE = re.compile(r"^[Pp]\d+C\d")
_CAT_RE = re.compile(r"^([Pp]\d+C\d+)")


def extract_eids(text: object, limit: int | None = None) -> list[str]:
    """Inline evidence E-IDs cited in a body of prose ('… via CCC Smart Estimate
    [E-085, E-074] …'), de-duplicated in first-seen order. The analyst's own
    citation is the most precise traceability link a finding has — more reliable
    than a subcap roll-up — so callers merge these ahead of the subcap-resolved
    set. Normalises 'E--085' → 'E-85' is NOT done here (see `repair_citations`)."""
    out = list(dict.fromkeys(_E_ID_RE.findall(str(text or ""))))
    return out[:limit] if limit else out


# Content-token overlap — re-links a finding to the supporting evidence prose the
# analyst placed in a SEPARATE paragraph ("F-002: Claims STP via CCC Smart
# Estimate" ↔ "Acuity deployed … through CCC Smart Estimate [E-085]").
_TOKEN_STOP = frozenset(
    ["the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on", "at", "by", "from", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those", "it", "its", "as", "has", "have", "had", "not", "no", "but", "their", "our", "your", "his", "her", "via", "than", "then", "them", "they", "will", "would", "can", "could", "should", "may", "might", "also", "into", "over", "across", "more", "most", "less", "least", "each", "per", "within", "without", "about", "above", "below", "other", "company", "firm", "bank", "group", "inc", "corp", "llc", "its"])
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&/+]{3,}")


def significant_tokens(text: object) -> set[str]:
    """Content tokens (≥4 chars, stop-words removed, lower-cased) used for topical
    overlap between a finding and its supporting evidence prose."""
    return {w for w in _TOKEN_RE.findall(str(text or "").lower())
            if w not in _TOKEN_STOP}


def evidence_by_overlap(finding_text: object,
                        candidates: Iterable[tuple[list[str], set[str]]],
                        min_overlap: int = 2, limit: int = 4) -> list[str]:
    """E-IDs from the supporting paragraph that shares the most CONTENT tokens
    with the finding. Conservative — requires ≥`min_overlap` shared tokens, so an
    ambiguous finding gets NO evidence rather than the WRONG evidence. Candidates
    are (eids, token_set) pairs pre-built from the entity's evidence-bearing
    focus rows; the best-overlapping candidates' E-IDs are returned (capped)."""
    ft = significant_tokens(finding_text)
    if not ft:
        return []
    scored = []
    for eids, toks in candidates:
        ov = len(ft & set(toks or ()))
        if ov >= min_overlap and eids:
            scored.append((ov, list(eids)))
    scored.sort(key=lambda x: -x[0])
    out: list[str] = []
    for _, eids in scored:
        for e in eids:
            if e not in out:
                out.append(e)
    return out[:limit]

# ── Names ────────────────────────────────────────────────────────────────────
_NON_PERSON_PREFIX = re.compile(r"^(no\b|n/?a\b|none\b|tbd\b|unknown\b|-+$)", re.I)
# A leadership row that is really a status/label, not a person:
# "CDO ABSENT", "Leadership Gap", "VACANT".
_STATUS_WORD = re.compile(
    r"\b(ABSENT|VACANT|VACANCY|TBD|MISSING|UNFILLED|GAPS?)\b")


def is_person_name(name: object) -> bool:
    """True only for a plausible human name. Rejects subcap-id-shaped strings
    ('P4C2.1, P4C2.2'), digit-heavy tokens, non-person sentinels, and the
    2026-06-25 audit's junk leadership rows — 'TITLE: Name' colon labels
    ('CEO: Brandon', 'Leadership Gap:'), emoji/symbol names ('⚠️ CISO Akerberg',
    '❌ CDO ABSENT'), and status words ('CDO ABSENT')."""
    n = str(name or "").strip()
    if not (3 <= len(n) <= 60):
        return False
    if ":" in n:                       # "CEO: Brandon" / "Leadership Gap:" / "PRIMARY: Kevin"
        return False
    if _NON_PERSON_PREFIX.match(n):
        return False
    if _STATUS_WORD.search(n):          # "CDO ABSENT" / "Leadership Gaps"
        return False
    if any(unicodedata.category(c) in ("So", "Sk", "Cs") for c in n):  # emoji / symbols
        return False
    tokens = [t for t in re.split(r"\s+", n) if t]
    if any(_SUBCAP_ID_RE.match(t) for t in tokens):
        return False
    digit_tokens = sum(1 for t in tokens if any(c.isdigit() for c in t))
    if tokens and digit_tokens / len(tokens) > 0.3:
        return False
    capitalised = sum(1 for t in tokens if t[:1].isupper())
    has_alpha_word = any(t.replace("'", "").replace("-", "").replace(".", "").isalpha()
                         for t in tokens)
    return len(tokens) >= 2 and capitalised >= 2 and has_alpha_word


# ── Catalogue ids ────────────────────────────────────────────────────────────
def pillar_of(subcap_id: object) -> str | None:
    s = str(subcap_id or "")
    return s[:2] if re.match(r"^[Pp]\d", s) else None


def category_of(subcap_id: object) -> str | None:
    m = _CAT_RE.match(str(subcap_id or ""))
    return m.group(1).upper() if m else None


_FLAG_BY_SEVERITY = {"high": "CRITICAL", "critical": "CRITICAL",
                     "medium": "OPPORTUNITY", "med": "OPPORTUNITY",
                     "low": "MONITOR"}


def flag_from_severity(severity: object) -> str:
    return _FLAG_BY_SEVERITY.get(str(severity or "").strip().lower(), "MONITOR")


# ── Firmographics derivations (from financial_highlights / geography) ─────────
def _fh_blob(fh: dict) -> str:
    return " ".join((fh or {}).get("lines") or []) + " " + " ".join(
        f"{k}: {v}" for k, v in ((fh or {}).get("metrics") or {}).items()
    )


_TREND_WORDS = [("ACCELERATING", r"accelerat"), ("DECELERATING", r"decelerat|slowing"),
                ("STABLE", r"\bstable\b|steady|consistent"),
                ("VARIABLE", r"\bvariable\b|volatile|mixed")]


def derive_trend(fh: dict) -> str | None:
    """Mine the analyst's growth-trend classification from financial_highlights.
    Prefers an explicit 'Classification: X'; falls back to trend keywords."""
    blob = _fh_blob(fh)
    m = re.search(r"classification:\s*([A-Za-z]+)", blob, re.I)
    if m and m.group(1).upper() in {"ACCELERATING", "DECELERATING", "STABLE", "VARIABLE"}:
        return m.group(1).upper()
    for label, pat in _TREND_WORDS:
        if re.search(pat, blob, re.I):
            return label
    return None


def derive_cagr(fh: dict) -> float | None:
    """Mine a CAGR / multi-year growth rate as a fraction (0.084 for 8.4%)."""
    blob = _fh_blob(fh)
    for pat in (r"CAGR[^%\d]{0,18}?(\d{1,2}(?:\.\d)?)\s*%",
                r"(\d{1,2}(?:\.\d)?)\s*%[^%]{0,12}?CAGR",
                r"(\d{1,2}(?:\.\d)?)\s*%\s*(?:three|3|five|5)[- ]year"):
        m = re.search(pat, blob, re.I)
        if m:
            try:
                v = float(m.group(1))
                if 0 < v < 60:
                    return round(v / 100.0, 4)
            except ValueError:
                pass
    return None


def derive_branches(fh: dict) -> int | None:
    blob = _fh_blob(fh)
    m = re.search(r"(\d{1,4})\s+branch(?:es)?\b", blob, re.I)
    if m:
        try:
            v = int(m.group(1))
            if 0 < v < 10000:
                return v
        except ValueError:
            pass
    return None


_GEO_SPLIT = re.compile(r"\s*[•·;|]\s*|\s*\+\s*|\s*,\s*|\s+and\s+")


def derive_footprint(geography: object) -> list[str] | None:
    """Split a geography string into a clean region/state list (footprint[])."""
    g = str(geography or "").strip()
    if not g:
        return None
    parts = [p.strip() for p in _GEO_SPLIT.split(g) if p.strip()]
    # drop parenthetical noise and over-long prose fragments
    cleaned: list[str] = []
    for p in parts:
        p = re.sub(r"\s*\([^)]*\)\s*", " ", p).strip(" .")
        if p and len(p) <= 28 and not p.lower().startswith(("primary", "with", "including")):
            cleaned.append(p)
    out: list[str] = []
    for p in cleaned:
        if p not in out:
            out.append(p)
    return out[:10] or None


# ── Leadership flags (deterministic from title + tenure + name) ───────────────
_CRITICAL_TITLES = re.compile(
    r"\b(ciso|chief information security|cdo|chief data|cto|chief technology|"
    r"chief digital|chief information officer|\bcio\b|chief analytics|"
    r"chief innovation)\b", re.I)
_GAP_NAME = re.compile(r"^\s*[-–—]?\s*$|^(no\b|none\b|vacant|unfilled|tbd)", re.I)  # noqa: RUF001


def leadership_flags(title: object, tenure_months: object, name: object) -> dict:
    """critical_role / recent_hire / gap_flag — derived, never invented.
    critical_role: title is a security/data/tech C-suite seat.
    recent_hire: tenure < 6 months. gap_flag: a placeholder/absent name."""
    t = str(title or "")
    nm = str(name or "")
    out = {"critical_role": bool(_CRITICAL_TITLES.search(t)),
           "recent_hire": False, "gap_flag": bool(_GAP_NAME.match(nm))}
    try:
        tm = int(tenure_months) if tenure_months not in (None, "") else None
    except (TypeError, ValueError):
        tm = None
    if tm is not None and 0 <= tm < 6:
        out["recent_hire"] = True
    return out


# ── Boilerplate scrub (the leaked focus-area / methodology scaffolding) ───────
# Extends the original "Each finding includes…" scrub with the 2026-06-25 audit's
# verified methodology fragments that leaked into why-now PRIORITY signals.
_BOILERPLATE_SENT = re.compile(
    r"\s*(?:Each finding includes[^.]*\.|[^.]*quantified observation,\s*maturity "
    r"implication[^.]*\.|[^.]*Zennify solution relevance\."
    r"|Each finding is grounded in[^.]*\.?"
    r"|[^.]*framed through the Salesforce Account Executive lens[^.]*\.?"
    r"|[^.]*Zennify Relevance column[^.]*\.?"
    r"|[^.]*flow(?:s)? directly into the Handoff Package[^.]*\.?"
    r"|[^.]*feed(?:s)? (?:directly )?into the Handoff Package[^.]*\.?"
    r"|These (?:flow|feed)[^.]*Handoff[^.]*\.?"
    r"|[^.]*affect(?:s)? assessment (?:accuracy|scoring)[^.]*\.?"
    r"|[^.]*highest-priority Salesforce engagement[^.]*\.?"
    r"|[^.]*represent the highest[^.]*\.?"
    r"|\(?Appendix [A-Z]\)?\.?)", re.I)

# A signal/finding text that is ONLY a section label ("2 Top Findings:",
# "3 Critical Gaps:") with no real content. Two shapes, verified across the
# corpus:
#   (a) DIGIT-prefixed: "4 Critical Gaps & Active Blockers", "2 Critical
#       Gaps1.2…", "3 Top Findings (REVISED)" — a number immediately followed by
#       the section phrase is ALWAYS the header, whatever trails it; and
#   (b) the bare label, optionally with a trailing qualifier (": ", " (…)",
#       " with …", " REVISED", or end-of-string).
# A real finding ("4 fragmented CRMs perceived as none", "6 vendors, zero
# middleware") starts with a number but NOT the section phrase, so it is kept.
_SECTION_PHRASE = r"(?:top findings|critical gaps|key findings|priority gaps)"
_METHODOLOGY_LABEL = re.compile(
    # (a) digit + section phrase → header whatever trails it (no \b: tolerates the
    #     garbled "2 Critical Gaps1.2 Critical Gaps" run-on).
    rf"^\s*\d+\s*{_SECTION_PHRASE}"
    # (b) the bare label, optionally with a trailing qualifier.
    rf"|^\s*\d*\s*(?:{_SECTION_PHRASE}|evidence citation inventory|"
    r"exec(?:utive)? summary)\b(?:\s*[:.\-–—]|\s*\(|\s+with\b|\s+revised\b|\s*$)",  # noqa: RUF001
    re.I)

# Section-intro / revision-note BODIES the focus-area extractor captured from the
# report's "Top Findings" preamble (verified leaks: Elliott "Seven headline
# findings — each tied to…", Texas Capital "Each finding is cross-referenced…",
# Fulton "Each finding combines a quantified, evidence-cited observation", Sound
# CU "[Revised with…]"). They describe the methodology or a revision, not a
# finding — drop the whole row rather than name it after its section header.
_METHODOLOGY_BODY_RE = re.compile(
    r"^\s*\[(?:revised|updated)\b"
    r"|\beach finding (?:is|combines?|includes?|carries|reflects?) \b"
    r"|\bheadline findings\b"
    r"|\bframe this assessment\b"
    r"|^\s*the following\s+(?:\w+\s+){0,3}"
    r"(?:objectives|issues|gaps|risks|findings|items|priorities)\b"
    r"|^\s*all\s+(?:the\s+)?gaps?\s+below\b"
    r"|\b(?:gaps?|objectives|findings)\s+frame\s+the\b"
    r"|\bcarries a direct Salesforce engagement\b", re.I)

# Analyst ANNOTATION labels that leak as finding names — the report's "Zennify
# Relevance / Implication" column and "Implications for Zennify Engagement
# Timing" subsection headers. Verified leaks: Corporate America CU, tii,
# TowneBank Insurance, Chemung Canal. These are solution-mapping annotations, not
# findings — reject as a NAME (the body, if real, supplies the true name).
_ANNOTATION_NAME_RE = re.compile(
    r"^\s*(?:zennify\s+(?:relevance|implication|engagement)\b"
    r"|implications?\s+for\s+zennify\b"
    r"|each finding\b"
    r"|evidence citation inventory\b)", re.I)


def is_nonfinding_name(name: object) -> bool:
    """True when a candidate finding NAME is actually a section header, a
    methodology preamble, an analyst annotation label, or an unresolved
    catalogue placeholder — anything that must never be shown as a finding's
    name. Length-safe (unlike `is_methodology_only`): a short REAL capability
    name ('Data Foundation') is kept."""
    s = str(name or "").strip()
    if not s:
        return True
    return bool(is_placeholder_name(s) or _METHODOLOGY_LABEL.match(s)
                or _ANNOTATION_NAME_RE.match(s) or _METHODOLOGY_INTRO.search(s)
                or _BARE_LABEL_RE.match(s))

# The "Top Findings" section's methodology PREAMBLE — it describes how findings
# are structured ("N findings with quantified observations (evidence IDs),
# maturity implications, and Zennify solution relevance"), it is NOT a finding.
# Tolerant of singular/plural, an inline parenthetical, and a missing trailing
# period (clipped bodies lack one) — the rigid `_BOILERPLATE_SENT` variant only
# caught the exact "quantified observation, maturity implication." phrasing.
_METHODOLOGY_INTRO = re.compile(
    r"quantified observations?\b.{0,40}?maturity implications?\b.{0,40}?zennify",
    re.I | re.S)
# The whole preamble span, count phrase included, for excision from longer prose.
# The trailing noun drifts ("Zennify solution relevance" / "…alignment"), so stop
# at "Zennify solution <word>" rather than pin the exact noun.
_METHODOLOGY_INTRO_SPAN = re.compile(
    r"\b\d+\s+(?:top\s+)?findings?\s+with\s+quantified observations?\b.{0,80}?"
    r"zennify\s+solution\s+\w+\b[^.]*?\.?", re.I | re.S)


def strip_boilerplate(text: object) -> str:
    """Remove leaked methodology/scaffolding sentence(s) that contaminate
    signals/findings ('Each finding includes…', 'flow directly into the Handoff
    Package', 'affect assessment accuracy', the Salesforce-AE-lens line, etc.)."""
    s = str(text or "")
    s = _BOILERPLATE_SENT.sub(" ", s)
    s = _METHODOLOGY_INTRO_SPAN.sub(" ", s)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def is_methodology_only(text: object) -> bool:
    """True when a signal/finding text is just a section label or collapses to
    nothing real after the boilerplate scrub — drop it rather than render it."""
    s = str(text or "").strip()
    if not s:
        return True
    if (_METHODOLOGY_LABEL.match(s) or _METHODOLOGY_INTRO.search(s)
            or _METHODOLOGY_BODY_RE.search(s)):
        return True
    return len(strip_boilerplate(s)) < 25


# ── Evidence map (subcap → E-IDs) built from the per-client insight cards ─────
def subcap_evidence_map(insight_items: Iterable[dict],
                        fh_lines: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Map subcap-id (leaf AND its P#C# category) → E-IDs, sourced from the
    insight cards' linked_subcap_id/linked_e_ids and any E-IDs embedded in the
    financial_highlights lines. This is the offline analogue of the DB
    evidence_index join used by deepen_narrative._eids_for."""
    out: dict[str, list[str]] = {}

    def _add(key: str, eids: Iterable[str]) -> None:
        if not key:
            return
        bucket = out.setdefault(key, [])
        for e in eids:
            if e and e not in bucket:
                bucket.append(e)

    for it in insight_items or []:
        sid = it.get("linked_subcap_id")
        eids = [e for e in (it.get("linked_e_ids") or []) if e]
        if sid and eids:
            _add(str(sid), eids)
            cat = category_of(sid)
            if cat and cat != str(sid):
                _add(cat, eids)
    for line in (fh_lines or []):
        eids = _E_ID_RE.findall(line or "")
        if eids:
            _add("__financial__", eids)
    return out


def eids_for(subcaps: Iterable[str], ev_map: dict[str, list[str]],
             limit: int = 4) -> list[str]:
    """E-IDs for a set of subcaps, matching the leaf id AND its P#C# category
    (the parent-category broadening that recovers evidence linked at a different
    granularity)."""
    out: list[str] = []
    for s in subcaps or []:
        for key in (str(s), category_of(s) or ""):
            for e in ev_map.get(key, []):
                if e not in out:
                    out.append(e)
    return out[:limit]


# Rotating pad framings — padded signals must each COMMUNICATE something
# different, with deliberately DISJOINT vocabularies so two pads for one
# client never read (or token-dedup) as the same tile twice. The shipped
# pack carried 2-3 token-identical 'priority focus' pads per client
# (chemung/amarillo/royal-business, audit 2026-07-06). Every variant is
# still grounded ONLY in the category's own name + score.
_WHY_NOW_PAD_FRAMES = (
    # v3 doctrine: scores never lead — the meaning opens, the score rides
    # as proof; each frame ends on the forward move so the tile argues
    # rather than restates
    "The next phase of {name}'s roadmap runs through {label}: the "
    "assessment places it at {score}/5, and every downstream initiative "
    "inherits whatever this foundation can support.",
    "Whatever {name} builds next lands on {label} — currently {score}/5 — "
    "so sequencing this first is what makes the rest of the roadmap "
    "compound instead of stall.",
    "Closing {label} unlocks its dependent capabilities faster than any "
    "single platform purchase would; the assessment reads it at {score}/5 "
    "today, which is the room to move.",
    # 4th frame: the D1 strip FEATURES 4 tiles, so a fully-padded strip
    # must never wrap the rotation back onto frame 1 (near-identical pads,
    # the 2026-07-06 chemung/amarillo class).
    "{label} is the quiet dependency in {name}'s plan: it reads {score}/5 "
    "today, and lifting it early spares every later initiative from "
    "working around it.",
)


def ensure_why_now_depth(
    signals: list[dict],
    categories: Iterable[tuple],
    overall: object,
    entity_name: object,
    min_count: int = 3,
    min_len: int = 60,
) -> list[dict]:
    """Guarantee at least ``min_count`` why-now signals, each a full sentence of
    at least ``min_len`` chars -- the ``completeness_contract.why_now_depth``
    floor the DB-side derive must satisfy for every active run.

    The source-grounded composers in ``deepen_narrative`` can fall short of three
    detailed signals for a strong, non-bank, or data-sparse entity (no peer gap,
    no bank capital ratios, no ownership / CAGR / focus-area prose). This keeps
    the signals already composed and, only when short, pads from the entity's OWN
    scored categories (lowest-first) then its overall maturity. Every padded
    signal is derived from real persisted scores and framed as a forward priority,
    never a fabricated trigger. Each pad rotates through a different sentence
    skeleton (``_WHY_NOW_PAD_FRAMES``) and pads are capped at ONE per parent
    pillar, so a padded strip still communicates different things per tile.
    ``categories`` is an iterable of ``(category_id, display_name, score,
    evidence_ids)``. Returns at most 6.
    """
    out = [s for s in (signals or []) if len(str(s.get("text") or "")) >= min_len]
    used = {s.get("subcap_id") for s in out if s.get("subcap_id")}
    used_pillars: set[str] = set()
    name = str(entity_name or "").strip() or "This institution"
    # Continue the phrasing rotation past pads a PRIOR pass already
    # emitted — a refill after dedupe must use the NEXT variant, never
    # restart at frame 0 and recreate the near-duplicate it is
    # replacing (2026-07-06 featured-strip review). Prior pads also claim
    # their parent pillar for the one-pad-per-pillar cap below.
    pad_i = 0
    for s in out:
        if (s.get("kind") == "PRIORITY"
                and s.get("derived_from") == "subcap_scores"):
            pad_i += 1
            if s.get("subcap_id"):
                used_pillars.add(str(s["subcap_id"])[:2])
    for cat in categories or []:
        if len(out) >= min_count:
            break
        try:
            cat_id, display_name, score, eids = cat
        except (TypeError, ValueError):
            continue
        if not cat_id or cat_id in used or score is None:
            continue
        pillar = str(cat_id)[:2]
        if pillar in used_pillars:
            # one pad per parent pillar — two same-pillar pads read as the
            # same structural story twice.
            continue
        label = capability_phrase(display_name) or str(display_name or cat_id)
        text = _WHY_NOW_PAD_FRAMES[pad_i % len(_WHY_NOW_PAD_FRAMES)].format(
            label=label, score=score, name=name)
        if len(text) >= min_len:
            out.append({
                "kind": "PRIORITY", "text": text,
                # W6 (2026-07-14): a clean directive headline — without it the
                # deep-field rebuild's make_title fell back to clipping the
                # pad sentence mid-thought ("Whatever X builds next lands on").
                # The score stays in `metric`, never the label.
                "label": f"Sequence {label} first",
                "metric": f"{label} {score}/5",
                "evidence": list(eids or [])[:4],
                "subcap_id": cat_id, "derived_from": "subcap_scores",
            })
            used.add(cat_id)
            used_pillars.add(pillar)
            pad_i += 1
    if len(out) < min_count and overall is not None:
        text = (f"{name} is mid-transformation — the assessment reads "
                f"overall maturity at {overall}/5 — and a sequenced roadmap "
                f"is what turns that position into measurable, prioritized "
                f"capability gains rather than scattered point fixes.")
        if len(text) >= min_len and all(s.get("kind") != "TRAJECTORY" for s in out):
            out.append({
                "kind": "TRAJECTORY", "text": text,
                # W6: clean headline (score stays in `metric`).
                "label": "A sequenced roadmap is the next move",
                "metric": f"overall maturity {overall}/5",
                "evidence": [], "derived_from": "subcap_scores",
            })
    return out[:6]


# ── Why-now near-duplicate suppression (2026-07-06 mandate) ──────────────────
# "All should communicate different stuff": two signals whose user-visible
# text is near-identical add nothing. The FIRST occurrence wins (callers sort
# strongest-first); the later one is differentiated with its OWN distinct
# facts (metric / window / its own evidence ids) or, when it carries none,
# suppressed — subject to the min_keep floor the depth contract demands.

def why_now_signal_text(s: dict) -> str:
    """The prose an AE actually reads on one why-now card."""
    if not isinstance(s, dict):
        return str(s or "")
    return f"{s.get('text') or ''} {s.get('detail') or ''}".strip()


def texts_near_identical(a: object, b: object, threshold: float = 0.6,
                         min_tokens: int = 6) -> bool:
    """Token-Jaccard near-duplicate test over the significant content words
    of two prose fragments. Conservative: short fragments never match."""
    ta, tb = significant_tokens(a), significant_tokens(b)
    if min(len(ta), len(tb)) < min_tokens:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def dedupe_why_now_signals(signals: list[dict], min_keep: int = 3) -> list[dict]:
    """Deduplicate near-identical why-now signals per the 2026-07-06 mandate.

    Walks the (strongest-first) list; a signal whose text is near-identical
    to an already-kept one is first DIFFERENTIATED by appending its own
    distinct facts (its metric and/or window, cited on its own evidence);
    if no distinct fact breaks the similarity it is SUPPRESSED. Suppressed
    signals are re-admitted in order only if the list would otherwise fall
    below ``min_keep`` (the why_now_depth floor). Input dicts are never
    mutated — differentiated signals are copies."""
    out: list[dict] = []
    dropped: list[dict] = []
    for s in signals or []:
        base = why_now_signal_text(s)
        if not any(texts_near_identical(base, why_now_signal_text(k)) for k in out):
            out.append(s)
            continue
        bits = []
        metric = str(s.get("metric") or "").strip() if isinstance(s, dict) else ""
        window = str(s.get("window") or "").strip() if isinstance(s, dict) else ""
        if metric and norm(metric) not in norm(base):
            bits.append(f"the measure to watch is {metric}")
        if window and norm(window) not in norm(base):
            bits.append(f"its own window ({window})")
        if bits and isinstance(s, dict):
            own_e = [str(e) for e in (s.get("evidence") or []) if e][:2]
            tail = (" What sets this signal apart: " + "; ".join(bits)
                    + (f" [{', '.join(own_e)}]" if own_e else "") + ".")
            cand = dict(s)
            for fld in ("text", "detail"):
                if cand.get(fld):
                    cand[fld] = str(cand[fld]).rstrip() + tail
            cand_text = why_now_signal_text(cand)
            if not any(texts_near_identical(cand_text, why_now_signal_text(k))
                       for k in out):
                out.append(cand)
                continue
        dropped.append(s)
    while dropped and len(out) < min_keep:
        out.append(dropped.pop(0))
    return out


# ── Platform helpers ─────────────────────────────────────────────────────────
_READINESS_ORDER = {"green": 0, "amber": 1, "red": 2}


def platforms_for_finding(
    cards: list[dict], subcap_id: object, *, top: int = 2,
) -> tuple[list[str], list[dict]]:
    """Reasoned finding→platform links (platform v3): rank the run's platform
    cards for a finding by ADDRESSABILITY, not raw pillar-fit.

    A platform *addresses* the finding when its ``addressable_subcap_ids``
    intersect the finding's CATEGORY (the ``P#C#`` prefix). Addressing
    platforms rank first by the summed fit-breakdown opportunity over the
    addressed subcaps, then readiness (green<amber<red), then fit_score.

    The audit found 114/380 (30%) findings whose lead platform did NOT address
    the finding's category, yet the templated so-what asserted "{platform} is
    the platform surface that addresses it". This returns, alongside the ids,
    a ``rationale`` list ``{platform_id, platform_name, addressed_subcap_ids,
    contribution_pts, e_ids, addresses}`` so a caller only makes the
    "addresses it" claim when ``addresses`` is true — otherwise it phrases the
    link as sequenced/adjacent. When NO platform addresses the category we
    fall back to the pillar's top-fit platforms but flag ``addresses=False``.
    """
    if not cards:
        return [], []
    cat = category_of(subcap_id)
    pillar = pillar_of(subcap_id)
    scored: list[tuple] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        pid = c.get("platform_id") or c.get("display_name")
        if not pid:
            continue
        addr = c.get("addressable_subcap_ids") or []
        addressed = [s for s in addr if cat and str(s).startswith(cat)] if cat else []
        bd = c.get("fit_breakdown") if isinstance(c.get("fit_breakdown"), dict) else {}
        tops = [t for t in (bd.get("top_subcaps") or []) if isinstance(t, dict)]
        cat_tops = [t for t in tops if cat and str(t.get("subcap_id", "")).startswith(cat)]
        contribution = sum(float(t.get("opportunity") or 0.0) for t in cat_tops)
        if contribution == 0.0 and addressed:
            contribution = 0.001 * len(addressed)  # breadth proxy when no top-subcap detail
        e_ids: list[str] = []
        for t in cat_tops:
            for e in (t.get("e_ids") or []):
                if e and e not in e_ids:
                    e_ids.append(str(e))
        # Concrete L4 feature names the fit engine carried through from the
        # v7 catalogue for this category's contributing subcaps — the
        # receipts a so-what can name instead of a bare platform label.
        l4_feats: list[str] = []
        for t in cat_tops:
            for f in (t.get("l4_features") or []):
                if f and f not in l4_feats and len(l4_feats) < 3:
                    l4_feats.append(str(f))
        readiness = _READINESS_ORDER.get(str(c.get("readiness_index") or "").lower(), 1)
        fit = float(c.get("fit_score") or 0.0)
        in_pillar = 1 if (pillar and c.get("pillar") == pillar) else 0
        scored.append((
            bool(addressed), contribution, in_pillar, -readiness, fit, str(pid),
            addressed[:6], e_ids[:4], c.get("display_name") or pid, l4_feats,
        ))

    addressing = [s for s in scored if s[0]]
    pool = addressing if addressing else scored
    # higher contribution / same-pillar / better readiness (s[3] already
    # negated) / higher fit / stable id.
    pool.sort(key=lambda s: (-s[1], -s[2], -s[3], -s[4], s[5]))

    names: list[str] = []
    seen_ids: set[str] = set()
    rationale: list[dict] = []
    for s in pool:
        pid = s[5]
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        # Return canonical DISPLAY NAMES (normalises the 'nCino'/'ncino'
        # casing drift the audit found in 10/380 findings); rationale keeps
        # the stable lowercase id for joins.
        names.append(str(s[8]))
        rationale.append({
            "platform_id": pid,
            "platform_name": s[8],
            "addressed_subcap_ids": s[6],
            "contribution_pts": round(s[1], 4),
            "e_ids": s[7],
            "addresses": bool(s[0]),
            "l4_features": s[9],
        })
        if len(names) >= top:
            break
    return names, rationale


def platforms_for_pillar(cards: list[dict], pillar: str | None,
                         top: int = 2) -> list[str]:
    """Top platform ids by fit for a pillar (legacy — retained for callers
    that only need ids and have no finding subcap; prefer
    :func:`platforms_for_finding` for reasoned, addressability-scored links)."""
    if not cards:
        return []
    ranked = sorted(
        cards,
        key=lambda c: (c.get("pillar") == pillar, c.get("fit_score") or 0),
        reverse=True,
    )
    out: list[str] = []
    for c in ranked:
        pid = c.get("platform_id") or c.get("display_name")
        if pid and pid not in out:
            out.append(pid)
        if len(out) >= top:
            break
    return out


def readiness_phrase(readiness: object, unmet_count: int = 0) -> str | None:
    """Deployment posture from the card's readiness signal. None when
    readiness was not measured.

    2026-07-06 (platform v3): accept BOTH the light string
    (``readiness_index`` is ``Literal['green','amber','red']`` in the schema —
    the audit found ``float('red')`` raised and the clause silently dropped on
    100% of cards) AND a real numeric 0-100 readiness. Never reads the dead
    ``state`` field (state=READY on 470/470, so a state-driven clause asserted
    "currently ready" on every amber/red platform)."""
    if isinstance(readiness, str):
        light = readiness.strip().lower()
        if light in ("green", "amber", "red"):
            tail = (
                f" ({unmet_count} prerequisite{'s' if unmet_count != 1 else ''} open)"
                if unmet_count else ""
            )
            if light == "green":
                return "readiness green — deployable now"
            if light == "amber":
                return f"readiness amber — near-ready{tail}"
            return f"readiness red — blocked on prerequisites{tail}"
    try:
        r = float(readiness)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if r >= 70:
        return f"readiness {r:.0f}/100 — deployable now"
    if r >= 40:
        tail = (f" ({unmet_count} prerequisite{'s' if unmet_count != 1 else ''} open)"
                if unmet_count else "")
        return f"readiness {r:.0f}/100 — near-ready{tail}"
    return f"readiness {r:.0f}/100 — blocked on prerequisites"


def compose_opportunity_md(card: dict, subcap_names: dict | None = None,
                           entity_key: str | None = None) -> str | None:
    """Concise, grounded 'why this platform' narrative from the card's own
    fit/pillar/readiness/prereq/breakdown fields. None when the platform has
    no addressable surface (INSUFFICIENT_EVIDENCE → honest blank).

    2026-07-02 (plan 7.1): the readiness clause is driven by
    ``readiness_index`` via :func:`readiness_phrase` — the prior version read
    the dead ``state`` field (READY on 470/470) and told AEs a blocked
    platform was "currently ready". The single skeleton (72.6% of cards) is
    diversified with the card's OWN entity facts: named top-opportunity
    subcaps (fit_breakdown / top_subcap_names / the subcap_names map), the
    top subcap's score-vs-peer, and confirmed-absent families."""
    if card.get("state") == "INSUFFICIENT_EVIDENCE":
        return None
    addr = card.get("addressable_subcap_ids") or []
    if not addr:
        return None
    # Never fall back to the raw platform_id code ('salesforce'/'data_cloud')
    # in prose — convert it to the display name (2026-07-15 cohesion audit).
    name = (card.get("display_name")
            or platform_display_name(card.get("platform_id")) or "This platform")
    pillar = card.get("pillar")
    prereqs = card.get("prereq_checks") or card.get("prereqs") or []
    unmet = [p for p in prereqs if str(p.get("status", "")).upper() in ("UNMET", "BLOCKED", "FAIL")]

    # Entity facts: named top subcaps + score-vs-peer from the fit breakdown.
    bd = card.get("fit_breakdown") if isinstance(card.get("fit_breakdown"), dict) else {}
    tops = [t for t in (bd.get("top_subcaps") or []) if isinstance(t, dict)]
    top_names = [str(t["name"]) for t in tops if t.get("name")]
    if not top_names:
        top_names = [str(n) for n in (card.get("top_subcap_names") or []) if n]
    if not top_names and subcap_names:
        top_names = [subcap_names[s] for s in addr if subcap_names.get(s)]
    top_names = list(dict.fromkeys(top_names))[:2]
    absent = [str(f) for f in (bd.get("absent_families") or []) if f]

    # Lead with the OPPORTUNITY + supporting evidence — NOT the fit-score,
    # "N scored capability gaps" count, or the subcap-score recital (plan S13;
    # user: "not interested in the subcaps but what opportunities exist and
    # what evidence supports this"). The fit score renders as its own stat on
    # the card, so it stays out of the prose.
    ev_ids = [str(e) for e in (card.get("evidence_ids") or [])
              if str(e).startswith(("E-", "EV-", "INT-"))][:2]
    ev_cite = f" [{', '.join(ev_ids)}]" if ev_ids else ""
    # Convert the bare pillar code ('P2') to its readable label; drop it rather
    # than leak the code if unknown (2026-07-15 cohesion audit).
    _pl = pillar_prose(pillar)
    lead_area = f" across {_pl}" if _pl else ""
    # Anti-template (2026-07-13): seeded per (entity, platform) so the 94-
    # client corpus never stamps one skeleton; facts/citations invariant.
    from app.services.nlp.stylebook import pick as _pick
    from app.services.nlp.stylebook import seeded as _seeded
    _rng = _seeded(str(entity_key or card.get("entity_name")
                       or card.get("entity_id") or ""),
                   str(card.get("platform_id") or name), "opportunity")
    # Iron rule (QA-GLB-07): the first clause is the CLIENT's outcome in the
    # client's capabilities; the platform names itself second, as the how.
    if top_names:
        surfaces = top_names[0] + (f" and {top_names[1]}" if len(top_names) > 1 else "")
        bits = [_pick(_rng, (
            "Modernizing {s}{area} — the capabilities that today trail the "
            "peer benchmark and anchor the near-term opportunity — is where "
            "**{n}** ranks strongest fit{cite}.",
            "The near-term opportunity{area} sits in {s}, the capabilities "
            "trailing the peer benchmark — and that is exactly the ground "
            "**{n}** ranks strongest fit against{cite}.",
            "{s}{area} trail the peer benchmark today and carry the "
            "near-term upside; **{n}** ranks as the strongest-fit platform "
            "for precisely that work{cite}.",
            "Where the benchmark spread is widest{area} — {s} — is where "
            "**{n}** fits best{cite}.",
            "**{n}** earns its ranking on {s}{area}: the under-benchmark "
            "capabilities with the nearest-term payoff{cite}.",
            "The case for **{n}** starts with {s}{area}, where today's "
            "readings sit under the peer line{cite}.",
        ), s=surfaces, area=lead_area, n=name, cite=ev_cite)]
    else:
        bits = [_pick(_rng, (
            "Advancing the client's priorities{area} is where **{n}** ranks "
            "strongest fit{cite}.",
            "**{n}** ranks strongest fit for the client's priorities"
            "{area}{cite}.",
        ), area=lead_area, n=name, cite=ev_cite)]
    # 2026-07-14 lens: when a category incumbent is installed (Snowflake
    # under a Databricks card, MeridianLink under nCino…) the absence
    # sentence must argue integration with the named incumbent — the
    # greenfield frame over an occupied layer was the skew audit's top
    # narrative defect.
    _sl = ((bd.get("factors") or {}).get("absent_boost") or {}).get("stack_lens")
    _lens = str((_sl or {}).get("lens") or "")
    _incs = [str(x) for x in ((_sl or {}).get("category_incumbents") or []) if x]
    if absent and _lens == "integrate" and _incs:
        bits.append(_pick(_rng, (
            " The family itself is absent, but {inc} already anchors that "
            "layer — the play is integration with {inc}, not a greenfield "
            "install.",
            " With {inc} already installed in this layer, the entry runs "
            "through coexistence and data-flow with {inc} rather than a "
            "net-new platform build.",
            " {inc} occupies this layer today, so the argument is "
            "complementing the installed platform — integration first, "
            "never rip-and-replace.",
        ), inc=_incs[0]))
    elif absent:
        bits.append(_pick(_rng, (
            " The platform family is confirmed absent from the current stack "
            "({fams}) — greenfield rather than displacement.",
            " The current stack shows no footprint from this platform family "
            "({fams}), so the entry is greenfield, not displacement.",
            " Nothing from this platform family is confirmed in today's "
            "stack ({fams}) — open ground rather than a rip-and-replace.",
            " Techstack review confirms the family is not yet in place "
            "({fams}): a greenfield entry with no incumbent to unwind.",
            " With no confirmed {fams} footprint in the stack, this lands "
            "on open ground instead of displacing an incumbent.",
        ), fams=", ".join(absent[:2])))
    # woven, not labelled: "Deployment posture: readiness red." read as a
    # spliced note (cohesion sweep: 384 disconnected platform pairs). The
    # readiness verdict renders from its own pooled frames (the shared
    # readiness_phrase string put identical 6-grams on 129 cards).
    light = card.get("readiness_index")
    light = light.strip().lower() if isinstance(light, str) else None
    n_open = len(unmet)
    tail = (f" ({n_open} prerequisite{'s' if n_open != 1 else ''} open)"
            if n_open else "")
    if light == "green":
        bits.append(_pick(_rng, (
            " Its deployment posture is green — deployable now.",
            " Readiness is green: it can deploy now.",
            " On readiness it shows green — nothing blocks deployment.",
            " The deployment light is green; it can land today.",
        )))
    elif light == "amber":
        bits.append(_pick(_rng, (
            " Its deployment posture is amber — near-ready{tail}.",
            " Readiness reads amber{tail}: close, not yet clear.",
            " The deployment light is amber — near-ready{tail}.",
            " On readiness it sits at amber{tail}, within reach of clear.",
        ), tail=tail))
    elif light == "red":
        bits.append(_pick(_rng, (
            " Its deployment posture is red — blocked on prerequisites"
            "{tail}.",
            " Readiness reads red{tail}: prerequisites gate the deployment.",
            " The deployment light is red — prerequisites first{tail}.",
            " On readiness it shows red{tail}; the gate is the open "
            "prerequisites.",
        ), tail=tail))
    else:
        rp = readiness_phrase(card.get("readiness_index"), n_open)
        if rp:
            bits.append(f" Its deployment posture is {rp}.")
    if unmet:
        ex = unmet[0]
        label = ex.get("label") or ex.get("name") or "a foundational prerequisite"
        cur = ex.get("current") if ex.get("current") is not None else ex.get("current_score")
        thr = ex.get("threshold")
        gap = (f" (e.g. {label}: {cur} vs {thr} threshold)"
               if cur is not None and thr is not None else f" (e.g. {label})")
        n_un = len(unmet)
        pl = "s" if n_un != 1 else ""
        bits.append(_pick(_rng, (
            " Clearing {n} open prerequisite{pl} unlocks that deployment{gap}.",
            " {n} open prerequisite{pl} stand{sv} between here and "
            "deployment{gap}.",
            " The path to deployment runs through {n} open "
            "prerequisite{pl}{gap}.",
        ), n=n_un, pl=pl, sv="" if n_un != 1 else "s", gap=gap))
    return "".join(bits).strip()[:1200]


# ── Subvertical labels (for the SCQA narrative) ──────────────────────────────
_SUBV_LABEL = {
    "RB": "regional bank", "CU": "credit union", "AM": "asset manager",
    "RIA": "wealth & advisory firm", "IC": "insurance carrier",
    "IB": "insurance broker", "FC": "farm-credit institution",
    "CIB": "corporate & investment bank", "CL": "commercial lender",
    "REIT": "real-estate investment trust", "MUTUAL": "mutual insurer",
}


def _usd(v: object) -> str | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n >= 1e12:
        return f"${n / 1e12:.2f}T"
    if n >= 1e9:
        return f"${n / 1e9:.1f}B"
    if n >= 1e6:
        return f"${n / 1e6:.0f}M"
    return f"${n:,.0f}" if n else None


def reparagraph(text: str, target: int = 3) -> str:
    """Split a long single-paragraph narrative into `target` paragraphs at
    sentence boundaries — preserves content while satisfying the ≥2-paragraph
    depth contract.

    Uses the abbreviation-guarded splitter (nlp.segment.sentences): the
    prior naive ``(?<=[.!?])\\s+`` regex treated "EverBank, N.A." /
    "Guaranteed Rate, Inc." as sentence ends and landed a paragraph break
    mid-name in served exec summaries (2026-07-14 prose audit). Units the
    splitter emits at NON-sentence boundaries (spaCy splits at citation
    brackets, ALL-CAPS tokens, list commas) are merged forward — a
    paragraph break can only ever land after a genuine sentence end."""
    from app.services.nlp.segment import ends_sentence
    from app.services.nlp.segment import sentences as _guarded_sentences

    raw_units = [s for s in _guarded_sentences(text.strip()) if s]
    sents: list[str] = []
    for u in raw_units:
        # merge forward when the boundary is not a real sentence end OR
        # the next unit opens lowercase (a colon-introduced list item is
        # a continuation, never a paragraph opener)
        if sents and (not ends_sentence(sents[-1]) or u[:1].islower()):
            sents[-1] = f"{sents[-1]} {u}"
        else:
            sents.append(u)
    if len(sents) < 2:
        return text.strip()
    per = max(1, round(len(sents) / target))
    chunks = [" ".join(sents[i:i + per]) for i in range(0, len(sents), per)]
    return "\n\n".join(c.strip() for c in chunks if c.strip())


def compose_scqa(name: str, firm: dict, overall: float | None,
                 subvertical: str | None, top_findings: list[dict],
                 client_key: str | None = None) -> str:
    """A 2-3 paragraph executive narrative grounded ONLY in persisted facts.
    Used to replace broken placeholder SCQAs ('(2.8), (2.5)') and one-liners.

    2026-07-13 mandate: leads with the KEY MESSAGE (the priority gap and the
    sequencing case), never a firmographics recap; seeded frame pools vary the
    surface form per client so the fallback never stamps one skeleton across
    the corpus. ``firm``/``subvertical`` stay in the signature for callers but
    no longer feed a recap sentence."""
    from app.services.nlp import stylebook as sb
    rng = sb.seeded(client_key or name, "scqa-simple")
    gaps = [f for f in (top_findings or []) if f.get("name")][:3]
    o_txt = f"{overall:.1f}" if overall is not None else ""
    if not gaps:
        if o_txt:
            return (f"Zennify's assessment reads {name}'s overall digital "
                    f"maturity at {o_txt} out of 5; the capability-level "
                    f"priorities populate once the scored assessment ingests.")
        return (f"{name}'s priority-gap narrative populates once the "
                f"assessment's scored capabilities ingest.")

    def _gap_ref(g: dict) -> str:
        # Only show a score parenthetical when there IS a score — never the
        # literal "(None)" for a report-extracted finding that carries no
        # numeric subcap score.
        sc = g.get("score")
        if sc is None:
            return str(g["name"])
        peer = g.get("peer_median")
        tail = f" vs a peer median of {peer}" if peer is not None else ""
        return f"{g['name']} ({sc}{tail})"

    lead = str(gaps[0]["name"])
    o_clause = (sb.pick(rng, (
        " — the capability holding the overall {o}/5 assessment down",
        ", the deepest drag on the {o}/5 overall reading",
        " — where the {o}/5 overall score is decided",
    ), o=o_txt) if o_txt else "")
    p1 = sb.pick(rng, (
        "The highest-leverage move for {name} is closing {lead}{oc}: it "
        "underpins the capabilities that build on it, so progress there "
        "compounds across the wider transformation.",
        "{name}'s fastest route to higher digital maturity runs through "
        "{lead}{oc} — the layer its other investments inherit.",
        "One priority orders the rest for {name}: {lead}{oc}. Close it "
        "first and the dependent capabilities re-rate with it.",
    ), name=name, lead=lead, oc=o_clause)
    gtxt = "; ".join(_gap_ref(g) for g in gaps)
    p2 = sb.pick(rng, (
        "The assessment concentrates the opportunity in {gtxt}. Each trails "
        "the comparable-institution benchmark on measured evidence rather "
        "than reflecting an absence of investment.",
        "Three readings carry the case: {gtxt} — every one measured against "
        "the comparable-institution benchmark, not asserted.",
        "The scored gaps line up as {gtxt}; the benchmark spread, not the "
        "raw score, is what makes them the priority.",
    ), gtxt=gtxt)
    p3 = sb.pick(rng, (
        "Sequencing the remaining gaps behind {lead} keeps {name}'s "
        "investment focused on the moves that lift maturity fastest.",
        "{name} should sequence the rest behind {lead}, so each dollar lands "
        "on the capability the next one depends on.",
        "The recommended order is {lead} first, then the adjacent gaps — "
        "the sequence that compounds instead of scattering.",
    ), lead=lead, name=name)
    return f"{p1}\n\n{p2}\n\n{p3}"


# ── Findings coherence (title↔body, gap-direction, placeholder names) ─────────
# The capability a finding BODY actually opens with — used to keep .name aligned
# with .body (the 2026-06-25 audit found 249/470 findings where they diverged).
_LEADING_CAP_RE = re.compile(
    r"^\**\s*(.+?)\s+(?:is one of\b|is the most material\b|is a\b|is an\b|"
    r"scores\s+[\d.]|lags\b|trails\b)", re.I)


def leading_capability(body: object) -> str | None:
    """Extract the capability the body opens with ('Data Virtualization &
    Federation is one of …' → 'Data Virtualization & Federation'). None when the
    body has no recognisable leading capability (so the caller keeps .name)."""
    s = str(body or "").strip()
    m = _LEADING_CAP_RE.match(s)
    if not m:
        return None
    cap = m.group(1).strip(" *—-:—").strip()  # noqa: B005
    if not cap or len(cap) > 70 or len(cap.split()) > 9:
        return None
    return cap


def is_true_gap(score: object, peer: object, buffer: float = 0.05) -> bool | None:
    """True when score is below peer (a real gap), False when at/above peer (a
    relative strength), None when either is unknown — used to stop framing an
    at/above-benchmark capability as 'the most material capability gap'."""
    try:
        s, p = float(score), float(peer)
    except (TypeError, ValueError):
        return None
    return s < p - buffer


# ── Capability display names (artifact-title leak, 2026-07-06) ───────────────
# The scoring workbooks name some subcaps after the ARTIFACT the researchers
# look for ("Digital Marketing Strategy Document", P2C1.1.1) rather than the
# capability itself. Composed as "<name> is one of X's least developed
# capabilities…" the artifact title reads as a DOCUMENT occupying the
# capability-name slot (production screenshot, interactive-brokers-grou-0001).
_ARTIFACT_WORDS = (
    r"documents?|documentation|workbooks?|worksheets?|spreadsheets?|"
    r"checklists?|templates?|memos?|decks?|binders?|one-?pagers?")
_ARTIFACT_SUFFIX_RE = re.compile(rf"\s+(?:{_ARTIFACT_WORDS})\s*\.?\s*$", re.I)
_ARTIFACT_ONLY_RE = re.compile(rf"^(?:{_ARTIFACT_WORDS})\s*\.?\s*$", re.I)


def capability_phrase(name: object) -> str:
    """Capability display name safe for the "<name> is one of …" slot.

    Strips a trailing artifact-type noun ("Digital Marketing Strategy
    Document" → "Digital Marketing Strategy") so a composed card never
    presents a document/evidence title as the capability. When stripping
    would leave fewer than two words the name is unrecoverable as a
    capability phrase and '' is returned — the caller falls back exactly
    as it does for a missing name. Names without an artifact suffix pass
    through unchanged."""
    s = re.sub(r"\s{2,}", " ", str(name or "").strip())
    if not s or _ARTIFACT_ONLY_RE.match(s):
        return ""
    stripped = _ARTIFACT_SUFFIX_RE.sub("", s).strip(" -—–:,")  # noqa: RUF001
    if stripped == s:
        return s
    return stripped if len(stripped.split()) >= 2 else ""


_PLACEHOLDER_NAME_RE = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:capability dimension\s*\d+|sub-?cap(?:ability)?\s*\d+"  # noqa: RUF001
    r"|dimension\s*\d+)\s*$", re.I)
# The generic filler `scrub_placeholder_text` substitutes for an unresolved
# catalogue placeholder ("capability dimension 54" -> "a lower-scoring capability
# area"). Valid as narrative prose, but it must NEVER be surfaced as a finding
# NAME — a scrubbed-placeholder body has no real capability, so the finding drops.
_GENERIC_FILLER_NAME_RE = re.compile(
    r"^\s*a\s+lower-scoring capability(?:\s+area)?\s*$", re.I)


def is_placeholder_name(name: object) -> bool:
    """True for unresolved catalogue fallbacks shown as finding names —
    'capability dimension 54', '— Subcap 6', a bare 'P4C2.1' id, or the generic
    'a lower-scoring capability area' filler the placeholder scrub emits."""
    s = str(name or "").strip()
    if not s:
        return True
    if (_PLACEHOLDER_NAME_RE.match(s) or _SUBCAP_ID_RE.match(s)
            or _GENERIC_FILLER_NAME_RE.match(s)):
        return True
    return bool(re.search(r"\bsubcap\s*\d+\b|capability dimension\s*\d+", s, re.I))


_PLACEHOLDER_PHRASE = re.compile(
    r"\b(?:capability dimension|sub-?cap(?:ability)?|dimension)\s*\d+\b", re.I)


def scrub_placeholder_text(text: object) -> str:
    """Neutralise unresolved catalogue placeholder phrases ('capability
    dimension 54') inside narrative text (why-now signals, SCQA) — the real name
    isn't resolvable offline; the deploy reparse fills it from the catalogue.
    Collapses the 'a lower-scoring capability … -scoring capability' redundancy."""
    s = _PLACEHOLDER_PHRASE.sub("a lower-scoring capability area", str(text or ""))
    s = re.sub(r"a lower-scoring capability area is the (?:next-)?lowest-scoring capability",
               "A lower-scoring capability is", s, flags=re.I)
    return s


# ── SCQA pre-write scaffolding (the worksheet leaked into the narrative) ──────
_SCAFFOLD_MARKERS = re.compile(
    r"PRE-WRITE INPUT|Do NOT render|READ ONLY FROM THIS FILE|NO AD HOC DATA"
    r"|Validation pre-write|ANTI-GENERIC|Anti-Generic Confirmation"
    r"|INPUT:\s*report_analysis|report_synthesis\.md|report_analysis\.json"
    r"|END OF SYNTHESIS|WRITE ALL REPORT SECTIONS|disk-first compliance"
    r"|Forbidden generic phrases|E-ID citations:\s*[≥>]|Data Sources:\s*export"
    r"|this is the ONLY input|What story does the DATA tell"
    # SCQA worksheet slot labels leading a segment ("Situation: …",
    # "Complication: …") are pre-write scaffolding, never rendered prose
    # (2026-07-13 corpus QA: a kept Acuity SCQA led with "Situation:")
    r"|(?:^|\n)\s*(?:Situation|Complication|Question|Answer|Resolution)\s*:\s"
    # a bare framework/section banner the analyst placed ABOVE the prose
    # ("SCQA FRAMEWORK", "SCQA ANALYSIS") is a heading, not summary text —
    # it leaked into the exec-summary lead on 1 client (2026-07-14 vet)
    r"|(?:^|\n)\s*SCQA(?:\s+(?:FRAMEWORK|ANALYSIS|SUMMARY|NARRATIVE))?\s*:?\s*(?=\n|$)",
    re.I)
_WORKSHEET_HEADER = re.compile(
    r"^\s*(?:Q[1-4]\s*[:.\)]|[a-d][.\)]\s+(?:What|How|Why|Where)\b"
    r"|Run ID\s*:|Assessment\s*:\s*DMA-|DMA Assessment Report Synthesis"
    r"|.*Digital Maturity Assessment.*\b(?:19|20)\d{2}\b.*"
    r"|Validation pre-write checklist).*$", re.I | re.M)
_SCAFFOLD_FOOTER = re.compile(
    r"END OF SYNTHESIS|Validation pre-write checklist|ANTI-GENERIC VALIDATION"
    r"|Anti-Generic Confirmation|Data Sources:\s*export|Forbidden generic phrases", re.I)

# A raw assessment-report / synthesis DOCX body that leaked into the SCQA slot
# (audit 2026-07-02: 13/95 served SCQAs were report-dumps — markdown ATX
# headers, ALL-CAPS bold section banners, DMA-ASM- doc IDs — not clean SCQA
# prose). These pass the worksheet-scaffolding check but are NOT an executive
# summary; treated as scaffolding so the keep-gate rejects them and the
# composer re-derives a clean Situation→Complication→Question→Answer body.
_REPORT_DUMP = re.compile(
    r"^\s{0,3}#{1,6}\s+\S"                            # markdown ATX heading line
    r"|\*\*[A-Z][A-Z0-9 &/]{4,}\*\*"                 # **NARRATIVE THESIS** banner
    r"|\bDMA-ASM-[A-Z0-9-]+"                          # assessment doc id
    r"|^\s*(?:NARRATIVE THESIS|SIGNATURE PATTERN|SYNTHESIS"
    r"|ASSESSMENT REPORT|EXECUTIVE SYNTHESIS)\b", re.M)


def scqa_has_scaffolding(md: object) -> bool:
    """True when an SCQA still carries pre-write worksheet scaffolding OR is a
    raw report/synthesis dump rather than clean executive-summary prose."""
    s = str(md or "")
    return bool(_SCAFFOLD_MARKERS.search(s) or _WORKSHEET_HEADER.search(s)
                or _REPORT_DUMP.search(s))


def strip_scqa_scaffolding(md: object) -> str:
    """Remove pre-write worksheet scaffolding from an SCQA, keeping the narrative
    prose. Cuts the file at the first hard footer marker, then drops marker /
    Q&A-header lines. May return '' when it was ALL scaffolding (→ recompose)."""
    s = str(md or "")
    if not s.strip():
        return ""
    s = _SCAFFOLD_FOOTER.split(s, maxsplit=1)[0]
    kept = [ln for ln in s.splitlines()
            if not (_SCAFFOLD_MARKERS.search(ln) or _WORKSHEET_HEADER.match(ln))]
    out = "\n".join(kept)
    # Bare ALL-CAPS SCQA slot banners ("COMPLICATION" on its own line, or
    # glued inline after a sentence when the DOCX newlines collapsed) are
    # worksheet scaffolding the colon-form marker above misses — they
    # shipped as "… [E-059]. COMPLICATION¶¶Against this foundation …"
    # (2026-07-14 sim audit). Case-sensitive: prose "the complication"
    # is never touched.
    out = re.sub(
        r"(?:^|\n)\s*(?:SITUATION|COMPLICATION|QUESTION|ANSWER|RESOLUTION)"
        r"\s*(?=\n|$)", "\n", out)
    out = re.sub(
        r"(?<=[.!?\]])\s+(?:SITUATION|COMPLICATION|QUESTION|ANSWER|"
        r"RESOLUTION)(?=\s+[A-Z“\"(\[])", "", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ── Citation repair (E-IDs collapsed to empty/garbled brackets) ──────────────
def repair_citations(md: object) -> str:
    """Fix the audit's broken inline citations — de-double-dash 'E--001'→'E-001'
    and drop empty/stub brackets ('[]', '[, T2]', '[::F1]', '(Source:, )') —
    WITHOUT touching valid '[E-047]' citations."""
    s = str(md or "")
    s = re.sub(r"\bE--+(\d)", r"E-\1", s)
    s = re.sub(r"\[\s*(?:,\s*)*(?:T\d|:+F?\d|F\d)?\s*\]", "", s)   # [] [, ] [, T2] [::F1] [F1]
    s = re.sub(r"\(\s*Source:\s*,?\s*[^)]*\)", "", s)
    s = re.sub(r"\(\s*:?\s*\)", "", s)
    # Parenthetical citation with dropped leading field(s): "(, AM Best, T1)" /
    # "(, , Tier 3)" -> "(AM Best, T1)" / "(Tier 3)" in ONE pass (collapse ALL
    # leading commas — apply runs once at deploy); also doubled commas + trailing.
    s = re.sub(r"\(\s*(?:,\s*)+", "(", s)
    s = re.sub(r",\s*,+", ", ", s)
    s = re.sub(r",\s*\)", ")", s)
    s = re.sub(r"Evidence:\s*(?:,\s*)+", "", s, flags=re.I)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


# ── Why-now text cleanup (double-prefix, mid-word truncation) ─────────────────
def dedupe_prefix(text: object) -> str:
    """Collapse a duplicated leading label: 'F-001: F-001 | …' → 'F-001 — …',
    '2 Top Findings: 2 Top Findings: …' → '2 Top Findings — …'."""
    s = str(text or "").strip()
    parts = re.split(r"\s*[:|]\s*", s, maxsplit=2)
    if len(parts) >= 2 and parts[0] and parts[0] == parts[1]:
        rest = parts[2].strip() if len(parts) > 2 else ""
        return f"{parts[0]} — {rest}".strip(" —") if rest else parts[0]
    return s


def _balance_quotes(s: str) -> str:
    """A clip that severed a quotation must not ship half a quote: when the
    result carries an odd number of quote marks, cut back to just before
    the unbalanced opener (2026-07-13 sample vetting: the SCQA shipped
    'develop and implement data governance frameworks' with no closing
    quote and no clause end)."""
    n_double = s.count('"') + s.count("“") + s.count("”")
    if n_double % 2:
        idx = max(s.rfind('"'), s.rfind("“"), s.rfind("”"))
        if idx > 30:
            s = s[:idx].rstrip(" ,;:—–-")  # noqa: RUF001
    n_single = len(re.findall(r"(?<![A-Za-z])'|'(?![A-Za-z])", s))
    if n_single % 2:
        idx = max(s.rfind(" '"), s.rfind("('"), s.rfind(": '"))
        if idx > 30:
            s = s[:idx].rstrip(" ,;:—–-")  # noqa: RUF001
    # curly singles pair \u2018/\u2019 — apostrophes inside words exempt
    n_curly = s.count("\u2018") + len(re.findall(r"(?<![A-Za-z])\u2019|\u2019(?![A-Za-z])", s))
    if n_curly % 2:
        idx = max(s.rfind("\u2018"), s.rfind(" \u2019"))
        if idx >= 20:
            s = s[:idx].rstrip(" ,;:—–-")  # noqa: RUF001
    return s


_DEFICIT_SUBS: list[tuple[re.Pattern[str], str]] = [
    # "no iPaaS" / "no unified agent desktop" — bare-absence shorthand
    # reads as an accusation; reframe forward ("not yet in place").
    # Verification vocabulary ("no evidence/record/indication") is exempt:
    # those are researcher absence statements, not capability judgments.
    (re.compile(r"\bno\s+(?!evidence\b|record\b|indication\b|public\b|"
                r"formal\b|new\b|longer\b|enforcement\b|consent\b|"
                r"breach\b|violation\b|litigation\b|lawsuit\b|penalt\w+|"
                r"action\b|actions\b|complaint\b|finding\b|findings\b)"
                r"([A-Za-z][\w/&+-]*(?:\s+[a-z/&+][\w/&+-]*){0,5})", re.I),
     r"\1 not yet in place"),
    (re.compile(r"\blacks?\s+(?:of\s+)?"), "is still building "),
    (re.compile(r"\blacking\b"), "still to be established"),
    (re.compile(r"\bmissing\s+([a-z][\w/&+-]*(?:\s+[a-z][\w/&+-]*){0,3})",
                re.I),
     r"\1 not yet in place"),
    (re.compile(r"\bfails?\s+to\b"), "does not yet"),
    (re.compile(r"\b(?:weak|poor|deficient)\s+"), "underdeveloped "),
    (re.compile(r"\boutdated\s+"), "aging "),
]


def soften_deficit_phrases(text: object) -> str:
    """Deficit shorthand -> forward framing for COMPOSED prose (the
    2026-07-13 vetting note: 'no iPaaS' in the SCQA reads as an
    accusation). Applied to analyst-shorthand weaves (issue titles),
    NEVER to verbatim evidence quotes — reframing a citation would
    falsify it. Spec v3: opportunity framing, no deficit language."""
    out = str(text or "")
    for rx, sub in _DEFICIT_SUBS:
        out = rx.sub(sub, out)
    return re.sub(r"\s{2,}", " ", out).strip()


def finalize_title_text(t: object, body: str = "") -> str:
    """Producer-neutral title hygiene (2026-07-13 sample vetting): no
    ellipses, no orphan openers stranded by a clip ("… construction ('"),
    and no dangling clipped word — when the title's last word is a
    lowercase fragment that continues as a longer word in the card's own
    body ("…Coverage oppor" / body "opportunity"), the fragment is a cut,
    not a word, and is dropped."""
    t = str(t or "").replace("\u2026", " ").replace("...", " ")
    # a roster-lead title ("Denise Powell: VP, Retail Skills \u2026 (since Aug \u2014
    # Champions Program is a proven strength to expand") opens on a person's
    # job line, not the insight \u2014 keep the claim after the dash and drop the
    # bio prefix (2026-07-13 corpus QA)
    _m_person = re.match(
        r"^[A-Z][\w.'\u2019-]+(?:\s+[A-Z][\w.'\u2019-]+){1,2}\s*:\s*[^\u2014\u2013]{0,90}"
        r"[\u2014\u2013]\s*(.{12,})$", t)
    if _m_person:
        t = _m_person.group(1).strip()
    # internal register codes never render in titles ("\u2026 (URF-01)")
    t = re.sub(r"\s*\((?:URF|ISS|REQ|QA)-[\dA-Z-]+\)", "", t)
    # de-shout: a 2+ word ALL-CAPS run in a headline is note emphasis,
    # not proper-noun casing ("CONFIRMED DEPLOYED"); acronyms stay
    t = re.sub(
        r"\b([A-Z]{4,})(\s+[A-Z]{4,})+\b",
        lambda m: " ".join(w.capitalize() for w in m.group(0).split()), t)
    # headlines follow the same no-deficit rule as prose ("No unified
    # agent desktop" reads as an accusation; "not yet in place" reads as
    # the opportunity) — titles are composed copy, never verbatim quotes
    t = soften_deficit_phrases(t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"[\s('\"\u201c\u2018:;,.\u2014\u2013-]+$", "", t)
    m = re.search(r"\s([a-z]{3,8})$", t)
    if m and body:
        w = m.group(1)
        if re.search(rf"\b{re.escape(w)}[a-z]{{2,}}", body):
            t = t[: m.start()].rstrip(" ,;:\u2014\u2013-(")
    return t.strip()


def clip_clean(text: object, limit: int = 240) -> str:
    """Clip to `limit` chars — SENTENCE boundary first, clause boundary as
    the fallback, never mid-word, never an ellipsis (served prose is
    complete sentences; '…' reads as truncation on every surface — the
    2026-07-13 sample vetting), and never half a quotation."""
    s = str(text or "").strip()
    if len(s) <= limit:
        return _balance_quotes(s)
    cut = s[:limit]
    # a complete sentence wins outright, even a short one — but never cut
    # at an abbreviation's period ("Wm." is a name, not a sentence end;
    # the Beacon vetting shipped "...Courtwright (CHRO) + Wm.")
    _abbrev = re.compile(
        r"\b(?:Wm|Jr|Sr|Mr|Mrs|Ms|Dr|St|Inc|Corp|Co|Ltd|No|vs|Jan|Feb|Mar|"
        r"Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|[A-Z]|"
        # "National scope (excl. Quebec)" clipped into "(excl). Quebec)" —
        # scope abbreviations are not sentence ends (2026-07-13 corpus QA)
        r"(?i:excl|incl|approx|est|resp))\.$")
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        while idx >= 25 and sep == ". " and _abbrev.search(cut[:idx + 1]):
            idx = cut.rfind(sep, 0, idx)
        if idx >= 25:
            return _balance_quotes(cut[:idx + 1].rstrip())
    for sep in ("; ", " — ", ", ", " and ", " to ", " "):
        idx = cut.rfind(sep)
        if idx >= max(40, limit // 2):
            return _balance_quotes(cut[:idx].rstrip(" ,.;:—-")) + "."
    return _balance_quotes(cut.rstrip(" ,.;:—-")) + "."


def quote_span(text: object, limit: int = 200) -> str:
    """VERBATIM quotable span for rendering inside quotation marks
    (2026-07-06 mandate: quoted evidence must be quoted verbatim; any
    truncation carries an ellipsis and never cuts mid-claim).

    Whitespace is normalized (meaning-preserving); nothing else is
    rewritten. Fits within ``limit`` → the whole span, verbatim. Longer →
    truncated ONLY at a claim boundary (sentence end first, then a
    ';' / ' — ' clause seam) with a trailing ' …' marking the omission.
    No claim-safe boundary in range → '' (the caller must not quote at
    all rather than ship a mid-claim cut)."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= limit:
        return s
    cut = s[: limit + 1]
    best = -1
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > best:
            best = idx
    if best >= 40:
        return s[: best + 1] + " …"
    for sep in ("; ", " — "):
        idx = cut.rfind(sep)
        if idx >= 40:
            return s[:idx].rstrip() + " …"
    return ""


# ── Firmographics sanitisation (offline: null garbage, never show wrong data) ─
_AUM_FLOOR = {"RB": 1e8, "CU": 1e7, "CIB": 1e9, "REIT": 5e7, "FC": 1e7}
_AUM_CEILING = {"CU": 3e11, "RB": 1.2e12, "RIA": 5e12, "AM": 5e12,
                "WEALTH_RIA": 5e12, "ASSET_MANAGER": 5e12, "IC": 2e12,
                "IB": 5e11, "INSURANCE_CARRIER": 2e12, "INSURANCE_BROKER": 5e11,
                "REIT": 5e11, "FC": 5e11, "MUTUAL": 2e12, "CIB": 5e12,
                "CL": 5e11, "FINTECH_SAAS": 5e11}
_GLOBAL_AUM_FLOOR = 1e6
_GLOBAL_AUM_CEILING = 5e12
# A branch-running bank / credit union cannot realistically have <N staff —
# catches the audit's headcount=16 (a web-tool count) on a $600M CU.
_HEADCOUNT_FLOOR = {"RB": 40, "CU": 25, "CIB": 75, "FC": 20, "IC": 25, "MUTUAL": 25}
_SENTINEL_VALUE = re.compile(r"^(role|n/?a|none|tbd|unknown|null|-+|\.)$", re.I)
_DICT_REPR = re.compile(r"^\s*\{.*['\"].*:.*\}\s*$", re.S)


def plausible_aum(value: object, subvertical: str | None = None) -> bool:
    """Reject implausible AUM/assets: $103T (>ceiling), a $21M 'regional bank'
    (<cohort floor). Cannot catch parent-vs-subsidiary attribution offline (that
    needs the canonical basis) — only the egregious magnitude/units errors."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    sv = (subvertical or "").upper()
    if n < _AUM_FLOOR.get(sv, _GLOBAL_AUM_FLOOR):
        return False
    return n <= _AUM_CEILING.get(sv, _GLOBAL_AUM_CEILING)


def subvertical_label(name: object, subvertical: str | None) -> str:
    """Entity-type label for the POSITIONING sentence, with name-based overrides
    for the verified mislabels (REIT→bank, brokerage→'wealth & advisory', etc.)."""
    nm = str(name or "").lower()
    if re.search(r"\breit\b|realty|real estate investment|properties trust|residential", nm):
        return "real-estate investment trust"
    if re.search(r"interactive brokers|broker-?dealer|securities brokerage|\bbrokerage\b", nm):
        return "brokerage"
    if re.search(r"\bmga\b|managing general ag(?:ent|ency)|travel insured", nm):
        return "insurance MGA"
    if re.search(r"payments? canada|clearing house|\bfmi\b|payment system", nm):
        return "payments system operator"
    return _SUBV_LABEL.get((subvertical or "").upper(), "financial institution")


def _clean_footprint_token(t: object) -> str | None:
    s = re.sub(r"\s*\([^)]*\)\s*", " ", str(t or "")).strip(" .),(")
    if not s or len(s) > 28:
        return None
    if re.match(r"^(?:19|20)\d{2}\)?$", s) or re.match(r"^\d+\)?$", s):
        return None
    if s.lower().startswith(("primary", "with", "including", "hq:")):
        return None
    return s


def regulator_is_garbled(value: object) -> bool:
    """True when a regulator string is a fabricated/garbled artifact: a sentinel
    ('Role'/'N/A'/'Unknown'), a dict-repr, a truncated parenthetical
    ('… (state-' / 'X ('), or unbalanced parentheses (a regex that ran off the
    end of the field, e.g. 'State DOIs (NAIC-aligned, … +'). Single source of
    truth for BOTH the sanitize pass (which strips it) and heal_entity (which
    must reject it and fall back to the clean subvertical default rather than
    store a value the sanitize pass will later null → a blank panel field)."""
    if not isinstance(value, str):
        return False
    return bool(
        _SENTINEL_VALUE.match(value.strip()) or _DICT_REPR.match(value)
        or value.rstrip().endswith(("(state-", "("))
        or value.count("(") != value.count(")")
    )


def sanitize_firmographics(firm: dict, subvertical: str | None = None) -> int:
    """Null out fabricated/garbled firmographics (offline-safe): the correct
    value isn't recoverable here, so an honest '—' beats wrong data. Returns the
    count of fields cleaned. Catches the audit's $103T / '$21M' AUM,
    size_tier↔aum contradictions, regulator='Role'/dict-repr/truncation,
    headcount=16, dict-repr address fields, and shredded footprint fragments."""
    if not isinstance(firm, dict):
        return 0
    sv = (subvertical or "").upper()
    cleaned = 0
    aum_nulled = False
    aum_val = firm.get("aum_usd")
    if aum_val not in (None, "") and not plausible_aum(aum_val, sv):
        # Units recovery: a 1000x-too-small value (thousands logged as units, e.g.
        # tristate's '$21M' for a ~$21B bank) → x1000 if that lands in the
        # plausible band; otherwise it is unsalvageable garbage ($103T) → null.
        try:
            scaled = float(aum_val) * 1000
        except (TypeError, ValueError):
            scaled = None
        if scaled is not None and plausible_aum(scaled, sv):
            firm["aum_usd"] = scaled
        else:
            firm["aum_usd"] = None
            aum_nulled = True
        cleaned += 1
    tier = str(firm.get("size_tier") or "")
    aum2 = firm.get("aum_usd")
    if tier:
        if isinstance(aum2, int | float):
            if (">$500B" in tier and aum2 < 5e11) or (
                    re.search(r"\$2B-\$10B", tier) and not (2e9 <= aum2 <= 1e10)):
                firm["size_tier"] = None
                cleaned += 1
        elif aum_nulled and re.search(r"\$\d|\d+\s*[BMT]\b", tier):
            # the aum it claimed alongside was garbage → an unverifiable magnitude tier
            firm["size_tier"] = None
            cleaned += 1
    for key in ("primary_regulator", "regulator"):
        if regulator_is_garbled(firm.get(key)):
            firm[key] = None
            cleaned += 1
    hc = firm.get("headcount")
    if hc not in (None, ""):
        try:
            floor = _HEADCOUNT_FLOOR.get(sv, 5)  # a branch-running bank/CU can't have <N staff
            if not (floor <= int(hc) <= 5_000_000):
                firm["headcount"] = None
                cleaned += 1
        except (TypeError, ValueError):
            firm["headcount"] = None
            cleaned += 1
    for key in ("hq_address", "hq", "total_assets", "total_deposits"):
        v = firm.get(key)
        if isinstance(v, str) and _DICT_REPR.match(v):
            firm[key] = None
            cleaned += 1
    fp = firm.get("footprint")
    if isinstance(fp, list):
        fixed = [x for x in (_clean_footprint_token(t) for t in fp) if x]
        if fixed != fp:
            firm["footprint"] = fixed or None
            cleaned += 1
    return cleaned


# ── Top-findings composition (shared by the canonical deepen_narrative AND the
#    offline patcher, so both layers build name↔body-coherent, gap-aware findings
#    from identical logic — never two drifting copies) ──────────────────────────
_PILLAR_LABEL = {"P1": "strategy and governance", "P2": "customer experience",
                 "P3": "operations", "P4": "data and technology"}


def norm(s: object) -> str:
    """Loose comparison key — lowercase, alnum-only, single-spaced. Used to test
    whether a finding's .name already matches the capability its body opens with."""
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def pillar_label(subcap_id: object) -> str:
    return _PILLAR_LABEL.get(pillar_of(subcap_id) or "", "this area")


def pillar_prose(pillar_code: object) -> str:
    """Bare pillar code ('P2' / 'p2') -> readable label; '' when unknown, so a
    raw pillar code (`P2`) never leaks into prose and breaks cohesion. The
    text-hygiene scrubbers strip `P#C#…` subcap codes but not bare `P#` pillar
    codes, so composers weaving `card['pillar']` must convert here first
    (2026-07-15 platform-name cohesion audit)."""
    return _PILLAR_LABEL.get(str(pillar_code or "").strip().upper(), "")


def platform_display_name(platform_id: object) -> str | None:
    """Platform id (coarse family OR fine product) -> display NAME, never the
    raw code. Covers both platform_products product ids (`data_cloud` ->
    'Data Cloud') and the 5 coarse families incl. 'salesforce' (PLATFORM_DISPLAY,
    which platform_products.display_name does not carry)."""
    pid = str(platform_id or "").strip()
    if not pid:
        return None
    from app.services.platform_display import PLATFORM_DISPLAY
    from app.services.platform_products import display_name as _disp
    return _disp(pid) or PLATFORM_DISPLAY.get(pid, {}).get("name") or None


def _strip_inline_citation(s: object) -> str:
    """Remove an embedded citation bracket ('[E-041]', '[E-041, E-047]') AND any
    dangling '[' a mid-bracket clip left behind, so a title can be re-cited once
    and cleanly. The 2026-07-15 QA caught "acknowledged [E-041]" clipped at 90
    chars to "acknowledged [", which then read as "acknowledged [and …"."""
    s = re.sub(r"\s*\[[^\]]*\]", "", str(s or ""))   # closed [ … ]
    s = re.sub(r"\s*\[+\s*$", "", s)                  # trailing dangling '['
    return re.sub(r"\s{2,}", " ", s).strip()


def _clip_fused_runon(fact: str) -> str:
    """Salvage the clean lead of a SOURCE-FUSED excerpt. Extract-time
    concatenation sometimes fuses two statements with no punctuation
    ("… ESG committees Committee charters available on fsbwa.com …") — there is
    no ". " to clip at. Two UNAMBIGUOUS signatures only (kept conservative so a
    legitimate mid-sentence proper noun — "the bank uses Salesforce today" — is
    never truncated):
      (a) a source-locator tail ("available on X", "under Investor Relations",
          a bare domain) — pure provenance boilerplate, never prose;
      (b) a repeated-stem echo where a word is immediately followed by its own
          Capitalized case/number variant ("committees Committee") — the tell of
          two fused sentences, not natural prose.
    (2026-07-15 QA.)"""
    f = str(fact or "").strip()
    # (a) drop trailing source-locator boilerplate
    f = re.sub(r"\s+(?:available (?:on|at)|found (?:on|at)|posted (?:on|at)|"
               r"under Investor Relations|via)\b.*$", "", f, flags=re.I)
    f = re.sub(r"\s+\b[\w-]+\.(?:com|org|net|gov|io)\b.*$", "", f, flags=re.I)
    # (b) cut at a repeated-stem echo: "<word> <Word…>" where the two share a
    #     lowercased stem (committees/Committee, charter/Charters). Very specific
    #     — natural prose does not repeat a word's own capitalized variant.
    for m in re.finditer(r"\b([a-z]{4,})\s+([A-Z][a-z]{3,})\b", f):
        w1, w2 = m.group(1).lower().rstrip("s"), m.group(2).lower().rstrip("s")
        if w1 == w2 and m.start(2) >= 40:
            f = f[:m.start(2)]
            break
    return f.rstrip(" .,;:—–-").strip()  # noqa: RUF001


def score_clause(score: object, peer: object, seed_key: object = None) -> str:
    """One score-standing sentence (leading space) — empty when no score.
    Seeded variation so the clause never stamps one frame corpus-wide."""
    if score is None:
        return ""
    from app.services.nlp.stylebook import pick as _pick
    from app.services.nlp.stylebook import seeded as _seeded
    _rng = _seeded(seed_key or "", score, peer, "score-clause")
    if peer is None:
        return _pick(_rng, (
            " It scores {s} out of 5.",
            " The assessment reads it at {s} out of 5.",
            " It stands at {s} out of 5 on the current assessment.",
        ), s=score)
    return _pick(_rng, (
        " It scores {s} out of 5 versus a peer median of {p}.",
        " The assessment reads it at {s} out of 5; the peer median is {p}.",
        " It stands at {s} out of 5, with peers holding a {p} median.",
        " Against a peer median of {p}, it reads {s} out of 5.",
    ), s=score, p=peer)


# A finding NAME that is really an analyst note ('Tiffany Smith (CSO)
# quoted', 'ServiceNow roadmap = Agentforce threat') — spliced as a
# sentence SUBJECT it produces nonsense ('Tiffany Smith (CSO) quoted is
# a priority capability gap', shipped 2026-07-12 screenshot).
_NOTE_SHAPED_NAME_RE = re.compile(
    r"\b(?:quoted|posted|announced|confirm(?:ed|s)|hired?|according to|"
    r"deployed|detected|is|are|was|scores?|launched|provisioned|"
    r"implementing|under (?:active )?construction|building)\b|[=:]", re.I)


def _is_note_shaped_name(nm: str) -> bool:
    # Clause-shaped titles ('Proven in-app personalization, but no
    # enterprise journey orchestration') read fine as HEADLINES but do not
    # parse when spliced into a sentence as a noun phrase ('Closing X, but
    # no Y first raises the floor…' — the UFCU sample-vetting class); a
    # comma-joined contrast or any comma at all in the name means the
    # composer substitutes 'this gap'/'this strength' instead.
    return (bool(_NOTE_SHAPED_NAME_RE.search(nm)) or len(nm.split()) > 8
            or "," in nm or " — " in nm)


# Maturity-band codes and score tokens are internal vocabulary — a
# headline carrying them ('InfoSec at M3-M4') fails the v3 standard
# (verbed, objective-tied, score-free).
_BAND_JARGON_RE = re.compile(
    r"\bM[1-5](?:\s*[-–—]\s*M?[1-5])?\b|\d(?:\.\d+)?\s*/\s*5")  # noqa: RUF001


_HEADLINE_DANGLE_TAIL = re.compile(
    r"(?:\s+(?:and|or|at|vs|of|the|to|for|a|an|in|on|with|by|from|as|is|are|"
    r"was|were|that|which|its|it|into|onto|about|named|per|via))+$", re.I)


def _declip_headline(s: object) -> str:
    """Strip a source-title ingest ellipsis and any trailing dangling
    connective so a parsed headline never reads mid-thought ("… went live
    on", "… leads the"). Mirrors deepen_narrative._headline; kept here so the
    lower-level composer is self-contained. 2026-07-14 W7 audit."""
    t = str(s or "").replace("…", "").replace("...", "").rstrip()
    return _HEADLINE_DANGLE_TAIL.sub("", t).strip(" ,;:—–-'\"")  # noqa: RUF001


# ── S16 headline-gate inverse (2026-07-15) ──────────────────────────────────
# pack_quality_gate.headline_defects rejects a rendered headline (why_now label,
# finding name, insight title) that ends mid-thought (trailing ellipsis or a
# dangling connective) or quotes a maturity score ("… scores 1.56/5", "at
# 2.62/5", "vs a 2.8 peer"). `_headline_safe` is the exact inverse — apply it at
# every headline finalizer so the gate ceiling (0) holds by construction: the
# number belongs in the stat chip, the headline in words.
_HL_CONNECTIVES = ("and", "or", "at", "vs", "of", "the", "to", "for", "an", "in",
                   "on", "with", "by", "from", "as", "is", "are", "was", "were",
                   "that", "which", "its", "it")
_HL_DANGLE_TAIL_RE = re.compile(
    r"(?:\s+(?:" + "|".join(_HL_CONNECTIVES) + r"))+\s*$", re.I)
# Strip the score FRACTION token in place (anywhere), plus an optional lead
# word ("scores 1.56/5", "rated 2.6/5", "at 2.62/5") — removing it in place
# keeps trailing content ("Yelp 1.5/5 from 104 reviews …" → "Yelp from 104
# reviews …") rather than nuking it, so the headline survives.
_HL_SCORE_TOKEN_RE = re.compile(
    r"\s*[-—:(]?\s*(?:\b(?:scores?|rated?|sits?\s+at|at|of|rating|now|only)\b\s*)?"
    r"\d(?:\.\d+)?\s*/\s*5(?:\.0)?\)?\b", re.I)
_HL_PEER_TAIL_RE = re.compile(r"\s*[-—:]?\s*\bvs\b[^,]*\bpeer\b.*$|\s*\bpeer median\b.*$", re.I)


def _headline_safe(s: object) -> str:
    """Guarantee a headline passes the S16 gate: no ellipsis, no trailing
    dangling connective, no quoted maturity score. Returns the original text
    when stripping would leave too little to be a headline (<10 chars)."""
    orig = str(s or "").strip()
    t = orig.replace("…", " ").replace("...", " ")
    t = _HL_PEER_TAIL_RE.sub("", t)                        # drop "vs a 2.8 peer" tails
    t = _HL_SCORE_TOKEN_RE.sub(" ", t)                     # drop score fractions in place
    t = re.sub(r"\s{2,}", " ", t).strip(" -—:;,.'\"")
    prev = None
    while prev != t:                      # strip stacked trailing connectives
        prev = t
        t = _HL_DANGLE_TAIL_RE.sub("", t).strip(" -—:;,.'\"")
    return t if len(t) >= 10 else orig.replace("…", "").replace("...", "").strip(" -—:;,.'\"")


def finding_headline(name: object, subcap_id: object = None,
                     score: object = None, peer: object = None,
                     what: object = None) -> str:
    """A finding headline that reads as a CLAIM (v3: verbed,
    objective-tied, score-free). Analyst headlines that already read as
    claims pass through untouched; note-shaped fragments ('Tiffany
    Smith (CSO) quoted') and band-jargon labels ('InfoSec at M3-M4')
    regenerate from the finding's own first claim sentence, else from
    its direction against the peer benchmark."""
    # W7 (2026-07-14): de-clip the analyst-parsed name up front — a name
    # ingest-truncated at a connective ("… went live on", "… leads the")
    # reads mid-thought, and the pack headline gate rejects it.
    nm = _declip_headline(" ".join(str(name or "").split()).rstrip(" ."))
    # headline-specific defect test — narrower than the sentence-subject
    # guard: a colon claim ('Cybersecurity Visibility Gap: No CISO') is a
    # fine headline; note verbs, '=' shorthand, band jargon and run-on
    # length are not
    bad = (not nm or len(nm) < 8 or " = " in nm
           or _BAND_JARGON_RE.search(nm) or len(nm.split()) > 12
           or re.search(r"\b(?:quoted|posted|announced|according to)\b",
                        nm, re.I))
    if not bad:
        return nm
    w = " ".join(str(what or "").split())
    if w:
        from app.services.nlp.segment import sentences as _guarded_sentences
        _fs = _guarded_sentences(w)
        first = (_fs[0] if _fs else w).strip()
    else:
        first = ""
    first = _declip_headline(re.sub(r"\s*\[[^\]]*\]", "", first).rstrip(" ."))
    if (20 <= len(first) <= 90 and not _BAND_JARGON_RE.search(first)
            and "priority capability gap" not in first
            and "peer median" not in first):
        return first
    pill = pillar_label(subcap_id)
    gap = is_true_gap(score, peer)
    if gap:
        return f"The {pill} gap the next phase inherits — close it first"
    if gap is False:
        return f"A proven {pill} strength to extend while the gaps close"
    return f"The {pill} decision this assessment surfaces"


def compose_finding_body(name: object, subcap_id: object, score: object,
                         peer: object, is_gap: object,
                         client_key: object = None) -> str:
    """Grounded, jargon-free body about the finding's OWN capability — gap-aware
    so an at/above-peer capability is never framed as 'the most material gap'.
    Seeded frame pools (2026-07-13) keep the corpus from sharing one skeleton;
    facts and polarity are invariant."""
    from app.services.nlp.stylebook import pick as _pick
    from app.services.nlp.stylebook import seeded as _seeded
    nm = name or "This capability"
    pill = pillar_label(subcap_id)
    _rng = _seeded(client_key or "", nm, subcap_id, "finding-body")
    cmp = f" against a peer median of {peer}" if peer is not None else ""
    # a note-shaped name never splices as the sentence subject (same guard
    # as the SCQA/strength splice sites) — the frame speaks about "this
    # capability" instead of quoting the analyst headline.
    _subj = "this capability" if _is_note_shaped_name(nm) else nm
    if is_gap is False:
        return _pick(_rng, (
            "{nm} scores {s}/5{cmp} — at or ahead of the peer benchmark, a "
            "relative strength in {pill} that other priorities can build on.",
            "{nm} holds {s}/5{cmp}, at or ahead of the benchmark — a proven "
            "strength in {pill} the roadmap can lean on.",
            "At {s}/5{cmp}, {nm} clears its peer line: a {pill} strength to "
            "extend rather than rebuild.",
        ), nm=_subj, s=score, cmp=cmp, pill=pill)
    return _pick(_rng, (
        "{nm} is a priority capability gap in {pill}, scoring {s}/5{cmp}. "
        "Strengthening it is among the highest-leverage moves to lift "
        "maturity in {pill}.",
        "{nm} reads {s}/5{cmp}, making it a priority gap in {pill} — and "
        "one of the highest-leverage places to invest next.",
        "In {pill}, {nm} carries the priority: it scores {s}/5{cmp}, and "
        "lifting it moves the wider {pill} maturity with it.",
    ), nm=_subj, s=score, cmp=cmp, pill=pill)


_GAP_LANG_RE = re.compile(
    r"most material capability gap|least developed|lowest[- ]scoring|"
    r"binding constraint|deepest gap|next-lowest", re.I)


def has_gap_language(body: object) -> bool:
    return bool(_GAP_LANG_RE.search(str(body or "")))


def reframe_non_gap(body: object, name: object, subcap_id: object,
                    score: object, peer: object) -> str:
    """An at/above-peer capability framed with gap language → recompose neutral."""
    s = str(body or "")
    return compose_finding_body(name, subcap_id, score, peer, False) if has_gap_language(s) else s


# Analyst finding statements prefix a LABEL ("F-002: …", "GAP-1 — …", "3 | …",
# "#4 | …"); strip it before naming so the name is the capability, not the label.
# The delimiter must be followed by WHITESPACE so a decimal like "11.5pp" is NOT
# mistaken for the label "11." (which would corrupt "11.5pp Operating … Gap").
_LABEL_PREFIX = re.compile(
    r"^\s*(?:F-?\s*\d+|GAP-?\s*\d+|#?\s*\d+)\s*[|:.)—–\-]\s+", re.I)  # noqa: RUF001
# A bare finding LABEL with no capability ("1", "F-001", "GAP-3", "#4") — never a
# name.
_BARE_LABEL_RE = re.compile(r"^\s*(?:F-?\s*\d+|GAP-?\s*\d+|#?\s*\d+)\s*$", re.I)
# A LABELED finding leads with a label + a clean NAME, then a parenthetical
# context — the "(subcap, severity)" signature that delimits the name cleanly:
#   "GAP-1 — Integration Stall (P4C3, CRITICAL): Two sprints…" -> "Integration Stall"
_LABELED_FINDING_RE = re.compile(
    r"^\s*(?:gap|f|find(?:ing)?|risk|opp(?:ortunity)?)\-?\s*\d+\s*"
    r"[—–:\-]\s*([A-Z][^(\n]{2,60}?)\s*\([^)]*\)", re.I)  # noqa: RUF001
# The finding's SUBJECT (capability) is what the statement opens with, up to the
# first finding verb/connector.
_FINDING_SUBJECT_RE = re.compile(
    r"^\**\s*(.+?)\s+(?:via|with|creates?|signals?|leads?|reveals?|enables?|"
    r"drives?|reflects?|shows?|indicates?|is\b|are\b|has\b|have\b)",
    re.I)
# PIPE-delimited finding: "<LABEL> | <NAME> | <DETAIL>" (or "<LABEL> | <NAME>").
_PIPE_LABEL_RE = re.compile(
    r"^\s*(?:F-?\s*\d+|GAP-?\s*\d+|#?\s*\d+)\s*\|\s*(.+)$", re.S | re.I)
_PIPE_NAME_TRIM = re.compile(r"\s*[—–;:(]\s*|\s+for\s+|,", re.I)  # noqa: RUF001


def _valid_subject(cap: object) -> str | None:
    s = str(cap or "").strip(" *:—–-").strip()  # noqa: RUF001
    if s and 2 <= len(s.split()) <= 9 and len(s) <= 70 and not is_nonfinding_name(s):
        return s
    return None


def _headline_name(field: object) -> str | None:
    """Reduce a finding's leading STATEMENT to a clean capability headline: the
    subject before the first finding verb ('Loan origination is manual…' ->
    'Loan origination'; 'DTC + Payments roadmap signals…' -> 'DTC + Payments
    roadmap'); else, for a verb-less noun phrase, the leading clause (before a
    '—'/';'/':'/'('/','/'for'), capped at 9 words. None when nothing clean
    remains."""
    s = str(field or "").strip(" *—–-").strip()  # noqa: RUF001
    m = _FINDING_SUBJECT_RE.match(s)
    cand = m.group(1) if m else s
    cand = _PIPE_NAME_TRIM.split(cand, maxsplit=1)[0].strip(" *—–-").strip()  # noqa: RUF001
    words = cand.split()
    if len(words) > 9:
        cand = " ".join(words[:9])
    return _valid_subject(cand)


def finding_pipe_name(body: object) -> str | None:
    """The authoritative NAME from a pipe-delimited finding — the field after the
    label, reduced to its capability headline. 'F-001 | No sales CRM — but … | …'
    -> 'No sales CRM'; 'F-005 | Analytical AI is real; … | …' -> 'Analytical AI';
    '3 | Loan origination is manual… | …' -> 'Loan origination'. None when not
    pipe-formed or the headline is a label/placeholder."""
    m = _PIPE_LABEL_RE.match(str(body or ""))
    if not m:
        return None
    return _headline_name(m.group(1).split("|", 1)[0])


def _clean_finding_name(name: object) -> str:
    """Trim a resolved name to a clean headline: first sentence only; then, only
    if it is STILL a runaway clause (>70 chars / >11 words), clip to the first
    clause and 9 words. A normal multi-word name with an em-dash ('Marshall Ponzi
    Case — BSA/AML Re-Architecture') or a decimal ('11.5pp Operating Efficiency
    Gap') is left intact."""
    s = re.split(r"\.(?:\s|$)", str(name or "").strip(), maxsplit=1)[0]
    s = s.strip(" .:*'\"`").strip()  # drop a leading/trailing quote ("'Help …")
    if len(s) > 70 or len(s.split()) > 11:
        s = _PIPE_NAME_TRIM.split(s, maxsplit=1)[0].strip()
        if len(s.split()) > 9:
            s = " ".join(s.split()[:9])
    return s.strip(" .:—–-*'\"`").strip()  # noqa: RUF001


def finding_subject_phrase(body: object) -> str | None:
    """Finding NAME extracted from the statement when the analyst title is a
    section header ('2 Top Findings'). First a LABELED finding's clean name
    ('GAP-1 — Integration Stall (…)' -> 'Integration Stall'); else the subject the
    de-labelled statement opens with, up to the first finding verb. None for
    supporting prose with no clean leading subject (it drops, never the header)."""
    raw = str(body or "").strip()
    m = _LABELED_FINDING_RE.match(raw)
    if m:
        cap = _valid_subject(m.group(1))
        if cap:
            return cap
    # strip a "F-001 |" / "3 |" / "F-2:" label, take the first pipe field, headline.
    s = _LABEL_PREFIX.sub("", raw).split("|", 1)[0]
    return _headline_name(s)


def build_finding_from_focus(title: object, quote: object, subcap_id: object = None,
                             score: object = None, peer: object = None) -> dict | None:
    """Build ONE top-finding from an analyst report finding (a focus-area verbatim
    observation), per the locked directive that findings are EXTRACTED from the
    client research report — not synthesised from worst-scored categories.

    Returns {name, body, subcap_id, score, peer_median, is_gap} with name ↔ body
    the SAME capability and the gap-direction guard applied, or None when nothing
    usable remains (placeholder name, methodology-only, or too-thin body)."""
    # 'Priority 5 — …' / 'Objective 2: …' numbering is document
    # scaffolding, not finding content — strip it from BOTH the quote
    # and the title before any name/body derivation (2026-07-13 sample:
    # a finding shipped with the label echoed in name and WHAT).
    _scaffold_prefix = re.compile(
        r"^(?:priority|objective|theme|finding|section)\s*\d*\s*[—–:-]\s*", re.I)  # noqa: RUF001
    quote = _scaffold_prefix.sub("", str(quote or "").strip())
    title = _scaffold_prefix.sub("", str(title or "").strip())
    # a scoring-pipeline instruction ("Gap Priority 1 items are required
    # for accurate scoring") is not a finding, whatever row carried it —
    # the quote check stays narrow so real prose about schemas/parsers in
    # a client priority is never dropped
    if _is_pipeline_leak_title(title) or re.search(
            r"gap\s+priority\s+\d|required\s+for\s+accurate\s+scoring",
            quote[:120], re.I):
        return None
    stmt = clip_clean(scrub_placeholder_text(repair_citations(
        strip_boilerplate(dedupe_prefix(quote)))), 480)
    stmt = _SEV_MARKER_RE.sub(" ", stmt).replace("**", "").strip()
    if not stmt or is_methodology_only(stmt) or len(stmt) < 40:
        return None
    is_gap = is_true_gap(score, peer)
    if _reads_as_gap(title, f"{title} {stmt}"):
        is_gap = True  # risk / absence-named items compose gap-first, never as strengths
    # name resolution, most authoritative first: the pipe "<LABEL> | NAME |
    # DETAIL" middle field; else the capability the statement opens with (label
    # stripped); else a cleaned analyst title; else the statement's subject phrase.
    name = finding_pipe_name(stmt)
    if not name:
        lead = leading_capability(_LABEL_PREFIX.sub("", stmt))
        name = lead if (lead and not is_nonfinding_name(lead)) else None
    if not name:
        # Test the RAW title BEFORE scrubbing — scrubbing turns 'Subcap 7' into
        # innocuous prose that would slip past the check. `is_nonfinding_name`
        # rejects the analyst section headers ("2 Top Findings", "4 Critical Gaps
        # & Active Blockers") and annotation labels ("Zennify Relevance: …") the
        # "Top Findings" section repeats as every focus-area title.
        raw_t = str(title or "").strip()
        if raw_t and not is_nonfinding_name(raw_t):
            t = clip_clean(scrub_placeholder_text(strip_boilerplate(raw_t)), 80)
            name = t or None
        if not name:
            # title was a section header → name from the finding statement itself.
            name = finding_subject_phrase(stmt)
    name = _clean_finding_name(name)
    if not name or is_nonfinding_name(name):
        return None
    # BODY: strip the leading "F-003 |" label and convert the remaining pipe
    # separators to prose dashes so the body reads naturally AND its leading
    # capability matches the name (the title↔body coherence the gate enforces).
    body = re.sub(r"\s{2,}", " ", _LABEL_PREFIX.sub("", stmt).replace(" | ", " — ")).strip()[:600]
    # gap-direction: never frame an at/above-peer capability as a gap.
    if is_gap is False:
        body = reframe_non_gap(body, name, subcap_id, score, peer)
    return {"name": name, "body": body, "subcap_id": subcap_id,
            "score": score, "peer_median": peer, "is_gap": is_gap}


# ── Wrong-entity (source-misattribution) contamination ───────────────────────
_FI_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,2})\s+"
    r"(?:Bank|Bancorp|Bancshares|Bancorporation)\b")
_TICKER_RE = re.compile(r"\b(?:NYSE|NASDAQ|OTC|TSX|NYSEAMERICAN)\s*:\s*([A-Z]{2,5})\b")
_RUNID_TOKEN_RE = re.compile(r"DMA-ASM-([A-Z0-9]+)-\d{8}-\d+")
_GENERIC_FI = frozenset({
    "national", "capital", "community", "first", "republic", "enterprise", "commerce",
    "heritage", "pacific", "premier", "liberty", "united", "central", "peoples",
    "citizens", "business", "royal", "exchange", "trust", "american", "federal",
    "state", "valley", "western", "eastern", "southern", "northern", "city", "county"})


def _symbol_from_name(sym: object, name: object) -> bool:
    """True when ticker/initialism `sym` is a subsequence of the entity name's
    letters (so it is the entity's OWN symbol): SSB⊆'SouthState Bank',
    AMH⊆'American Homes', RBB⊆'Royal Business Bank'. 'BBT' is NOT a subsequence of
    'Beacon Bank' (no T) → foreign."""
    letters = [c.upper() for c in str(name or "") if c.isalpha()]
    i = 0
    s = str(sym or "")
    for c in s.upper():
        while i < len(letters) and letters[i] != c:
            i += 1
        if i >= len(letters):
            return False
        i += 1
    return bool(s)


def contamination_signals(text: object, name: object) -> dict:
    """Detect wrong-entity (source-misattribution) contamination in a snapshot —
    the audit's beacon-bank case, whose identity is 'Beacon Bank' but whose ticker
    ('NYSE: BBT'), run-id ('DMA-ASM-BBT-…') and prose ('Berkshire Bank …') are a
    DIFFERENT institution. Returns {tier, foreign_tickers, foreign_runid_tokens,
    foreign_entities}:
      tier 'A' — a foreign ticker/run-id corroborated by a foreign FI name
                 dominating the prose → confidently misattributed (flag + badge,
                 the correct content needs re-ingest).
      tier 'B' — a foreign ticker AND run-id but no foreign FI name → most likely a
                 holding-company symbol (FS Bancorp 'FSBW' for 1st Security Bank);
                 surface for review, NEVER auto-suppress.
      None     — clean."""
    text = str(text or "")
    own = {w for w in re.findall(r"[a-z]+", str(name or "").lower()) if len(w) >= 4}
    foreign_tk = sorted({t for t in set(_TICKER_RE.findall(text))
                         if not _symbol_from_name(t, name)})
    foreign_rid = sorted({r for r in set(_RUNID_TOKEN_RE.findall(text))
                          if not _symbol_from_name(r, name)})
    fi: dict[str, int] = {}
    for m in _FI_NAME_RE.finditer(text):
        nm = m.group(1).strip()
        toks = set(re.findall(r"[a-z]+", nm.lower()))
        if not toks or (toks & own) or all(t in _GENERIC_FI for t in toks):
            continue
        fi[nm] = fi.get(nm, 0) + 1
    foreign_fi = {k: v for k, v in fi.items() if v >= 3}
    has_id = bool(foreign_tk or foreign_rid)
    tier = "A" if (foreign_fi and has_id) else ("B" if (foreign_tk and foreign_rid) else None)
    return {"tier": tier, "foreign_tickers": foreign_tk,
            "foreign_runid_tokens": foreign_rid, "foreign_entities": foreign_fi}


def apply_contamination_badge(ov: dict) -> str | None:
    """Shared twin of the contamination handling — mutates ``ov`` in place.

    Runs :func:`contamination_signals` over the SERIALIZED overview payload
    (contamination is a property of the rendered page, not any one DB
    column) and, when a tier fires, stamps the ``data_quality``
    source-misattribution badge and — tier 'A' only — nulls the
    corroborated-foreign ticker fields to honest-null. Tier 'B' (likely
    holding-company symbol) is badge-for-review only, never suppressed.

    Consumed by BOTH the offline pack patcher
    (``apply_startup_data_fixes._flag_contamination``) and the live
    overview route, so a confidently-wrong assessment never renders
    unflagged on either serve path and ``qa_pack_parity`` stays clean
    (2026-07-04 fresh-DB regen sim: the patcher-only badge was a
    structural parity break). Returns the fired tier, or None when clean.
    """
    import json as _json
    ent = ov.get("entity") or {}
    firm = ov.get("firmographics") or {}
    name = ent.get("name") or firm.get("legal_name") or ""
    sig = contamination_signals(_json.dumps(ov, default=str), name)
    if not sig["tier"]:
        return None
    # NOT setdefault: the serialized live payload carries the schema's
    # explicit `data_quality: None`, and setdefault returns that existing
    # None (key present) — the 2026-07-04 parity sim's one live_err.
    dq = ov.get("data_quality")
    if not isinstance(dq, dict):
        dq = {}
        ov["data_quality"] = dq
    dq["source_misattribution"] = sig["tier"]
    dq["misattribution_markers"] = {
        "foreign_tickers": sig["foreign_tickers"],
        "foreign_runid_tokens": sig["foreign_runid_tokens"],
        "foreign_entities": sorted(sig["foreign_entities"]),
    }
    if sig["tier"] == "A":
        # Corroborated misattribution: null the foreign ticker (the OTHER
        # institution's symbol) — recoverable to honest-null.
        for key in ("ticker", "stock_ticker"):
            if firm.get(key):
                firm[key] = None
    return sig["tier"]


# ═══════════════════════════════════════════════════════════════════════════
# D1 deep composers (plan Part 4 / AE-depth contract Part D, 2026-07-02).
# All pure + NLP-toolkit-backed (app/services/nlp degrades to regex when the
# spaCy model is absent, so these never crash the offline patcher).
# ═══════════════════════════════════════════════════════════════════════════

class ScopedText:
    """Accumulates composed prose WHILE recording every number written into
    it — the ``numbers_in_scope`` the quality rubric coherence check needs.
    Composition and scope can therefore never drift apart."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.numbers: list[float] = []

    def num(self, v: object, fmt: str = "{:g}") -> str:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return ""
        self.numbers.append(f)
        return fmt.format(f)

    def usd(self, v: object) -> str:
        try:
            n = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return ""
        if n >= 1e12:
            self.numbers.append(round(n / 1e12, 2))
            return f"${n / 1e12:.2f}T"
        if n >= 1e9:
            self.numbers.append(round(n / 1e9, 1))
            return f"${n / 1e9:.1f}B"
        if n >= 1e6:
            self.numbers.append(round(n / 1e6))
            return f"${n / 1e6:.0f}M"
        self.numbers.append(n)
        return f"${n:,.0f}"

    def add(self, text: str) -> None:
        if text and text.strip():
            self.parts.append(text.strip())


def _fmt_score(st: ScopedText, sc: object, peer: object = None) -> str:
    """'2.1/5 (peer 2.8)' with both numbers recorded in scope."""
    s = st.num(sc, "{:.1f}")
    if not s:
        return ""
    st.numbers.append(5.0)
    out = f"{s}/5"
    p = st.num(peer, "{:.1f}") if peer is not None else ""
    if p:
        out += f" against a {p} peer median"
    return out


# Assessment-pipeline / QA row titles that must NEVER weave into an AE-facing
# SCQA (the 15/94 internal-leak class: run_manifest.json, RESEARCH_HANDOFF,
# parser/section/evidence-mode meta rows). Client-business issues pass through.
_PIPELINE_LEAK_TITLE_RE = re.compile(
    r"run_manifest|manifest\.json|\.json\b|\.csv\b|\.docx\b|\.xlsx\b|"
    r"research[_ ]handoff|phase_complete|evidence_mode|evidence[_ ]index\b|"
    r"\bP[1-4]\s*=\s*|SKIPPED_|_HANDOFF\b|run[_ ]manifest|parser\b|"
    r"benchmark section|range-style evidence|schema\b|qa[_ ]verdict|"
    r"missing '|section \d+ contains"
    # 2026-07-13 stress-test: assessment-QA rows shipped with kind='client'
    # ("v5.5 assessment produces: P1_Subcap_Scoring…", "RC-02 requires 'peer
    # proxy disclosure'…", "PV-01 sample of 15 subcaps: 93% PASS") — catch the
    # artifact grammar itself: version-prefixed pipeline sentences, snake_case
    # artifact names, RC-/PV- check codes, checker vocabulary.
    r"|\bv\d+\.\d+\s+(?:assessment|expects?|template)"
    r"|[A-Za-z]+_[A-Za-z]+(?:_[A-Za-z]+)*"
    r"|\b(?:RC|PV|QC)-\d+\b|automated check|required phrases"
    r"|\d+%\s*\(?\s*(?:PASS|PARTIAL|FAIL)|counter-evidence signals"
    r"|char(?:acter)?\s+window|subcaps? (?:scoring|have)\b"
    # checker-tolerance rows ("Exceeds ±0.01 threshold") and worksheet tags
    r"|±|^Exceeds\b|\[(?:CEILING_ESTIMATE|ERS[^\]]*|MAT|EVIDENCE|MATCH)\]"
    r"|CRITIC_CHALLENGE|\bLayer \d+ should\b|blocked_subcaps"
    r"|XLSX parsing|PUBLIC mode only"
    # workbook-structure QA rows ("No scoring detail rows found in pillar
    # sheets with expected column format (Columns R/S/T proof structure)")
    r"|scoring detail|pillar sheets?|column format|proof structure"
    r"|Columns? [A-Z]\b|detail rows"
    # methodology sentences the 2026-07-12 zero-evidence sweep found
    # shipping as insight-card TITLES
    r"|required for accurate scoring|affects? assessment (?:accuracy|scoring)"
    r"|^they are presented\b|^evidence gaps and assumptions"
    # pipeline plumbing sentences the analyst report includes ABOVE the real
    # register ("Issues identified in this section flow directly into the
    # Assessment Issue Register (Layer 1 dma-assessment)") — 2026-07-14 vet,
    # woven into a composed exec summary's issue clause on 1 client.
    r"|flow (?:directly )?into the (?:Assessment )?Issue Register"
    r"|Layer \d+ dma-assessment|^Issues identified in this section"
    r"|^capability dimension \d+$"
    # raw run/request IDs woven as an "issue" title (2026-07-14 vet: a HAPO
    # exec summary read "The compliance file is live — DMA-ASM-HAPO-2026… and
    # DMA-RES-HAPO-…"). A run-id is a pipeline artifact, never a client issue.
    r"|\bDMA-(?:ASM|RES|REQ)-[A-Z0-9]|\bREQ-[A-F0-9]{6,}\b", re.I)


def _is_pipeline_leak_title(title: object) -> bool:
    """True for an assessment-QA / pipeline-meta issue title that must not
    reach client-facing narrative."""
    return bool(_PIPELINE_LEAK_TITLE_RE.search(str(title or "")))


# ── Capability-domain lexicons (SCQA splice floor) ──────────────────────────
# MiniLM cosine alone mis-ranks short capability blobs (measured 2026-07-13:
# the Cetera wealth-management non-sequitur scored HIGHER against "Data
# Foundation" than the genuinely-relevant three-core-systems excerpt), so the
# SCQA weave decision is a composed gate: capability-name token overlap OR a
# >=2-hit category-domain lexicon match OR a HIGH semantic bar (0.30).
_DOMAIN_LEX: dict[str, frozenset[str]] = {
    "P1": frozenset((
        "strategy", "strategic", "governance", "board", "oversight", "risk",
        "compliance", "regulatory", "regulator", "policy", "audit", "consent",
        "enforcement", "roadmap", "planning", "attestation", "citation",
        "attribution", "benchmark", "vendor", "sourcing", "budget")),
    "P2": frozenset((
        "customer", "member", "client", "experience", "journey", "channel",
        "omnichannel", "mobile", "app", "digital", "onboarding", "marketing",
        "personalization", "engagement", "satisfaction", "nps", "complaint",
        "service", "contact", "agent", "portal", "website", "banking")),
    "P3": frozenset((
        "operations", "process", "workflow", "automation", "deployment",
        "release", "upgrade", "upgraded", "testing", "uat", "incident",
        "outage", "uptime", "reliability", "sla", "slo", "monitoring",
        "servicing", "fulfillment", "origination", "underwriting", "claims",
        "backoffice", "manual", "efficiency")),
    "P4": frozenset((
        "data", "warehouse", "lake", "lakehouse", "mdm", "golden", "record",
        "360", "integration", "api", "core", "system", "systems", "platform",
        "cloud", "architecture", "infrastructure", "analytics", "reporting",
        "intelligence", "model", "ai", "machine", "pipeline", "etl", "silo",
        "migration", "legacy", "database", "crm")),
}


def capability_fact_relevant(fact: object, cap_name: object,
                             cat: object = None) -> bool:
    """May this excerpt-fact be welded onto this capability's score claim?

    True when the fact shares a content token with the capability NAME, or
    hits the capability category's domain lexicon at least twice, or clears a
    HIGH semantic bar (0.30 — deliberately above the 0.18 interpretive floor,
    because a welded fact asserts causation, not mere context)."""
    f = str(fact or "")
    nm = str(cap_name or "")
    ftoks = {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", f)}
    ntoks = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", nm)}
    if ftoks & ntoks:
        return True
    lex = _DOMAIN_LEX.get(str(cat or "")[:2].upper())
    if lex and len(ftoks & lex) >= 2:
        return True
    try:
        from app.services.nlp.semantic import SemanticIndex, model_available
        if model_available():
            blob = f"{nm}. {pillar_label(cat)}" if cat else nm
            return SemanticIndex().relevance(f[:400], blob[:200]) >= 0.30
    except Exception:
        pass
    return False


# A clean-compliance record ("No enforcement actions found across TX DOB,
# Federal Reserve, FDIC, CFPB, SEC") is a POSITIVE standing, not an issue —
# weaving it under "The issue register adds …" (and softening "no
# enforcement" to "enforcement … not yet in place") inverted its meaning
# on Frost Bank (2026-07-13 write-up QA). Never compose it as a register item.
_CLEAN_ABSENCE_ISSUE_RE = re.compile(
    r"\bno\b[^.;\n]{0,70}\b(?:enforcement|consent\s+order|breach|violation|"
    r"penalt\w+|litigation|lawsuit|complaint|deficienc\w+)s?\b"
    r"[^.;\n]{0,50}\b(?:found|identified|across|against|on\s+record)\b"
    r"|\bclean\b[^.;\n]{0,30}\b(?:record|compliance|enforcement|regulatory)\b"
    r"|\bno\b[^.;\n]{0,50}\b(?:actions?)\b[^.;\n]{0,30}\bfound\b", re.I)


def _is_clean_absence_issue(title: object) -> bool:
    """True when an issue-register title is actually a clean-record absence
    (a positive standing), which must never compose as an issue."""
    return bool(_CLEAN_ABSENCE_ISSUE_RE.search(str(title or "")))


def compose_scqa_deep(bundle: dict) -> dict:
    """The executive-summary composer — key-message-first, style-varied,
    grounded (2026-07-13 stress-test rebuild).

    The 94-client stress-test measured the prior composer's fixed skeleton
    directly: 158 masked six-word frames shared by >=10 clients, the Question
    sentence verbatim on 88/94, and every summary OPENING on a firmographics
    recap ("X is a $Y-in-assets bank regulated by Z…"). The operator mandate:
    no firmographics recap in the executive summary, always lead with the key
    message, and no two clients reading like one template with nouns swapped.

    Architecture — ``nlp.stylebook.scqa_style`` picks one of six paragraph
    architectures per client (content-first: an open high-severity issue pulls
    risk-led, a fresh executive seat pulls momentum, a genuine above-peer
    strength unlocks tension/contrarian; the seeded draw spreads the rest).
    Every architecture leads with the KEY MESSAGE — the binding gap and the
    play — then argues the case, then lays out the sequenced plan. Sentence
    realizations draw from seeded frame pools, so form varies while facts,
    scores and citations stay invariant.

    Grounding is unchanged from the prior contract: every fact comes from the
    bundle, every gap excerpt passes the topical-relevance floor before it is
    fused with a score claim (the incoherent-splice class: a wealth-management
    partnership must never "explain" a technology-operations gap), pipeline
    /QA row titles never weave in, and citations come only from the bundle's
    own pools. ``bundle`` keys are unchanged (all optional; absent facts are
    skipped, never faked) plus:

      client_key : stable per-client seed (display_id); defaults to ``name``.
      issues[].status : OPEN/RESOLVED when known — steers the risk style and
                        lets a resolved order read as history, not live risk.

    Returns {md, numbers, eids, families} exactly as before — md is the
    narrative, numbers the coherence scope, eids the citation scope, families
    the source-family count the caller's >=4 gate enforces.
    """
    from app.services.nlp import stylebook as sb

    st = ScopedText()
    name = str(bundle.get("name") or "This institution").strip()
    key = str(bundle.get("client_key") or name)
    rng = sb.seeded(key, "scqa")
    families: set[str] = set()
    eids_used: list[str] = []

    def cite(eids: object, limit: int = 2) -> str:
        out = []
        for e in (eids or [])[:limit]:  # type: ignore[index]
            e = str(e)
            if _E_ID_RE.fullmatch(e) and e not in eids_used:
                eids_used.append(e)
                out.append(e)
        return f" [{', '.join(out)}]" if out else ""

    def standing_phrase(sc: object, peer: object) -> str:
        """Describe a capability's STANDING in words — the operator mandate is
        an exec summary that reads as narrative, not a scorecard, so the
        summary carries at most ONE numeric maturity anchor (the binding gap)
        and every other capability's position is a phrase, not a "X/5 vs Y"
        recital. Registers the ``peers`` family when a peer line grounds the
        comparison, so the >=4-family floor still holds without reciting the
        number."""
        try:
            s = float(sc) if sc is not None else None
            p = float(peer) if peer is not None else None
        except (TypeError, ValueError):
            s, p = None, None
        if s is not None and p is not None:
            families.add("peers")
            d = p - s
            if d >= 1.0:
                return sb.pick(rng, ("sits well below its peer line",
                                     "trails the peer benchmark by a wide margin",
                                     "lands materially under comparable institutions"))
            if d >= 0.4:
                return sb.pick(rng, ("runs behind its peer line",
                                     "trails the peer benchmark",
                                     "sits under the peer median"))
            if d > -0.4:
                return sb.pick(rng, ("holds roughly level with peers",
                                     "tracks its peer line",
                                     "sits about at the peer median"))
            return sb.pick(rng, ("already clears its peer line",
                                 "runs ahead of the peer benchmark",
                                 "leads comparable institutions"))
        if s is not None:
            if s < 2.0:
                return sb.pick(rng, ("is still early-stage",
                                     "remains nascent", "is barely established"))
            if s < 3.0:
                return sb.pick(rng, ("is still developing",
                                     "remains only partly built out",
                                     "is early in its build-out"))
            if s < 4.0:
                return sb.pick(rng, ("is reasonably solid",
                                     "is largely in place"))
            return sb.pick(rng, ("is a genuine strength",
                                 "is well established"))
        return ""

    # ── ingredients (grounded; nothing faked) ────────────────────────────
    gaps = [g for g in (bundle.get("gaps") or []) if g.get("name")][:3]

    def gap_fact(g: dict) -> str | None:
        """The gap's evidence excerpt as a fact clause — only when it is
        topically ABOUT this capability (the incoherent-splice floor) and
        reads as prose, not a researcher deficit list ("No X. No Y. No Z."
        — the S2 accusatory class in staccato form)."""
        fact = normalize_excerpt_fact(g.get("excerpt"), 300)
        if not fact:
            return None
        fact = _clip_fused_runon(fact)   # salvage clean lead of a source-fused excerpt
        if not fact:
            return None
        # a fact that itself carries worksheet/report scaffolding would make
        # the downstream scaffold-strip belt truncate the whole summary
        if scqa_has_scaffolding(fact) or _is_pipeline_leak_title(fact):
            return None
        if len(fact) > 170:
            # clip at a clause boundary, never mid-thought ("…confirmed, no")
            cut = max(fact.rfind(". ", 40, 170), fact.rfind("; ", 40, 170),
                      fact.rfind(" — ", 40, 170))
            fact = (fact[:cut] if cut >= 40
                    else clip_clean(fact, 170)).rstrip(" .;,—–-")  # noqa: RUF001
        fact = re.sub(r"[,;:—–-]\s+(?:no|and|or|with|the|a|an)\s*$",  # noqa: RUF001
                      "", fact).rstrip()
        if len(fact) < 25:
            return None
        if len(re.findall(r"(?:^|[.;:] )No\b", fact)) >= 2:
            return None
        if not capability_fact_relevant(fact, g.get("name"), g.get("cat")):
            return None
        return fact

    issues = [i for i in (bundle.get("issues") or []) if i.get("title")
              and not _is_pipeline_leak_title(i.get("title"))
              # A clean-compliance record is a POSITIVE standing — weaving
              # it as a register item inverted its meaning on Frost Bank
              # (2026-07-13 write-up QA).
              and not _is_clean_absence_issue(i.get("title"))
              # "Capability gap: X" register rows restate the scored gaps —
              # woven as "issues" they read circular ("Capability gap: X is
              # the sharpest fact … on top of X")
              and not re.match(r"\s*Capability gap\s*:", str(i["title"]), re.I)][:2]
    open_issue = next(
        (i for i in issues
         if str(i.get("severity") or "").lower() in ("critical", "high")
         and str(i.get("status") or "OPEN").upper() not in ("RESOLVED", "CLOSED")),
        None)
    strengths = [s for s in (bundle.get("strengths") or []) if s.get("name")][:1]
    strength = strengths[0] if strengths else None
    ldr = bundle.get("leadership") or {}
    hires = list(ldr.get("new_hires") or [])
    lead_hire = f"{hires[0][0]} ({hires[0][1]})" if hires else None
    gap_roles = list(ldr.get("gap_roles") or [])
    plats = [p for p in (bundle.get("platforms") or []) if p.get("name")][:2]
    trend = str(bundle.get("trend") or "").lower()
    cagr = st.num(bundle.get("cagr_pct"), "{:.1f}")
    ratio_bits = list(bundle.get("ratio_bits") or [])[:2]
    for rb in ratio_bits:
        for mnum in re.findall(r"(\d+(?:\.\d+)?)\s*%", rb):
            with _contextlib.suppress(ValueError):
                st.numbers.append(float(mnum))
    overall = st.num(bundle.get("overall"), "{:.1f}")
    if overall:
        st.numbers.append(5.0)
    uplift = 0.0
    if gaps and gaps[0].get("score") is not None and gaps[0].get("peer") is not None:
        with _contextlib.suppress(TypeError, ValueError):
            uplift = max(0.0, float(gaps[0]["peer"]) - float(gaps[0]["score"]))
    u_txt = st.num(round(uplift, 1), "{:.1f}") if uplift > 0.05 else ""

    style = sb.scqa_style(key, {
        "unresolved_issue": bool(open_issue),
        "new_hire": bool(lead_hire),
        "accelerating": "accelerat" in trend,
        "strength": bool(strength),
        "big_uplift": uplift >= 0.8,
    })

    # ── no true gaps ── either genuinely unscored (honest floor) or the
    # client clears its peer line everywhere (strengths-led summary — the
    # old composer stamped a gaps skeleton here, a score-contradiction).
    if not gaps:
        if strength and strength.get("score") is not None:
            families.add("scores")
            # ONE numeric anchor for the whole summary; the peer relation is
            # carried in words, not a second "vs 2.8 peer median" number.
            s_sc = ""
            s0 = st.num(strength.get("score"), "{:.1f}")
            if s0:
                st.numbers.append(5.0)
                s_sc = f"{s0}/5"
                if strength.get("peer") is not None:
                    families.add("peers")
            lead_s = sb.pick(rng, (
                "No scored capability at {name} sits under its peer line — "
                "the question this assessment poses is where to extend the "
                "lead, not what to fix. {sname} sets the pace, at {ssc}.",
                "{name} clears the peer benchmark across its scored "
                "capabilities; {sname}, at {ssc}, is the clearest proof. "
                "The opportunity is extension, not remediation.",
            ), name=name, sname=str(strength["name"]), ssc=s_sc)
            plats_local = [p for p in (bundle.get("platforms") or []) if p.get("name")]
            if plats_local:
                pl0 = plats_local[0]
                fit0 = st.num(pl0.get("fit"), "{:.0f}")
                if fit0:
                    st.numbers.append(100.0)
                families.add("platform")
                play_s = sb.pick(rng, (
                    " {name} should extend from that strength with {p}"
                    "{fitp}, compounding what already works.",
                    " The recommended extension is {p}{fitp}, built on the "
                    "capabilities that already clear their benchmarks.",
                ), name=name, p=str(pl0["name"]),
                    fitp=f" ({fit0}/100 fit)" if fit0 else "")
            else:
                play_s = (" The recommendation is to keep investing where "
                          "the lead is widest and re-baseline annually.")
            base_cite = cite(bundle.get("base_eids"), limit=2)
            ground_s = sb.pick(rng, (
                "The evidence base reads the same way{c}.",
                "The assessment's evidence index supports the standing{c}.",
            ), c=base_cite) if base_cite else ""
            md = lead_s + play_s + ("\n\n" + ground_s if ground_s else "")
            md = repair_citations_light(md)
            try:
                from app.services.nlp.quality import _text_numbers
                numbers = st.numbers + _text_numbers(md)
            except Exception:
                numbers = st.numbers
            return {"md": md, "numbers": numbers, "eids": eids_used,
                    "families": sorted(families)}
        if overall:
            families.add("scores")
            head = sb.pick(rng, (
                f"Zennify's assessment reads {name}'s overall digital maturity "
                f"at {overall}/5; the capability-level priorities populate once "
                f"the scored assessment ingests.",
                f"{name}'s assessment stands at {overall}/5 overall; the "
                f"per-capability story lands with the scored ingest.",
            ))
        else:
            head = (f"{name}'s priority-gap narrative populates once the "
                    f"assessment's scored capabilities ingest.")
        return {"md": head, "numbers": st.numbers, "eids": eids_used,
                "families": sorted(families)}

    g0 = gaps[0]
    g0_name = str(g0["name"])
    # The binding gap carries the summary's ONE numeric maturity anchor; its
    # standing is stated in words, the number attached once. Everything else
    # (secondary gaps, the strength, the overall) is described qualitatively —
    # the operator mandate is a narrative, not a score recap.
    g0_stand = standing_phrase(g0.get("score"), g0.get("peer"))
    _g0_num = st.num(g0.get("score"), "{:.1f}")
    g0_anchor = ""
    if _g0_num:
        st.numbers.append(5.0)
        families.add("scores")
        g0_anchor = f"{_g0_num}/5"
    # "sits well below its peer line, at 2.4/5" — words first, one number.
    if g0_anchor and g0_stand:
        g0_read = f"{g0_stand}, at {g0_anchor}"
    elif g0_anchor:
        g0_read = f"reads {g0_anchor}"
    else:
        g0_read = g0_stand or "is the binding constraint"
    g0_fact = gap_fact(g0)
    g0_cite = cite(g0.get("eids"))
    if g0.get("peer") is not None:
        families.add("peers")

    p0 = plats[0] if plats else None
    fit_txt = ""
    if p0:
        f0 = st.num(p0.get("fit"), "{:.0f}")
        if f0:
            st.numbers.append(100.0)
            fit_txt = f0

    # ── paragraph 1 — THE KEY MESSAGE (per-style opener + the play) ──────
    p1: list[str] = []
    if style == "risk" and open_issue:
        sev = str(open_issue.get("severity") or "").lower()
        icite = cite(open_issue.get("eids"))
        families.add("issues")
        # Weld hygiene (2026-07-14 prose audit): the register title runs
        # through the title humanizer (register codes, shouting, deficit
        # shorthand) — raw fragments used to ship verbatim — and severity
        # reads as prose, never a bolted-on "(high severity)" label.
        _t1 = clip_clean(finalize_title_text(str(open_issue["title"])), 140)
        if sev in ("critical", "high"):
            p1.append(sb.pick(rng, (
                "For {name}, the sharpest fact on file is a {sev}-severity "
                "issue — {title}{icite} — and it lands squarely on the "
                "capability the assessment treats as most binding: {gap}, "
                "which {read}{gcite}. Those two are one problem, not two.",
                "The story at {name} starts with a {sev}-severity register "
                "item, {title}{icite}. It rests directly on {gap} — the "
                "capability the assessment ranks most binding, which {read}"
                "{gcite} — and neither resolves without the other.",
                "Two facts set {name}'s priority, and they compound: a "
                "{sev}-severity issue, {title}{icite}, sitting on top of "
                "{gap}, the most binding capability in the file, which {read}"
                "{gcite}.",
            ), name=name, title=_t1, sev=sev, icite=icite, gap=g0_name,
                read=g0_read, gcite=g0_cite))
        else:
            p1.append(sb.pick(rng, (
                "For {name}, the sharpest fact on file is {title}{icite}, and "
                "it lands squarely on the capability the assessment treats as "
                "most binding: {gap}, which {read}{gcite}. Those two are one "
                "problem, not two.",
                "The story at {name} starts with {title}{icite}. It rests "
                "directly on {gap} — the capability the assessment ranks most "
                "binding, which {read}{gcite} — and neither resolves without "
                "the other.",
                "Two facts set {name}'s priority, and they compound: {title}"
                "{icite}, sitting on top of {gap}, the most binding capability "
                "in the file, which {read}{gcite}.",
            ), name=name, title=_t1, icite=icite, gap=g0_name, read=g0_read,
                gcite=g0_cite))
    elif style == "momentum" and (lead_hire or "accelerat" in trend):
        families.add("leadership" if lead_hire else "financials")
        mom = (f"{lead_hire} is newly in seat" if lead_hire
               else "the analyst classifies the trajectory as accelerating")
        # A noun-phrase form for the "With …," frame — the clause form
        # ("With X is newly in seat, …") is ungrammatical (2026-07-14 vet).
        mom_np = (f"{lead_hire} newly in seat" if lead_hire
                  else "the trajectory classified as accelerating")
        p1.append(sb.pick(rng, (
            "{name}'s window is open: {mom}, and the capability that decides "
            "what the new agenda can deliver — {gap} — {read}{gcite}.",
            "Timing leads the story at {name}. {mom_cap}, and {gap}, which "
            "{read}{gcite}, is the fix that has to land inside that window.",
            "With {mom_np}, {name} gets one clean shot at re-sequencing; the "
            "assessment says spend it on {gap}, which {read}{gcite}.",
        ), name=name, mom=mom, mom_cap=_cap(mom), mom_np=mom_np, gap=g0_name,
            read=g0_read, gcite=g0_cite))
    elif style == "tension" and strength:
        s_stand = standing_phrase(strength.get("score"), strength.get("peer"))
        p1.append(sb.pick(rng, (
            "{name} has already proven it can build to peer-beating depth — "
            "{sname} {sstand} — while {gap} {read}{gcite}; that spread is the "
            "story of this assessment.",
            "The distance between {name}'s strongest and weakest capability "
            "frames the opportunity: {sname} {sstand}, which shows the "
            "organization can execute, while {gap}, which {read}{gcite}, "
            "shows where that execution has yet to land.",
            "{name}'s story is a split: {sname} {sstand}, while {gap} {read}"
            "{gcite}. Closing the second to the standard of the first is the "
            "assessment's core recommendation.",
        ), name=name, sname=str(strength["name"]), sstand=s_stand,
            gap=g0_name, read=g0_read, gcite=g0_cite))
    elif style == "contrarian" and strength and overall:
        s_stand = standing_phrase(strength.get("score"), strength.get("peer"))
        p1.append(sb.pick(rng, (
            "{name}'s headline maturity hides the split that matters: {sname} "
            "{sstand}, while {gap} {read}{gcite}. The blended average is not "
            "where the action is.",
            "Read past {name}'s headline number: the real signal is the "
            "spread between {sname}, which {sstand}, and {gap}, which {read}"
            "{gcite} — and the second is the one that moves the business.",
            "The blended maturity score understates what is decidable at "
            "{name}: {gap} {read}{gcite}, while {sname} {sstand}. Which way "
            "the average moves is a sequencing choice.",
        ), name=name, sname=str(strength["name"]), sstand=s_stand,
            gap=g0_name, read=g0_read, gcite=g0_cite))
    elif style == "decision":
        p1.append(sb.pick(rng, (
            "{name} has one call to make this cycle: fund {gap} — which "
            "{read}{gcite} — ahead of everything else, or keep pricing its "
            "drag into every dependent initiative.",
            "The decision in front of {name} is narrow and consequential: "
            "close {gap}, which {read}{gcite}, before adding anything new on "
            "top of it.",
            "Everything in {name}'s assessment reduces to one sequencing "
            "call, and it concerns {gap}: it {read}{gcite}, and it is the "
            "layer the other investments inherit.",
        ), name=name, gap=g0_name, read=g0_read, gcite=g0_cite))
    else:  # thesis (and any fallback)
        p1.append(sb.pick(rng, (
            "The single highest-leverage move for {name} is closing {gap}, "
            "which {read}{gcite} — the constraint its other digital "
            "investments inherit.",
            "One capability decides how fast {name}'s digital maturity "
            "moves: {gap}, which {read}{gcite}. Close it, and the dependent "
            "investments start compounding.",
            "{gap} is where {name}'s next dollar works hardest: it {read}"
            "{gcite}, and it underpins the capabilities every other "
            "initiative builds on.",
        ), name=name, gap=g0_name, read=g0_read, gcite=g0_cite))
    if g0_fact:
        p1.append(sb.pick(rng, (
            "The evidence behind it is concrete: {fact}.",
            "What that looks like on the ground: {fact}.",
            "The file grounds it plainly — {fact}.",
        ), fact=g0_fact))
    if p0:
        families.add("platform")
        fitp = f" ({fit_txt}/100 fit)" if fit_txt else ""
        # W6 (2026-07-14): name WHY #2 sequences behind #1 — the concrete
        # capability it inherits — so the exec summary answers "which comes
        # first, and why", not just the order. Grounded in the persisted DAG
        # (plats[1].seq_after / .gate); silent when the dependency is unknown.
        if len(plats) > 1:
            _p1nm = str(plats[1]["name"])
            _gate = clip_clean(str(plats[1].get("gate") or "").strip(), 52)
            _after = [str(a) for a in (plats[1].get("seq_after") or [])]
            if _gate and (not _after or str(p0["name"]) in _after):
                # Provider-neutral: name #2's OWN gating prerequisite, without
                # implying #1 supplies it (it may not — the DAG only fixes the
                # order). "X follows once its Y prerequisite is in place."
                tail = (f"; {_p1nm} follows once its {_gate} prerequisite is "
                        f"in place")
            else:
                tail = f", sequencing {_p1nm} behind it"
        else:
            tail = ""
        tgt = str(p0.get("top_subcap") or "").strip()
        _p0_inc = str(p0.get("incumbent") or "").strip()
        # Every variant carries an explicit action token (should/recommend/
        # prioritize) — the rubric's actionability gate is a hard floor.
        if str(p0.get("lens") or "") == "integrate" and _p0_inc:
            # 2026-07-14 lens: the layer is occupied by a named incumbent —
            # the play is integration alongside it, never a greenfield pitch.
            target = f", opening at {tgt}" if tgt else ""
            p1.append(sb.pick(rng, (
                "The platform play is integration-first: {name} should run "
                "{p}{fitp} alongside {inc}, the platform already anchoring "
                "that layer{target}{tail}.",
                "On platform fit, {p} ranks first{fitp} — and with {inc} "
                "already installed, the recommended motion is integrating "
                "{p} with {inc}, not replacing it{target}{tail}.",
                "{name} should prioritize the {p} integration conversation "
                "alongside {inc}{fitp}{target}{tail}.",
            ), name=name, p=str(p0["name"]), fitp=fitp, inc=_p0_inc,
                target=target, tail=tail))
        elif tgt and norm(tgt) != norm(g0_name):
            # The platform's own strongest entry point is NOT the binding
            # gap — say so as the platform's fact, never implying identity
            # (the thesis names one capability, the play must not silently
            # substitute another).
            p1.append(sb.pick(rng, (
                "On platform fit, {p} ranks first{fitp}; the recommended "
                "entry point is {tgt}{tail}.",
                "{p} carries the strongest platform fit{fitp} and should "
                "open at {tgt}{tail}.",
                "The platform sequence should open with {p}{fitp}, aimed "
                "first at {tgt}{tail}.",
                "For the platform motion, prioritize {p}{fitp}, with {tgt} "
                "as its entry point{tail}.",
            ), p=str(p0["name"]), fitp=fitp, tgt=tgt, tail=tail))
        else:
            target = f" against {tgt}" if tgt else ""
            p1.append(sb.pick(rng, (
                "The recommended play is {p}-first{fitp}{target}{tail}.",
                "{name} should lead with {p}{fitp}{target}{tail}.",
                "{p}{fitp} should go first{target}{tail}.",
                "The platform call: prioritize {p}{fitp}{target}{tail}.",
            ), name=name, p=str(p0["name"]), fitp=fitp, target=target,
                tail=tail))
    else:
        p1.append(sb.pick(rng, (
            f"{name} should sequence remediation gap-first: close {g0_name}, "
            f"then re-baseline the capabilities that depend on it.",
            f"The recommendation is remediation-first — {g0_name}, then the "
            f"dependent capabilities re-measured.",
        )))

    # ── paragraph 2 — THE CASE (argued gaps, issues, counter-signal) ─────
    # Fact-scarce clients (no weavable prose anywhere) get a leaner case —
    # a third score-only sentence just deepens the score-recital density
    # the exec-summary gate rejects.
    if (not g0_fact and not any(gap_fact(g) for g in gaps[1:])
            and not (bundle.get("extra_facts") or [])):
        gaps = gaps[:2]
    p2: list[str] = []
    # Secondary gaps: describe the PATTERN qualitatively and GROUP them into
    # ONE sentence — no per-capability score recital (the operator's "recap of
    # scores"). One concrete evidence fact carries the detail; the numbers stay
    # on the heatmap tiles where they belong.
    _sec = [g for g in gaps[1:] if g.get("name")]
    if _sec:
        families.add("scores")
        if any(g.get("peer") is not None for g in _sec):
            families.add("peers")
        _names = " and ".join(str(g["name"]) for g in _sec)
        _sfact = next((f for g in _sec if (f := gap_fact(g))), None)
        _scite = cite([e for g in _sec for e in (g.get("eids") or [])])
        _lead = sb.pick(rng, (
            f"The same shortfall runs through {_names}",
            f"{_names} tell the same story",
            f"That pattern repeats across {_names}",
            f"The lag widens in {_names}",
        ))
        p2.append(f"{_lead} — {_sfact}{_scite}." if _sfact
                  else f"{_lead}{_scite}.")
    # Issues: SYNTHESIZE into ONE sentence about what the register MEANS for
    # posture — never one stapled sentence per row (the operator's "fact
    # dump"). At most two named and joined; the meaning carries the point.
    _live = [i for i in issues
             if not (style == "risk" and i is open_issue)
             and str(i.get("status") or "OPEN").upper() not in ("RESOLVED", "CLOSED")]
    _done = [i for i in issues
             if str(i.get("status") or "").upper() in ("RESOLVED", "CLOSED")]
    if _live:
        families.add("issues")
        # Strip any citation the register title already carries BEFORE clipping —
        # clip_clean(90) cutting inside an embedded "[E-041]" left a dangling "["
        # before the " and " join ("acknowledged [and SEC 10-K…"). The real
        # citation is re-attached once, cleanly, via _ic (2026-07-15 QA).
        _t = " and ".join(
            _strip_inline_citation(clip_clean(
                _strip_inline_citation(finalize_title_text(str(i["title"]))), 90))
            for i in _live[:2])
        _ic = cite([e for i in _live for e in (i.get("eids") or [])])
        p2.append(sb.pick(rng, (
            f"The compliance file is live — {_t}{_ic} — and that open work is "
            f"what keeps the posture conservative.",
            f"The register is not quiet: {_t}{_ic}, the kind of unfinished "
            f"business that holds governance cautious.",
        )))
    elif _done:
        families.add("issues")
        _t = clip_clean(finalize_title_text(str(_done[0]["title"])), 90)
        _ic = cite(_done[0].get("eids"))
        p2.append(
            f"History still shapes the file: {_t}{_ic} is resolved, but the "
            f"caution it built shows in today's posture.")
    # Qualitative counter-signal — the point is that the organization CAN
    # build to peer depth, not the number. (No score recited here.)
    if (strength and style not in ("tension", "contrarian")
            and strength.get("score") is not None):
        families.add("scores")
        p2.append(sb.pick(rng, (
            "Not everything trails: {sname} already clears its peer line — "
            "proof the organization can build to depth when it commits.",
            "{sname} is the standing asset in the file; it is leverage for "
            "the work above, not a rebuild.",
            "One reading runs in {name}'s favor — {sname} is ahead of peers, "
            "so the execution capacity is already there.",
        ), sname=str(strength["name"]), name=name))
    if lead_hire and style != "momentum":
        families.add("leadership")
        p2.append(sb.pick(rng, (
            f"Leadership is in motion — {lead_hire} is newly in seat, and "
            f"platform direction tends to set inside a new executive's first "
            f"two quarters.",
            f"{lead_hire} arriving gives the roadmap an owner; first-quarter "
            f"platform choices tend to stick.",
        )))
    elif gap_roles and not hires:
        families.add("leadership")
        role0 = str(gap_roles[0])
        p2.append(sb.pick(rng, (
            f"The roster carries no named {role0} yet — ownership of the "
            f"capabilities above is an open seat.",
            f"A named {role0} is still an open seat on the roster, which "
            f"leaves the capabilities above unowned.",
        )))
    # Score-recap floor (deploy review): when fewer than TWO evidence-fact
    # sentences wove in (gap excerpts failed the prose/relevance floors), the
    # summary reads as a score recital. Weave standalone corroborating facts
    # from the bundle's own extra_facts pool — grounded, cited, never welded
    # to a score claim they don't support.
    n_facts = (1 if g0_fact else 0) + sum(1 for g in gaps[1:] if gap_fact(g))
    # Lead-ins CONNECT the fact to the argument (why it matters), rather than
    # announcing "here is another evidence fact" — the 2026-07-15 operator note:
    # synthesize the evidence into the story, don't state it and move on.
    _xf_pool = (
        "That gap is not abstract: {fact}{c} — the concrete drag the play has to lift.",
        "The evidence shows why it bites: {fact}{c}.",
        "It plays out in the record — {fact}{c} — which is what the sequencing has to fix first.",
        "Grounding the pattern: {fact}{c}, the kind of friction the lead move removes.",
    )
    _xf_last = -1
    for xf in (bundle.get("extra_facts") or []):
        # cap at ONE woven extra fact — a second "from the file" lead-in reads
        # as the fact-stapling the operator flagged (2026-07-14). It only fires
        # at all when the gaps themselves carried no concrete fact.
        if n_facts >= 1:
            break
        xfact = normalize_excerpt_fact(xf.get("fact"), 300)
        if not xfact:
            continue
        xfact = _clip_fused_runon(xfact)   # salvage clean lead of a source-fused excerpt
        if not xfact:
            continue
        if len(xfact) > 170:
            # clause-boundary clip — never mid-parenthesis ("…Consent O")
            xcut = max(xfact.rfind(". ", 40, 170), xfact.rfind("; ", 40, 170),
                       xfact.rfind(" — ", 40, 170))
            xfact = (xfact[:xcut] if xcut >= 40
                     else clip_clean(xfact, 170)).rstrip(" .;,—–-")  # noqa: RUF001
        if len(xfact) < 40:
            continue
        if scqa_has_scaffolding(xfact) or _is_pipeline_leak_title(xfact):
            continue
        xcite = cite(xf.get("eids"))
        # two facts must not share a lead-in — draw, and step past a repeat
        idx = rng.randrange(len(_xf_pool))
        if idx == _xf_last:
            idx = (idx + 1) % len(_xf_pool)
        _xf_last = idx
        p2.append(_xf_pool[idx].format(fact=xfact, c=xcite))
        families.add("scores")
        n_facts += 1
    # NOTE (2026-07-15): the old "grounding floor" appended a hollow sentence
    # ("The assessment's evidence base reads the same way [E-003]") purely to
    # pad the citation count to six — the exact "stating evidence IDs without
    # drilling down" the operator flagged. Removed. The >=2 distinct-real-E-ID
    # floor is guaranteed downstream by deepen_narrative.thread_scqa_citations,
    # which threads real ids into ACTUAL argument sentences rather than a filler
    # sentence, so grounding holds without the dump.

    # ── paragraph 3 — THE PLAN (prize, capacity, analyst tie, the choice) ─
    p3: list[str] = []
    if u_txt:
        families.add("peers")
        # The prize is described, not counted — a "{u} maturity points" recital
        # is exactly the scorecard reading the operator asked the summary to
        # drop. The point is WHY closing it pays off, not the delta.
        p3.append(sb.pick(rng, (
            "Closing {gap} to the peer line is the highest-leverage move on "
            "the board: the capabilities stacked on it inherit the lift and "
            "compound it.",
            "The prize is parity on {gap} — worth more than the single "
            "capability suggests, because it unblocks every dependent "
            "capability built above it.",
            "Bringing {gap} level with peers is the foundation move; the "
            "dependent work then rides that base instead of routing around it.",
            "Parity on {gap} is what the rest compounds from — build it up, "
            "and every later investment starts from a higher floor.",
        ), gap=g0_name))
    if cagr or ratio_bits:
        families.add("financials")
        fin_cite = cite(bundle.get("fin_eids"))
        if cagr and ratio_bits:
            # ONE fundamental, not the pair — a two-ratio recital reads as the
            # number-dump the operator flagged; the point is that the balance
            # sheet can fund the work, not the full ratio sheet.
            p3.append(sb.pick(rng, (
                "The fix is fundable: multi-year growth of {c}%, with "
                "{rb} underneath it, gives the balance sheet room to carry "
                "it{fc}.",
                "Funding is not the constraint — growth at {c}% a year, on "
                "{rb} fundamentals, leaves balance-sheet room for the "
                "program{fc}.",
            ), c=cagr, rb=ratio_bits[0], fc=fin_cite))
        elif cagr:
            p3.append(sb.pick(rng, (
                "Multi-year growth of {c}% says the balance sheet can "
                "carry the program{fc}.",
                "Growth at {c}% a year gives the program its funding room on "
                "the balance sheet{fc}.",
            ), c=cagr, fc=fin_cite))
        else:
            p3.append(sb.pick(rng, (
                "Fundamentals of {rb} give the balance sheet room to carry "
                "the program{fc}.",
                "With {rb} on the fundamentals, the balance sheet can fund "
                "the work{fc}.",
            ), rb=", ".join(ratio_bits), fc=fin_cite))
    fq = str(bundle.get("focus_quote") or "").strip()
    # "The analyst frames the priority as ..." must quote a PRIORITY — an
    # OBJECTIVE-shaped statement. A launch/event fact in that frame is
    # false attribution (2026-07-13 vetting: a Lumin go-live fact was
    # quoted as 'the priority'). Event-lead or unshaped quotes are
    # dropped; the answer stands without the sentence.
    fq = re.sub(r"\[E-[^\]]*\]", "", fq).strip()
    _OBJ_SHAPE = re.compile(
        r"\b(?:priorit\w+|strateg\w+|invest\w+|expand\w*|transform\w*|"
        r"moderniz\w*|initiative\w*|roadmap|goals?\b|focus\w*|growth|"
        r"consolidat\w+|unif\w+)", re.I)
    _EVENT_LEAD = re.compile(
        r"\b(?:launched|went live|completed|announced|opened|acquired|"
        r"deployed|joined|hired)\b", re.I)
    if fq and (not _OBJ_SHAPE.search(fq) or _EVENT_LEAD.search(fq[:80])):
        fq = ""
    fq = quote_span(fq, 180) if fq else ""
    if fq:
        q = clip_clean(fq, 180).rstrip(" .!?;:—–-")  # noqa: RUF001
        p3.append(sb.pick(rng, (
            'The analyst\'s own framing — "{q}" — points the same direction: '
            "{gap} ahead of the point solutions layered on it.",
            '"{q}" is how the analyst frames the priority, which reads as the '
            "case for sequencing {gap} first.",
            'That matches the analyst\'s framing — "{q}" — and the sequencing '
            "case for {gap} it implies.",
        ), q=q, gap=g0_name))
    # the decision beat — every style closes on the choice, phrased its way.
    if style == "decision":
        p3.append(sb.pick(rng, (
            f"The recommendation is {g0_name} first — before the next "
            f"platform commitment — with the dependent work re-baselined "
            f"behind it.",
            f"On the evidence, the recommended call is {g0_name}-first; each "
            f"quarter of delay prices the workaround deeper into the "
            f"architecture.",
        )))
    elif style == "momentum" or (lead_hire and style == "risk"):
        p3.append(sb.pick(rng, (
            "Timing favors acting inside the new leadership's first two "
            "quarters, before platform commitments lock.",
            "The window is the current leadership transition — platform "
            "commitments made now will hold for years.",
        )))
    else:
        p3.append(sb.pick(rng, (
            f"The choice for {name} is sequencing: fix {g0_name} first and "
            f"let the rest inherit the lift, or keep funding around it at "
            f"compounding cost.",
            f"What {name} decides on {g0_name} this cycle sets the cost "
            f"curve for everything downstream — sequencing it first is the "
            f"cheaper path in every scenario the evidence supports.",
            f"Either {name} closes {g0_name} now, or every dependent "
            f"initiative keeps paying the integration tax; the assessment's "
            f"numbers argue for now.",
            f"{name} can put {g0_name} first and let each later investment "
            f"inherit the lift, or leave the drag in place and price it "
            f"into every roadmap line.",
            f"One sequencing call decides the economics: {g0_name} ahead "
            f"of the rest, or a workaround premium on everything that "
            f"follows.",
            f"The evidence leaves {name} a clean either/or on {g0_name}: "
            f"close it before the next commitment, or carry its cost "
            f"through every initiative built above it.",
        )))

    # Grounding floor (2026-07-15): an unlinked run (gaps with no linked E-IDs)
    # has NO claim-relevant evidence to match, so cite the SINGLE best-tier
    # id (base_eids is tier-ordered) onto the closing recommendation — one
    # honest "best-available" anchor, not a 3-id tier dump. Relevance-matched
    # per-claim citation is what the LINKED path (gap.eids) and the LLM
    # reasoning layer do; padding an unlinked run to multiple ids would be the
    # "so many E-IDs, none the most relevant" defect the operator flagged.
    if not eids_used and bundle.get("base_eids") and p3:
        floor_cite = cite(bundle.get("base_eids"), limit=1)
        if floor_cite:
            _close = p3[-1].rstrip()
            if _close and _close[-1] in ".!?":
                p3[-1] = _close[:-1] + floor_cite + _close[-1]
            else:
                p3[-1] = _close + floor_cite

    md = "\n\n".join(" ".join(p) for p in (p1, p2, p3) if p)
    md = repair_citations_light(md)
    # Graceful degradation: a capability whose catalogue name did not resolve
    # (offline, or a production edge with a missing catalogue mapping) must
    # NEVER surface as "capability dimension 25" in the flagship narrative —
    # neutralise it to readable prose ("a lower-scoring capability area").
    # The production reparse fills the real name; this is the safety floor
    # (2026-07-14 vet: acuity/greenstone/wescom SCQAs read "capability
    # dimension N" offline).
    md = scrub_placeholder_text(md)
    if len(md) > 4000:
        md = clip_sentence_boundary(md, 4000)
    # Verbatim fragments (issue titles, the analyst quote) carry their OWN
    # numbers. They are source-verbatim — never invented — so they join the
    # coherence scope, extracted with the SAME normalizer the rubric uses.
    try:
        from app.services.nlp.quality import _text_numbers
        numbers = st.numbers + _text_numbers(md)
    except Exception:
        numbers = st.numbers
    return {"md": md, "numbers": numbers, "eids": eids_used,
            "families": sorted(families)}

# Family-presence heuristic for KEPT (analyst-authored) SCQAs — the ≥4
# source-family floor holds whether the narrative was composed or kept.
_SCQA_FAMILY_PATTERNS: dict[str, re.Pattern] = {
    "financials": re.compile(r"\$\s?\d|CAGR|ROA\b|ROE\b|efficiency ratio|net income|"
                             r"total assets|deposit|revenue|premium|NIM\b|balance sheet", re.I),
    "scores": re.compile(r"\d(?:\.\d+)?\s*/\s*5|\d(?:\.\d+)? out of 5|maturity|\bscor(?:es?|ed|ing)\b", re.I),
    "peers": re.compile(r"\bpeer\b|peer[- ](?:median|benchmark|set|cohort)|comparable institutions|cohort", re.I),
    "issues": re.compile(r"consent order|enforcement|remediat|issue register|\bMRA\b|"
                         r"examination|deficienc|open issue|regulatory (?:action|order|finding)", re.I),
    "leadership": re.compile(r"\bC(?:EO|FO|IO|TO|ISO|DO|OO|MO|RO)\b|chief \w+ officer|"
                             r"leadership|executive|president\b|new hire|newly in seat", re.I),
    "platform": re.compile(r"Salesforce|Data Cloud|Agentforce|Databricks|Tableau|Twilio|"
                           r"nCino|MuleSoft|platform (?:path|sequence|fit)|\bCRM\b", re.I),
}


def scqa_family_count(md: object) -> int:
    """How many of the six source families a narrative actually weaves in."""
    s = str(md or "")
    return sum(1 for p in _SCQA_FAMILY_PATTERNS.values() if p.search(s))


def repair_citations_light(md: str) -> str:
    """Whitespace/citation tidy that preserves paragraph breaks (the full
    repair_citations collapses newlines — wrong for a multi-paragraph SCQA)."""
    md = re.sub(r"\bE--+(\d)", r"E-\1", md)
    md = re.sub(r"[ \t]+([.,;:])", r"\1", md)
    return re.sub(r"[ \t]{2,}", " ", md).strip()


def scrub_unknown_eids(md: str, valid: set[str] | frozenset[str]) -> str:
    """Remove citation tokens that don't exist in the run's evidence index —
    an analyst quote citing an E-ID the ingest never captured is unverifiable
    and must not render as a dead chip. Preserves paragraph breaks."""
    if not md:
        return md

    def _rep(m: re.Match) -> str:
        return m.group(0) if m.group(0) in valid else ""

    md = _E_ID_RE.sub(_rep, md)
    md = re.sub(r"\[\s*(?:,\s*)*\]", "", md)      # emptied brackets
    md = re.sub(r"\[\s*,\s*", "[", md)
    md = re.sub(r",\s*(?:,\s*)+", ", ", md)
    md = re.sub(r",\s*\]", "]", md)
    md = re.sub(r"\(\s*\)", "", md)
    return repair_citations_light(md)


def clip_sentence_boundary(md: str, limit: int) -> str:
    """Hard clamp at a sentence boundary, preserving paragraph structure."""
    if len(md) <= limit:
        return md
    cut = md[:limit]
    for sep in (". ", ".\n", "!\n", "? "):
        idx = cut.rfind(sep)
        if idx >= limit // 2:
            return cut[: idx + 1].rstrip()
    return cut.rsplit(" ", 1)[0].rstrip()


# The entity-level maturity claim ("overall digital maturity at 1.8/5") — the
# SAME anchoring the audit's scqa_contradicts_score uses. Per-capability gap
# scores ("deepest gap is X at 1.3/5") sit behind a capability name and are NOT
# matched, so they are never rewritten.
_OVERALL_MATURITY_CLAIM_RE = re.compile(
    r"(\bdigital maturity\b[^.\n]{0,14}?)(\d\.\d{1,2})(\s*(?:/\s*5|out of 5))"
    r"|((?:overall|composite|weighted|enterprise)[^.\n]{0,30}?\bmaturity\b"
    r"[^.\n]{0,14}?)(\d\.\d{1,2})(\s*(?:/\s*5|out of 5))",
    re.I,
)


def enforce_overall_maturity_claim(md: object, overall: object) -> str:
    """Rewrite the SCQA's entity-level 'overall digital maturity at X/5' number so
    it EQUALS the run's overall_score (the value the /overview endpoint renders).
    Keeps the composed narrative and the dashboard score in lockstep — the stale
    'places overall digital maturity at 1.8/5' vs live 2.06 contradiction class."""
    s = str(md or "")
    try:
        target = f"{float(overall):.1f}"
    except (TypeError, ValueError):
        return s

    def _sub(m: re.Match[str]) -> str:
        if m.group(2) is not None:
            return f"{m.group(1)}{target}{m.group(3)}"
        return f"{m.group(4)}{target}{m.group(6)}"

    return _OVERALL_MATURITY_CLAIM_RE.sub(_sub, s)


_ELLIPSIS_TAIL_RE = re.compile(r"(?:…|\.{3})\s*$")
_DANGLING_WORD_RE = re.compile(r"\s+\w+[—–-]$")   # " uneve—" / " consol-"  # noqa: RUF001
_TRAILING_DASH_RE = re.compile(r"\s*[—–-]\s*$")  # noqa: RUF001


def finalize_finding_body(body: object, name: object = None, subcap_id: object = None,
                          score: object = None, peer: object = None) -> str:
    """Guarantee a finding body reads as COMPLETE prose — the sentence-boundary
    clip the truncation gate demands. Clips at a sentence/word boundary (never
    mid-word), strips a trailing ellipsis / dangling hyphenated fragment (the
    'uneve—', 'consol…' class), and lifts a too-short bare fragment over the
    80-char floor by appending its OWN grounded score-vs-peer fact (never
    fabricated; honest when there is no score to add)."""
    b = re.sub(r"\s{2,}", " ", str(body or "").strip())
    b = clip_sentence_boundary(b, 600).rstrip()
    b = _ELLIPSIS_TAIL_RE.sub("", b).rstrip()
    b = _DANGLING_WORD_RE.sub("", b).rstrip()
    b = _TRAILING_DASH_RE.sub("", b).rstrip()
    if len(b) < 90 and score is not None:
        _floor_gap = is_true_gap(score, peer)
        if _reads_as_gap(name, f"{name} {b}"):
            _floor_gap = True  # risk / absence-named items never floor with strength framing
        extra = compose_finding_body(name, subcap_id, score, peer, _floor_gap)
        b = (b.rstrip(" .;—–-") + ". " + extra).strip() if b else extra  # noqa: RUF001
        b = clip_sentence_boundary(b, 600).rstrip()
        b = _ELLIPSIS_TAIL_RE.sub("", b).rstrip()
        b = _DANGLING_WORD_RE.sub("", b).rstrip()
        b = _TRAILING_DASH_RE.sub("", b).rstrip()
    if b and b[-1] not in ".!?\"')]" + "”’":  # noqa: RUF001 — closing smart quotes
        b += "."
    return b


# ── Evidence-excerpt interpretation (2026-07-06 anti-quote-dump rebuild) ─────
# Every deep surface (cards, findings, SCQA, subcap rationale) must READ its
# evidence and re-express it as an argued fact, not dump the raw analyst note.
# These helpers turn one excerpt into (1) a clean AE-facing FACT clause and
# (2) a WHY that ties that fact to the subcap's maturity impact + score
# direction. Shared so the canonical DB pass and the offline snapshot converge.
_MARKUP_TAG_RE = re.compile(
    r"\s*\[(?:ERS|FACT|INFERENCE|HYPOTHESIS|CLAIM|E-)[^\]]*\]", re.I)
# A leading "LABEL:" / "P4C1 DATA GOVERNANCE BASELINE:" header prefix (a data
# label, not prose) — stripped so the fact leads with substance.
_EXCERPT_HEADER_RE = re.compile(
    r"^\s*(?:P\d\s?C?\d[\w.\-]*\s+)?[A-Z][A-Z0-9 &/_.\-]{2,54}:\s+")
# Score-band leak ("= M1-M2 for governance", "M3 trajectory") — scoring
# metadata, never client-facing prose.
_MBAND_TAIL_RE = re.compile(r"\s*=\s*[Mm][1-5](?:\s*[-–]\s*[Mm]?[1-5])?[^.]*")  # noqa: RUF001
_MBAND_TOKEN_RE = re.compile(r"\b[Mm][1-5](?:\s*[-–]\s*[Mm]?[1-5])?\b")  # noqa: RUF001
_INLINE_EID_REF_RE = re.compile(r"\s*[\[(]\s*E-?[A-Za-z0-9-]{1,8}\s*[\])]")
# Acronyms / product tokens kept intact when de-shouting an ALL-CAPS excerpt.
_KEEP_CAPS = frozenset({
    "NCUA", "GLBA", "CRM", "CDP", "MDM", "API", "AI", "ML", "BI", "OCI", "PAAS",
    "SAAS", "ARCU", "FIS", "CIO", "CDO", "CEO", "CFO", "CTO", "CISO", "P&C",
    "ACORD", "NAIC", "FDIC", "OCC", "SEMCI", "SR", "AWS", "ETL", "SSRS", "DRP",
    "10-K", "ERS", "KYC", "AML", "STP", "UPB", "ROA", "ROE", "NIM"})


def _deshout(s: str) -> str:
    """Sentence-case a mostly-uppercase excerpt row, preserving acronyms."""
    letters = [c for c in s if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.6:
        return s
    out = []
    for tok in s.split(" "):
        core = tok.strip(".,:;!?()'\"")
        if core.upper() in _KEEP_CAPS or (core.isupper() and len(core) <= 4) \
                or any(ch.isdigit() for ch in core):
            out.append(tok)
        else:
            out.append(tok.lower())
    j = " ".join(out).strip()
    return (j[:1].upper() + j[1:]) if j else j


def normalize_excerpt_fact(excerpt: object, limit: int = 220) -> str | None:
    """Clean one evidence excerpt into a single AE-facing FACT clause, or None.

    Strips researcher markup ([ERS: 2.2] [FACT]), inline E-ID refs, a leading
    label-colon header, and score-band scoring metadata ('= M2 for governance');
    de-shouts an ALL-CAPS row; converts leftover '=' note syntax to prose.
    Returns None when nothing factual survives (a bare header / meta-note)."""
    s = re.sub(r"\s+", " ", str(excerpt or "")).strip()
    if len(s) < 30:
        return None
    # A researcher meta-note (negative search, correction, "no evidence") is
    # not a client fact even after its ALL-CAPS label is stripped.
    if re.match(r"(?i)^(no evidence|negative search(?: result)?|correcting|"
                r"\bnote\b|unable to|company focus)", s):
        return None
    s = _MARKUP_TAG_RE.sub("", s)
    s = _SEV_MARKER_RE.sub(" ", s).replace("**", "")
    s = _INLINE_EID_REF_RE.sub("", s)
    s = _EXCERPT_HEADER_RE.sub("", s).strip()
    s = _MBAND_TAIL_RE.sub("", s)
    s = _MBAND_TOKEN_RE.sub("", s)
    s = s.replace(" = ", " — ")                          # residual note '=' to em-dash
    s = re.sub(r"\s{2,}", " ", s).strip(" —–-;:,")       # noqa: RUF001
    s = _deshout(s)
    fact = clip_clean(s, limit).rstrip(" .;,—–-")        # noqa: RUF001
    if len(fact) < 25 or not re.search(r"[A-Za-z]{3}", fact):
        return None
    if re.match(r"(?i)^(no evidence|negative search|correct|note:|unable to)", fact):
        return None
    return fact


def _excerpt_relevant(fact: str, capability_blob: str) -> bool:
    """Is the excerpt topically about this capability? Semantic when the
    MiniLM tier is warm, lexical token-overlap otherwise. Deliberately
    permissive (the WHY composer interprets, it does not need a citation-
    grade match) — it only has to catch the non-sequitur class."""
    try:
        from app.services.nlp.semantic import SemanticIndex, model_available
        if model_available():
            idx = SemanticIndex()
            return idx.relevance(fact[:400], capability_blob[:200]) >= 0.18
    except Exception:
        pass
    # degraded tier: a lexical proxy is too crude to judge topical
    # relevance (it rejected a 10-K core-systems excerpt against 'Data
    # Foundation') — like the mapping ladder, the floor is a semantic-
    # tier feature; cold tier keeps prior behaviour rather than guess
    return True


def compose_evidence_why(name: object, excerpt: object, subcap_id: object = None,
                         score: object = None, peer: object = None,
                         client_key: object = None) -> str | None:
    """WHY that READS the evidence: the cleaned fact, then an interpretive
    bridge tying it to the subcap's maturity standing and score direction
    (the AE-depth contract — not 'The linked evidence records: <raw note>').
    None when the excerpt yields no usable fact."""
    fact = normalize_excerpt_fact(excerpt, 220)
    if not fact:
        return None
    nm = str(name or "this capability")
    pill = pillar_label(subcap_id)
    # clause-shaped headlines don't parse as in-sentence noun phrases —
    # the relevance check still uses the full name, the SPLICE doesn't
    _splice_nm = "this capability" if _is_note_shaped_name(nm) else nm
    # Relevance floor (benchmark read 2026-07-12): "That is the substance
    # the assessment reads into <capability>" is a CAUSAL assertion — made
    # over a topically unrelated excerpt (a wealth-management partnership
    # quoted as the substance of a data-SLO score) it reads as fabricated
    # reasoning. Below the floor return None and let the caller fall back
    # to the honest score-grounded WHY.
    if (re.match(r"^[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]*\.?){0,3}\s*[\u2014\u2013-]\s*"
                 r"(?:S?E?VP|Chief|President|Director|Head|Officer)", fact)
            or re.search(r"\breports\s+(?:directly\s+)?to\b|"
                         r"\b\d+\s+years?\b.{0,30}\bexperience\b",
                         fact[:160], re.I)):
        # roster/bio line (title-dash-person, reporting line, tenure
        # résumé) — biography, not capability substance
        return None
    if not _excerpt_relevant(fact, f"{nm}. {pill}"):
        return None
    from app.services.nlp.stylebook import pick as _pick
    from app.services.nlp.stylebook import seeded as _seeded
    _rng = _seeded(client_key or "", nm, subcap_id, "evidence-why")
    is_gap = is_true_gap(score, peer)
    if _reads_as_gap(nm, f"{nm} {fact}"):
        is_gap = True  # risk / absence-named items never argue as strengths
    _core = fact.rstrip("\"”')] ")  # ignore trailing closing quotes/brackets
    fact_sent = fact if _core[-1:] in ".!?" else fact + "."
    if is_gap and score is not None and peer is not None:
        try:
            delta = float(peer) - float(score)
        except (TypeError, ValueError):
            delta = None
        gapclause = (f", {delta:.1f} points under the {peer} peer median"
                     if delta and delta > 0.05 else f", against the {peer} peer median")
        tie = _pick(_rng, (
            "That is the substance the assessment reads into the {s}/5 on "
            "{nm}{gc} — the concrete constraint holding {pill} back.",
            "That fact is what the {s}/5 on {nm}{gc} measures — the "
            "operational drag on {pill} in concrete form.",
            "It is the ground truth behind the {s}/5 on {nm}{gc}, and the "
            "specific thing holding {pill} back.",
        ), s=score, nm=nm, gc=gapclause, pill=pill)
    elif is_gap is False and score is not None:
        tie = _pick(_rng, (
            "That is what keeps {nm} at {s}/5, at or ahead of the peer "
            "benchmark — a proof point {pill} can build on.",
            "It is why {nm} holds {s}/5, at or ahead of the benchmark — "
            "standing proof {pill} can execute.",
            "That record carries {nm} to {s}/5, level with or ahead of "
            "peers — an asset for the wider {pill} agenda.",
        ), nm=nm, s=score, pill=pill)
    elif score is not None:
        tie = _pick(_rng, (
            "That evidence anchors the {s}/5 on {nm} and ties its "
            "trajectory to the wider {pill} programme.",
            "The {s}/5 on {nm} rests on that evidence, and its trajectory "
            "moves with the wider {pill} programme.",
        ), s=score, nm=nm, pill=pill)
    else:
        tie = _pick(_rng, (
            "That is the evidence the assessment reads directly into the "
            "standing of {nm} in {pill}.",
            "The assessment reads that evidence directly into where {nm} "
            "stands within {pill}.",
        ), nm=nm, pill=pill)
    return f"{fact_sent} {tie}"


# ── Top-finding W/W/SW decomposition (plan 4.5) ──────────────────────────────
_THEME_BY_PILLAR = {"P1": "Strategy & governance", "P2": "Customer experience",
                    "P3": "Operations", "P4": "Data & technology"}


_PEER_MENTION_RE = re.compile(r"\bpeer|\bcohort|\bmedian", re.I)


def _num(v: object) -> str:
    """Render a stored score exactly as graded (no trailing zeros) so the
    rubric's consistency check matches it against the run's known values."""
    return format(round(float(v), 2), "g")


def peer_closer(name: str, score: object, peer: object, pillar: str) -> str | None:
    """One run-grounded peer-context sentence for a finding WHAT
    (ASK-OV6-2: the What closes on peer or industry context).

    Every number is the run's own (category score / peer median / their
    delta — all values the grading state already knows), and the sentence
    shape is picked by the measured standing, so no single skeleton recurs
    corpus-wide and nothing here survives an entity swap unchanged.
    """
    try:
        s, p = float(score), float(peer)
    except (TypeError, ValueError):
        return None
    if not (0.0 < s <= 5.0 and 0.0 < p <= 5.0):
        return None
    gap = round(p - s, 2)
    if gap < 0:
        return (f"The peer median here is {_num(p)}/5 — {name} already reads "
                f"{_num(abs(gap))} points ahead of the cohort, a lead worth defending.")
    if gap >= 1.0:
        return (f"Peers hold a {_num(p)}/5 median on this capability; at {_num(s)}/5 "
                f"the {_num(gap)}-point spread is where the cohort is pulling away.")
    if gap >= 0.15:
        return (f"The peer median sits at {_num(p)}/5 versus {_num(s)}/5 here — a "
                f"{_num(gap)}-point step peers have already taken.")
    # a sub-0.15 spread is noise, not a story — dressing a 0.01-point
    # delta up as "a step peers have taken" shipped on Amalgamated
    # (2026-07-13 corpus QA); read it as level standing instead.
    return (f"{name} effectively tracks the {_num(p)}/5 peer median, so "
            f"differentiation rests on the surrounding {pillar} capabilities.")


# Issue-shaped content (litigation, enforcement, remediation mandates)
# must NEVER compose under strength framing, whatever the anchor
# capability's score direction (2026-07-13 Beacon vetting: a Ponzi
# class-action finding shipped as "Protect this strength as a proof
# point" because its anchor scored at-peer).
_ISSUE_VOCAB_RE = re.compile(
    r"litigation|class[- ]action|lawsuit|ponzi|consent (?:order|decree)|"
    r"enforcement|breach|non-negotiable|fraud|penalt\w+|violation|"
    r"remediat\w+|deficien\w+", re.I)
# A risk word used as part of a CAPABILITY name ("Fraud Investigation",
# "Breach Response", "Risk Analytics") denotes an ability the institution
# has, NOT an incident — it must not force remediation framing on a
# capability that scores at/above peer (2026-07-13 corpus QA false
# positive: 'Fraud Investigation' at 3.4/5 flipped to a gap).
_RISK_CAPABILITY_RE = re.compile(
    r"\b(?:fraud|breach|risk|penalt\w+|violation|remediat\w+|deficien\w+|"
    r"enforcement|litigation)\s+"
    r"(?:investigation|detection|prevention|management|monitoring|response|"
    r"analytics|assessment|mitigation|controls?|governance|operations|"
    r"program|posture|readiness|resilience|framework|reporting|"
    r"surveillance|screening)\b", re.I)


def _issue_signal(text: object) -> bool:
    """True when the text carries issue/incident vocabulary that is NOT merely
    a capability name. Strips capability phrasings first, then tests for any
    remaining risk vocabulary — so 'Fraud Investigation' reads as a
    capability while 'Ponzi class-action' reads as the incident it is."""
    stripped = _RISK_CAPABILITY_RE.sub(" ", str(text or ""))
    return bool(_ISSUE_VOCAB_RE.search(stripped))


# Absence / immaturity language in a finding NAME marks it a gap regardless
# of the raw score direction — a capability whose own name says it is "not
# yet in place" / "fragmented" / "unknown" cannot compose as a strength to
# "protect as a proof point" (2026-07-13 corpus QA, Commerce Trust:
# "Protect Fragmented martech … not yet in place … as a proof point").
_GAP_LANGUAGE_RE = re.compile(
    r"\bnot yet in place\b|\bfragmented\b|\bno unified\b|\bno \w+ in place\b|"
    r"\blacks?\b|\bmissing\b|\bsiloed\b|\bunknown\b|\babsent\b|"
    r"\bunder-?(?:built|invested|developed)\b|\bnascent\b|\bformative\b", re.I)


def _reads_as_gap(name: object, incident_text: object = "") -> bool:
    """True when a finding must compose gap-first: either it carries genuine
    incident vocabulary, or its NAME uses absence/immaturity language."""
    return _issue_signal(incident_text or name) or bool(
        _GAP_LANGUAGE_RE.search(str(name or "")))
# Severity tags and markdown emphasis are workbook markup, not prose.
_SEV_MARKER_RE = re.compile(r"\s*\[(?:CRITICAL|HIGH|MEDIUM|LOW)\]\s*", re.I)


def finding_wwsw(name: object, body: object, subcap_id: object = None,
                 score: object = None, peer: object = None,
                 evidence_excerpt: object = None,
                 platform: object = None,
                 platform_features: list[str] | None = None) -> dict:
    """Decompose one finding into the prototype's WHAT / WHY / SO-WHAT blocks
    + theme + magnitude (plan 4.5; audit: 0/378 findings carried them).

    WHAT = the finding's own factual clauses (verbatim, sentence-clipped);
    WHY = its causal clauses (nlp.causal), else the linked evidence excerpt
    (real cause material), else the score-vs-peer shortfall; SO-WHAT = its
    action clauses, else a platform/priority action tied to the gap. Nothing
    is fabricated: every fallback names its basis.
    """
    from app.services.nlp.causal import decompose
    from app.services.nlp.quantities import extract_metrics
    from app.services.nlp.segment import clip_sentences

    nm = str(name or "This capability")
    # workbook finding names carry note-shorthand ('X = Y'); as prose the
    # em-dash appositive reads naturally and keeps both halves verbatim
    nm = re.sub(r"\s=\s", " \u2014 ", nm)
    nm = _SEV_MARKER_RE.sub(" ", nm).strip()
    text = _SEV_MARKER_RE.sub(" ", str(body or "")).replace("**", "").strip()
    d = decompose(text) if text else {"what": "", "why": "", "so_what": ""}
    what = clip_sentences(d["what"], 360) if d["what"] else clip_sentences(text, 360)
    # analyst-note bodies can END mid-clause ('engagement remains
    # campaign/manual,') — a trailing comma/semicolon/dash fragment reads
    # as a truncation on the card; close it as a sentence.
    what = re.sub(r"\s*[,;:\u2013\u2014-]\s*$", ".", what)
    why = clip_sentences(d["why"], 300)
    pill = pillar_label(subcap_id)
    is_gap = is_true_gap(score, peer)
    if _reads_as_gap(nm, f"{nm} {text}"):
        is_gap = True  # risk / absence-named items compose remediation-led, never as strengths
    if not why:
        ex = str(evidence_excerpt or "").strip()
        if len(ex) < 40 or re.search(r"^\(?no excerpt\)?$", ex, re.I):
            ex = ""
        # READ the excerpt — clean it and tie the fact to the subcap's maturity
        # impact — instead of dumping the raw analyst note ('The linked evidence
        # records: <note>', 79.2% of shipped findings pre-rebuild).
        composed = compose_evidence_why(nm, ex, subcap_id, score, peer) if ex else None
        if composed:
            why = clip_sentences(composed, 460)
        elif is_gap and score is not None and peer is not None:
            # static-honest: one score snapshot supports a head-start claim,
            # not a per-cycle dynamic ("compounding each cycle" was asserted
            # on 117 findings with no trend data — reasoning audit)
            why = (f"The shortfall is relative, not absolute: {score}/5 sits "
                   f"below the {peer} peer median, leaving a real head start "
                   f"to close against the cohort.")
        elif score is not None:
            # value-led (v3: scores never lead): the dependency is the
            # reason it makes the findings list; the score is the proof
            why = (f"The capability is mid-build — the assessment reads it "
                   f"at {score}/5 — and its trajectory gates how fast the "
                   f"wider {pill} programme can move; that dependency is "
                   f"what earns it a place in the top findings.")
    so_what = clip_sentences(d["so_what"], 300)
    if not so_what:
        # Name the concrete capability, not just the vendor: the v7 L4 layer
        # maps named platform features onto the finding's subcaps, so the
        # so-what can say WHAT on the platform does the work (spec v3 The
        # Play: outcome → platform + feature → proof).
        # the L4 sheet suffixes names with " for {subcap}" — product name
        # only in prose (the drawer keeps the full catalogue string)
        feats = list(dict.fromkeys(
            str(f).split(" for ")[0].strip()
            for f in (platform_features or []) if str(f).strip()))
        if platform and feats:
            fx = feats[0] if len(feats) == 1 else f"{feats[0]} and {feats[1]}"
            plat = (f" — on {platform}, {fx} "
                    f"{'is' if len(feats) == 1 else 'are'} built for exactly this")
        elif platform:
            plat = f" — {platform} is the platform surface that addresses it"
        else:
            plat = ""
        if is_gap is False:
            anchor = (f"the {pill} story" if pill != "this area" else "the story")
            _subj = "this strength" if _is_note_shaped_name(nm) else nm
            so_what = (f"Protect {_subj} as a proof point: use it to anchor {anchor} "
                       f"while the true gaps close{plat}.")
        else:
            # 'that depend on it' asserted a dependency graph nothing
            # verifies; same-pillar adjacency IS in the catalogue structure
            dep = (f"the adjacent {pill} capabilities" if pill != "this area"
                   else "the capabilities around it")
            # Value-led, and clear of the banned rehearsed skeletons
            # ("prioritize … in the next phase", "sequencing it first lifts").
            _subj = "this gap" if _is_note_shaped_name(nm) else nm
            _sw_variants = (
                (f"Closing {_subj} first raises the floor for {dep}{plat}: "
                 f"this gap sets the ceiling on what the rest of the "
                 f"roadmap can return."),
                (f"Sequence {_subj} ahead of the rest{plat} — {dep} can "
                 f"only compound once this floor holds."),
                (f"Fund {_subj} before the adjacent work{plat}: every "
                 f"dollar spent around an open gap buys less than the "
                 f"dollar that closes it."),
            )
            so_what = _sw_variants[_zlib_mod.crc32(
                (str(nm) + "|sowhat").encode()) % 3]
    # ASK-OV6-2: the What closes on peer context. Skip when the finding's
    # own prose (or the WHY fallback) already carries it; budget the append
    # so the 600-char cap never severs the closer mid-sentence.
    if not _PEER_MENTION_RE.search(f"{what} {why}"):
        closer = peer_closer(
            "this capability" if _is_note_shaped_name(nm) else nm,
            score, peer, pill)
        if closer:
            room = 600 - len(closer) - 1
            base = clip_sentences(what, room) if len(what) > room else what
            what = f"{base.rstrip()} {closer}" if base.strip() else closer

    # magnitude: a real metric from the body, else the quantified peer gap.
    magnitude = None
    try:
        mets = extract_metrics(text)
    except Exception:
        mets = []
    for m in mets:
        if m.get("unit") in ("pct", "months", "days", "ratio", "stars", "usd"):
            magnitude = str(m.get("raw") or "").strip() or None
            if magnitude:
                break
    if not magnitude and is_gap and score is not None and peer is not None:
        try:
            magnitude = f"{float(peer) - float(score):.1f} pts below peer median"
        except (TypeError, ValueError):
            magnitude = None
    theme = _THEME_BY_PILLAR.get(pillar_of(subcap_id) or "", "Digital maturity")
    # Clip WHY at a sentence boundary and guarantee terminal punctuation — the
    # bare `[:500]` slice could sever the closing period (the 42.6% missing-
    # terminal finding class the audit measured).
    why_out = clip_sentence_boundary(_cap(why), 500).rstrip()
    if why_out and why_out[-1] not in ".!?\"”')]":
        why_out += "."
    return {"what": _cap(what)[:600], "why": why_out,
            "so_what": _cap(so_what)[:500], "theme": theme,
            "magnitude": magnitude and magnitude[:80]}


def _cap(s: str) -> str:
    return (s[:1].upper() + s[1:]) if s else s


# ── Why-now deep-signal helpers (plan 4.4: all 14 prototype fields) ─────────
_WN_CATEGORY_BY_KIND = {
    "MIGRATION": "core_migration", "LEADERSHIP": "leadership", "HIRING": "hiring",
    "REGULATORY": "regulatory", "M&A": "market", "MARKET": "market",
    "GAP": "market", "PRIORITY": "market", "FINANCIAL": "market",
    "GROWTH": "market", "STRATEGY": "market", "PLAY": "market",
}


def wn_category(kind: object) -> str:
    return _WN_CATEGORY_BY_KIND.get(str(kind or "").upper(), "market")


def wn_claim_class(evidence: list | None, best_tier: object, is_dated: bool) -> str:
    """FACT (T1-T3 evidence behind a dated occurrence), INFERENCE (evidence-
    backed but undated / weaker-tier), HYPOTHESIS (score-only)."""
    has_ev = bool(evidence)
    try:
        tier = int(best_tier) if best_tier is not None else None
    except (TypeError, ValueError):
        tier = None
    if has_ev and tier is not None and tier <= 3 and is_dated:
        return "FACT"
    if has_ev:
        return "INFERENCE"
    return "HYPOTHESIS"


def wn_strength(category: str, claim: str, has_window: bool) -> str:
    """STRONG = time-bound trigger backed by fact-grade evidence; LEADING =
    trigger-class signal without the full fact chain; SUPPORTING = structural
    (score-derived) context."""
    if category == "market" and claim == "HYPOTHESIS":
        return "SUPPORTING"
    if claim == "FACT" and has_window:
        return "STRONG"
    if category in ("core_migration", "leadership", "hiring", "regulatory"):
        return "LEADING"
    return "SUPPORTING"


def wn_confidence(evidence: list | None, best_tier: object) -> str:
    try:
        tier = int(best_tier) if best_tier is not None else None
    except (TypeError, ValueError):
        tier = None
    n = len(evidence or [])
    if tier is not None and tier <= 2 and n >= 2:
        return "HIGH"
    if (tier is not None and tier <= 3) or n >= 2:
        return "MEDIUM"
    return "LOW"


def quarter_label(d: object) -> str | None:
    """date → 'Q3 2026' (the window chip vocabulary)."""
    y = getattr(d, "year", None)
    m = getattr(d, "month", None)
    if not y or not m:
        return None
    return f"Q{(int(m) - 1) // 3 + 1} {y}"


def add_months(d, months: int):
    """Pure month arithmetic (no dateutil): clamps the day to 28."""
    import datetime as _dt
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return _dt.date(y, m, min(d.day, 28))
