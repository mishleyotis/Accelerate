#!/usr/bin/env python3
"""The content checks — the ones the old gates measured length instead of.

WHY THIS EXISTS. A cluster of findings share one shape: a gate that checks
PRESENCE and LENGTH and calls the result quality.

  AUD-0009/0016/0019/0026  the skeleton template passed every gate unmodified,
                           and an all-STUB synthesis closed a subcap.
  AUD-0079                 absence detection was a 6-alternative regex with
                           29% recall and a 100% false-positive rate.
  AUD-0073                 the contradicts-probe detector looked for the
                           substring "contradict", which the shipped
                           contradicts query never contains.
  AUD-0080                 a 2-rung ladder was published as a 4-rung ladder,
                           because nothing counted rungs.
  AUD-0076                 nothing computed sibling evidence overlap, so
                           smearing one document across a category was the
                           cheapest way to close it.

Every detector here is measured against the probe battery in
tests/skills/research_engine/test_quality.py, and each one states the recall
and precision it was built to reach. A detector that cannot say what it
misses is a detector that will be waived away."""
from __future__ import annotations

import re
from collections import Counter

# ── boilerplate and form-filling ─────────────────────────────────────────

_STUB_MARKERS = (
    "stub", "lorem ipsum", "todo", "tbd", "xxx", "placeholder",
    "fill in", "fill this", "<insert", "insert here", "replace this",
    "example text", "sample text", "n/a", "not applicable",
)

#: Filler that satisfies a minLength and says nothing. Each was observed in
#: the AUD-0026 "fluent emptiness" probe or the AUD-0009 skeleton.
_EMPTY_PHRASES = (
    "further research is needed", "more evidence is required",
    "additional analysis", "to be determined", "cannot be determined at this time",
    "this subcapability", "the organization has capabilities",
    "evidence shows", "it is likely that", "appears to be the case",
    "no specific details", "generally speaking", "as noted above",
)


def is_boilerplate(text) -> str | None:
    """A reason string when `text` is form-filling, else None.

    Length is never the test. The skeleton the archive shipped satisfied
    five of six minLength constraints while carrying the literal word STUB
    in every field; the sixth field was not in the schema's `required` list,
    so dropping it validated."""
    if text is None:
        return "empty"
    s = str(text).strip()
    if not s:
        return "empty"
    low = s.lower()
    for m in _STUB_MARKERS:
        if re.search(rf"(?<![a-z]){re.escape(m)}(?![a-z])", low):
            return f"placeholder marker {m!r}"
    if re.fullmatch(r"[\W_]+", s):
        return "punctuation only"
    words = re.findall(r"[a-z0-9']+", low)
    if len(words) < 6:
        return f"only {len(words)} words"
    # A single phrase repeated to reach a length.
    if len(set(words)) <= max(3, len(words) // 4):
        return "one phrase repeated to reach a length"
    hits = [p for p in _EMPTY_PHRASES if p in low]
    if hits and len(words) < 40:
        return f"filler phrase {hits[0]!r} carrying most of a short field"
    return None


def is_fluent_but_empty(text, *, must_name: list[str] | None = None) -> str | None:
    """Fluent prose that names nothing checkable.

    AUD-0026: gate output byte-identical to the golden fixture, on a
    synthesis that had no content. A claim about a capability has to contain
    at least one of: a figure, a date, a proper noun, or a cited id. Prose
    with none of those is describing a feeling."""
    r = is_boilerplate(text)
    if r:
        return r
    s = str(text)
    anchors = 0
    anchors += len(re.findall(r"\b\d{4}\b", s))                    # a year
    anchors += len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|percent)", s))
    anchors += len(re.findall(r"\[E-\d+(?::F\d+)?\]", s))          # a citation
    anchors += len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", s))
    if anchors == 0:
        return ("names no figure, date, proper noun or cited id — nothing in "
                "it can be checked")
    for token in (must_name or []):
        if token.lower() not in s.lower():
            return f"does not name {token!r}, which it is about"
    return None


# ── absence, stated properly ─────────────────────────────────────────────
#
# The old detector was:
#   \b(no |not evidenced|absent|does not exist|nothing (was )?found|zero )
# It caught 4 of 14 real absence phrasings and fired on 3 of 3 presence
# sentences containing "no fewer than", "no doubt" and "absent-minded".

_ABSENCE_PATTERNS = (
    r"\bno\s+(?:documented|published|disclosed|public|evidence|record|sign|"
    r"indication|trace|mention|reference|\w+\s+(?:was|were|is|are)\s+found)",
    r"\bno\s+(?!fewer|less|doubt|longer|later|more than|matter)\w+",
    r"\bnot\s+(?:evidenced|documented|disclosed|published|established|found|"
    r"visible|present|available|observed)",
    r"\babsent\b(?!-minded)",
    r"\ban?\s+absence\s+of\b",
    r"\bdoes\s+not\s+(?:exist|appear|disclose|publish|document|evidence)",
    r"\bdo\s+not\s+(?:exist|appear|disclose|publish|document|evidence)",
    r"\bnothing\s+(?:was\s+)?(?:found|located|surfaced|disclosed|published)",
    r"\bnothing\s+in\s+the\b",
    r"\bzero\s+\w+\s+(?:were|was)\s+(?:found|identified|located)",
    r"\blacks?\b", r"\blacking\b",
    r"\bfound\s+nothing\b",
    r"\bmissing\b", r"\bunevidenced\b", r"\bundisclosed\b",
    r"\bneither\b[^.]{0,80}\bnor\b",
    r"\bnever\s+(?:established|published|disclosed|documented|evidenced)",
    r"\bsilent\s+on\b",
    r"\bcould\s+not\s+be\s+(?:established|found|evidenced|located)",
    r"\bwe\s+did\s+not\s+find\b",
    r"\bunable\s+to\s+(?:find|locate|establish|evidence)",
)

#: Phrases that contain an absence token and are not absence claims. Removed
#: before matching so they cannot fire the detector (the 100% false-positive
#: rate AUD-0079 measured came from exactly these).
_ABSENCE_DECOYS = (
    r"\bno\s+fewer\s+than\b", r"\bno\s+less\s+than\b", r"\bno\s+doubt\b",
    r"\bno\s+longer\b", r"\bno\s+later\s+than\b", r"\bno\s+more\s+than\b",
    r"\bno\s+matter\b", r"\babsent-minded\b", r"\bmissing\s+the\s+point\b",
    r"\bsecond\s+to\s+none\b", r"\bnone\s+other\s+than\b",
)

_ABSENCE_RE = re.compile("|".join(_ABSENCE_PATTERNS), re.I)
_DECOY_RE = re.compile("|".join(_ABSENCE_DECOYS), re.I)


def claims_absence(text) -> bool:
    """True when `text` asserts that something was not found.

    An absence claim carries obligations — a proxy log, a negative-finding
    ladder, an escalation — and AUD-0079 measured those obligations turning
    on one verb choice: 'has no documented artefact' fired the gate and
    'lacks any documented artefact' did not."""
    if not text:
        return False
    s = _DECOY_RE.sub(" ", str(text))
    return bool(_ABSENCE_RE.search(s))


# ── the contradicts probe, recognised by shape ───────────────────────────

_CONTRADICTS_OPERATORS = (
    "lawsuit", "enforcement", "consent order", "criticism", "criticised",
    "criticized", "delayed", "delay", "abandoned", "cancelled", "canceled",
    "scrapped", "shelved", "yet to", "failed", "failure", "setback",
    "postponed", "paused", "wound down", "written off", "restated",
    "fine", "penalty", "breach", "outage", "complaint", "downgrade",
    "sued", "investigation", "probe", "misled", "overstated",
)


def probes_contradicts(query: str, facet: str | None = None) -> bool:
    """True when a search record is a contradiction probe.

    AUD-0073: both old detectors accepted a record only if `facet ==
    'contradicts'` or the literal substring 'contradict' appeared in the
    query — and 0 of 851 shipped contradicts queries contain that substring.
    An agent that fired the right query and logged it failed the check;
    an agent that fired nothing and wrote `facet: contradicts` passed it.
    Here the QUERY is what is read, and the declared facet is corroborating
    rather than sufficient."""
    q = (query or "").lower()
    if "contradict" in q:
        return True
    hits = sum(1 for op in _CONTRADICTS_OPERATORS if op in q)
    if hits >= 2:
        return True
    # A declared facet still counts, but only when the query does SOME
    # adversarial work — one operator, or an explicit negation.
    if (facet or "").lower() == "contradicts" and (hits >= 1 or " -" in q):
        return True
    return False


# ── negative-finding ladders, counted ────────────────────────────────────

LADDER_RUNGS = ("direct", "proxy", "peer", "regulatory")


def ladder_report(ladder, searches) -> dict:
    """What a negative-finding ladder actually establishes.

    AUD-0080: the gate checked only that >=2 distinct proxy_class values
    appeared anywhere; it never counted rungs, never checked the claimed
    queries were fired, and the report then printed a fixed '4-rung ladder'.
    Here the rungs are counted, and a rung whose query is not in the search
    log is reported as CLAIMED_NOT_FIRED rather than counted."""
    rows = list(ladder or [])
    fired = {(_norm_q(s.get("Query") or s.get("query"))) for s in (searches or [])}
    seen, unfired = [], []
    for row in rows:
        rung = str(row.get("rung") or row.get("proxy_class") or "").strip().lower()
        q = _norm_q(row.get("query"))
        if rung not in LADDER_RUNGS:
            continue
        if q and q not in fired:
            unfired.append({"rung": rung, "query": row.get("query")})
            continue
        if rung not in seen:
            seen.append(rung)
    return {
        "rungs_claimed": len(rows),
        "rungs_established": len(seen),
        "rungs": seen,
        "claimed_not_fired": unfired,
        "label": f"{len(seen)}-rung ladder",
    }


def norm_query(q) -> str:
    """The identity of a query: case, whitespace and outer quoting removed.

    ONE owner (QA audit F-D05-033, 28-09-2026). The relay queue, the ladder
    report and the Search_Log's duplicate refusal all decide "the same
    query" here, so two lanes asking one thing in two casings owe one
    search, and a query the log already holds is the query the log holds."""
    q = " ".join(str(q or "").split()).strip().strip("\"'`“”‘’").strip()
    return q.lower()


_norm_q = norm_query


# ── evidence smearing across siblings (R22 / SG-09) ──────────────────────

def evidence_smear(rows, *, threshold: float = 0.60, min_siblings: int = 3):
    """Sibling subcaps sharing most of their evidence.

    AUD-0076: R22 and SG-09 both specify a warning when >=3 sibling subcaps
    share >60% identical evidence ids; what existed measured identical QUERY
    sets at build time and read no ledger. This reads the ledger — the
    workbook's own scoring rows — and returns the capabilities where
    smearing has happened, so a category cannot be closed by citing one
    document everywhere."""
    by_cap: dict[str, list[tuple[str, set]]] = {}
    for r in rows:
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell or "." not in cell:
            continue
        ids = {i for i in _ids(r.get("Evidence_IDs")) if i != "NO_EVIDENCE"}
        if not ids:
            continue
        by_cap.setdefault(cell.rsplit(".", 1)[0], []).append((cell, ids))
    out = []
    for cap, sibs in sorted(by_cap.items()):
        if len(sibs) < min_siblings:
            continue
        counts = Counter()
        for _, ids in sibs:
            counts.update(ids)
        # The evidence set shared by at least `min_siblings` of them.
        shared = {e for e, n in counts.items() if n >= min_siblings}
        if not shared:
            continue
        smeared = [c for c, ids in sibs
                   if ids and len(ids & shared) / len(ids) > threshold]
        if len(smeared) >= min_siblings:
            out.append({
                "capability": cap,
                "subcaps": sorted(smeared),
                "shared_evidence": sorted(shared),
                "detail": (f"{len(smeared)} sibling subcaps under {cap} draw "
                           f">{int(threshold*100)}% of their evidence from the "
                           f"same {len(shared)} item(s)"),
            })
    return out


def _ids(v) -> list[str]:
    if v is None:
        return []
    return [s.strip() for s in str(v).replace(";", ",").split(",") if s.strip()]


# ── proxy-only evidence must not read as fact ────────────────────────────

def proxy_only(row) -> bool:
    """True when a row's whole case is proxy searching.

    AUD-0021: proxy-only evidence closed as FACT and published as M4 with
    HIGH confidence. A proxy establishes what a peer or a sector does; it
    never establishes what THIS entity does."""
    ids = [i for i in _ids(row.get("Evidence_IDs")) if i != "NO_EVIDENCE"]
    proxied = str(row.get("Proxy_Searched") or "").strip().upper()
    return proxied in ("YES", "TRUE", "1") and not ids


def claim_label_supported(row) -> str | None:
    """A reason the row's claim label is stronger than its evidence."""
    label = str(row.get("Claim_Label") or "").strip().upper()
    ids = [i for i in _ids(row.get("Evidence_IDs")) if i != "NO_EVIDENCE"]
    # Proxy first: it is the more specific diagnosis, and it names the
    # mechanism AUD-0021 measured — proxy-only evidence closing as FACT and
    # publishing as M4 with HIGH confidence. "no evidence id" is true of that
    # row too, and is the less useful of two true sentences.
    if label == "FACT" and proxy_only(row):
        return "FACT resting on proxy searching alone"
    if label == "FACT" and not ids:
        return "FACT with no resolvable evidence id"
    if label and label not in ("FACT", "INFERENCE", "HYPOTHESIS",
                              "CEILING_ESTIMATE"):
        return f"claim label {label!r} is not in the vocabulary"
    return None


# ── the hallucination pinpointer: numbers must come from somewhere ────────
#
# A fabricated figure is the highest-damage hallucination this pipeline can
# ship: it reads as the most rigorous sentence in the synthesis and it is
# the one a client will quote back. RRF + the excerpt discipline mean every
# real figure entered through a VERBATIM excerpt of a fused, cited source —
# so a number in the synthesis prose that appears in NO excerpt registered
# to the subcap has no provenance at all, and the refusal can name it.

_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
#: A bracketed CITATION is ids only — [E-0001:F2], [E-192, E-195], [TS-004].
#: It used to be ANY bracketed text, so "[2025]", "[July 15, 2025]" or
#: "[27 hits]" passed as citations and a figure no excerpt carries slipped the
#: grounding check by wearing brackets (B1 Bank, 2026-10-08: a research agent
#: read this module after a refusal and bracketed its ungrounded figures).
_ID = r"[A-Z][A-Z0-9]*-[A-Z0-9][\w.\-]*(?::\w+)?"
_CITATION = re.compile(rf"\[\s*{_ID}(?:\s*[,;]\s*{_ID})*\s*\]")
#: An id is never a figure, wherever it sits — "[E-877; fetch refused …]" is a
#: citation with a note, and its digits are the id's, not a claim.
_ID_TOKEN = re.compile(rf"\b{_ID}")

#: Prose fields whose numbers must be grounded — the fields that CLAIM what
#: sources say. NOT_RUN values are skipped whole ("no hits across four
#: queries" is a reason, not a finding). The analyst-argument fields
#: (Ceiling_Reasoning, Why_It_Matters, DMA_Impact) are deliberately absent:
#: "changes what 2026 planning can lean on" is forward reasoning, not a
#: sourced figure, and flagging it teaches agents to strip years from
#: analysis instead of grounding claims.
NUMERIC_CLAIM_FIELDS = (
    "Dominant_Claim", "What_We_Found", "DQ_Works", "DQ_Fails", "DQ_Value",
    "DQ_Contradicts", "DQ_Corroborates", "Triangulation",
)


def _figures(text: str) -> set[str]:
    """Comma-stripped numeric tokens big enough to be claims.

    Small bare integers ("two of three sources", "5 branches") are left
    alone — the false-positive cost outruns the risk — but decimals,
    percent-scale figures and years all check."""
    out = set()
    for tok in _NUM_TOKEN.findall(_ID_TOKEN.sub(" ", _CITATION.sub(" ", text or ""))):
        plain = tok.replace(",", "")
        try:
            big = float(plain) >= 13 or "." in plain
        except ValueError:
            continue
        if big:
            out.add(plain)
    return out


def ungrounded_numbers(record: dict, excerpts: list[str]) -> list[str]:
    """Figures asserted in the synthesis that no registered excerpt carries.

    `excerpts` is every Excerpt + Anchor_Quote registered to this subcap.
    Grounding is plain containment on comma-stripped text: the excerpt is
    VERBATIM source material, so if the figure is real it is in there."""
    ground = " ".join(str(e or "") for e in excerpts).replace(",", "")
    missing = []
    for field in NUMERIC_CLAIM_FIELDS:
        v = str(record.get(field) or "").strip()
        # NOT_RUN and NO_FINDING are outcome reports about the volley, not
        # claims about a source — "hunted 2023-2026, nothing came back" has
        # no excerpt to ground against and needs none.
        if not v or v.upper().startswith(("NOT_RUN", "NO_FINDING")):
            continue
        for fig in sorted(_figures(v)):
            if fig not in ground and fig not in missing:
                missing.append(fig)
    return missing


# ── functional language: impact without accusation ────────────────────────
#
# Two tiers, per references/functional_language.md. JUDGMENT words are
# banned everywhere — they are verdicts about people, not findings about
# capabilities. BLAME constructions are banned in the fields a client
# reads as being about THEM (Why_It_Matters, DMA_Impact, report
# narrative); a gap is framed as the opportunity it opens, with the
# evidence, not as a fault.

_JUDGMENT = ("woefully", "abysmal", "dismal", "embarrassing", "incompetent",
             "negligent", "lazy", "inexcusable", "shockingly", "hopeless",
             "pathetic", "reckless", "asleep at the wheel", "amateurish",
             "clueless")
_BLAME = ("failed to", "fails to", "neglected to", "refuses to",
          "does not bother", "ignored the", "chose to ignore",
          "can't be bothered", "dropped the ball")

#: The impact fields — where blame constructions are also refused.
IMPACT_FIELDS = ("Why_It_Matters", "DMA_Impact")


def accusatory(text: str, *, impact_field: bool = False) -> str | None:
    """The offending phrase and the repair, or None."""
    low = f" {str(text or '').lower()} "
    for w in _JUDGMENT:
        if w in low:
            return (f"{w!r} is a verdict about people, not a finding about a "
                    f"capability — state what the evidence shows and what it "
                    f"makes possible")
    if impact_field:
        for w in _BLAME:
            if w in low:
                return (f"{w!r} frames the gap as a fault. Frame it as the "
                        f"opportunity it opens: what becomes possible when "
                        f"closed, grounded in the cited evidence")
    return None


# ── claim verification: a sentence must be in its own excerpts ───────────
#
# Measured 28-09-2026 (QA audit F-D04-005) on a promoted run's cell
# syntheses: 30 cells, 67 claims, 20 cells verifiable from the excerpts
# cited under them (67%); 12 claims (18%) NOT_SUPPORTED — a named CEO
# attribution no excerpt names, a committee structure no excerpt describes,
# an after-state ("hours to minutes") no excerpt states. Every one of those
# is a sentence whose CONTENT is absent from the verbatim material it cites,
# and that is checkable without a model: the excerpt is verbatim source
# text, so a name, a figure or a content word the claim rests on either
# appears in it or has no provenance at all.
#
# This is a lexical judge — deterministic, offline (invariant 1) — and it
# says so. It measures whether the words a sentence asserts WITH are in the
# excerpts, not whether the excerpt logically entails the sentence. Its
# recall on the audit's three unsupported shapes is total and measured in
# tests/skills/research_engine/test_verify_claim.py. Its known limits, also
# measured there: a faithful paraphrase sharing few words with its source
# grades `partial`, never `not_supported`, unless a name or a figure is
# missing; and a sentence whose every word is in the excerpt but whose
# RELATION is wrong ("the Supervisory Committee is chaired by Paul Martin"
# when the excerpt chairs the Technology Committee) passes — the challenger
# reads relations, this reads words.

VERIFY_VERDICTS = ("entailed", "partial", "not_supported", "frame")
#: Content-word coverage lines, measured on the battery in test_verify_claim:
#: every supported probe clears 0.70, the paraphrase probe sits at 0.44, the
#: committee-structure probe at 0.33. 0.70 / 0.40 separate the three.
ENTAILED_FLOOR = 0.70
PARTIAL_FLOOR = 0.40

#: Words a sentence does not assert WITH: function words, plus the H2 frame
#: the contract mandates on every synthesis (the score, the median, the
#: band, the inventory of items). A figure or a word in the frame register
#: is derived from the score table, not from a source, and is not verified
#: against one — a synthesis that says "sits at 2.5 against a peer median
#: of 3.0" is obeying its contract, not citing a document.
_CLAIM_STOP = frozenset("""
a an and are as at be by for from has have how in is it its of on or that
the this to was what when where which who with does do did their they also
than into over under within across both each more most not no but so if
then one two own per via about after before since while would could should
may might can will been being were had having there these those such some
any all only just very up out new now here where already still yet rather
whether because though although between through during without against
""".split())
_FRAME = frozenset("""
score scores scored scoring sits sitting sit median medians peer peers
band bands cohort grain rounded activating building competing
differentiating threshold thin evidence item items cited cites citation
citations source sources grounded rests speaks position inches rendered
above below at
""".split())
_LABELS = frozenset("""
fact inference hypothesis ceiling_estimate not_run no_finding unverified
current aging stale archival t1 t2 t3 t4
""".split())
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"\u201c(\[A-Z0-9])")
_WORDTOK = re.compile(r"[A-Za-z][A-Za-z0-9'\u2019&-]*|[$\u00a3\u20ac]?\d[\d,]*(?:\.\d+)?%?")
_NUMTOK = re.compile(r"^[$\u00a3\u20ac]?\d[\d,]*(?:\.\d+)?%?$")
_SCORE_SHAPED = re.compile(r"^\d\.\d{1,2}$")
_QUOTED = re.compile(r"[\"\u201c]([^\"\u201d]{3,})[\"\u201d]")


def _stem(w: str) -> str:
    """A light suffix strip, so 'reached' meets 'reach' and 'members'
    meets 'member'. Not a stemmer — enough for containment, never for
    meaning."""
    w = w.lower().strip("'\u2019-&")
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _plain_number(tok: str) -> str:
    return tok.replace(",", "").strip("$\u00a3\u20ac").rstrip("%")


def claim_tokens(sentence: str, *, entity: str | None = None) -> dict:
    """What ONE sentence asserts with: `content` (stemmed content words and
    figures) and `hard` (the subset a source must carry verbatim — figures,
    names, quoted phrases). The entity's own name is exempt: it is the
    subject of every sentence and need not be in every excerpt."""
    text = _CITATION.sub(" ", sentence or "")
    ent = {_stem(t) for t in _WORDTOK.findall(entity or "") if len(t) > 2}
    words = _WORDTOK.findall(text)
    lows = [w.lower() for w in words]
    frame_hit = any(w in _FRAME for w in lows)
    content, hard, score_numbers = set(), set(), set()
    for i, tok in enumerate(words):
        low = lows[i]
        if _NUMTOK.match(tok):
            plain = _plain_number(tok)
            if (frame_hit and _SCORE_SHAPED.match(plain)
                    and not tok.startswith(("$", "\u00a3", "\u20ac"))
                    and not tok.endswith("%") and float(plain) <= 5.0):
                score_numbers.add(plain)    # the rendered score, not a claim
                continue
            content.add(plain)
            hard.add(plain)
            continue
        if low in _FRAME or low in _LABELS or low in _CLAIM_STOP:
            continue
        st = _stem(low)
        if len(st) < 3 or st in ent:
            continue
        content.add(st)
        # A capitalised token past the sentence's first word is a name (an
        # acronym anywhere is one too). A name at sentence start is missed
        # as a NAME and still counted as a content word — a stated limit.
        if tok[0].isupper() and (i > 0 or tok.isupper()):
            hard.add(st)
    for m in _QUOTED.finditer(text):
        for w in _WORDTOK.findall(m.group(1)):
            st = _stem(w)
            if len(st) >= 3 and w.lower() not in _CLAIM_STOP and st not in ent:
                content.add(st)
                hard.add(st)
    return {"content": content, "hard": hard, "frame": frame_hit,
            "score_numbers": score_numbers}


def _ground(excerpts) -> tuple[set, list[str]]:
    """The stemmed vocabulary of every excerpt, and the excerpts' sentences
    (for the span report)."""
    vocab: set = set()
    sentences: list[str] = []
    for ex in excerpts or []:
        s = str(ex or "")
        if not s.strip():
            continue
        for tok in _WORDTOK.findall(s):
            if _NUMTOK.match(tok):
                vocab.add(_plain_number(tok))
            else:
                vocab.add(_stem(tok))
        sentences.extend(p.strip() for p in _SENT_SPLIT.split(s) if p.strip())
    return vocab, sentences


def verify_sentence(sentence: str, excerpts, *, entity: str | None = None) -> dict:
    """One sentence against the excerpts it is cited on."""
    ct = claim_tokens(sentence, entity=entity)
    vocab, sents = _ground(excerpts)
    content, hard = ct["content"], ct["hard"]
    if not content and not hard:
        return {"text": sentence, "verdict": "frame", "coverage": None,
                "missing": [], "missing_hard": [], "span": None,
                "note": "no checkable content — the score frame or a connective"}
    missing = sorted(w for w in content if w not in vocab)
    missing_hard = sorted(w for w in hard if w not in vocab)
    coverage = round(1.0 - len(missing) / len(content), 3) if content else 1.0
    if missing_hard or coverage < PARTIAL_FLOOR:
        verdict = "not_supported"
    elif coverage >= ENTAILED_FLOOR:
        verdict = "entailed"
    else:
        verdict = "partial"
    span, best = None, 0
    for s in sents:
        hit = len(content & {_stem(t) if not _NUMTOK.match(t) else _plain_number(t)
                             for t in _WORDTOK.findall(s)})
        if hit > best:
            best, span = hit, s[:240]
    return {"text": sentence, "verdict": verdict, "coverage": coverage,
            "missing": missing, "missing_hard": missing_hard, "span": span}


_WORST = {"not_supported": 3, "partial": 2, "entailed": 1, "frame": 0}


def verify_claim(text: str, excerpts, *, entity: str | None = None) -> dict:
    """Every sentence of `text` against `excerpts`; the verdict is the worst
    sentence's. A `frame`-only text (nothing checkable) reports `frame`."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(str(text or "").strip())
                 if s.strip()]
    rows = [verify_sentence(s, excerpts, entity=entity) for s in sentences]
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERIFY_VERDICTS}
    verdict = max((r["verdict"] for r in rows), key=lambda v: _WORST[v], default="frame")
    return {"verdict": verdict, "sentences": rows, "counts": counts,
            "floors": {"entailed": ENTAILED_FLOOR, "partial": PARTIAL_FLOOR}}


def verify_cell(cell: dict, *, entity: str | None = None) -> dict:
    """An H2 `cells[]` row against its own `items[].excerpt`. A cell with no
    items and a synthesis that asserts content is `not_supported` by
    construction — unless it is a declared absence (thin + sources_searched +
    closure_condition), which asserts what was NOT found and is not
    verified against excerpts it does not have."""
    items = cell.get("items") or []
    excerpts = [str(i.get("excerpt") or "") for i in items if isinstance(i, dict)]
    excerpts += [str(i.get("anchor_quote") or "") for i in items
                 if isinstance(i, dict) and i.get("anchor_quote")]
    declared = (cell.get("thin") is True and bool(cell.get("sources_searched"))
                and bool(str(cell.get("closure_condition") or "").strip()))
    if declared and not excerpts:
        return {"subcap_id": cell.get("subcap_id"), "verdict": "frame",
                "grade": "declared", "sentences": [], "counts": {},
                "note": "a declared absence is verified by its ladder, not by excerpts"}
    out = verify_claim(str(cell.get("synthesis") or ""), excerpts, entity=entity)
    out["subcap_id"] = cell.get("subcap_id")
    out["grade"] = "cited" if excerpts else "uncited"
    return out


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
