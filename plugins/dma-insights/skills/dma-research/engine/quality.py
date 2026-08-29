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


def _norm_q(q) -> str:
    return re.sub(r"\s+", " ", str(q or "")).strip().lower()


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
_CITATION = re.compile(r"\[[^\]]*\]")   # [E-0001:F2] — ids are not figures

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
    for tok in _NUM_TOKEN.findall(_CITATION.sub(" ", text or "")):
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


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
