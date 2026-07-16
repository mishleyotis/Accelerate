"""AE-readability rubric + markdown lint — "quality only ships".

Why: the SCQA/insight audits measured 97-98% template prose, 92/94
zero-citation narratives, "(: 1.68" label artifacts and 31K-char report
dumps. :func:`rubric_score` is the deterministic floor of the
self-improvement loop (plan Part 2): review agents run it during
convergence, and every failure becomes a registry rule plus a regression
fixture under ``tests/fixtures/nlp_cases/``. Five dimensions, each
0-1:

- specificity — named entities + numbers per 100 words
- grounding   — E-ID citations vs claim count (out-of-scope IDs flagged)
- filler      — template-phrase blacklist (any hit fails the gate)
- coherence   — numbers in the text must sit within tolerance of the
  caller-supplied in-scope numbers (±15%)
- actionability — imperative / next-step presence
- incorporation — every cited E-ID whose excerpt the caller supplies must
  share ≥3 significant tokens with the sentence it is cited in. A score-
  template sentence with an E-ID stapled on the end (the 2026-07-06
  citation-washing class — 31.4% of cards) scores 0 here even though the
  bare-grounding count reads 1.0. Defaults to 1.0 when no excerpts are
  supplied, so existing callers are unaffected.
- score_echo — 1 minus (score-restatement sentences / total). A "sits N/5,
  M points below the peer median … progress compounds" sentence with no
  evidence-derived fact ($/%/date/vendor) is a score restatement. Only
  gates ``pass`` when ``enforce_score_echo=True`` (the insight-card /
  finding persist paths); always reported.

``pass`` requires every gating score ≥ 0.5 AND zero filler hits.
:func:`markdown_lint` flags the presentation artifacts the audits
found shipping to AEs.
"""
from __future__ import annotations

import re
import zlib as _zlib
from collections.abc import Iterable, Mapping

from app.services.nlp.entities import extract
from app.services.nlp.segment import sentences

# Template families measured in the audits — any hit is an automatic fail.
_FILLER_PHRASES = (
    "points to meaningful room",
    "targeted programme to close the gap",
    "targeted program to close the gap",
    "binding constraint on",
    "clear headroom to move toward best practice",
    "pending analyst synthesis",
    "well positioned to capitalize",
)

# Canonical "E-047" plus the corpus's real id variants ("E0001" dash-less,
# "EV-12"/"INT-3" connector ids) — 782/7,203 index rows use them; a grounded
# citation of those rows must count as grounding (2026-07-02).
_EID_RE = re.compile(
    r"\b(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}\b|\bE\d{3,4}\b")
_ACTION_RE = re.compile(
    r"\b(?:should|recommend(?:s|ed|ation)?|next\s+steps?|prioriti[sz]e|must|"
    r"requires?|would\s+enable|we\s+suggest|focus\s+on|invest\s+(?:in|to)|"
    # natural recommendation phrasings the reasoning-layer LLM emits — a
    # synthesized exec summary says "lead with X" / "the recommended play is"
    # / "sequence X first", not always "should X" (2026-07-15: these were
    # scoring actionability=0 and getting the good summary rejected).
    r"lead(?:s|ing)?\s+with|the\s+recommended\s+(?:move|play|path|motion|entry)|"
    r"the\s+(?:play|call|move|recommendation)\s+is|sequenc\w+\s+\w+\s+first|"
    r"\bgo(?:es)?\s+first\b|first\s+move)\b",
    re.IGNORECASE,
)
# A sentence that LEADS with a directive verb is a call to action. Beyond the
# migration verbs, the deterministic so-what composer leads with "Make … a
# focus", "Protect and build on …", "Prioritize …" — all genuine imperatives
# the gate must credit (audit 2026-07-03: 63% of so-what led with an
# unrecognized-but-valid directive).
_IMPERATIVE_LEAD_RE = re.compile(
    r"^(?:Deploy|Implement|Launch|Consolidate|Migrate|Establish|Build|Adopt|"
    r"Pilot|Sequence|Start|Stand\s+up|Close|Extend|Modernize|Make|Protect|"
    r"Prioriti[sz]e|Focus|Invest|Target|Address|Strengthen|Scale|Unlock|"
    r"Accelerate|Reduce|Expand|Automate|Integrate|Replace|Upgrade|Fix)\b"
)

_REL_TOL = 0.15
_ABS_TOL = 0.05

# ── incorporation + score-echo (2026-07-06 anti-shallow gates) ──────────────
# Significant-token overlap between a citing sentence and the evidence excerpt
# it cites — the "did the prose actually USE the evidence, or just staple the
# chip on?" check. Mirrors startup_enrich.significant_tokens (kept local to
# avoid an import cycle: startup_enrich imports this module lazily).
_INCORP_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&/+.-]{2,}")
_INCORP_STOP = frozenset(
    "the a an and or of to in for with on at by from is are was were be been "
    "being this that these those it its as has have had not no but their our "
    "your his her via than then them they will would can could should may "
    "might also into over across more most less least each per within without "
    "about above below other score scores scored scoring point points out "
    "assessment capability institution institutions comparable typically seen "
    "peer median already runs sits below above versus".split())

# A score-restatement sentence: a maturity-score claim wrapped in the
# deterministic template family's generic boilerplate, carrying no
# evidence-derived fact. It must show a score signature AND a template-
# boilerplate phrase — so an evidence-tied score sentence ("that fragmentation
# holds X at 1.8/5, below the 2.6 peer median") is NOT flagged, but the
# diagnosed "sits N points below the M typically seen at comparable
# institutions … progress here compounds" family is. A fact marker
# ($/%/date/vendor) or a quoted excerpt always exempts the sentence.
_SCORE_SIG_RE = re.compile(
    r"\bout of 5\b|\d\s*/\s*5\b|\bpoints?\s+(?:below|above|behind|ahead)\b|"
    r"peer[- ]median|peer[- ]cohort|comparable institutions|typically seen at",
    re.I)
# The template-family phrasings the 2026-07-06 audit measured verbatim across
# 68.8% of card whys — generic filler that never names a client fact.
_SCORE_ECHO_BOILERPLATE_RE = re.compile(
    r"typically seen at comparable institutions|"
    r"progress here compounds|compounds across the rest of the business|"
    r"widest distance to close|\bdistance to close\b|"
    r"reaches well beyond this single capability|"
    r"priority focus for the next phase|"
    r"lower-scoring capabilit|"
    r"strengthening (?:it|this) would deliver|"
    r"an early-stage capability|a developing capability still short|"
    r"keeps? investing so",
    re.I)
_FACT_MARKER_RE = re.compile(
    r"\$|%|\bbps\b|\bQ[1-4]\b|\b(?:19|20)\d\d\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\b|"
    r"\b(?:Salesforce|Databricks|Tableau|Twilio|nCino|MuleSoft|Mulesoft|Oracle|"
    r"Siebel|Episys|Snowflake|Azure|AWS|Power\s?BI|Unity\s?Catalog|Delta\s?Lake|"
    r"SEMCI|ACORD|CDP|CRM|MDM|API|NAIC|NCUA|GLBA|FDIC|OCC|SR\s?11-7|10-?K)\b",
    re.I)
_QUOTE_MARK_RE = re.compile(r"[\"“][^\"”]{15,}")


def _significant_tokens(text: str) -> set[str]:
    return {w for w in _INCORP_TOKEN_RE.findall(str(text or "").lower())
            if len(w) >= 4 and w not in _INCORP_STOP}


def _is_score_restatement(sentence: str) -> bool:
    s = str(sentence or "").strip()
    if _FACT_MARKER_RE.search(s) or _QUOTE_MARK_RE.search(s):
        return False
    if not _SCORE_SIG_RE.search(s):
        return False
    return bool(_SCORE_ECHO_BOILERPLATE_RE.search(s))


def _score_echo_density(sents: list[str]) -> float:
    real = [s for s in sents if s and s.strip()]
    if not real:
        return 0.0
    return sum(1 for s in real if _is_score_restatement(s)) / len(real)


def _text_numbers(text: str) -> list[float]:
    ents = extract(text)
    values: list[float] = []
    for family in ("money", "percents", "cardinals"):
        for item in ents[family]:
            norm = item.get("norm")
            if isinstance(norm, int | float):
                values.append(float(norm))
    # Years are labels, not measurements — do not coherence-check them.
    return [v for v in values if not (v.is_integer() and 1900 <= v <= 2099)]


def _coherent(value: float, scope: list[float]) -> bool:
    return any(
        abs(value - s) <= max(_ABS_TOL, _REL_TOL * max(abs(s), abs(value)))
        for s in scope
    )


def rubric_score(
    text: str,
    evidence_ids: Iterable[str] = (),
    numbers_in_scope: Iterable[float] = (),
    evidence_excerpts: Mapping[str, str] | None = None,
    enforce_score_echo: bool = False,
) -> dict:
    """Score AE-facing prose → ``{scores, pass, flags}``.

    ``evidence_ids``: E-IDs legitimately in scope — cited IDs outside
    this set are flagged (when the set is empty, any citation counts).
    ``numbers_in_scope``: the live values claims must agree with (±15%);
    empty means no coherence constraint.
    ``evidence_excerpts``: ``{eid: excerpt}`` for the cited evidence.
    When supplied, the ``incorporation`` dimension checks each cited E-ID
    actually shares ≥3 significant tokens with its citing sentence
    (kills citation-washing); absent → incorporation is 1.0 (no-op).
    ``enforce_score_echo``: when True, a ≥50% score-restatement density
    fails the gate (the insight-card / finding persist paths); the
    dimension is always reported, only gated when this is set.
    """
    flags: list[str] = []
    text = text or ""
    words = max(1, len(text.split()))
    lowered = text.lower()

    ents = extract(text)
    mention_count = sum(len(ents[k]) for k in
                        ("persons", "orgs", "money", "percents", "dates", "cardinals"))
    specificity = min(1.0, (mention_count / words * 100) / 5.0)

    sents = sentences(text)
    claims = max(1, len(sents))
    cited = set(_EID_RE.findall(text))
    scope_ids = {str(e) for e in evidence_ids}
    unknown = sorted(cited - scope_ids) if scope_ids else []
    valid = cited - set(unknown)
    for eid in unknown:
        flags.append(f"unknown_evidence_id:{eid}")
    grounding = min(1.0, len(valid) / max(1.0, claims / 2.0))
    if not valid and claims:
        flags.append("uncited_claims")

    filler_hits = [p for p in _FILLER_PHRASES if p in lowered]
    for phrase in filler_hits:
        flags.append(f"filler:{phrase}")
    filler = 1.0 if not filler_hits else max(0.0, 1.0 - 0.5 * len(filler_hits))

    scope_numbers = [float(n) for n in numbers_in_scope]
    numbers = _text_numbers(text)
    if not scope_numbers or not numbers:
        coherence = 1.0
    else:
        good = [n for n in numbers if _coherent(n, scope_numbers)]
        coherence = len(good) / len(numbers)
        for n in numbers:
            if n not in good:
                flags.append(f"incoherent_number:{n:g}")

    # A warm-spaCy "sentence" that spans a paragraph break is a segmentation
    # artifact: the tokenizer glues a trailing citation to the next paragraph
    # ("…[E-118].\n\nMake …" = ONE span), so the imperative lead never heads
    # a sentence and the same blob graded actionable on the cold regex tier
    # and no_action in-image (2026-07-13 live-pg divergence). Paragraphs are
    # composer units — re-split before the lead check.
    lead_units = [u.lstrip() for s in sents for u in re.split(r"\n{2,}", s)]
    actionable = bool(_ACTION_RE.search(text)) or any(
        _IMPERATIVE_LEAD_RE.match(u) for u in lead_units if u
    )
    actionability = 1.0 if actionable else 0.0
    if not actionable:
        flags.append("no_action")

    # incorporation — each cited E-ID whose excerpt is supplied must share
    # ≥3 significant tokens with its citing sentence. A stapled "[E-x]" on
    # score-template prose scores 0 here even when bare grounding reads 1.0.
    excerpt_map = {str(k): str(v) for k, v in (evidence_excerpts or {}).items()
                   if str(v or "").strip()}
    incorporation = 1.0
    if excerpt_map:
        checked = washed = 0
        for sent in sents:
            sent_toks = _significant_tokens(re.sub(r"\[[^\]]*\]", " ", sent))
            for eid in set(_EID_RE.findall(sent)):
                ex = excerpt_map.get(eid)
                if not ex:
                    continue
                checked += 1
                if len(sent_toks & _significant_tokens(ex)) < 3:
                    washed += 1
                    flags.append(f"citation_washing:{eid}")
        if checked:
            incorporation = round((checked - washed) / checked, 4)

    # score_echo — 1 minus score-restatement density. Always reported; only a
    # gate when the caller opts in (insight-card / finding persist paths). A
    # density at or above 0.5 fails the gate (the prose is more score-template
    # than argument).
    echo_density = _score_echo_density(sents)
    score_echo = round(1.0 - echo_density, 4)
    score_echo_ok = (not enforce_score_echo) or echo_density < 0.5
    if enforce_score_echo and not score_echo_ok:
        flags.append(f"score_echo:{echo_density:.2f}")

    scores = {
        "specificity": round(specificity, 4),
        "grounding": round(grounding, 4),
        "filler": round(filler, 4),
        "coherence": round(coherence, 4),
        "actionability": round(actionability, 4),
        "incorporation": round(incorporation, 4),
        "score_echo": score_echo,
    }
    gating = [scores["specificity"], scores["grounding"], scores["filler"],
              scores["coherence"], scores["actionability"], scores["incorporation"]]
    passed = (all(v >= 0.5 for v in gating) and not filler_hits and score_echo_ok)
    return {"scores": scores, "pass": passed, "flags": flags}


# --- markdown lint --------------------------------------------------------

_DOUBLE_SPACE_RE = re.compile(r"(?<=\S)  +(?=\S)")
_F_MARKER_RE = re.compile(r"::F\d")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+")
_MAX_LEN = 4000
_MAX_BULLET_RUN = 8


def markdown_lint(text: str) -> list[str]:
    """Flag presentation artifacts in AE-facing markdown.

    Stable flag codes (prefix-matchable): ``double_space``,
    ``stray_heading_mid_text``, ``unbalanced_emphasis``,
    ``paren_colon_artifact`` ("(: 1.68" label-resolution bug),
    ``f_marker_leak`` ("::F1"), ``bullet_dump:N``, ``too_long:N``.
    """
    flags: list[str] = []
    if not text:
        return flags
    if _DOUBLE_SPACE_RE.search(text):
        flags.append("double_space")
    for m in re.finditer(r"##+", text):
        if m.start() != 0 and text[m.start() - 1] != "\n":
            flags.append("stray_heading_mid_text")
            break
    if text.count("**") % 2 == 1 or text.count("__") % 2 == 1:
        flags.append("unbalanced_emphasis")
    if "(: " in text:
        flags.append("paren_colon_artifact")
    if _F_MARKER_RE.search(text):
        flags.append("f_marker_leak")
    run = longest = 0
    for line in text.splitlines():
        if _BULLET_RE.match(line):
            run += 1
            longest = max(longest, run)
        elif line.strip():
            run = 0
    if longest > _MAX_BULLET_RUN:
        flags.append(f"bullet_dump:{longest}")
    if len(text) > _MAX_LEN:
        flags.append(f"too_long:{len(text)}")
    return flags


# --- proofread: final exec-summary typography + light-flow cleanup ----------
# The SCQA executive summary is the highest-visibility AE surface. The deploy
# review (2026-07-06 operator report) read every client's summary and found
# typos + poor flow that "non-empty" QA never catches: ellipsis-clipped excerpt
# fragments, emoji spliced from research notes ("MAJOR FINDING:"), ALL-CAPS
# shout labels ("CONFIRMED GAP:", "NUANCE:"), article disagreement ("A 8.9%"),
# pipeline/QA-meta rows read as findings ("manifest=0, registry=135"), and
# repeated sentence stems ("The issue register adds X. The issue register adds
# Y."). proofread() is the deterministic, IDEMPOTENT cleanup the composer runs
# as its FINAL step so none of these can ship; proofread_flags() is the
# companion rubric check (the same defect classes as stable codes) the composer
# asserts on and the deploy audit mirrors.

# Emoji / pictographs that leak from evidence excerpts. Deliberately excludes
# the 2600-26FF block so rating glyphs (star) and the staleness marker survive.
# Trailing group = optional variation selectors (VS15 U+FE0E / VS16 U+FE0F).
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF][\uFE0E\uFE0F]?")
# ALL-CAPS analyst-note labels spliced mid-excerpt: strip the label, keep the
# content ("NEGATIVE - No single customer view" -> "No single customer view").
# The label separator can be colon, hyphen, en-dash (U+2013) or em-dash (U+2014).
_SHOUT_LABEL_RE = re.compile(
    r"\b(?:NUANCE|CONFIRMED GAP|CONFIRMED|MAJOR FINDING|KEY FINDING|FINDING|"
    r"NOTE|NEGATIVE|POSITIVE|CAUTION|IMPORTANT|WARNING|OBSERVATION|CORRECTION)"
    "\\s*[:\\-\u2013\u2014]\\s+")
# PRESENT/ABSENT are tech-stack status labels \u2014 strip ONLY as a sentence
# lead ("PRESENT \u2014 Tableau: ..."); mid-sentence they are load-bearing
# ("documentation is ABSENT \u2014 confirmed by search" must keep its negation).
_STATUS_LEAD_RE = re.compile(
    r"(?:(?<=^)|(?<=[.!?]\s))(?:PRESENT|ABSENT)\s*[\u2014\u2013-]\s+(?=[A-Z0-9'\"])")
# Pipeline / assessment-QA meta rows that are NOT a client finding: they must
# never reach an AE-facing summary (the exporter drops kind='assessment_qa' but
# these ship with kind='client' and a QA-artifact title).
_META_QA_RE = re.compile(
    r"manifest\s*=|registry\s*=\s*\d|unique E-?ID|E-?ID citations|threshold\s*:|"
    r"NO_EVIDENCE|proof completeness|weights?\s+sum\s+to\s+100|per-row single tier|"
    r"not in registry|\bmismatch(?:es)?\b|citation density|schema drift|"
    r"run_manifest|evidence count|under-?cite|pillar sections|"
    r"\bT[123]\s+evidence\b|\(\d+\s+E-?IDs\)", re.I)
# Article disagreement before a number whose spoken form opens on a vowel
# ("a 8.9%" -> "an 8.9%", "a 11.2%", "a 18%"); scoped to the percent/rate form
# the composer emits so it never touches "a 5.0" ("a five-point-oh").
_ARTICLE_PCT_RE = re.compile(r"\b([Aa]) (?=(?:8|11|18)(?:\.\d+)?\s?%)")
_ARTICLE_WORD_RE = re.compile(r"\b([Aa]) (?=(?:hour|honest|honou?rs?|heir)\b)")
# "The issue register adds ..." repeated as its own sentence stem (poor flow).
_ISSUE_LEAD_RE = re.compile(r"\bThe issue register adds\b")

# Real initialisms that must survive the shout-run decapitalizer (kept in
# sync with qa_paragraph_cohesion._ACRONYM_OK — the measuring instrument).
_CAPS_KEEP = {
    "FDIC", "NCUA", "GLBA", "CISO", "CDO", "CMO", "CIO", "CTO", "CFO",
    "CFPB", "FFIEC", "NIST", "SIEM", "SOC", "SOAR", "API", "APIS", "CRM",
    "ERP", "LOS", "AML", "BSA", "KYC", "GRC", "ESG", "FCA", "OCC", "SBA",
    "ROI", "SLA", "SLO", "KPI", "GENAI", "AI", "ML", "BI", "RPA", "PEO",
    "AUM", "FDX", "ACH", "RTP", "CUSO", "HELOC", "IRA", "SOC2", "PDF",
    "MSC", "USDA", "REIT", "NYSE", "IPO", "LP", "GP", "RIA", "SEC",
    "FINTRAC", "FINCEN", "OSFI", "HRIS",
}
# A shouty word: >=4 chars, pure ALL-CAPS letters (digit-bearing tokens like
# SOC2/M365 read as product codes, not shouting). A run is >=3 in a row;
# analyst notes join them with '+' as often as with spaces ("DATA
# ARCHITECTURE + INTEGRATION").
_SHOUT_RUN_RE = re.compile(
    r"\b[A-Z][A-Z/&'-]{3,}(?:(?:\s*[+&]\s*|\s+)[A-Z][A-Z/&'-]{3,}){2,}\b")


def _decap_shout_word(w: str) -> str:
    parts = re.split(r"([-/])", w)
    out = []
    for p in parts:
        if p in "-/" or len(p) < 4 or p in _CAPS_KEEP \
                or not re.search(r"[AEIOUY]", p):
            out.append(p)
        else:
            out.append(p.lower())
    return "".join(out)


def _decap_shout_runs(text: str) -> str:
    """Sentence-case residual ALL-CAPS analyst emphasis ('FORMAL DATA
    GOVERNANCE FUNCTION EXISTS' -> 'formal data governance function
    exists', capitalized when it opens a sentence). Verbatim quoted spans
    are exempt — a quotation is cited material, allowed to shout. A run
    with no word >=7 chars is left alone: short-token runs (TILA RESPA
    ECOA FCRA, cert lists, vendor modules) are domain initialisms whose
    casing IS their spelling."""
    segs = text.split('"')

    def fix(seg: str) -> str:
        def rep(m: re.Match[str]) -> str:
            words = m.group(0).split()
            if not any(len(w) >= 7 for w in words):
                return m.group(0)
            fixed = " ".join(_decap_shout_word(w) for w in words)
            head = seg[:m.start()]
            at_start = (not head.strip()
                        or re.search(r"[.!?:]\s*$", head) is not None)
            if at_start and fixed[:1].islower():
                fixed = fixed[0].upper() + fixed[1:]
            return fixed
        return _SHOUT_RUN_RE.sub(rep, seg)

    return '"'.join(fix(s) if i % 2 == 0 else s
                    for i, s in enumerate(segs))

# Unicode literals used by proofread, named so no ambiguous glyph sits in source.
_ELLIPSIS = "\u2026"
_EM_DASH = "\u2014"
_NBSP, _THIN_SP, _HAIR_SP = "\u00a0", "\u2009", "\u200a"
_LDQUO, _RDQUO, _LSQUO, _RSQUO = "\u201c", "\u201d", "\u2018", "\u2019"


def _an(m: re.Match[str]) -> str:
    return "An " if m.group(1) == "A" else "an "


def _drop_meta_sentences(text: str) -> str:
    """Drop QA/pipeline-meta sentences, paragraph structure preserved."""
    out: list[str] = []
    for para in text.split("\n\n"):
        parts = re.split(r"(?<=[.!?])\s+", para)
        kept = [p for p in parts if p.strip() and not _META_QA_RE.search(p)]
        out.append(" ".join(kept))
    return "\n\n".join(p for p in out if p.strip())


def _collapse_issue_leads(text: str) -> str:
    """Second and later 'The issue register adds' stems become 'It also flags'
    (they always sentence-start in the composed SCQA), so a client with several
    open issues reads as one flowing sentence group, not a stuttered list."""
    n = 0

    def rep(_m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return "The issue register adds" if n == 1 else "It also flags"

    return _ISSUE_LEAD_RE.sub(rep, text)


def proofread(text: str) -> str:
    """Deterministic, idempotent typography + light-flow cleanup for AE prose.

    Normalizes whitespace, punctuation and quotes; strips the excerpt-splice
    defect classes the deploy review found (emoji, ALL-CAPS shout labels,
    ellipsis clip-artifacts, QA-meta sentences, empty citations); fixes article
    disagreement; and collapses the repeated issue-register stem. Preserves
    [E-###] citations, paragraph breaks and source numbers, and never grows the
    text -- safe to run as the final step of composition. Idempotent:
    proofread(proofread(x)) == proofread(x).
    """
    s = str(text or "")
    if not s.strip():
        return ""
    # unicode whitespace + line endings
    s = (s.replace(_NBSP, " ").replace(_THIN_SP, " ").replace(_HAIR_SP, " ")
         .replace("\r\n", "\n").replace("\r", "\n"))
    # double-dash citation artifacts ("EV--013", "E--001") -> single dash, so
    # the chip renders and the E-ID counts as grounding (repair_citations_light
    # only fixed the bare "E--" form, leaving the "EV--"/"INT--" variants).
    s = re.sub(r"\b(EV|INT|E)-{2,}(?=\d)", r"\1-", s)
    # quotes -> straight (matches the composer's own quoting), collapse doubles
    s = (s.replace(_LDQUO, '"').replace(_RDQUO, '"')
         .replace(_LSQUO, "'").replace(_RSQUO, "'"))
    s = re.sub(r'""+', '"', s)
    # excerpt-splice noise
    s = _EMOJI_RE.sub("", s)
    s = _SHOUT_LABEL_RE.sub("", s)
    s = _STATUS_LEAD_RE.sub("", s)
    # 2026-07-13 corpus QA placeholder classes — all shipped in executive
    # summaries. These run BEFORE the clipped-parenthetical repair below so
    # the pass reaches its fixed point in one application (idempotency):
    #   "Erie Insurance ( WP)"     → empty stripped-value parenthetical
    #   "Technology Leadership (: 2.61 …)" → husk of a stripped inner code
    #   "acknowledged [[E-041"     → doubled citation bracket
    s = re.sub(r"\s*\(\s+[A-Za-z]{0,6}\s*\)", "", s)   # "( WP)" / "(  )"
    s = re.sub(r"\(\s*:\s*", "(", s)                    # "(: 2.61" → "(2.61"
    s = re.sub(r"\[{2,}(?=[A-Z])", "[", s)              # "[[E-041" → "[E-041"
    # an unterminated citation opener at sentence end — "[E-041." — regains
    # its close so the chip parses
    s = re.sub(r"(\[(?:EV|INT|E)-\d+(?:,\s*(?:EV|INT|E)-\d+)*)(?=\s*\.(?:\s|$))",
               r"\1]", s)
    # orphan value-operator debris: "writing + in premium" (the figure was
    # stripped upstream) — drop the dangling operator token
    s = re.sub(r"(?<=[a-z])\s+\+\s+(?=in\s)", " ", s)
    # doubled terminal period after a quote/paren: 'formative". .' → '".'
    # (whitespace REQUIRED between the stops — "..." belongs to the
    # ellipsis handler below, not this rule)
    s = re.sub(r"([.!?][\"')\]]?)\s+\.(?=\s|$)", r"\1", s)
    # internal register/pipeline codes never render in prose — alone
    # "(URF-01)" / "[URF-02]", or embedded in a citation "(…, T3; ISS-009)".
    # The square-bracket form is scoped to URF/ISS/REQ/QA so real E-ID
    # citations "[E-041]" are never touched.
    s = re.sub(r"\s*[(\[](?:URF|ISS|REQ|QA)-[\dA-Z-]+[)\]]", "", s)
    s = re.sub(r"[;,]\s*(?:URF|ISS|REQ|QA)-[\dA-Z-]+(?=\s*[)\].,;])", "", s)
    # a clipped parenthetical severed before its close — "(August 11
    # [E-005]." — regains its close before the citation/terminal so the
    # sentence parses; content untouched
    s = re.sub(r"(\([^()\[\].\n]{1,58}[^\s()\[\].])(?=\s*(?:\[[A-Z][\w-]*"
               r"(?:,\s*[A-Z][\w-]*)*\])?\s*\.(?:\s|$))",
               r"\1)", s)
    # generic analyst shout-lead: a sentence-start run of ALL-CAPS words
    # before a colon ("MAJOR TECH FIND:", "DIRECT EVIDENCE:") — research-
    # tool emphasis, not prose (same rule as the drawer excerpt cleaner).
    # Tolerates year tokens and one parenthetical before the colon
    # ("DEFINITIVE TECH STACK 2026 (echoloc.ai):").
    s = re.sub(r"(?:(?<=^)|(?<=[.!?]\s))"
               r"[A-Z][A-Z0-9/&'-]{1,18}"
               r"(?:\s+[A-Z0-9][A-Z0-9/&'-]{0,18}){1,5}"
               r"(?:\s*\([^()\n]{1,40}\))?"
               r"\s*:\s+(?=[A-Z0-9'\"])", "", s)
    # residual mid-prose shouting (no colon to strip on): sentence-case it,
    # acronyms and quoted verbatim spans preserved
    s = _decap_shout_runs(s)
    # analyst-note operator husks left by clipped joins: "( + )", "( + + )"
    s = re.sub(r"\s*\(\s*[+&](?:[+&\s])*\)", "", s)
    # "e.g. X" -> "e.g., X": the comma keeps naive sentence splitters
    # (and readers) from treating the abbreviation as a full stop
    s = re.sub(r"\b(e\.g\.|i\.e\.)\s+(?!,)", r"\1, ", s)
    # our own composed SCQA complication openers, when they directly
    # follow the overall-score sentence ("... at 2.2/5."): tie back with
    # the demonstrative bridge. Idempotent — the bridged form no longer
    # matches either pattern.
    s = re.sub(r"(?<=/5\.)\s+The binding gap is\b",
               " The binding gap inside that number is", s)
    s = re.sub(r"(?<=/5\.)\s+"
               r"(?=(?!Inside\b)[A-Z][^.\n]{5,90} runs at \d[\d.]*/5 "
               r"against a [\d.]+ peer median, the constraint)",
               " Inside that number, ", s)
    # our own retired SCQA-answer template asserted a dependency graph
    # nothing verifies ("capabilities that depend on it") — kept-if-deep
    # rows still carry it; heal to the honest floor claim the current
    # composer writes (reasoning audit R3, evidence-gated relations)
    # The heal maps ONLY the retired dependency-graph phrase; it rotates
    # deterministically (seeded on the text head) so kept rows carrying it
    # don't all heal to one 51-client line. The composer writes its own
    # entity-seeded floor tails, so this never touches fresh output.
    _floor_variants = (
        "and it raises the floor the surrounding capabilities work from",
        "and the capabilities around it inherit the stronger baseline",
        "and adjacent capabilities get a firmer floor to build on",
    )
    _floor_pick = _floor_variants[_zlib.crc32(s[:80].encode()) % 3]
    s = s.replace(
        "and the capabilities that depend on it compound the gain",
        _floor_pick)
    # our own composed card-why labels: tie back to the rated-priority
    # sentence before them (cohesion sweep: disconnected). Idempotent —
    # the possessive form no longer matches the bare label.
    s = re.sub(r"(?<![A-Za-z] )\bEntry-point signal:", "Its entry-point signal:", s)
    s = re.sub(r"(?<![A-Za-z] )\bPillar alignment:", "Its pillar alignment:", s)
    # workbook name-shorthand ("Regulatory & Legal Manager = Kate Mahan")
    # reads as an em-dash appositive in prose; arithmetic '=' (a digit
    # shortly before) is notation and stays
    s = re.sub(
        r"(?<=[a-z)'\"])\s=\s(?=[A-Z$])",
        lambda m: (" = " if re.search(
            r"\d", s[max(0, m.start() - 24):m.start()])
            else f" {_EM_DASH} "),
        s)
    s = _drop_meta_sentences(s)
    # a clip that severed a "+"-joined name ("Training +. Governance") —
    # rejoin; the cohesion sweep's splice:plus_period class
    s = re.sub(r"\+\s*\.\s*(?=[A-Z])", "+ ", s)
    # dashes: '--' -> em-dash, collapse runs, single spacing
    s = re.sub(r"\s*--+\s*", f" {_EM_DASH} ", s)
    s = re.sub(_EM_DASH + r"{2,}", _EM_DASH, s)
    # ellipsis: unify then remove truncation artifacts
    s = re.sub(r"\.{3,}", _ELLIPSIS, s)
    s = re.sub(r"\s*" + _ELLIPSIS + r"+\s*(?=\[)", " ", s)      # "MDM... [E-1]" -> "MDM [E-1]"
    s = re.sub(r"\s*" + _ELLIPSIS + r"+(?=[.,;:)\]\n]|$)", "", s)  # before punct/EOL -> drop
    s = re.sub(r"\s*" + _ELLIPSIS + r"+\s+(?=[A-Z0-9])", ". ", s)  # broken join -> sentence break
    s = s.replace(_ELLIPSIS, "")                                # any straggler
    # empty citation / bracket junk ("['', '']", "()")
    s = re.sub(r"\[\s*(?:''|\"\"|,|\s)*\]", "", s)
    s = re.sub(r"\(\s*\)", "", s)
    # label-strip husk: a paren whose leading label was resolved away leaves a
    # bare colon ("Digital Marketing (: 1.66 vs 2.25)" — 2026-07-14 vet). Drop
    # the orphaned colon so the number reads inside a clean parenthesis.
    s = re.sub(r"\(\s*:\s*", "(", s)
    # punctuation spacing
    s = re.sub(r"[ \t]+([.,;:!?])", r"\1", s)               # no space before punct
    s = re.sub(r"(?<=[a-z])([.!?])(?=[A-Z])", r"\1 ", s)    # missing space after period
    s = re.sub(r"([.,;:!?])\1+", r"\1", s)                  # ".."/",," -> single
    # article agreement
    s = _ARTICLE_PCT_RE.sub(_an, s)
    s = _ARTICLE_WORD_RE.sub(_an, s)
    # flow: de-stutter the issue-register stem
    s = _collapse_issue_leads(s)
    # bracket inner spacing + final whitespace
    s = re.sub(r"\[\s+", "[", s)
    s = re.sub(r"\s+\]", "]", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+([.,;:!?])", r"\1", s)               # re-tidy after joins
    return s.strip()


def proofread_flags(text: str) -> list[str]:
    """Residual exec-summary defects as stable codes (the proofread rubric).

    Codes: double_space, orphan_punct, missing_space_after_period,
    stray_ellipsis, emoji, article_agreement, shout_label, meta_qa_leak,
    under_cited (<2 distinct E-IDs). Empty list == clean. A well-composed SCQA
    that has been through proofread() returns [].
    """
    s = str(text or "")
    flags: list[str] = []
    if _DOUBLE_SPACE_RE.search(s):
        flags.append("double_space")
    if re.search(r"\s[.,;:!?](?:\s|$)", s) or re.search(r"([.,;:!?])\1", s):
        flags.append("orphan_punct")
    if re.search(r"(?<=[a-z])[.!?](?=[A-Z])", s):
        flags.append("missing_space_after_period")
    if _ELLIPSIS in s or "..." in s:
        flags.append("stray_ellipsis")
    if _EMOJI_RE.search(s):
        flags.append("emoji")
    if _ARTICLE_PCT_RE.search(s):
        flags.append("article_agreement")
    if _SHOUT_LABEL_RE.search(s):
        flags.append("shout_label")
    if _META_QA_RE.search(s):
        flags.append("meta_qa_leak")
    if len(set(_EID_RE.findall(s))) < 2:
        flags.append("under_cited")
    return flags
