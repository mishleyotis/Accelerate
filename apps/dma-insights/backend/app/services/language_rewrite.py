"""Deterministic language-rewrite pass for the rendered narrative surface.

Per the integrated batched plan Batch 6 spec + the operator mandate
"check on whether the language used to communicate findings has been
sanitized to fit the language guidelines in the design documents":
this module rewrites bot-emitted narrative text (subcap rationales,
SCQA, top-findings, DOCX section bodies, recommendation descriptions)
into Zennify product voice per the UI/UX brief.

The rewriter is deterministic (regex-based, pure-function, <1ms per
text) so it ships without any Vertex dependency. Each rule is the
inverse of a corresponding ``qa_language_audit.py`` rule -- the
audit's "forbidden phrase" becomes the rewriter's "replacement
mapping".

Anchor preservation (the hard guarantee):
  - Evidence anchors (``E-099``, ``[E-099]``) are PRESERVED VERBATIM.
  - Subcap IDs (``P1C1.1.1``, ``[P1C1.1.1]``) are PRESERVED VERBATIM.
  - Numbers, dates, monetary values, percentages are PRESERVED.
  - Bracketed citation blocks (``[E-099,E-101]``) are PRESERVED.
  - The post-rewrite validator counts anchor occurrences before and
    after; if any anchor was dropped, the rewrite is rejected and
    the caller receives the ORIGINAL text plus a validation_passed=False
    flag. The wrapper in ``narrative_polish`` then serves the original
    -- never broken content.

State branches (the 4 documented outcomes):

  applied              -- one or more rules matched; rewrite kept all
                          anchors; rewritten text returned.
  no_change_needed     -- source has zero forbidden patterns; source
                          returned unchanged.
  validator_rejected   -- rewrite dropped one or more anchors;
                          validation_passed=False; caller serves
                          ORIGINAL text. The audit harness should
                          surface these for tuning.
  empty_input          -- source is empty/None; returns "" as-is.

The pure-function design makes the unit tests fast (no DB, no
network) and lets the cache + endpoint integration layers compose
freely.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# ── Anchor preservation patterns ────────────────────────────────────
# These patterns MUST appear in the rewritten text in EXACTLY the
# same count as in the source. Detect by extraction; check by set
# membership + count.

_ANCHOR_PATTERNS = (
    # Evidence ID: E-001, E-1234. Word-boundary anchored.
    re.compile(r"\bE-\d{1,5}\b"),
    # Subcap ID: P1C1, P1C1.1.1, P1C1.1.1-T2 etc. Captures any
    # subcap-shaped reference at any depth.
    re.compile(r"\bP[1-4]C\d+(?:\.\d+){0,3}(?:[-_][A-Za-z0-9]+)?\b"),
    # Issue / cap IDs: IR-001, SEV-001, INT-005, DMA-ASM-...
    re.compile(r"\b(?:IR|SEV|INT|CAP|REC|FA|D|REQ|DMA-[A-Z]+)-?\d+\b"),
    # Monetary: $1.5B, $25.4M, $1,200, $1.2M-$2.5M
    re.compile(r"\$\d+(?:[.,]\d+)?\s*[BMK]?(?:\s*-\s*\$\d+(?:[.,]\d+)?\s*[BMK]?)?"),
    # Percentages: 25%, 25.5%, -0.34%
    re.compile(r"-?\d+(?:\.\d+)?%"),
    # Score notation: M1.5, M2, M3.0 (with optional trailing decimal)
    re.compile(r"\bM[1-5](?:\.\d)?\b"),
    # Catalogue versions: v5.5, v7.0, v8
    re.compile(r"\bv\d+(?:\.\d+)?\b"),
)


def extract_anchors(text: str) -> list[str]:
    """Return every anchor token in the text (with repetitions).

    The order is the appearance order, then by pattern; duplicates
    are kept so the validator can detect "rewrite dropped 1 of 3
    citations of E-099".
    """
    if not text:
        return []
    out: list[str] = []
    for pat in _ANCHOR_PATTERNS:
        out.extend(pat.findall(text))
    return out


def _anchor_count_diff(
    source: str, rewritten: str,
) -> dict[str, tuple[int, int]]:
    """Per-anchor before/after counts. Used by the validator."""
    src = extract_anchors(source)
    rew = extract_anchors(rewritten)
    diff: dict[str, tuple[int, int]] = {}
    for tok in set(src) | set(rew):
        diff[tok] = (src.count(tok), rew.count(tok))
    return diff


# ── Rewrite rules ─────────────────────────────────────────────────
# Each rule is a tuple of (compiled regex, replacement, rule_id).
# Patterns use word boundaries to avoid eating substrings inside
# E-IDs / subcap IDs (e.g. "may" inside "MAY" anchor is safe).

@dataclass(frozen=True)
class _RewriteRule:
    pattern: re.Pattern[str]
    replacement: str
    rule_id: str
    description: str


# Bump on ANY change to the rule table below. The narrative-polish cache
# folds this into its fingerprint — without it, a ruleset update never
# reaches text whose old rewrite is already cached (found 2026-07-12:
# S2_accusatory stayed frozen at 84 across a rule release because every
# insight body was served from rewrite-v1 cache rows).
RULESET_VERSION = "rw-2026-07-12.4"

# Order matters: longer phrases first so "a number of opportunities"
# matches the multi-word rule BEFORE the bare "number" rule.
_RULES: tuple[_RewriteRule, ...] = (
    # ── S1 -- analyst focus-codes must not lead AE-facing prose ─────
    _RewriteRule(
        re.compile(r"(?:^|(?<=[.;!?]\s))(?:Finding\s+)?F-\d{1,3}[:\s]\s*"),
        "",
        "S1_jargon",
        "'F-006: <headline>' analyst focus-code lead -> stripped "
        "(F-codes are not anchors; the headline carries the meaning)",
    ),
    # ── R2 -- Opportunity framing ─────────────────────────────────
    _RewriteRule(
        re.compile(r"\bpain\s+points?\b", re.IGNORECASE),
        "areas of focus",
        "R2_opportunity_framing",
        "Avoid deficit language -- 'pain point' -> 'area of focus'",
    ),
    _RewriteRule(
        re.compile(r"\bweaknesses\b", re.IGNORECASE),
        "opportunities",
        "R2_opportunity_framing",
        "'weaknesses' -> 'opportunities'",
    ),
    _RewriteRule(
        re.compile(r"\bweakness\b", re.IGNORECASE),
        "opportunity",
        "R2_opportunity_framing",
        "'weakness' -> 'opportunity'",
    ),
    # Verb forms of deficit language -- common in bot prose
    # ("significantly weaken P1C1...") so the noun-only rules miss them.
    _RewriteRule(
        re.compile(r"\bweakens\b", re.IGNORECASE),
        "narrows",
        "R2_opportunity_framing",
        "'weakens' -> 'narrows'",
    ),
    _RewriteRule(
        re.compile(r"\bweakened\b", re.IGNORECASE),
        "narrowed",
        "R2_opportunity_framing",
        "'weakened' -> 'narrowed'",
    ),
    _RewriteRule(
        re.compile(r"\bweaken\b", re.IGNORECASE),
        "narrow",
        "R2_opportunity_framing",
        "'weaken' -> 'narrow'",
    ),
    _RewriteRule(
        re.compile(r"\bfailures\b", re.IGNORECASE),
        "gaps",
        "R2_opportunity_framing",
        "'failures' -> 'gaps'",
    ),
    _RewriteRule(
        re.compile(r"\bfailure\b", re.IGNORECASE),
        "gap",
        "R2_opportunity_framing",
        "'failure' -> 'gap'",
    ),
    _RewriteRule(
        re.compile(r"\bdeficient\b", re.IGNORECASE),
        "below benchmark",
        "R2_opportunity_framing",
        "'deficient' -> 'below benchmark'",
    ),
    _RewriteRule(
        re.compile(r"\black\s+of\b", re.IGNORECASE),
        "headroom in",
        "R2_opportunity_framing",
        "L5: 'lack of' -> 'headroom in'",
    ),
    _RewriteRule(
        re.compile(r"\blacks\b", re.IGNORECASE),
        "has headroom to build out",
        "R2_opportunity_framing",
        "L5: 'lacks' -> 'has headroom to build out'",
    ),
    _RewriteRule(
        re.compile(r"\blacking\b", re.IGNORECASE),
        "not yet built out",
        "R2_opportunity_framing",
        "L5: 'lacking' -> 'not yet built out'",
    ),
    _RewriteRule(
        re.compile(r"(?:^|(?<=[.;:!?]\s))No\s+([A-Z][\w &/()+-]{2,60}?)(?=\s*[:\u2014\u2013-])"),
        r"\1 not yet in place",
        "R2_opportunity_framing",
        "L1/L8: 'No <Capability>:' headline lead -> '<Capability> not yet in place:'",
    ),
    _RewriteRule(
        # prose variant of L1: a sentence that OPENS "No <Capability>,|." —
        # ("No AI chatbot, no automated tier-1 deflection.") — the headline
        # rule above only fires before a colon/dash lead
        re.compile(r"(?:^|(?<=[.;!?]\s))No\s+([A-Z][\w &/()+-]{2,60}?)(?=\s*[,.;]|\s*$)"),
        r"\1 is not yet in place",
        "R2_opportunity_framing",
        "L1: sentence-lead 'No <Capability>,' -> '<Capability> is not yet in place,'",
    ),
    _RewriteRule(
        # raw analyst-note shout in titles ("FCA Enforcement History —
        # NONE 1998-2025") -> human copy; the clean-standing FACT is kept
        re.compile(r"([\u2014\u2013-])\s*NONE\b(?!\s+Identified)"),
        r"\1 none on record",
        "R2_opportunity_framing",
        "'— NONE' -> '— none on record'",
    ),
    _RewriteRule(
        re.compile(r"\bwith\s+no\s+([a-z][\w-]*"
                   r"(?:\s+(?!and\b|or\b|but\b|the\b|is\b|are\b|was\b|were\b)"
                   r"[a-z][\w-]*)?)", re.IGNORECASE),
        r"with \1 not yet in place",
        "R2_opportunity_framing",
        "L8: 'with no <X>' -> 'with <X> not yet in place'",
    ),
    _RewriteRule(
        re.compile(r"\bdoes\s+not\s+have\b", re.IGNORECASE),
        "has yet to add",
        "R2_opportunity_framing",
        "'does not have' -> 'has yet to add'",
    ),
    _RewriteRule(
        # bare-verb frame only ("does not integrate" -> "has yet to
        # integrate"); 'cannot' is deliberately NOT rewritten — validated-
        # absence statements ("Cannot confirm after exhaustive proxy
        # searches") are spec-required honesty (QA-OV-25 / QA-TS-01)
        re.compile(r"\bdoes\s+not\s+(?=[a-z]+\b)", re.IGNORECASE),
        "has yet to ",
        "R2_opportunity_framing",
        "'does not <verb>' -> 'has yet to <verb>'",
    ),
    _RewriteRule(
        re.compile(r"\bis\s+absent\b", re.IGNORECASE),
        "is a near-term opportunity",
        "R2_opportunity_framing",
        "L6: 'is absent' -> 'is a near-term opportunity'",
    ),
    _RewriteRule(
        re.compile(r"\babsent\b", re.IGNORECASE),
        "not yet in place",
        "R2_opportunity_framing",
        "L6: 'absent' -> 'not yet in place'",
    ),
    _RewriteRule(
        re.compile(r"\bis\s+missing\b", re.IGNORECASE),
        "has yet to add",
        "R2_opportunity_framing",
        "L6: 'is missing' -> 'has yet to add'",
    ),
    _RewriteRule(
        re.compile(r"\bmissing\b", re.IGNORECASE),
        "yet-to-be-added",
        "R2_opportunity_framing",
        "L6: 'missing <X>' -> 'yet-to-be-added <X>'",
    ),
    _RewriteRule(
        re.compile(r"\bfails?\s+to\b", re.IGNORECASE),
        "has yet to",
        "R2_opportunity_framing",
        "'fails to' -> 'has yet to'",
    ),
    _RewriteRule(
        re.compile(r"\bunable\s+to\b", re.IGNORECASE),
        "not yet able to",
        "R2_opportunity_framing",
        "'unable to' -> 'not yet able to'",
    ),
    # ── R6 -- consultant jargon (pack S1) ─────────────────────────
    _RewriteRule(
        re.compile(r"\bpeer[- ]cohort\b", re.IGNORECASE),
        "peer group",
        "R6_jargon",
        "S1: 'peer cohort' -> 'peer group'",
    ),
    _RewriteRule(
        re.compile(r"\bpriority\s+lever\b", re.IGNORECASE),
        "priority move",
        "R6_jargon",
        "S1: 'priority lever' -> 'priority move'",
    ),
    _RewriteRule(
        re.compile(r"\bcross[- ]pillar\b", re.IGNORECASE),
        "cross-domain",
        "R6_jargon",
        "S1: 'cross-pillar' -> 'cross-domain'",
    ),
    _RewriteRule(
        re.compile(r"\bthe\s+pillar\b", re.IGNORECASE),
        "the area",
        "R6_jargon",
        "S1: 'the pillar' -> 'the area'",
    ),
    _RewriteRule(
        re.compile(r"\bsub-?caps\b", re.IGNORECASE),
        "capabilities",
        "R6_jargon",
        "S1: 'subcaps' -> 'capabilities'",
    ),
    _RewriteRule(
        re.compile(r"\bsub-?cap\b(?![\w_])", re.IGNORECASE),
        "capability",
        "R6_jargon",
        "S1: 'subcap' -> 'capability'",
    ),
    _RewriteRule(
        re.compile(r"\bpoorly\b", re.IGNORECASE),
        "narrowly",
        "R2_opportunity_framing",
        "'poorly' -> 'narrowly'",
    ),
    _RewriteRule(
        re.compile(r"\bpoor\b", re.IGNORECASE),
        "limited",
        "R2_opportunity_framing",
        "'poor' -> 'limited'",
    ),
    _RewriteRule(
        re.compile(r"\blags\b", re.IGNORECASE),
        "trails",
        "R2_opportunity_framing",
        "'lags' -> 'trails'",
    ),
    # Deficit phrases the bot/template prose still emits (D2). The brief
    # bans deficit language ("slipping behind / erodes / lags"); these
    # are the residual ones the noun-only rules above miss. Defence-in-
    # depth on the rendered surface -- the deepen_narrative source
    # templates are reframed in tandem. All phrase-only (no anchors),
    # so the anchor-count validator never rejects the rewrite.
    _RewriteRule(
        re.compile(r"\bleft\s+unaddressed\b,?\s*", re.IGNORECASE),
        "",
        "R2_opportunity_framing",
        "Drop 'left unaddressed,' threat clause",
    ),
    _RewriteRule(
        re.compile(r"\bslipping\s+behind\b", re.IGNORECASE),
        "trailing",
        "R2_opportunity_framing",
        "'slipping behind' -> 'trailing'",
    ),
    _RewriteRule(
        re.compile(r"\bslips\s+behind\b", re.IGNORECASE),
        "trails",
        "R2_opportunity_framing",
        "'slips behind' -> 'trails'",
    ),
    _RewriteRule(
        re.compile(r"\bfalling\s+behind\b", re.IGNORECASE),
        "trailing",
        "R2_opportunity_framing",
        "'falling behind' -> 'trailing'",
    ),
    _RewriteRule(
        re.compile(r"\bfalls\s+behind\b", re.IGNORECASE),
        "trails",
        "R2_opportunity_framing",
        "'falls behind' -> 'trails'",
    ),
    _RewriteRule(
        re.compile(r"\berodes\b", re.IGNORECASE),
        "reduces",
        "R2_opportunity_framing",
        "'erodes' -> 'reduces'",
    ),
    _RewriteRule(
        re.compile(r"\beroding\b", re.IGNORECASE),
        "reducing",
        "R2_opportunity_framing",
        "'eroding' -> 'reducing'",
    ),
    _RewriteRule(
        re.compile(r"\berode\b", re.IGNORECASE),
        "reduce",
        "R2_opportunity_framing",
        "'erode' -> 'reduce'",
    ),
    _RewriteRule(
        re.compile(r"\bwidens\s+the\s+gap\b", re.IGNORECASE),
        "leaves a gap",
        "R2_opportunity_framing",
        "'widens the gap' -> 'leaves a gap'",
    ),
    _RewriteRule(
        re.compile(r"\bholding\s+back\b", re.IGNORECASE),
        "limiting",
        "R2_opportunity_framing",
        "'holding back' -> 'limiting'",
    ),
    _RewriteRule(
        re.compile(r"\bheld\s+back\b", re.IGNORECASE),
        "limited",
        "R2_opportunity_framing",
        "'held back' -> 'limited'",
    ),
    # ── R3 -- Word economy ─────────────────────────────────────────
    _RewriteRule(
        re.compile(r"\bthere\s+are\s+a\s+number\s+of\b", re.IGNORECASE),
        "there are",
        "R3_word_economy",
        "'there are a number of' -> 'there are'",
    ),
    _RewriteRule(
        re.compile(r"\ba\s+number\s+of\b", re.IGNORECASE),
        "several",
        "R3_word_economy",
        "'a number of' -> 'several'",
    ),
    _RewriteRule(
        re.compile(r"\bsignificantly\b", re.IGNORECASE),
        "notably",
        "R3_word_economy",
        "'significantly' -> 'notably' (numeric delta preferred)",
    ),
    _RewriteRule(
        re.compile(r"\bsignificant\b", re.IGNORECASE),
        "material",
        "R3_word_economy",
        "'significant' -> 'material' (numeric delta preferred)",
    ),
    _RewriteRule(
        re.compile(r"\bvarious\b", re.IGNORECASE),
        "multiple",
        "R3_word_economy",
        "'various' -> 'multiple'",
    ),
    # ── R1 -- Hedging ──────────────────────────────────────────────
    _RewriteRule(
        re.compile(r"\bmay\s+be\s+some\b", re.IGNORECASE),
        "may be",
        "R1_no_hedging",
        "'may be some' -> 'may be'",
    ),
    _RewriteRule(
        re.compile(r"\bpotentially\b", re.IGNORECASE),
        "",
        "R1_no_hedging",
        "Drop 'potentially' -- claim or omit",
    ),
    _RewriteRule(
        re.compile(r"\bit\s+seems\b", re.IGNORECASE),
        "evidence shows",
        "R1_no_hedging",
        "'it seems' -> 'evidence shows'",
    ),
    _RewriteRule(
        re.compile(r"\bit\s+appears\b", re.IGNORECASE),
        "evidence shows",
        "R1_no_hedging",
        "'it appears' -> 'evidence shows'",
    ),
    _RewriteRule(
        re.compile(r"\bappears\s+to\s+be\b", re.IGNORECASE),
        "is",
        "R1_no_hedging",
        "'appears to be' -> 'is'",
    ),
    _RewriteRule(
        re.compile(r"\bappears\s+to\b", re.IGNORECASE),
        "is",
        "R1_no_hedging",
        "'appears to' -> 'is'",
    ),
    # ── R4 -- Jargon ───────────────────────────────────────────────
    _RewriteRule(
        re.compile(r"\bAPI\s+error\b"),
        "integration error",
        "R4_no_jargon",
        "'API error' -> 'integration error'",
    ),
    _RewriteRule(
        re.compile(r"\bHTTP\s+(\d{3})\b"),
        r"service error (code \1)",
        "R4_no_jargon",
        "'HTTP 500' -> 'service error (code 500)'",
    ),
    _RewriteRule(
        re.compile(r"\bJWT\s+expired\b", re.IGNORECASE),
        "session expired",
        "R4_no_jargon",
        "'JWT expired' -> 'session expired'",
    ),
    _RewriteRule(
        re.compile(r"\bstack\s+trace\b", re.IGNORECASE),
        "error log",
        "R4_no_jargon",
        "'stack trace' -> 'error log'",
    ),
    # ── R5 -- No apologies ─────────────────────────────────────────
    _RewriteRule(
        re.compile(r"\bunfortunately,?\s*", re.IGNORECASE),
        "",
        "R5_no_apologies",
        "Drop 'unfortunately'",
    ),
    _RewriteRule(
        re.compile(r"\bapologies\b", re.IGNORECASE),
        "",
        "R5_no_apologies",
        "Drop 'apologies'",
    ),
    _RewriteRule(
        re.compile(r"\boops\b[\.\!,]?", re.IGNORECASE),
        "",
        "R5_no_apologies",
        "Drop 'oops'",
    ),
    _RewriteRule(
        re.compile(r"\b(?:we'?re\s+)?sorry\b[\.\!,]?", re.IGNORECASE),
        "",
        "R5_no_apologies",
        "Drop 'sorry' / 'we're sorry'",
    ),
    # ── R6 -- Passive voice ─────────────────────────────────────────
    _RewriteRule(
        re.compile(
            r"\bThis\s+report\s+was\s+generated\s+by\s+(.+?)\b", re.IGNORECASE,
        ),
        r"\1 generated this report",
        "R6_active_voice",
        "'This report was generated by X' -> 'X generated this report'",
    ),
)


@dataclass
class RewriteResult:
    """Outcome of a rewrite pass.

    Fields:
      rewritten_text     -- the rewritten content (or source unchanged
                            when no_change_needed / validator_rejected).
      source_text        -- the original input (kept for caller's
                            fallback path).
      state              -- 'applied' | 'no_change_needed' |
                            'validator_rejected' | 'empty_input'.
      applied_rules      -- ordered list of rule_ids that fired (with
                            duplicates -- one entry per match).
      validation_passed  -- True when every anchor in source appears
                            in the rewrite (same count). False when
                            an anchor was dropped.
      dropped_anchors    -- anchors lost during the rewrite (empty
                            when validation_passed=True).
      source_hash        -- SHA256 of source_text; cache key + audit.
    """

    rewritten_text: str
    source_text: str
    state: str
    applied_rules: list[str] = field(default_factory=list)
    validation_passed: bool = True
    dropped_anchors: list[str] = field(default_factory=list)
    source_hash: str = ""


def rewrite_text(source: str) -> RewriteResult:
    """Apply the rule set to ``source``; preserve anchors verbatim.

    Pure-function. Safe to call on any input including None / "". The
    caller decides whether to serve the rewritten text or fall back
    to source via ``state`` + ``validation_passed``.
    """
    if not source or not isinstance(source, str) or not source.strip():
        return RewriteResult(
            rewritten_text=source or "",
            source_text=source or "",
            state="empty_input",
            source_hash=hashlib.sha256((source or "").encode("utf-8")).hexdigest(),
        )

    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    rewritten = source
    applied: list[str] = []
    for rule in _RULES:
        rewritten_after, n_subs = rule.pattern.subn(rule.replacement, rewritten)
        if n_subs:
            applied.extend([rule.rule_id] * n_subs)
            rewritten = rewritten_after
    # Collapse double spaces introduced by deletions (e.g.
    # "potentially " -> ""). Preserve leading/trailing spaces around
    # punctuation that ',' / '.' would otherwise leave dangling.
    rewritten = re.sub(r"\s{2,}", " ", rewritten)
    rewritten = re.sub(r"\s+([.,;:!?])", r"\1", rewritten)
    rewritten = re.sub(r"\(\s+", "(", rewritten)
    rewritten = re.sub(r"\s+\)", ")", rewritten)
    rewritten = rewritten.strip()

    if not applied:
        return RewriteResult(
            rewritten_text=source,
            source_text=source,
            state="no_change_needed",
            source_hash=source_hash,
        )

    # Validator: every anchor in source must appear in the rewrite at
    # the same count. Drop = validator_rejected; caller serves source.
    diff = _anchor_count_diff(source, rewritten)
    dropped: list[str] = []
    for anchor, (src_n, rew_n) in diff.items():
        if rew_n < src_n:
            dropped.extend([anchor] * (src_n - rew_n))
    if dropped:
        return RewriteResult(
            rewritten_text=source,    # safe fallback
            source_text=source,
            state="validator_rejected",
            applied_rules=applied,
            validation_passed=False,
            dropped_anchors=sorted(set(dropped)),
            source_hash=source_hash,
        )
    return RewriteResult(
        rewritten_text=rewritten,
        source_text=source,
        state="applied",
        applied_rules=applied,
        validation_passed=True,
        source_hash=source_hash,
    )


def is_rewrite_safe(source: str, rewritten: str) -> bool:
    """Standalone safety check -- True iff every anchor preserved."""
    diff = _anchor_count_diff(source or "", rewritten or "")
    return all(rew_n >= src_n for src_n, rew_n in diff.values())


def applied_rule_summary(result: RewriteResult) -> dict[str, int]:
    """Per-rule fire count for the audit pipeline."""
    out: dict[str, int] = {}
    for r in result.applied_rules:
        out[r] = out.get(r, 0) + 1
    return out
