"""Shared narrative hygiene — strip internal jargon / raw taxonomy codes
from user-facing narrative text.

Centralised so EVERY surface scrubs identically: the generators
(`scripts.deepen_narrative`) clean text by construction, and the
serve-time narrative builders (`services.section_routing`) scrub
whatever older generators left behind. A stakeholder must never see
`P#C#` codes, `E-###` evidence ids, M-band shorthand ("M3"), the
"subcap" / "pillar" consultant-speak, the "Severity-to-Maturity Cap
Matrix" methodology label, or the internal "*Derived from extracted
scores*" provenance footer.

Two entry points:
  - ``plain(s)``     — single-line scrub (insight-card WHAT/WHY/SO-WHAT
                       and other short fields); collapses ALL whitespace.
  - ``scrub_md(s)``  — markdown-safe scrub (multi-paragraph section
                       bodies: per_pillar / issue_register / scqa);
                       preserves newline structure + strips the
                       internal provenance footer.
"""
from __future__ import annotations

import re

# jargon / raw-taxonomy-code → plain language. Order matters: the
# specific rules (e.g. "Level: M3", "Pillar Score") run BEFORE the
# generic band/word rules so they win the rewrite.
_JARGON_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\s*\(P[1-4]C\d+(?:[._]\w+)*\)", re.I), ""),
    (re.compile(r"\bE-\d{2,}(?:_[A-Za-z0-9]+)*", re.I), ""),           # inline evidence-id tokens
    (re.compile(r"\bREC-\d+\s*\(([^)]+)\)", re.I), r"\1"),             # "REC-02 (Data Cloud)" -> "Data Cloud"
    (re.compile(r"\b(?:REC|REQ)-\d+\b", re.I), ""),                    # bare recommendation/request ids
    # Pipeline run/request IDs are internal artifacts — never client-facing
    # (2026-07-14 verbatim vet: analyst DOCX bodies cite the research run-id
    # as provenance — "borrowed from … (DMA-RES-GRATE-20260415-0001, §3)").
    # A parenthetical that carries a run-id exists only to cite it, so drop
    # the whole wrapper; a bare token elsewhere is stripped and the repair
    # passes clean the residue. Case-SENSITIVE uppercase so ordinary prose
    # ("DMA-driven", "DMA-based") can never match.
    (re.compile(r"\([^()]*DMA-[A-Z]{2,4}-[A-Z0-9-]+[^()]*\)"), ""),
    (re.compile(r"\bDMA-[A-Z]{2,4}(?:-[A-Z0-9]+)+\b"), ""),
    (re.compile(r"\bREQ-[A-F0-9]{6,}\b", re.I), ""),                   # REQ-{hex} request ids
    # Internal scaffolding / methodology codes that leak into card + focus text
    # (plan S1): URF unit-reference codes, F-## focus-KPI labels, the
    # "Recommended move/play:" stub prefix, the "targets N capabilities" count
    # clause, and the trailing "— CRITICAL/HIGH/MEDIUM/LOW" severity tail.
    # "capped level 3 per ISS-002 MATERIAL" -> "capped level 3": the
    # issue-register reference + its severity tag are internal traceability,
    # not client-facing prose (2026-07-13 corpus QA, CalPrivate cards)
    (re.compile(r"\s*\bper\s+(?:URF|ISS|REQ|QA)-[\dA-Z-]+"
                r"(?:\s+(?:MATERIAL|MINOR|MAJOR|MODERATE|CRITICAL))?", re.I), ""),
    (re.compile(r"\b(?:URF|ISS|REQ|QA)-\d+(?:-\d+)*"
                r"(?:\s+(?:MATERIAL|MINOR|MAJOR|MODERATE))?\b", re.I), ""),
    (re.compile(r"\bF-\d{2,}\b"), ""),
    (re.compile(r"\bRecommended (?:move|play):\s*", re.I), ""),
    (re.compile(r"\b(?:this recommendation\s+)?targets?\s+\d+\s+capabilit(?:y|ies)",
                re.I), "targets the mapped capabilities"),
    (re.compile(r"\s*[\u2014\u2013-]\s*(?:CRITICAL|HIGH|MEDIUM|LOW)\b"), ""),
    (re.compile(r"(?<![A-Za-z])P[1-4]C\d+(?:[._][A-Za-z0-9]+)*", re.I), ""),  # codes even after _/.
    # PLURAL first (same \b-mid-word trap as the "pillars" rule below): the
    # singular rule's trailing \b can't fire inside "subcaps", so a dedicated
    # plural rule keeps the scrubber a superset of the jargon gate.
    (re.compile(r"\bsub-?caps\b", re.I), "capabilities"),
    (re.compile(r"\bsub-?cap(?:abilit(?:y|ies))?\b", re.I), "capability"),
    # Methodology / structured-stub labels that leak into section bodies.
    # No leading article in the replacement — the source text usually
    # already has one ("through THE Severity-to-Maturity Cap Matrix"), so
    # adding another would double it ("the the").
    (re.compile(r"\bSeverity[- ]to[- ]Maturity Cap Matrix\b", re.I),
     "assessment's scoring methodology"),
    (re.compile(r"\bLevel:\s*M([1-5])\b"), r"maturity level \1"),      # before the generic M-band rule
    (re.compile(r"\bPillar Weight\b", re.I), "Weighting"),
    (re.compile(r"\bPillar Score\b", re.I), "Score"),
    (re.compile(r"peer[- ]cohort median", re.I), "the typical score for comparable institutions"),
    (re.compile(r"\bpeer[- ]cohort\b", re.I), "peers"),
    (re.compile(r"\bcohort median\b", re.I), "the peer benchmark"),
    (re.compile(r"cross[- ]pillar dependencies", re.I), "the other capabilities that build on it"),
    (re.compile(r"\bcross[- ]pillar\b", re.I), "connected"),
    (re.compile(r"\bthe most direct lever\b", re.I), "the most direct way"),
    (re.compile(r"\bpriority lever\b", re.I), "priority"),
    (re.compile(r"\blever to lift\b", re.I), "way to raise"),
    (re.compile(r"\blever for\b", re.I), "opportunity for"),
    (re.compile(r"\bM5 best-in-class bar\b", re.I), "the top maturity level"),
    (re.compile(r"\bbest-in-class bar\b", re.I), "best-in-class level"),
    # PLURAL first — the completeness-contract insight_jargon regex flags
    # `the pillar` as a raw substring, so it ALSO fires on "the pillars"
    # ("…compounds across the pillars it feeds"). The singular `\bthe pillar\b`
    # rule below can't strip the plural (its trailing \b fails before the "s"),
    # so a generic `\bpillars\b` rule keeps the scrubber a SUPERSET of the
    # contract — anything that passes plain()/scrub_md() also passes the gate.
    (re.compile(r"\bpillars\b", re.I), "areas"),
    (re.compile(r"\bthe pillar's\b", re.I), "this area's"),
    (re.compile(r"\bthis pillar's\b", re.I), "this area's"),
    (re.compile(r"\bthe pillar\b", re.I), "this area"),
    (re.compile(r"\bthis pillar\b", re.I), "this area"),
    (re.compile(r"\bcomposite score\b", re.I), "overall score"),
    (re.compile(r"\bM([1-5])\b"), r"level \1"),
]

# Internal provenance footer the DERIVED-tier SCQA appends — must never
# reach a user-facing surface.
_PROVENANCE_FOOTER_RE = re.compile(
    r"\n*\*+\s*Derived from extracted scores[^\n]*", re.I
)

# ── Pipeline PROCESS scaffolding (2026-07-14 verbatim vet) ───────────────────
# Analyst DOCX section bodies (benchmark / issue-register / trend /
# recommendations) are served largely as pass-through. They carry
# pipeline-internal notes a client must NEVER see: data-borrowing
# disclaimers, QA-protocol banners ("Anti-Generic Protocol", "0 forbidden
# phrases", "Vibe Prospecting match + Exa search"), provenance citations
# ("borrowed from the Research Report per the Data Borrowing Protocol"),
# and structural labels ("[ROOT CAUSE — SITUATION]"). A SENTENCE dominated
# by one of these markers is dropped whole; a mixed sentence keeps its
# substance with only the process CLAUSE removed (see
# ``_strip_process_scaffolding``). The markers are high-confidence internal
# strings, so an emptied body was genuinely all-scaffolding — the builder's
# ``or None`` then falls back to the skeleton, which is correct.
_PROCESS_SENTENCE_RE = re.compile(
    r"(?:"
    r"data[- ]borrowing protocol"
    r"|anti[- ]generic"                                  # any "anti-generic …" banner
    r"|forbidden phrase"
    r"|specificity test applied"
    # Pipeline QA/process phrases — unambiguously internal (never appear in a
    # substantive client-facing fact), so safe to drop whole. Bare enrichment
    # TOOL names (LeadIQ / Explorium / ZoomInfo / technographic) are NOT here:
    # they appear inside substantive technographic FACTS ("HubSpot confirmed
    # (LeadIQ T3 source) — provides CRM"), where a whole-sentence drop would
    # destroy real content. The methodology PREAMBLES that cite those tools are
    # caught by the structural markers below (all-N-recommendations, when-not-
    # to-recommend, N-factor-framework, …) without needing the tool name.
    r"|vibe prospecting"
    r"|exa search"
    r"|connector validation"
    # methodology framing that precedes a recommendation / gap table
    r"|\d+[- ]solution catalog"
    r"|\d+[- ]factor (?:scoring|priority) framework"
    r"|prioriti[sz]ed\s+(?:using|based on)\s+(?:the\s+)?\d+[- ]factor"
    r"|gaps?\s+were\s+prioriti[sz]ed"
    r"|\d+[- ]gate validation"
    r"|validation protocol"
    r"|mandatory protocol"
    r"|peer set is immutable"
    r"|immutable\s+(?:per protocol|throughout|for the)"
    r"|\beach maps to\b[^.]*\bzennify\b"
    r"|when not to recommend"
    r"|each recommendation\s+(?:traces|includes|follows|maps|satisfies)"
    r"|\beach traces to\b"
    r"|the following\s+\d*\s*recommendations"
    r"|recommendations?\s+(?:satisfy|passed the|are evidence-grounded|derived from"
    r"|maps? to|confirmed absent|(?:have\s+been\s+|been\s+|are\s+)?validated)"
    r"|all\s+\d+\s+recommendations"                      # "All 8 recommendations …" (aggregate meta)
    r"|\btag applied\b|internal discovery prerequisite"
    r"|derived from the gap prioriti"
    # investment / sizing disclaimers (kept out of every client surface by
    # policy). Anchored on the disclaimer lead-in ("No investment amounts …")
    # so a legitimate sentence that merely mentions cost/ROI is untouched.
    r"|(?:no|zero)\s+investment amounts"
    r"|engagement sizing is handled"
    r"|per (?:assessment policy|R\d+ rule|(?:the\s+)?zennify dma framework)"
    r"|caps are immutable"
    r"|issues are borrowed"
    r"|assessment[- ]layer\s+(?:\w+\s+){0,3}annotations?\s+(?:added|applied)"
    r"|(?:borrowed|drawn)\s+(?:and\s+annotated\s+)?from\b[^.]*?research report"
    r"|this section is borrowed"
    r"|enriched with\s+(?:layer\s*\d+\s+)?(?:assessment\s+)?scoring impact"
    r"|^\s*legend\b"
    r")", re.I | re.M)

# Process CLAUSES stripped from an otherwise-substantive sentence (the
# sentence carries real content, only the meta-clause is internal).
_PROCESS_CLAUSE_SUBS: list[tuple[re.Pattern[str], str]] = [
    # "… locked in research Phase 0", "… and locked in Research Phase
    # (Batch 1)", "… in Research Phase (Batch 1):" — a provenance clause on an
    # otherwise-substantive peer-set sentence; strip the clause, keep the peers.
    (re.compile(r"\s*(?:and\s+)?(?:lock(?:ed|ing)?\s+)?(?:in|during)\s+(?:the\s+)?"
                r"research phase(?:\s*\d+)?(?:\s*\(batch\s*\d+\))?", re.I), ""),
    (re.compile(r"\s*\bidentified during the research phase\b", re.I), ""),
    (re.compile(r"\s*\bper (?:the\s+)?(?:phase\s*\d+\s+)?data[- ]borrowing protocol\b",
                re.I), ""),
    # internal document cross-references ("in Section 6", ", Sections 3.2-3.4")
    (re.compile(r"[,;]?\s*\bin sections?\s+[\d.]+(?:\s*[\u2013\u2014-]\s*[\d.]+)?\b",
                re.I), ""),
]

# Internal bracketed structural / ownership labels ("[ROOT CAUSE —
# SITUATION]", "[ZENNIFY]", "[CLIENT]") — pipeline tags, never client copy.
_INTERNAL_LABEL_RE = re.compile(
    r"\[\s*(?:root cause|situation|complication|question|answer|zennify|"
    r"client|internal|ae|tech validation|strategic alignment)[^\]]*\]", re.I)


def _strip_process_scaffolding(s: str | None) -> str | None:
    """Drop pipeline-internal process scaffolding from an analyst section
    body while preserving analytical substance. Line-by-line then
    sentence-by-sentence: a sentence dominated by a process marker is
    dropped whole; a mixed sentence keeps its substance with only the
    process clause removed. Never raises; returns the input on falsy."""
    if not s:
        return s
    out = _INTERNAL_LABEL_RE.sub("", s)
    kept_lines: list[str] = []
    for line in out.split("\n"):
        if not line.strip():
            kept_lines.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [p for p in parts
                if p.strip() and not _PROCESS_SENTENCE_RE.search(p)]
        new_line = " ".join(kept)
        for pat, repl in _PROCESS_CLAUSE_SUBS:
            new_line = pat.sub(repl, new_line)
        kept_lines.append(new_line)
    return "\n".join(kept_lines)

# ── Opportunity framing (plan S2) ────────────────────────────────────────
# Gaps must read as opportunities; nothing accusatory. The deterministic net
# below is the HARD floor (a gate asserts 0 accusatory phrasings on the served
# pack); the Stage-2 Claude overlay supplies the nuanced, report-grounded copy.
#
# CRITICAL distinction: a RISK/compliance "no X" (no breaches, no enforcement,
# no litigation) is a POSITIVE clean-posture fact — it must NEVER be reframed as
# an opportunity ("opportunity to add data breaches" would be absurd). Those are
# matched first and left intact (only the accusatory "— NONE Identified" tail is
# trimmed). Everything else — a capability/tooling absence — is forward-framed.
_CLEAN_POSTURE_RE = re.compile(
    r"\b(?:no|zero|none|without|nil)\b[^.;:]{0,40}?"
    r"\b(?:breach|incident|enforcement|consent[- ]order|litigation|lawsuit|"
    r"adverse|sanction|violation|fine|penalt|default|complaint|action|"
    r"data\s+loss|outage|fraud\s+event|regulatory\s+record)", re.I)
# Neutral/positive STRATEGY absence — a stated posture, not a capability gap
# ("no M&A interest", "no plans to divest"). Protected like clean-posture.
_NEUTRAL_ABSENCE_RE = re.compile(
    r"\bno\b[^.;:]{0,24}?\b(?:m&a|acquisition|interest|appetite|plans?|"
    r"intention|intent|desire|need)\b", re.I)
# Audit-tone prefixes ("Critical finding:", "CRITICAL:") — drop; severity is a chip.
_AUDIT_PREFIX_RE = re.compile(
    r"(^|[\u2014\u2013|]\s*)(?:critical\s+finding|key\s+finding|critical)\s*:\s*",
    re.I)

# accusatory tail on an otherwise-neutral fact ("… — NONE Identified").
_NONE_TAIL_RE = re.compile(r"\s*[\u2014\u2013-]\s*NONE(?:\s+Identified)?\.?\s*$", re.I)

# Deficit → opportunity rewrites. Order matters (specific → generic). Each keeps
# the SUBJECT and only swaps the accusatory framing verb/quantifier.
_CAP = r"([A-Za-z][\w /&.+-]{1,44}?)"  # a capability / tooling noun phrase
# A clause boundary the "No X …" rules anchor to — start / after . ; : | or an
# em/en-dash. Anchoring keeps them from mangling a mid-sentence "X has no Y"
# subject-verb-object (which needs a full sentence rewrite → the generative
# tier's job, never the regex floor's — a broken/awkward reframe is worse than
# the accusatory original).
_LEAD = r"(^|[.;:]\s|\|\s*|[\u2014\u2013]\s*)"


def _greenfield_or_drop(m: re.Match[str]) -> str:
    """Clause-lead "No X deployed/in place" → "<boundary>X greenfield"; when the
    text already frames it as greenfield just name the capability (avoids
    "greenfield … greenfield" / "Opportunity: X Deployed" awkwardness)."""
    boundary, subject = m.group(1), m.group(2).strip()
    gf = subject if "greenfield" in (m.string or "").lower() else f"{subject} greenfield"
    return f"{boundary}{gf}"


_OPPORTUNITY_SUBS: list[tuple[re.Pattern[str], object]] = [
    # specific tech/AI absences (highest-value, unambiguous). "no/zero AI(/ML)
    # in production" → "an opportunity to move AI/ML into production": grammatical
    # AFTER a possessive verb ("has no AI/ML in production" → "has an opportunity
    # to move AI/ML into production"), so it does NOT invert meaning the way a
    # bare "AI/ML greenfield" swap did. Covers the operator's trend example.
    (re.compile(r"\b(?:no|zero)\s+(AI(?:\s*/\s*ML)?|ML|machine\s+learning)\s+in\s+production\b", re.I),
     lambda m: f"an opportunity to move {m.group(1).strip()} into production"),
    (re.compile(r"\b(?:has\s+)?no\s+(?:formal\s+)?(?:GRC|governance,?\s*risk[, ]*(?:and\s+)?compliance)\b(?:\s+tooling)?", re.I),
     "an opportunity to stand up enterprise governance (GRC) tooling"),
    (re.compile(r"\bno\s+(?:conversational\s+AI|chatbot|virtual\s+assistant)\b", re.I),
     "room to add conversational self-service"),
    # L9 evidence-availability (a disclosure gap, not a capability gap)
    (re.compile(r"\bno\s+(?:direct\s+)?public\s+evidence\s+(?:of|for|surfaced\s+for)\b", re.I),
     "limited public disclosure of"),
    (re.compile(r"\bno\s+(?:direct\s+)?public\s+evidence\b", re.I),
     "limited public disclosure"),
    (re.compile(r"\bno\s+public\s+", re.I), "limited public "),
    # L2 clause-lead "No X deployed / in place / present / in production" →
    # "X greenfield" (lead-anchored so "BOKF has no X in production" is left).
    (re.compile(_LEAD + r"no\s+" + _CAP +
                r"\s+(?:is\s+|are\s+)?(?:deployed|in[- ]place|present|in\s+production)\b", re.I),
     _greenfield_or_drop),
    # L8 tooling scans: "with no X detected" (grammatical mid-sentence) + a
    # clause-lead bare "No X detected".
    (re.compile(r"\bwith\s+no\s+([A-Za-z][\w /&.,+-]{1,70}?)\s+detected\b", re.I),
     r"with \1 as a greenfield opportunity"),
    (re.compile(_LEAD + r"no\s+([A-Za-z][\w /&.,+-]{1,70}?)\s+detected\b", re.I),
     r"\1\2 not yet in place"),
    (re.compile(r"\bwith\s+NO\s+" + _CAP), r"with \1 as an opportunity"),
    # L3 "zero X" → greenfield (the WORD zero only, never the digit 0, and never
    # inside a hyphenated term like "net-zero").
    (re.compile(r"(?<![-\w])(?<!has )(?<!have )zero\s+" + _CAP, re.I), r"a greenfield \1"),
    # L5/L6/L7 deficit verbs
    (re.compile(r"\b(?:currently\s+)?lacks?\s+", re.I), "has headroom to build out "),
    (re.compile(r"\b(?:is\s+)?lacking\s+(?:in\s+)?", re.I), "has headroom in "),
    (re.compile(r"\black\s+of\s+", re.I), "the opportunity in "),
    (re.compile(r"\b(?:is\s+|are\s+)?(?:currently\s+)?absent\b", re.I), "is a near-term opportunity"),
    (re.compile(r"\bis\s+missing\b", re.I), "is not yet in place"),
    (re.compile(r"\bare\s+missing\b", re.I), "are not yet in place"),
    (re.compile(r"\bfail(?:s|ing)?\s+to\s+", re.I), "has not yet "),
    (re.compile(r"\bdoes\s+not\s+(?:yet\s+)?", re.I), "has not yet "),
    (re.compile(r"\b(?:is\s+|are\s+)?unable\s+to\s+", re.I), "is not yet able to "),
    (re.compile(r"\bcannot\s+", re.I), "is not yet able to "),
    # L4 "X without Y" at clause end → "X; Y is the next opportunity"
    (re.compile(r"\s+without\s+(?:a\s+|an\s+)?([\w /&.+-]{3,44})\s*$", re.I),
     r"; \1 is the next opportunity"),
    # L10 deficit adjectives
    (re.compile(r"\b(?:is\s+|are\s+)?(?:weak|immature|nascent|rudimentary)\b", re.I),
     "is an emerging capability with room to mature"),
    (re.compile(r"\bdeficient\b", re.I), "below benchmark"),
    (re.compile(r"\bpoorly\b", re.I), "narrowly"),
    (re.compile(r"\bpoor\b", re.I), "limited"),
    # Bare "No <Capability>" lead (title/clause start, incl. after an em-dash)
    # → opportunity framing. Capitalized-only so a lowercase mid-sentence "no"
    # (which may be a clean-posture fact this pass can't disambiguate) is left
    # for the report-grounded Stage-2 overlay.
    (re.compile(r"(^|[.;:]\s|\|\s*|[\u2014\u2013]\s*|,\s+)No\s+(?=[A-Z])"), r"\1Opportunity: "),
]


def opportunity_reframe(s: str | None) -> str | None:
    """Reframe accusatory/deficit phrasing as forward-looking opportunity
    language (plan S2), WITHOUT touching risk/compliance clean-posture facts.
    Idempotent and citation-safe (operates on prose, never inside [E-###]).
    Returns the input unchanged when it carries no accusatory phrasing."""
    if not s or not s.strip():
        return s
    # Protect clean-posture positives + neutral strategy absences as SPANS so a
    # MIXED sentence still reframes its capability gap while leaving the positive
    # intact (a whole-string skip used to leave "No integration layer; no
    # breaches on record" fully accusatory).
    protected: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        protected.append(m.group(0))
        return f"\x00CP{len(protected) - 1}\x00"

    out = _CLEAN_POSTURE_RE.sub(_protect, s)
    out = _NEUTRAL_ABSENCE_RE.sub(_protect, out)
    out = _NONE_TAIL_RE.sub("", out)
    out = _AUDIT_PREFIX_RE.sub(r"\1", out)
    for pat, repl in _OPPORTUNITY_SUBS:
        out = pat.sub(repl, out)
    for i, span in enumerate(protected):
        out = out.replace(f"\x00CP{i}\x00", span)
    # tidy doubled article / greenfield / dangling space the swaps introduced
    out = re.sub(r"\b(the|a|an)\s+\1\b", r"\1", out, flags=re.I)
    out = re.sub(r"(?i)\bgreenfield\b(?:\s+\S+){0,3}?\s+\bgreenfield\b", "greenfield", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    return out.strip() or s


# Markdown emphasis (**bold**, __bold__, *italic*) leaks from LLM/analyst prose
# into fields the UI renders as RAW TEXT (there is no markdown renderer), so it
# surfaces as literal asterisks on cards / why-now / conversation-starters
# (2026-07-09 QA). Strip the emphasis markers, keep the inner text. Single "_"
# is left alone (it collides with snake_case ids / URLs); "**", "__" and a
# standalone "*" cover the reported leak.
_EMPHASIS_PAIR_RE = re.compile(r"\*\*([^*\n]+?)\*\*|__([^_\n]+?)__")
_EMPHASIS_STAR_RE = re.compile(r"(?<!\w)\*([^*\n]+?)\*(?!\w)")


def strip_md_emphasis(s: str) -> str:
    """Remove markdown emphasis markers (keeping the inner text). Structural
    markdown (headings, list bullets) is left untouched — only emphasis, which
    is what leaks as literal ``**`` in the raw-text UI."""
    out = _EMPHASIS_PAIR_RE.sub(lambda m: m.group(1) or m.group(2), s)
    return _EMPHASIS_STAR_RE.sub(r"\1", out)


def plain(s: str | None) -> str:
    """Strip internal jargon / raw taxonomy codes from a SHORT user-facing
    string. Collapses all whitespace — do NOT use on multi-paragraph
    markdown (use ``scrub_md``).

    Citation handling mirrors ``scrub_md`` (2026-07-06 deploy review:
    card WHAT/WHY shipped "[, ]" / "(, " / ".." debris): bracketed chips
    ("[E-059, E-079]") and report-style paren citations ("(E-002, AM
    Best, T1)") are deliberate grounding — protected verbatim; only BARE
    inline E-ID tokens are stripped, and the repair passes clean up any
    separator shells stripping leaves behind."""
    out = s or ""
    _cites: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        _cites.append(m.group(0))
        return f"\x00CITE{len(_cites) - 1}\x00"

    out = re.sub(
        r"\[[^\[\]]*\b(?:EV|INT|E)-[A-Za-z0-9][^\[\]]*\]"
        r"|\([^()]*\b(?:EV|INT|E)-\d[^()]*\)",
        _protect, out)
    for pat, repl in _JARGON_SUBS:
        out = pat.sub(repl, out)
    for i, cite in enumerate(_cites):
        out = out.replace(f"\x00CITE{i}\x00", cite)
    # A RAW taxonomy code that rode INSIDE a protected citation survives the
    # jargon subs above ("(E-006:F5 re-mapped to P3C1)" — the paren is kept
    # for its E-006 id, but P3C1 is stakeholder jargon). Strip the standalone
    # code now, guarding on a preceding '-' so an E-ID whose own id encodes the
    # pillar (E-P3C4-008 / EV-P2C1) is preserved intact.
    out = re.sub(r"(?<![-A-Za-z0-9])P[1-4]C\d+(?:[._][A-Za-z0-9]+)*", "", out)
    # Shells left by token removal: "()", "(, )", "[ ; ]" — drop whole;
    # partial residue "(, X)" / "(X, )" — trim the dangling separator.
    out = re.sub(r"[(\[]\s*[,;\s]*[)\]]", "", out)
    out = re.sub(r"\(\s*[,;]+\s*", "(", out)
    out = re.sub(r"\s*[,;]+\s*\)", ")", out)
    # A connector word left dangling because the run-id it introduced was
    # stripped ("scores 1/5 on this run per ." → "…on this run.").
    out = re.sub(r"\s+\b(?:per|from|see|cf\.?|ref|via)\b\s*(?=[.;:,)\]]|$)",
                 "", out, flags=re.I)
    out = re.sub(r"\b(the|a|an)\s+\1\b", r"\1", out, flags=re.I)
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    out = re.sub(r",\s*\.", ".", out)
    # ".." / ",," left when a stripped token sat between two stops.
    out = re.sub(r"([.,;:])(?:\s*\1)+", r"\1", out)
    out = strip_md_emphasis(out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # A trailing dangling separator/dash left when the token it introduced
    # was stripped ("Report Synthesis —" → "Report Synthesis"). Only fires
    # after whitespace so hyphenated words ("well-established") are safe.
    return re.sub(r"\s+[\u2014\u2013,;:-]+$", "", out).strip()


def scrub_md(s: str | None) -> str | None:
    """Scrub a markdown narrative body for serving: apply the jargon subs
    + strip the internal provenance footer, WITHOUT flattening the
    markdown (newlines / paragraph breaks / headings preserved). Returns
    ``None`` for empty/whitespace-only input so a builder's ``or None``
    stays ``None``."""
    if not s:
        return s
    out = _PROVENANCE_FOOTER_RE.sub("", s)
    # Preserve BRACKETED evidence citations ("[E-059, E-079]", "[E-P3C3-003]")
    # verbatim — the AE-facing NarrativeText renders them as clickable evidence
    # chips (AE-depth contract 2026-07-02). Only BARE inline E-ID tokens in
    # prose are jargon and get stripped by _JARGON_SUBS below. Protect the
    # bracket groups with placeholders across the sub loop, then restore.
    _cites: list[str] = []

    def _protect(m: re.Match[str]) -> str:
        _cites.append(m.group(0))
        return f"\x00CITE{len(_cites) - 1}\x00"

    # Bracketed chips ("[E-059, E-079]") AND report-style parenthetical
    # citations ("(E-002, AM Best, T1)") are deliberate grounding — preserve
    # both. The paren pattern requires E-<digit> so it can never swallow
    # "(E-commerce)" / "(E-signature)". Only truly BARE inline E-ID tokens in
    # prose remain jargon and get stripped by _JARGON_SUBS below.
    # Match the FULL E-ID grammar (E-, EV-, INT-, incl. connector forms like
    # EV-P2C4-013 / EV-CONN-001) — not just the bare "E-" prefix. The old
    # "\bE-" only recognised E-NNN citations, so a bracket citing ONLY the
    # EV-/INT- connector form went unprotected and the subcap-id jargon sub
    # stripped its middle segment ("EV-P2C4-013" → "EV--013"), corrupting a
    # real citation into a dead, un-gradeable chip (2026-07-06 deploy review:
    # empower's exec summary under-cited + ",," debris traced here).
    out = re.sub(
        r"\[[^\[\]]*\b(?:EV|INT|E)-[A-Za-z0-9][^\[\]]*\]"
        r"|\([^()]*\b(?:EV|INT|E)-\d[^()]*\)",
        _protect, out)
    for pat, repl in _JARGON_SUBS:
        out = pat.sub(repl, out)
    for i, cite in enumerate(_cites):
        out = out.replace(f"\x00CITE{i}\x00", cite)
    # Drop pipeline-internal process scaffolding (provenance citations,
    # QA-protocol banners, data-borrowing disclaimers, structural labels)
    # AFTER jargon subs have already stripped the run-id tokens they cite,
    # so an emptied provenance sentence collapses cleanly.
    out = _strip_process_scaffolding(out) or ""
    # A paren/bracket left holding only separators after token removal
    # ("(E-091, E-099)" → "(, )", "[P3C1.6.1]" → "[]") is dropped entirely.
    out = re.sub(r"\(\s*[,;\s]*\)", "", out)
    out = re.sub(r"\[\s*[,;\s]*\]", "", out)
    # A clause-lead separator left when a run-id paren was dropped from the
    # head of a sentence ("Peer set  , Section" → "Peer set"): trim a
    # dangling leading separator inside what remains.
    out = re.sub(r"\(\s*[,;]+\s*", "(", out)
    out = re.sub(r"\s*[,;]+\s*\)", ")", out)
    # A connector word left dangling at a clause/sentence end because the
    # run-id it introduced was stripped ("scores 1/5 on this run per ." →
    # "scores 1/5 on this run.").
    out = re.sub(r"\s+\b(?:per|from|see|cf\.?|ref|via)\b\s*(?=[.;:,)\]\n]|$)",
                 "", out, flags=re.I)
    # A removed token can leave a doubled article ("the the", "a a") —
    # collapse it (case-insensitive on the first, preserve the second).
    out = re.sub(r"\b(the|a|an)\s+\1\b", r"\1", out, flags=re.I)
    out = re.sub(r"[ \t]+([.,;:])", r"\1", out)
    # A stripped bare-ID list ("— P3C4.2.1, P3C4.3.1, P3C4.4.1") leaves comma
    # debris ("— , ,") the jargon subs don't own. Collapse doubled inline
    # separators, then drop a dash/em-dash that now leads only into separators
    # before a closing quote / newline / EOL (2026-07-06 deploy review:
    # empower's exec summary shipped a "—,," from a subcap-id list stripped out
    # of a focus quote — horizontal-space classes only, never touch newlines).
    out = re.sub(r"([,;:])(?:[ \t]*\1)+", r"\1", out)
    out = re.sub(r"[ \t]*[\u2014\u2013-][ \t]*(?:[,;][ \t]*)+"
                 r"(?=[\"'\u201d\u2019\n]|$)", "", out)
    out = re.sub(r"[ \t]+([.,;:])", r"\1", out)
    # Pipe-table cleanup BEFORE the whitespace cleanup, so removing a
    # trailing/empty pipe can't leave a dangling space that only a 2nd
    # pass would catch (kept the scrub idempotent). Horizontal-only
    # whitespace classes throughout — never join or collapse newlines.
    out = re.sub(r"\|[ \t]*\|", "|", out)
    out = re.sub(r"\|[ \t]*$", "", out, flags=re.M)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+$", "", out, flags=re.M)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = strip_md_emphasis(out)
    return out.strip() or None
