# ruff: noqa: RUF001, RUF003
# This module matches against, and documents, the literal Unicode em-dash
# (U+2014) and en-dash (U+2013) characters that appear in analyst-authored
# Assessment Report prose. Replacing them with ASCII hyphen-minus would
# break the regex match against real fixture content.
"""Extract structured recommendations from the Assessment Report DOCX
when no canonical JSON rec source ships with the package.

Per the 2026-06-07 user correction, every package's
`04_reports/*_Assessment_Report*.docx` carries the recommendations under
the section-9 "Recommendations" heading (with section-10 "Transformation
Roadmap" as a sibling). The shapes vary across folders:

  Alma_Bank    - 7 distinct `REC-NN: <title>` heading-2 subsections,
                 each with body 1960-2494 chars (canonical analyst shape).
  Nicola       - `REC-NNN: <title> [ZENNIFY]` heading-2 + per-rec
                 sub-blocks `[ROOT CAUSE]` / `[SOLUTION]` /
                 `[EXPECTED OUTCOMES]` / `[RISK OF INACTION]` / `[BUYER MAP]`.
  WSFS         - rec IDs inline in the parent body text
                 (`REC-001 — ...`, `REC-002 — ...`); sub-blocks
                 split out as `[ROOT CAUSE]`, `[SOLUTION]`,
                 `[EXPECTED OUTCOMES]` headings.
  Odlum_Brown  - `R-NN` references in body text (6 recs); the full
                 detail lives in the `recommendations_register.json`
                 sibling which the JSON path already handles.
  Calprivate   - single 23 KB body under section-9 with `R-NNN` IDs
                 inline across the prose (8 distinct IDs).
  IBKR         - severity-banner shape: each rec's title lives in a 1x1
                 DOCX table cell (`R1 [CRITICAL]  Financial Services
                 Cloud — …` + a `Capabilities: … | Timeline: …` meta
                 line), followed by per-rec `9.N.x` sub-headings
                 (Capability Score Impact / Why This Solution /
                 Expected Outcomes / Risk of Inaction). Requires the
                 document-order table fix in assessment_report.py so
                 the banners land inside the §9 region.

The extractor is a strict fallback - it runs ONLY when no JSON rec
source was found. End-user impact: AE-facing recs strip and
RecommendationsPage render real content for WSFS / Nicola / Calprivate
instead of empty state.

State branches:
  - no `recommendations` section_kind in report_sections -> return []
  - heading-based match (Alma / Nicola shape) -> preferred path
  - severity-banner match (IBKR shape) -> second path
  - tab-row match (Guaranteed Rate / Cornerstone shape: §9 rec-table
    rows flattened to tab-joined lines — id/severity/title cells in
    either column order) -> third path
  - body-text match (WSFS / Calprivate / Odlum shape) -> fallback path
  - duplicate IDs -> first occurrence wins (body references like
    `R-01 establishes...` don't create duplicate recs)
  - no separator-anchored IDs in the body-text path -> return []
    (NEVER split on bare mid-sentence cross-references — the 2026-07-06
    defect family shipped fragment titles like ') and personalized MCAE
    journeys (' exactly that way)
  - fragment-shaped titles -> candidate DROPPED + counted in the
    warnings out-param (never '(untitled)' or a placeholder)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.schemas.package import RecommendationRow, ReportSectionRow

log = logging.getLogger(__name__)

# Match `REC-NN`, `REC-NNN`, `R-NN`, `R-NNN` (case-insensitive). The
# 1-3 digit range catches every observed shape across the 5 fixtures
# without false-positives on standalone "R" or "REC" words.
# `RECOMMENDATION N` (Valley-style prose §9) is matched FIRST so the
# narrower `REC`/`R` alternations don't shadow it.
_REC_ID_RE = re.compile(
    r"\b(RECOMMENDATION[-\s]?\d{1,3}|REC[-\s]?\d{1,3}|R[-\s]?\d{1,3})\b",
    re.IGNORECASE,
)

# Match the SUB-BLOCK markers inside a rec body. Two shapes observed
# across the 5 real fixtures:
#   1. Bracketed (WSFS / Nicola / Alma):  `[ROOT CAUSE]`, `[SOLUTION]`, …
#      — tolerant of a dash-joined SCQA qualifier inside the bracket
#      (Cornerstone: `[ROOT CAUSE — SITUATION]`, `[SOLUTION — ANSWER]`).
#   2. Bare-colon (Calprivate):           `Root Cause: …`, `Solution: …`
# Both anchored to a line/paragraph start so E-ID citations like `[E-0121]`
# embedded in body prose don't false-positive on the bracket-shape.
# `^` is used in multiline mode at the call site (re.MULTILINE).
_SUB_BLOCK_HEADINGS = {
    "root_cause": re.compile(
        r"(?:^|\n)\s*(?:\[\s*ROOT\s+CAUSE(?:\s*[—–:-][^\]]{0,60})?\s*\]"
        r"|ROOT\s+CAUSE\s*[:\-])\s*",
        re.IGNORECASE,
    ),
    "solution": re.compile(
        r"(?:^|\n)\s*(?:\[\s*SOLUTION(?:\s*[—–:-][^\]]{0,60})?\s*\]"
        r"|SOLUTION\s*[:\-])\s*",
        re.IGNORECASE,
    ),
    "expected_outcomes": re.compile(
        r"(?:^|\n)\s*(?:\[\s*EXPECTED\s+OUTCOMES?(?:\s*[—–:-][^\]]{0,60})?\s*\]"
        r"|EXPECTED\s+OUTCOMES?\s*[:\-])\s*",
        re.IGNORECASE,
    ),
    "risk_of_inaction": re.compile(
        r"(?:^|\n)\s*(?:\[\s*RISK\s+OF\s+INACTION(?:\s*[—–:-][^\]]{0,60})?\s*\]"
        r"|RISK\s+OF\s+INACTION\s*[:\-])\s*",
        re.IGNORECASE,
    ),
    "buyer_map": re.compile(
        r"(?:^|\n)\s*(?:\[\s*BUYER\s+MAP\s*\]|BUYER\s+MAP\s*[:\-])\s*",
        re.IGNORECASE,
    ),
    "strategic_objectives": re.compile(
        r"(?:^|\n)\s*(?:\[\s*STRATEGIC\s+OBJECTIVES?\s*\]"
        r"|STRATEGIC\s+OBJECTIVES?\s*[:\-]"
        r"|STRATEGIC\s+OBJECTIVE\s+ALIGNMENT\s*[:\-])\s*",
        re.IGNORECASE,
    ),
}


@dataclass
class _RecCandidate:
    """Working accumulator while walking the section list."""
    rec_id: str
    title: str
    body_parts: list[str]


# Bracketed severity tag between the rec ID and its title — the IBKR
# roadmap-definition shape: `R1 [CRITICAL]  Financial Services Cloud — …`.
_SEVERITY_TAG_RE = re.compile(
    r"^\s*\[\s*(CRITICAL|HIGH|MEDIUM|LOW)\s*\]\s*", re.IGNORECASE,
)


def _normalize_rec_id(raw: str) -> str:
    """Standardize REC IDs to upper-case dash form: `REC-01`, `R-01`.
    `RECOMMENDATION 1` → `REC-01`; `REC-1` → `REC-01` (zero-padded so a
    body cross-reference `REC-1` dedups against the real `REC-01` rec —
    the ANB fixture shipped both as SEPARATE recs before 2026-07-06).
    Digit strings that already carry 2+ digits keep their width
    (`REC-001` stays `REC-001` — the WSFS canonical form)."""
    s = raw.upper().strip()
    m = re.search(r"(\d{1,3})", s)
    if not m:
        s = s.replace(" ", "-")
        # Collapse double-dashes from `REC--01` if any
        while "--" in s:
            s = s.replace("--", "-")
        return s
    digits = m.group(1)
    num = f"{int(digits):02d}" if len(digits) < 2 else digits
    prefix = "REC" if s.startswith("REC") else "R"
    return f"{prefix}-{num}"


# `[:–—\-]` matches colon, en-dash, em-dash, ASCII hyphen —
# every separator we've seen between a rec ID and its title across the
# 5 real fixtures.
_TITLE_SEP_RE = re.compile("^\\s*[:–—\\-]+\\s*")
# A rec sliced at a MID-SENTENCE "(Rn)" anchor (e.g. "…MCAE journeys (R2) from
# real-time signals…") leaves the title starting with an orphaned close-bracket
# once the "R2" token is stripped — ") from real-time signals…". Drop a leading
# orphaned close-bracket / stray punctuation the id+separator strip leaves behind
# (2026-07-09 QA: Interactive Brokers R2 shipped ") from real-time account…").
_ORPHAN_LEAD_RE = re.compile(r"^[)\]\}\s,;:–—-]+")


def _split_title_from_heading(heading: str, rec_id: str) -> str:
    """Strip the rec_id prefix AND any leading title-separator from a
    heading like `REC-01: Title` or `REC-001 <em-dash> Title` -> `Title`.

    Strips on any of: colon, em-dash (U+2014), en-dash (U+2013), hyphen,
    surrounding spaces. Falls back to the heading verbatim when no
    separator is found.
    """
    if not heading:
        return ""
    # First strip a leading rec-id token in ANY observed form (REC-01 /
    # R-1 / Recommendation 1) — the rec_id-derived pattern below can't match
    # the spelled-out "Recommendation N" heading form.
    h = heading.strip()
    lead = _REC_ID_RE.match(h)
    if lead:
        rest = _ORPHAN_LEAD_RE.sub("", _TITLE_SEP_RE.sub("", h[lead.end():])).strip()
        if rest:
            return rest
    pat = re.compile(re.escape(rec_id).replace(r"\-", r"[-\s]?"), re.IGNORECASE)
    m = pat.search(heading)
    if not m:
        return heading.strip()
    rest = heading[m.end():]
    rest = _ORPHAN_LEAD_RE.sub("", _TITLE_SEP_RE.sub("", rest)).strip()
    return rest or heading.strip()


# ── Title sanity gate (2026-07-06) ─────────────────────────────────────
# The deployed pack shipped 9 punctuation-start titles, 6 unbalanced-paren
# titles, 2 bare '.' titles and lowercase connector fragments ('through')
# — all fabricated from mid-sentence prose. A rec title must never ship
# in any of those shapes; rejected candidates are DROPPED (never
# '(untitled)') and counted in the extractor warnings.

_MIN_TITLE_CHARS = 12

# Connector / function words that can never stand alone as a rec title
# (the regex tier of the noun-phrase check when spaCy is unavailable).
_CONNECTOR_WORDS = frozenset({
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
    "into", "it", "of", "on", "or", "the", "then", "this", "through",
    "to", "via", "with",
})

_FIRST_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'&./-]*")


def _has_noun_phrase(title: str) -> bool:
    """True when the title carries a noun phrase — spaCy POS tier when the
    model is loaded, connector-word blacklist tier otherwise (the nlp
    package's degradation contract)."""
    try:
        from app.services.nlp import get_nlp
        nlp = get_nlp()
    except Exception:
        nlp = None
    if nlp is not None:
        doc = nlp(title)
        return any(tok.pos_ in ("NOUN", "PROPN") for tok in doc)
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", title)
    content = [w for w in words if w.lower() not in _CONNECTOR_WORDS]
    return bool(content)


def title_reject_reason(title: str | None) -> str | None:
    """The fragment-rejection gate. Returns a stable reason code when the
    title must NOT ship, or None when it passes. Applied on EVERY extraction
    path so a mid-sentence fragment ('through the platform', 'Deploy FSC
    (Financial Services') can never become a rec title (2026-07-06).

    Reason codes: ``empty`` / ``too_short`` / ``punctuation_start`` /
    ``lowercase_start`` / ``unbalanced_parens`` / ``unbalanced_quotes`` /
    ``no_noun_phrase``. Brand-cased leading words (nCino, iPipeline) are
    exempt from the lowercase-start rule.
    """
    t = (title or "").strip()
    if not t:
        return "empty"
    if len(t) < _MIN_TITLE_CHARS:
        return "too_short"
    first_char = t[0]
    if not (first_char.isalnum() or first_char in "$€£"):
        return "punctuation_start"
    if first_char.islower():
        fw = _FIRST_WORD_RE.match(t)
        # `nCino`-style brand casing (an uppercase letter later in the
        # first word) is legitimate; anything else is a mid-sentence
        # fragment ('launching without Data Cloud foundation…').
        if not (fw and any(c.isupper() for c in fw.group(0)[1:])):
            return "lowercase_start"
    if t.count("(") != t.count(")") or t.count("[") != t.count("]"):
        return "unbalanced_parens"
    if t.count('"') % 2 == 1 or t.count("“") != t.count("”"):
        return "unbalanced_quotes"
    if not _has_noun_phrase(t):
        return "no_noun_phrase"
    return None


# Banner title clean-up: collapse whitespace, then when the full clause
# exceeds the display budget cut at the primary dash separator (that
# yields the platform clause: 'Financial Services Cloud — Enterprise
# Relationship Intelligence for 4.4M Accounts…' → 'Financial Services
# Cloud'); word-boundary clip as the last resort.
_MAX_TITLE_CHARS = 90
_TITLE_DASH_SPLIT_RE = re.compile(r"\s+[—–]\s+|\s+-\s+")


def _clean_rec_title(raw: str, max_chars: int = _MAX_TITLE_CHARS) -> str:
    t = re.sub(r"\s+", " ", raw or "").strip().strip("—–-: ")
    if len(t) > max_chars:
        head = _TITLE_DASH_SPLIT_RE.split(t)[0].strip()
        if len(head) >= _MIN_TITLE_CHARS:
            t = head
    if len(t) > max_chars:
        cut = t.rfind(" ", 0, max_chars)
        t = t[:cut] if cut > 0 else t[:max_chars]
        t = t.rstrip(" ,;:—–-.")
    # Sentence-case the lead character — but leave brand-cased words
    # (nCino) alone.
    if t and t[0].islower():
        fw = _FIRST_WORD_RE.match(t)
        if not (fw and any(c.isupper() for c in fw.group(0)[1:])):
            t = t[0].upper() + t[1:]
    return t


def _extract_sub_blocks(body: str) -> dict[str, str]:
    """Walk a rec body and slice out `[ROOT CAUSE]` / `[SOLUTION]` / etc.
    sub-block payloads.

    Returns a dict mapping schema-field names to plain-text payloads.
    Unmatched body remains accessible to the caller via the original
    `body` argument; we don't try to remove it.
    """
    if not body:
        return {}
    # Walk every sub-block start; record (field_name, start, end).
    spans: list[tuple[str, int, int]] = []
    for field_name, rx in _SUB_BLOCK_HEADINGS.items():
        for m in rx.finditer(body):
            spans.append((field_name, m.start(), m.end()))
    if not spans:
        return {}
    spans.sort(key=lambda t: t[1])
    out: dict[str, str] = {}
    for i, (field_name, _start, end) in enumerate(spans):
        next_start = spans[i + 1][1] if i + 1 < len(spans) else len(body)
        payload = body[end:next_start].strip()
        if payload:
            # Duplicate markers concatenate (the IBKR banner path emits a
            # leading ROOT CAUSE span for the banner's own meta line plus
            # one for the 9.N.1 score-impact grid) — never drop content.
            out[field_name] = (
                f"{out[field_name]}\n{payload}" if field_name in out else payload
            )
    return out


# Flattened DOCX score-table rows: `P2C1\t1.79\t2.80\t+1.01` (Capability /
# Current / Target / Improvement columns). Rendered as readable per-rec
# transitions — the arithmetic content of the analyst's own table, never
# invented.
_TABLE_TRANSITION_ROW_RE = re.compile(
    r"^(P[1-4]C\d+(?:\.\d+)*)\t(\d(?:\.\d+)?)\t(\d(?:\.\d+)?)"
    r"(?:\t\+?-?\d(?:\.\d+)?)?\s*$"
)
_TABLE_HEADER_RE = re.compile(
    r"^capabilit(?:y|ies)\t|^\w[\w ]*\tcurrent\s+score\t", re.IGNORECASE,
)


def _describe_body(body: str, max_chars: int = 1800) -> str:
    """AE-readable description from a definition block that carries NO
    `[ROOT CAUSE]`/`[SOLUTION]` sub-block markers (the IBKR bracket-
    severity table shape, live 2026-07-06: the persisted description
    collapsed to the title, so every card lost its own transitions,
    timeline and validation prose — and the outcomes grid fell back to
    the run-wide worst gap, printing the identical "P2C1 score 1.79 →
    4.0 · 12-18 months · L" on all five cards).

    Score-table rows become `P2C1 1.79 → 2.80` clauses (comma-joined on
    one lead line, so `extract_score_transitions` reads the rec's OWN
    targets); the table header row drops; other tab-separated rows read
    as ` — `-joined cells; prose lines stay verbatim, sentence-clipped.
    """
    from app.services.nlp.segment import clip_sentences

    prose: list[str] = []
    transitions: list[str] = []
    for line in (body or "").splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = _TABLE_TRANSITION_ROW_RE.match(line)
        if m:
            transitions.append(f"{m.group(1)} {m.group(2)} → {m.group(3)}")
            continue
        if _TABLE_HEADER_RE.match(line.strip()):
            continue
        if "\t" in line:
            line = " — ".join(c.strip() for c in line.split("\t") if c.strip())
        prose.append(line.strip())
    parts: list[str] = []
    if transitions:
        parts.append(
            "Projected capability improvements: " + ", ".join(transitions) + ".")
    if prose:
        budget = max_chars - (len(parts[0]) + 2 if parts else 0)
        clipped = clip_sentences("\n".join(prose), max(budget, 0))
        if clipped:
            parts.append(clipped)
    return "\n\n".join(parts).strip()


def _build_recommendation_row(
    rec_id: str, title: str, body: str, severity: str | None = None
) -> RecommendationRow:
    """Construct a RecommendationRow from raw extracted data, dropping
    the sub-block payloads onto their schema fields using the CANONICAL
    key names so the downstream persistence layer's `_rec_description()`
    helper (package_persist.py:198) picks them up.

    Canonical shapes (from `08_appendices/recommendations_detail.json`):
      root_cause: {gap_description, evidence_ids, evidence_detail,
                   scoring_impact, proof_of_gap}
      solution:   {zennify_offering, description, approach,
                   scoping_note}
      expected_outcomes: list of {outcome_type, metric, baseline,
                                  target, business_impact}

    Our DOCX prose carries only flat text per sub-block (no structured
    sub-keys). We populate `gap_description` / `description` (the keys
    `_rec_description()` reads) and the long-form prose also lands in
    `source_body` for frontend rendering.
    """
    sub_blocks = _extract_sub_blocks(body)
    # Callers gate the title BEFORE building the row (title_reject_reason),
    # so a placeholder fallback is never needed — and never shipped.
    kwargs: dict[str, object] = {
        "id": rec_id,
        "title": title,
    }
    # Severity from the banner tag (`R1 [CRITICAL] …`) maps onto the
    # canonical `priority` field the JSON rec shapes already use.
    if severity:
        kwargs["priority"] = severity
    # `root_cause` -> `{gap_description: <text>}` matches the canonical
    # key that package_persist._rec_description reads. Preserves
    # downstream description persistence.
    if "root_cause" in sub_blocks:
        kwargs["root_cause"] = {"gap_description": sub_blocks["root_cause"]}
    elif body.strip() and "solution" not in sub_blocks:
        # No sub-block markers at all (bracket-severity table shape):
        # the block's own prose IS the gap/validation narrative — compose
        # a readable description from it so the persisted card never
        # collapses to a bare title (2026-07-06 uniform-outcomes fix).
        described = _describe_body(body)
        if described:
            kwargs["root_cause"] = {"gap_description": described}
    # `solution` -> `{description: <text>}` for the same reason.
    if "solution" in sub_blocks:
        kwargs["solution"] = {"description": sub_blocks["solution"]}
    # expected_outcomes shape (canonical): list of dicts with structured
    # outcome_type/metric/baseline/target/business_impact. The analyst's
    # prose isn't structured enough to split without a richer parser;
    # we surface as a single business_impact entry so the schema validates
    # and the downstream RecommendationsPage at least shows it.
    if "expected_outcomes" in sub_blocks:
        kwargs["expected_outcomes"] = [
            {"business_impact": sub_blocks["expected_outcomes"]}
        ]
    if "strategic_objectives" in sub_blocks:
        # Split on newline / pipe / semicolon; fall back to a single-
        # element list when no splitter is found.
        raw = sub_blocks["strategic_objectives"]
        parts = re.split(r"[\n|;]+", raw)
        kwargs["strategic_objectives"] = [p.strip() for p in parts if p.strip()]
    # Surface the full source body as an extra so the frontend can render
    # the long-form analyst prose even when the structured sub-fields
    # are sparse. (Firmographics uses the same `extra='allow'` pattern
    # for `branches` / `narrative_md`.)
    kwargs["source_body"] = body
    if "risk_of_inaction" in sub_blocks:
        kwargs["risk_of_inaction"] = sub_blocks["risk_of_inaction"]
    if "buyer_map" in sub_blocks:
        kwargs["buyer_map"] = sub_blocks["buyer_map"]
    return RecommendationRow(**kwargs)


def _extract_via_heading(
    sections: list[ReportSectionRow],
    warnings: list[str],
) -> list[RecommendationRow]:
    """Walk sections in order; collect any section whose heading
    starts with a rec_id pattern. Each rec spans from its heading
    until the next rec heading (or end of recs region).

    This is the Alma / Nicola path — both ship REC-NN as heading-2.
    """
    out: list[RecommendationRow] = []
    in_recs_region = False
    current: _RecCandidate | None = None
    seen_ids: set[str] = set()

    def _close():
        nonlocal current
        if current is not None and current.rec_id not in seen_ids:
            # Gate the title on EVERY path (2026-07-06): a fragment-shaped
            # title ('through the platform', an unbalanced-paren clip) is
            # dropped rather than shipped — the body-text fallback and the
            # downstream selection-QA still surface the real recs. A
            # rejected candidate does NOT consume its rec_id, so a later
            # duplicate heading with a clean title can still win.
            reason = title_reject_reason(current.title)
            if reason:
                warnings.append(
                    f"rec_title_rejected:{current.rec_id}:{reason}"
                )
            else:
                seen_ids.add(current.rec_id)
                out.append(_build_recommendation_row(
                    current.rec_id, current.title,
                    "\n".join(current.body_parts),
                ))
        current = None

    # Sections are typically ordinal-sorted but we sort defensively.
    sorted_secs = sorted(sections, key=lambda s: s.ordinal)
    for s in sorted_secs:
        kind = s.kind
        heading = (s.heading or "").strip()
        body = s.body or ""

        if kind == "recommendations":
            in_recs_region = True
            # Some reports (Zions) classify EACH "Recommendation N: …"
            # heading-2 as its own recommendations-kind section rather than
            # a single parent marker + sibling 'other' sections. When the
            # heading itself is a rec id, treat this section AS a rec.
            m = _REC_ID_RE.match(heading)
            if m:
                _close()
                rec_id = _normalize_rec_id(m.group(1))
                current = _RecCandidate(
                    rec_id=rec_id,
                    title=_split_title_from_heading(heading, rec_id),
                    body_parts=[body] if body else [],
                )
            continue
        if kind == "roadmap":
            # Closing the recs region — flush any in-progress candidate.
            _close()
            in_recs_region = False
            continue
        if not in_recs_region:
            continue

        m = _REC_ID_RE.match(heading)
        if m:
            # New rec heading; flush prior candidate first.
            _close()
            rec_id = _normalize_rec_id(m.group(1))
            title = _split_title_from_heading(heading, rec_id)
            current = _RecCandidate(rec_id=rec_id, title=title, body_parts=[body] if body else [])
        elif current is not None:
            # In-progress rec — accumulate sub-block headings AND their
            # bodies so the sub-block extractor can find them. Re-emit
            # the heading as a `[…]` marker line so the regex catches it.
            if heading.startswith("[") or heading.startswith("R-") or heading.startswith("REC"):
                current.body_parts.append(heading)
            if body:
                current.body_parts.append(body)
    # Flush final candidate.
    _close()
    return out


# ── Severity-banner path (IBKR shape, 2026-07-06) ──────────────────────
# `R1 [CRITICAL]  Financial Services Cloud — …` banner lines. The anchor
# REQUIRES the `[SEVERITY]` tag at line start — mid-sentence cross-
# references ("prerequisite for R1 and R2") and sequencing-logic lines
# ("R1 (FSC) + R5 …") can never fabricate a rec here. Severity-less
# dash-anchored forms stay with the body-text path below.
# "IMMEDIATE" is Cornerstone's urgency word for its fastest-win rec
# ("IMMEDIATE — FASTEST WIN"); rec_files.extract_phase already maps it
# to phase 1 when it lands on `priority`.
_SEVERITY_WORDS = (
    "CRITICAL", "URGENT", "IMMEDIATE", "HIGH", "MEDIUM", "MODERATE", "LOW",
)
_BANNER_RE = re.compile(
    r"^[ \t]*((?:REC|R)[-\s]?\d{1,3})[ \t]*"
    r"\[[ \t]*(" + "|".join(_SEVERITY_WORDS) + r")[ \t]*\]"
    r"[ \t]*[—–:-]?[ \t]*"
    r"([A-Za-z(\"'][^\n]*?)[ \t]*$",
    re.MULTILINE,
)

# Per-rec `9.N.x` sub-headings remapped to the canonical sub-block
# markers so `_extract_sub_blocks` slices the IBKR shape exactly like
# the WSFS/Nicola bracket shapes.
_SUBHEAD_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"capabilit(?:y|ies)\s+score|score\s+impact", re.I), "ROOT CAUSE:"),
    (re.compile(r"why\s+this\s+solution|specificity\s+test", re.I), "SOLUTION:"),
    (re.compile(r"expected\s+outcomes?", re.I), "EXPECTED OUTCOMES:"),
    (re.compile(r"risk\s+of\s+inaction", re.I), "RISK OF INACTION:"),
]


def _subheading_marker(heading: str) -> str | None:
    for rx, marker in _SUBHEAD_MARKERS:
        if rx.search(heading):
            return marker
    return None


def _collect_recs_region(
    sections: list[ReportSectionRow], *, remap_subheadings: bool
) -> str:
    """Concatenate the recs-region bodies (between `kind='recommendations'`
    and the next `kind='roadmap'`) in ordinal order. `remap_subheadings`
    re-emits the IBKR `9.N.x` sub-headings as sub-block markers."""
    parts: list[str] = []
    in_recs_region = False
    for s in sorted(sections, key=lambda s: s.ordinal):
        if s.kind == "recommendations":
            in_recs_region = True
            if s.body:
                parts.append(s.body)
            continue
        if s.kind == "roadmap":
            in_recs_region = False
            continue
        if not in_recs_region:
            continue
        heading = (s.heading or "").strip()
        if heading.startswith("["):
            # Sub-block marker (`[ROOT CAUSE]` / `[SOLUTION]` / …);
            # re-emit as a literal so the sub-block extractor finds it.
            parts.append(heading)
        elif remap_subheadings:
            marker = _subheading_marker(heading)
            if marker:
                parts.append(marker)
        if s.body:
            parts.append(s.body)
    return "\n".join(parts)


def _extract_via_banner(
    sections: list[ReportSectionRow],
    warnings: list[str],
) -> list[RecommendationRow]:
    """Severity-banner extraction (IBKR shape). Each rec spans from its
    banner line to the next banner (or region end). The banner's own
    meta line (`Capabilities: … | Timeline: 12 months | Validation: …`)
    plus the 9.N.1 score-impact grid fold into `root_cause.gap_description`
    — that is what lets the derive passes ground each rec's outcomes in
    ITS OWN capability targets instead of one shared entity-level gap.
    """
    concatenated = _collect_recs_region(sections, remap_subheadings=True)
    if not concatenated:
        return []
    anchors: list[tuple[int, int, str, str, str]] = []
    seen: set[str] = set()
    for m in _BANNER_RE.finditer(concatenated):
        rid = _normalize_rec_id(m.group(1))
        if rid in seen:
            continue
        seen.add(rid)
        anchors.append(
            (m.start(), m.end(), rid, m.group(2).upper(), m.group(3))
        )
    out: list[RecommendationRow] = []
    for i, (_start, end, rid, severity, raw_title) in enumerate(anchors):
        next_start = (
            anchors[i + 1][0] if i + 1 < len(anchors) else len(concatenated)
        )
        title = _clean_rec_title(raw_title)
        reason = title_reject_reason(title)
        if reason:
            warnings.append(f"rec_title_rejected:{rid}:{reason}")
            continue
        body = concatenated[end:next_start].strip()
        # The lead lines between the banner and the first sub-marker are
        # the banner cell's own metadata — semantically the gap statement.
        # Injecting a leading ROOT CAUSE marker (with the severity tag the
        # derive passes band effort from) folds them into gap_description;
        # duplicate markers concatenate in _extract_sub_blocks.
        body = f"ROOT CAUSE:\nSeverity: [{severity}]\n{body}"
        out.append(_build_recommendation_row(rid, title, body, severity=severity))
    return out


# ── Tab-row path (Guaranteed Rate / Cornerstone shapes, 2026-07-06) ────
# The document-order table flattening emits §9 rec-table rows as
# tab-joined lines. Two real layouts:
#   Cornerstone : `REC-001\t<title>\tCRITICAL — IMMEDIATE\t[ZENNIFY]`
#                 (one physical line: id, TITLE, severity+qualifier, tag)
#   Guaranteed  : the 1x5 banner cell stacks `REC-01\nHIGH` so the id
#   Rate          lands on its OWN line and the NEXT line reads
#                 `HIGH\t<title>` — severity-led cells.
# Column order is detected per row: the severity cell is whichever cell
# matches the severity lexicon (qualifiers like `CRITICAL — IMMEDIATE`
# allowed); the title is the longest non-severity, non-`[ZENNIFY]`,
# non-`Category:` cell.
_TAB_ANCHOR_RE = re.compile(r"^[ \t]*((?:REC|R)[-\s]?\d{1,3})(?:\t+(.+))?[ \t]*$")
_SEVERITY_CELL_RE = re.compile(
    r"^(" + "|".join(_SEVERITY_WORDS) + r")\b\s*(?:[—–:-]\s*(\S.{0,40}))?$")
_CATEGORY_CELL_RE = re.compile(r"^Category\s*[:\-]", re.IGNORECASE)

# Tab-separated label rows inside a rec's detail table (`ROOT CAUSE\t<prose>`,
# `ZENNIFY SOLUTION\t<prose>`, …) rewritten to the canonical bare-colon
# markers so `_extract_sub_blocks` slices them like every other shape.
_TAB_LABEL_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^[ \t]*ROOT\s+CAUSE[ \t]*\t", re.I), "ROOT CAUSE:\n"),
    (re.compile(r"^[ \t]*(?:ZENNIFY\s+)?SOLUTION[ \t]*\t", re.I), "SOLUTION:\n"),
    (re.compile(r"^[ \t]*EXPECTED\s+OUTCOMES?[ \t]*\t", re.I), "EXPECTED OUTCOMES:\n"),
    (re.compile(r"^[ \t]*RISK\s+OF\s+INACTION[ \t]*\t", re.I), "RISK OF INACTION:\n"),
]


def _classify_banner_cells(cells: list[str]) -> tuple[str | None, str, list[str]]:
    """(severity, raw_title, leftover_meta) from one rec-row's cells.

    Severity = the first cell matching the severity lexicon (its dash
    qualifier — `CRITICAL — IMMEDIATE` — is folded into the meta so it
    survives in gap_description). Title = the longest remaining cell
    that isn't a `[ZENNIFY]`-style template tag or a `Category:` meta
    cell; everything else is meta."""
    severity: str | None = None
    qualifier: str | None = None
    candidates: list[str] = []
    meta: list[str] = []
    for cell in cells:
        c = cell.strip()
        if not c:
            continue
        m = _SEVERITY_CELL_RE.match(c)
        if m and severity is None:
            severity = m.group(1).upper()
            qualifier = (m.group(2) or "").strip() or None
            continue
        if c.startswith("["):
            # Template tag (`[ZENNIFY]`) — presentation noise, drop.
            continue
        if _CATEGORY_CELL_RE.match(c):
            meta.append(c)
            continue
        candidates.append(c)
    title_raw = max(candidates, key=len) if candidates else ""
    meta.extend(c for c in candidates if c != title_raw)
    if qualifier:
        meta.insert(0, f"Priority qualifier: {qualifier}")
    return severity, title_raw, meta


def _extract_via_tab_rows(
    sections: list[ReportSectionRow],
    warnings: list[str],
) -> list[RecommendationRow]:
    """Tab-row extraction. Each rec spans from its id row (plus the
    severity-led cell line the Guaranteed-Rate shape stacks under it) to
    the next id row. Label rows (`ROOT CAUSE\\t…`) are remapped to the
    canonical sub-block markers, and — exactly like the banner path —
    a leading ROOT CAUSE marker folds the row's own meta cells
    (severity, Category/score cells) into gap_description so the derive
    passes ground each rec in ITS OWN capability targets."""
    region = _collect_recs_region(sections, remap_subheadings=True)
    if not region:
        return []
    lines = region.split("\n")

    # anchor = (line_idx, lines_consumed, rid, severity, raw_title, meta)
    anchors: list[tuple[int, int, str, str | None, str, list[str]]] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        m = _TAB_ANCHOR_RE.match(line)
        if not m:
            continue
        consumed = 1
        if m.group(2) is not None:
            cells = m.group(2).split("\t")
        else:
            # Bare-id line (Guaranteed Rate) — only an anchor when the
            # NEXT line is a severity-led cell row; a bare cross-
            # reference line never fabricates a rec.
            nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
            cells = nxt.split("\t")
            if not _SEVERITY_CELL_RE.match(cells[0].strip()):
                continue
            consumed = 2
        rid = _normalize_rec_id(m.group(1))
        if rid in seen:
            continue
        seen.add(rid)
        severity, title_raw, meta = _classify_banner_cells(cells)
        anchors.append((idx, consumed, rid, severity, title_raw, meta))

    out: list[RecommendationRow] = []
    for i, (idx, consumed, rid, severity, title_raw, meta) in enumerate(anchors):
        next_idx = anchors[i + 1][0] if i + 1 < len(anchors) else len(lines)
        title = _clean_rec_title(title_raw)
        reason = title_reject_reason(title)
        if reason:
            warnings.append(f"rec_title_rejected:{rid}:{reason}")
            continue
        body_lines: list[str] = []
        for raw_line in lines[idx + consumed:next_idx]:
            rewritten = raw_line
            for rx, marker in _TAB_LABEL_MARKERS:
                if rx.match(raw_line):
                    rewritten = rx.sub(marker, raw_line, count=1)
                    break
            body_lines.append(rewritten)
        lead = [f"Severity: [{severity}]"] if severity else []
        body = "\n".join(["ROOT CAUSE:", *lead, *meta, *body_lines]).strip()
        out.append(_build_recommendation_row(rid, title, body, severity=severity))
    return out


def _extract_via_body_text(
    sections: list[ReportSectionRow],
    warnings: list[str],
) -> list[RecommendationRow]:
    """Concatenate ALL section bodies in the recs region (between
    `kind='recommendations'` and the next `kind='roadmap'`) and split
    on rec_id patterns.

    This is the WSFS / Calprivate / Odlum path — rec IDs are inline
    in the prose rather than as heading-2 markers. WSFS specifically
    interleaves REC-001's text into the parent §9 body, then puts
    `[ROOT CAUSE]` / `[SOLUTION]` / `[EXPECTED OUTCOMES]` heading-3
    sub-blocks per rec; REC-002's intro paragraph lives at the start
    of REC-001's `[EXPECTED OUTCOMES]` body (because the assessment_report
    parser groups paragraphs under the most-recent heading).
    Concatenating the bodies in document order surfaces every rec ID.
    """
    out: list[RecommendationRow] = []
    concatenated = _collect_recs_region(sections, remap_subheadings=False)
    if not concatenated:
        return out

    # Keep only IDs that look like recommendation-definition anchors,
    # picking the STRONGEST anchor per ID (a `[CRITICAL]`-tagged
    # definition block beats a summary-table `R1: …` row beats nothing).
    # Cross-references — parenthesized "(R1)", "prerequisite for R1 and
    # R2", "R-01 establishes…" — score 0 and never become split points,
    # so a split can never start a rec's text mid-parenthesis (the
    # production ') and personalized MCAE journeys (' class). NO fallback
    # to un-anchored matches: when nothing anchors, this report simply
    # has no body-text recs — the derive chain fills grounded,
    # cleanly-titled gap recs instead. (The pre-2026-07-06
    # `anchored or matches` fallback split on bare mid-sentence
    # cross-references and fabricated fragment-titled recs.)
    best_by_id = _best_anchors(concatenated, min_strength=1)
    if not best_by_id:
        # No definition-shaped anchor in the recs region: the region only
        # cross-references its recommendations (IBKR intro-prose shape —
        # the real definitions live in DOCX tables, which the paragraph
        # flattener appends after the LAST section). Fall back to a
        # whole-document scan that accepts ONLY the unambiguous
        # `R1 [CRITICAL]  Title` bracket-severity definition shape.
        whole = "\n".join(
            s.body for s in sorted(sections, key=lambda s: s.ordinal) if s.body
        )
        best_by_id = _best_anchors(whole, min_strength=3)
        if not best_by_id:
            # Honest empty beats prose shredded at "(R1)" boundaries —
            # the derive layer synthesizes grounded recs instead.
            return out
        concatenated = whole
    ordered = sorted(
        ((rid, pos) for rid, (_s, pos) in best_by_id.items()),
        key=lambda t: t[1],
    )
    for i, (rid, start_pos) in enumerate(ordered):
        end_pos = ordered[i + 1][1] if i + 1 < len(ordered) else len(concatenated)
        slice_text = concatenated[start_pos:end_pos].strip()
        first_line, _, rest = slice_text.partition("\n")
        priority: str | None = None
        # Strip the rec-id token, then the bracket-severity tag
        # (`R1 [CRITICAL]  Title`) — the tag rides `priority`, not the title.
        id_lead = _REC_ID_RE.match(first_line.strip())
        if id_lead:
            after_id = first_line.strip()[id_lead.end():]
            sev = _SEVERITY_TAG_RE.match(after_id)
            if sev:
                priority = sev.group(1).upper()
                first_line = f"{id_lead.group(0)}: {after_id[sev.end():]}"
        title = _split_title_from_heading(first_line, rid)
        # A summary-table row (`R1: Financial Services Cloud\tP2C1 …`)
        # keeps only its title cell — the tab-separated score columns
        # are table data, not title prose.
        title = title.split("\t", 1)[0].strip()
        # Fragment gate (2026-07-06): drop shredded cross-references,
        # mid-sentence fragments, and unbalanced-paren clips rather than
        # shipping them as rec titles. Supersedes the old
        # startswith(")")/endswith("(") spot-check.
        reason = title_reject_reason(title)
        if reason:
            warnings.append(f"rec_title_rejected:{rid}:{reason}")
            continue
        row = _build_recommendation_row(rid, title, rest.strip())
        if priority and not getattr(row, "priority", None):
            row.priority = priority
        out.append(row)
    return out


def _best_anchors(body: str, *, min_strength: int) -> dict[str, tuple[int, int]]:
    """{normalized rec_id → (strength, position)} for every rec-ID
    occurrence scoring at least ``min_strength`` — the strongest anchor
    per ID wins; ties keep the earliest occurrence."""
    best: dict[str, tuple[int, int]] = {}
    for m in _REC_ID_RE.finditer(body):
        strength = _anchor_strength(body, m)
        if strength < min_strength:
            continue
        rid = _normalize_rec_id(m.group(1))
        prior = best.get(rid)
        if prior is None or strength > prior[0]:
            best[rid] = (strength, m.start())
    return best


def _paren_open_at(body: str, pos: int) -> bool:
    """True when ``pos`` sits inside an unclosed '(' on its own line."""
    line_start = body.rfind("\n", 0, pos) + 1
    depth = 0
    for ch in body[line_start:pos]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
    return depth > 0


def _anchor_strength(body: str, m: re.Match[str]) -> int:
    """Rank a rec-ID occurrence: 0 = cross-reference (never split here),
    1 = mid-prose separator-anchored definition (`… REC-001 — Deploy …`),
    2 = line-start separator-anchored heading (`R-01: Title`),
    3 = bracket-severity definition block (`R1 [CRITICAL]  Title`).

    Reference shapes that must stay 0: parenthesized ids ("(R1)"), ids
    inside an open parenthetical span, connector-word list mentions
    ("for R1 and R2", "prerequisite for R1"), and bare mid-sentence ids
    ("R-01 establishes …").
    """
    start = m.start()
    # Parenthesized cross-reference: "(R1)" / "(see REC-04)".
    before = body[:start].rstrip(" \t")
    if before.endswith("("):
        return 0
    after = body[m.end():]
    if after.lstrip(" \t").startswith(")"):
        return 0
    # Inside an unclosed parenthetical on this line — splitting here is
    # what produced titles beginning with ")".
    if _paren_open_at(body, start):
        return 0
    at_line_start = start == 0 or body[start - 1] == "\n"
    # A mid-prose ID preceded by a connector word ('for R1 and R2',
    # 'see R-02') is a cross-reference, never a definition — reject
    # before looking at the separator (2026-07-06 fragment-fabrication
    # fix). Line-start headings are exempt: a previous line's trailing
    # connector can never suppress a real `R-01: Title` heading.
    if not at_line_start and re.search(
        r"\b(?:for|and|with|via|by|of|see|to)\s+$",
        body[max(0, start - 12):start], re.IGNORECASE,
    ):
        return 0
    if _SEVERITY_TAG_RE.match(after):
        return 3
    # `[—–:\-]` covers em-dash (U+2014), en-dash (U+2013), colon, hyphen
    # — the four title-separator chars observed across the fixtures.
    tail = body[start:start + 30]
    if re.search(r"^\S+[-\s]?\d{1,3}\s*[—–:\-]\s+", tail):
        return 2 if at_line_start else 1
    return 0


def _looks_like_rec_anchor(body: str, start: int) -> bool:
    """Back-compat wrapper: True when the ID at ``start`` is a
    recommendation-definition anchor rather than a cross-reference."""
    m = _REC_ID_RE.match(body, start)
    return bool(m) and _anchor_strength(body, m) > 0


def extract_recommendations_from_report_sections(
    sections: list[ReportSectionRow],
    warnings: list[str] | None = None,
) -> list[RecommendationRow]:
    """Main entrypoint. Tries heading-based extraction first, then the
    severity-banner shape, then body-text extraction. Returns [] when
    no recs found — NEVER a fabricated fragment.

    ``warnings`` (optional out-param) collects one
    ``rec_title_rejected:<rec_id>:<reason>`` entry per candidate the
    fragment gate dropped; the count is also logged for parser
    observability when the caller doesn't pass a list.
    """
    if not sections:
        return []
    w: list[str] = warnings if warnings is not None else []
    # Try heading-based first (Alma / Nicola — preferred shape).
    out = _extract_via_heading(sections, w)
    if not out:
        # Severity-banner shape (IBKR — 1x1 table banners inside §9).
        out = _extract_via_banner(sections, w)
    if not out:
        # Tab-row shape (Guaranteed Rate / Cornerstone — §9 rec tables
        # flattened to tab-joined rows).
        out = _extract_via_tab_rows(sections, w)
    if not out:
        # Fall back to body-text extraction (WSFS / Calprivate / Odlum).
        out = _extract_via_body_text(sections, w)
    rejected = [x for x in w if x.startswith("rec_title_rejected:")]
    if rejected:
        log.info(
            "report_recommendations: fragment gate dropped %d candidate(s): %s",
            len(rejected), "; ".join(rejected),
        )
    return out
