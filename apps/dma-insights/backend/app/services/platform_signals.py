"""Evidence-text stack signals + firmographic scale for platform fit.

Part of the 2026-07-06 platform-reasoning mandate: fit/readiness must be
REASONED over ALL relevant evidence — not just tech_stack_entries rows
and subcap scores. Two signal families live here (pure, no DB):

1. **Stack mentions** — :func:`classify_stack_mentions` scans the run's
   evidence excerpts for platform-family product names (the same
   PLATFORM_FAMILY_PATTERNS the tech-stack scan uses) and classifies
   each mention's polarity from its own sentence:

     - ``in_use``  — usage/deployment language ("uses", "deployed",
       "migrating to", "rollout", "1,800 Tableau users")
     - ``absent``  — researcher negative-search / negation ("no CDP",
       "lacks", "internal alternative to Salesforce")
     - ``planned`` — forward-looking ("evaluating", "plans to", "RFP")
     - ``mention`` — named without a classifiable frame

   Every signal carries the E-ID + the VERBATIM sentence (quote_span
   clipping — never mid-claim), so the correction it drives is
   auditable end-to-end.

2. **Firmographic scale** — :func:`scale_context` bands the entity by
   assets/headcount. Platform implementation lift is real AE reasoning:
   a $200M credit union with 40 staff is not a greenfield Databricks
   opportunity however absent the family is. The band feeds a bounded,
   documented dampener on the absent-family boost for heavy-lift
   platforms — and lands in the reasoning record either way.

Effects on the fit engine (compute_platform_fit_v2):
  - a family with an ``in_use`` evidence signal loses the greenfield
    absent boost even when tech_stack_entries missed it (the evidence
    corrects the stack table, cited by E-ID);
  - a small-scale entity halves the absent boost on HEAVY platforms;
  - everything lands in ``fit_breakdown.stack_signals`` /
    ``fit_breakdown.scale`` / ``fit_breakdown.reasoning``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# Sentence-local polarity frames. Ordered: absence beats planned beats
# in-use when several match (a negated deployment is an absence).
_ABSENT_RE = re.compile(
    r"\b(?:no|not|never|without|lack(?:s|ing)?|absen(?:t|ce)|"
    r"does\s+not\s+(?:use|have|run)|internal\s+alternative|"
    r"could\s+not\s+identify|none\s+identified|no\s+evidence\s+of|"
    r"not\s+(?:deployed|adopted|implemented|in\s+use)|"
    r"has\s+yet\s+to|declined\s+to\s+adopt)\b",
    re.IGNORECASE,
)
_PLANNED_RE = re.compile(
    r"\b(?:plan(?:s|ned|ning)?\s+to|evaluat(?:e|ing|ion)|consider(?:s|ing)|"
    r"explor(?:e|ing)|rfp|proof\s+of\s+concept|pilot(?:s|ing)?|"
    r"intend(?:s|ed)?\s+to|roadmap\s+to|select(?:ing|ion)\s+process|"
    r"upcoming|will\s+(?:deploy|adopt|migrate))\b",
    re.IGNORECASE,
)
_IN_USE_RE = re.compile(
    r"\b(?:used?s?|using|deploy(?:ed|s|ment)|migrat(?:ed|ing|ion)|"
    r"runs?\s+on|live\s+on|went\s+live|goes\s+live|rollout|rolled\s+out|"
    r"implement(?:ed|ation)|"
    r"adopt(?:ed|ion)|licens(?:ed|es)|instance\s+of|built\s+on|"
    r"powered\s+by|standardi[sz]ed\s+on|users?\b|go-live|in\s+production)\b",
    re.IGNORECASE,
)

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'(])")

# Implementation lift per scored platform — drives the scale dampener.
# HEAVY = multi-quarter, data-team-and-integration dependent; MODERATE
# = deployable by a small team on existing infrastructure.
PLATFORM_LIFT: dict[str, str] = {
    "salesforce": "heavy",
    "databricks": "heavy",
    "ncino": "heavy",
    "twilio": "moderate",
    "tableau": "moderate",
}

# Scale bands (assets in USD, headcount). Deterministic and documented:
# below EITHER small threshold ⇒ small; above EITHER large threshold ⇒
# large; else mid. Honest None when both inputs are missing.
_SMALL_AUM = 500e6
_LARGE_AUM = 10e9
_SMALL_HEADCOUNT = 100
_LARGE_HEADCOUNT = 2000

# Absent-boost dampener for small-scale entities on heavy platforms.
SMALL_SCALE_ABSENT_DAMP = 0.5

# Absent-boost residual when a CATEGORY incumbent (Snowflake for the
# databricks family, MeridianLink for ncino, …) is already deployed: the
# greenfield argument is gone — what remains is a bounded
# integration/complement entry (2026-07-14 skew audit).
INCUMBENT_ABSENT_RESIDUAL = 0.25


@dataclass
class StackSignal:
    """One evidence mention of a platform family, verbatim + cited."""

    platform_id: str
    e_id: str
    polarity: str          # in_use | absent | planned | mention
    excerpt: str           # verbatim sentence (quote_span-clipped)
    products: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _polarity(sentence: str) -> str:
    if _ABSENT_RE.search(sentence):
        return "absent"
    if _PLANNED_RE.search(sentence):
        return "planned"
    if _IN_USE_RE.search(sentence):
        return "in_use"
    return "mention"


def classify_stack_mentions(
    evidence_rows: list[tuple[str, str]],
    *,
    family_patterns: dict[str, re.Pattern[str]],
    family_products: dict[str, list[tuple[str, re.Pattern[str]]]] | None = None,
    max_per_platform: int = 6,
) -> dict[str, list[StackSignal]]:
    """Scan (e_id, excerpt) rows for family mentions, sentence-scoped.

    ``family_patterns``/``family_products`` are the SAME tables the
    tech-stack absent scan uses (platform_fit_data) — one vocabulary,
    two sources. Returns {platform_id: [StackSignal...]} with at most
    ``max_per_platform`` signals, ``in_use`` first (they drive the
    correction), then absent/planned/mention.
    """
    from app.services.startup_enrich import quote_span

    family_products = family_products or {}
    out: dict[str, list[StackSignal]] = {pid: [] for pid in family_patterns}
    rank = {"in_use": 0, "absent": 1, "planned": 2, "mention": 3}
    for e_id, excerpt in evidence_rows:
        if not excerpt:
            continue
        for sentence in _sentences(str(excerpt)):
            for pid, rx in family_patterns.items():
                if not rx.search(sentence):
                    continue
                products = [
                    name for name, prx in family_products.get(pid, [])
                    if prx.search(sentence)
                ]
                verbatim = quote_span(sentence, 240)
                if not verbatim:
                    # No claim-safe clip inside budget — keep the whole
                    # sentence rather than fabricate a truncation.
                    verbatim = sentence
                out[pid].append(StackSignal(
                    platform_id=pid,
                    e_id=str(e_id),
                    polarity=_polarity(sentence),
                    excerpt=verbatim,
                    products=products,
                ))
    for pid, signals in out.items():
        signals.sort(key=lambda s: (rank.get(s.polarity, 9), s.e_id))
        # One signal per (e_id, polarity) — an excerpt restating the same
        # fact shouldn't multiply the record.
        seen: set[tuple[str, str]] = set()
        deduped: list[StackSignal] = []
        for s in signals:
            key = (s.e_id, s.polarity)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(s)
        out[pid] = deduped[:max_per_platform]
    return out


def evidence_confirms_in_use(signals: list[StackSignal]) -> bool:
    """The correction gate: at least one in-use mention. Absent/planned
    mentions do NOT flip the greenfield read — they corroborate it."""
    return any(s.polarity == "in_use" for s in signals)


def scale_context(
    aum_usd: float | None,
    headcount: int | None,
) -> dict:
    """{band: small|mid|large|None, aum_usd, headcount, basis} — honest
    None band when neither input exists."""
    band: str | None = None
    basis: list[str] = []
    if aum_usd is not None or headcount is not None:
        small = ((aum_usd is not None and aum_usd < _SMALL_AUM)
                 or (headcount is not None and headcount < _SMALL_HEADCOUNT))
        large = ((aum_usd is not None and aum_usd >= _LARGE_AUM)
                 or (headcount is not None and headcount >= _LARGE_HEADCOUNT))
        band = "large" if large else ("small" if small else "mid")
        if aum_usd is not None:
            basis.append(f"assets ${aum_usd / 1e9:.1f}B" if aum_usd >= 1e9
                         else f"assets ${aum_usd / 1e6:.0f}M")
        if headcount is not None:
            basis.append(f"headcount {headcount:,}")
    return {
        "band": band,
        "aum_usd": aum_usd,
        "headcount": headcount,
        "basis": ", ".join(basis) or None,
    }


def absent_boost_adjustment(
    *,
    platform_id: str,
    base_absent: bool,
    signals: list[StackSignal],
    scale: dict | None,
    category_incumbents: list[str] | None = None,
    graded_base: float | None = None,
) -> tuple[float, str | None, list[str]]:
    """(boost 0..1, reason, citing E-IDs) — the reasoned greenfield read.

    Ladder (order matters; first matching rung returns):
      evidence says in-use     → 0.0 (evidence corrects the stack table)
      stack table has it       → 0.0 (family detected; no greenfield)
      category incumbent there → INCUMBENT_ABSENT_RESIDUAL — the argument
                                 shifts from greenfield adoption to
                                 integration with the installed platform
      small scale + heavy      → min(graded_base, SMALL_SCALE_ABSENT_DAMP)
      confirmed absent         → graded_base (peer-coverage-graded stack
                                 alignment) when supplied, else 1.0

    ``category_incumbents`` — third-party platforms occupying the same
    functional category (from platform_incumbents.detect_category_incumbents).
    ``graded_base`` — the peer-coverage-graded stack_alignment value; before
    2026-07-14 this rung was a flat 1.0, which made cohort adoption
    invisible on the prod path ("0% of peers deploy it" next to a 70+ card).
    Both kwargs default to None ⇒ byte-identical legacy behaviour.
    """
    in_use = [s for s in signals if s.polarity == "in_use"]
    if in_use:
        e_ids = sorted({s.e_id for s in in_use})[:3]
        return 0.0, (
            "evidence names the family in use — greenfield boost removed"
        ), e_ids
    if not base_absent:
        return 0.0, None, []
    absent_cites = sorted({s.e_id for s in signals if s.polarity == "absent"})[:3]
    if category_incumbents:
        names = ", ".join(category_incumbents[:3])
        return INCUMBENT_ABSENT_RESIDUAL, (
            f"a category incumbent is already deployed ({names}) — the "
            "argument shifts from greenfield adoption to integration with "
            "the installed platform"
        ), absent_cites
    band = (scale or {}).get("band")
    if band == "small" and PLATFORM_LIFT.get(platform_id) == "heavy":
        damp = SMALL_SCALE_ABSENT_DAMP
        if graded_base is not None:
            damp = min(float(graded_base), damp)
        return damp, (
            "family absent from the detected stack, but the entity's scale "
            f"({(scale or {}).get('basis') or 'small'}) halves the greenfield "
            "weight on a heavy-implementation platform"
        ), absent_cites
    reason = "family confirmed absent from the detected stack — greenfield entry"
    if absent_cites:
        reason += " (evidence corroborates the absence)"
    if graded_base is not None:
        return round(max(0.0, min(1.0, float(graded_base))), 4), (
            reason + "; weighted by cohort adoption (peer coverage)"
        ), absent_cites
    return 1.0, reason, absent_cites
