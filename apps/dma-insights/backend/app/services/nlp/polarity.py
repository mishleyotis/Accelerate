"""Negation/absence detection, signal polarity, event-vs-baseline gating.

Why: the context audit found "NEGATIVE SEARCH RESULT: No formal
enforcement orders…" rendered as a red regulatory EVENT — the exact
opposite of what the researcher recorded. Three primitives fix that
class everywhere:

- :func:`is_negated_absence` — recognizes researcher negative-search
  phrasing ("no evidence of", "not named", "NEGATIVE SEARCH", …) so
  clean-standing notes are never promoted as incidents.
- :func:`signal` — lexicon polarity with local negation flip; a negated
  ABSENCE of something bad ("no formal enforcement orders") reads as
  positive clean standing, not negative.
- :func:`is_event` — True only for DATED occurrences with an event verb
  (launched/acquired/fined/…); baselines/obligations ("must maintain"),
  hypotheticals ("would enable"), analyst notes, and negated absences
  are all excluded, so timeline dots represent things that happened.
"""
from __future__ import annotations

import re

from app.services.nlp.dates import resolve_event_date

_ABSENCE_RE = re.compile(
    r"no\s+evidence\s+(?:of|that)|not\s+named|negative\s+search|"
    r"no\s+formal\s+enforcement|absence\s+of|no\s+record\s+of|not\s+party\s+to|"
    r"no\s+publicly\s+named|internal\s+alternative|could\s+not\s+identify|"
    r"none\s+identified|no\s+public\s+record|not\s+identified|no\s+indication\s+of|"
    # 2026-07 audit: "NCUA Enforcement Actions database search: NO actions,
    # consent orders, or prohibitions found" was promoted as a NEGATIVE
    # regulatory event — the "NO actions" phrasing wasn't covered.
    r"no\s+(?:new\s+|formal\s+|public\s+|regulatory\s+)?(?:enforcement\s+)?actions?\b|"
    # 2026-07-13 UFCU sample vetting: "VALIDATED CLEAN (Jun 2026): … does
    # NOT appear in NCUA Administrative Orders …, and no UFCU-specific
    # data breach appears in current breach trackers" became a timeline
    # EVENT and then a false live-order why-now signal ("remediation
    # clock running"). Researcher clean-verification conventions:
    r"validated\s+clean|does?\s+not\s+appear\b|do\s+not\s+appear\b|"
    r"no\s+\S{2,20}-specific\b|"
    r"no\s+[\w /-]{0,40}(?:posting|listing|filing|record)s?\s+"
    r"(?:currently\s+)?(?:indexed|listed|posted|found)\b|"
    # 2026-07-13 corpus QA: "NO FINTRAC enforcement action found against …"
    # and "No breach notification letter, no regulatory enforcement action,
    # no … statement found" ran through the remediation-order template — an
    # agency name / adjective between "no" and the noun defeated every
    # branch above. Generic absence shape: "no <short span> found".
    r"\bno\b[^.;\n]{0,60}\b(?:found|identified|located|surfaced)\b|"
    r"\bno\s+(?:data\s+)?breach\b",
    re.IGNORECASE,
)

_POSITIVE_RE = re.compile(
    r"\b(?:growth|grew|improv(?:ed|ing|ement)|launch(?:ed)?|award(?:ed)?|"
    r"expan(?:sion|ded)|strong|record|exceeded|surpassed|gains?|"
    r"partner(?:ship|ed|ing)s?|"
    r"promot(?:ed|ion)|raised|secured|momentum|upgrad(?:ed|e)|milestone|"
    r"profitable|won|outperform(?:ed)?|accelerat(?:ed|ing)|"
    # 2026-07 audit: resolution/clean-up verbs and hiring read as good news
    # ("consent order fully remediated", "VP Compliance Manager hired").
    # "court-appointed" (administrators/receivers) is litigation, not a hire.
    r"resolv(?:ed|es)|remediated|hir(?:ed|es|ing)|"
    r"(?<!court-)(?<!court\s)appoint(?:ed|ments?))\b",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"\b(?:fined?|fines|lawsuits?|breach(?:es)?|declin(?:e|ed|ing)|loss(?:es)?|"
    r"attrition|consent\s+order|penalt(?:y|ies)|outages?|layoffs?|churn|"
    r"downgrad(?:e|ed)|complaints?|violations?|weak(?:ness|ening)?|deficit|"
    r"enforcement|fraud|investigations?|deficienc(?:y|ies)|shortfall|"
    r"resignations?|departed|closures?|below|missed|underperform(?:ed|ing)?|"
    r"indict(?:ed|ments?)|litigation)\b",
    re.IGNORECASE,
)
_NEGATOR_RE = re.compile(r"\b(?:no|not|never|without|none)\b", re.IGNORECASE)

# Resolution verbs that close out a regulatory/legal negative. Deliberately
# past-tense/completed forms only — "requires remediation within 18 months"
# (an OPEN obligation) must never read as resolved.
_RESOLUTION_RE = re.compile(
    r"\b(?:terminat(?:ed|es|ing|ion)|remediated|fully\s+remediated|"
    r"remediation\s+complet\w+|resolv(?:ed|es)|lifted|closed\s+out|"
    r"satisfied|released\s+from)\b",
    re.IGNORECASE,
)
# The regulatory/legal negatives a resolution verb can govern. "consent
# order TERMINATED" is a positive clean-standing signal; "consent order
# ISSUED" stays negative because no resolution verb is present.
_REG_RESOLVABLE_RE = re.compile(
    r"consent\s+(?:order|decree)|enforcement(?:\s+action)?|"
    r"cease\s+and\s+desist|penalt(?:y|ies)|sanctions?|violations?|"
    r"deficienc(?:y|ies)|\bMRA\b|formal\s+agreement|written\s+agreement|"
    r"lawsuits?|complaints?|investigations?",
    re.IGNORECASE,
)
# Background-context frames: a negative noun that only situates the event in
# time ("VP Compliance Manager hired AFTER consent order", "risk governance
# response to enforcement action") is context, not the event's polarity.
_CONTEXT_FRAME_RE = re.compile(
    r"\b(?:after|following|(?:in\s+)?response\s+to|post-|in\s+the\s+wake\s+of)\b",
    re.IGNORECASE,
)

_EVENT_VERB_RE = re.compile(
    r"\b(?:launched|completed|hired|appointed|acquired|closed|announced|fined|"
    r"migrated|deployed|opened|merged|partnered|signed|raised|crossed)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL_RE = re.compile(
    r"\b(?:would|could|might|hypothetical(?:ly)?|plans?\s+to|intends?\s+to|"
    r"expect(?:s|ed)?\s+to|aims?\s+to|considering|exploring|if)\b",
    re.IGNORECASE,
)
_OBLIGATION_RE = re.compile(
    r"\b(?:must|shall|is\s+required\s+to|are\s+required\s+to|obligated\s+to|"
    r"is\s+subject\s+to\s+ongoing)\b",
    re.IGNORECASE,
)
_ANALYST_NOTE_RE = re.compile(
    r"\b(?:analyst\s+note|we\s+believe|we\s+assess|in\s+our\s+view|our\s+view|"
    r"likely\s+(?:to|reflects?)|may\s+(?:be|indicate|suggest)|appears\s+to)\b",
    re.IGNORECASE,
)


def is_negated_absence(text: str) -> bool:
    """True when the text records that something was NOT found/present.

    Catches researcher negative-search conventions ("NEGATIVE SEARCH
    RESULT:", "no formal enforcement", "internal alternative", "could
    not identify", …) case-insensitively. These rows must never surface
    as incidents/events.
    """
    return bool(text) and bool(_ABSENCE_RE.search(text))


def _hits_with_negation_flip(text: str) -> tuple[int, int]:
    """(positive, negative) lexicon hits; a nearby negator flips a hit.

    A negative hit sitting in a background-context frame ("hired AFTER
    consent order", "response to enforcement action") is skipped entirely —
    it situates the event, it is not the event's polarity.
    """
    pos = neg = 0
    for regex, is_positive in ((_POSITIVE_RE, True), (_NEGATIVE_RE, False)):
        for m in regex.finditer(text):
            window = text[max(0, m.start() - 24) : m.start()]
            if not is_positive and _CONTEXT_FRAME_RE.search(
                text[max(0, m.start() - 30) : m.start()]
            ):
                continue
            flipped = bool(_NEGATOR_RE.search(window))
            if is_positive != flipped:
                pos += 1
            else:
                neg += 1
    return pos, neg


def _is_resolved_regulatory(text: str) -> bool:
    """True when a resolution verb governs a regulatory/legal negative.

    "Fed has TERMINATED a consent order" / "CFPB consent order fully
    REMEDIATED" / "RESOLVED 2022 CFPB Consent Order" — the order noun and
    a non-negated resolution verb must co-occur within a ±100-char window,
    so "consent order issued … remediation required within 18 months"
    (open obligation, verb form not in the lexicon) stays negative.
    """
    for m in _REG_RESOLVABLE_RE.finditer(text):
        window = text[max(0, m.start() - 100) : m.end() + 100]
        for r in _RESOLUTION_RE.finditer(window):
            lookback = window[max(0, r.start() - 24) : r.start()]
            if not _NEGATOR_RE.search(lookback):
                return True
    return False


def signal(text: str) -> str:
    """Classify polarity → ``"positive" | "neutral" | "negative"``.

    Negation-aware: "no decline" counts positive, "not improved" counts
    negative, and a negated absence of something bad ("no formal
    enforcement orders") is clean standing → positive. A RESOLVED
    regulatory negative ("consent order terminated/remediated/lifted")
    is likewise a positive clean-standing signal — the 2026-07 audit
    found 12 pack events rendering consent-order terminations as red.
    """
    if not text or not text.strip():
        return "neutral"
    if is_negated_absence(text):
        # Absence OF a negative (enforcement, order, fine…) = clean standing.
        return "positive" if _NEGATIVE_RE.search(text) else "neutral"
    if _is_resolved_regulatory(text):
        return "positive"
    # A PLANNED/scheduled operational step ("Friday all branches closed;
    # weekend system integration; Monday reopen as Beacon Bank") is
    # execution of a milestone, not bad news — the 2026-07-13 Beacon
    # vetting shipped "All branches closed [negative]" from a planned
    # conversion-weekend outage.
    if re.search(r"\b(?:planned|scheduled|conversion|migration|cutover|"
                 r"integration weekend|reopen)\b", text, re.I) and re.search(
                 r"\bclos(?:ed|ing|ure)s?\b|\boutage\b", text, re.I):
        return "neutral"
    pos, neg = _hits_with_negation_flip(text)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# Event kinds that carry an INHERENT polarity when the claim text has no
# sentiment word of its own. On a digital-evolution timeline an acquisition, a
# product launch, or a partnership is unambiguously a forward step, but the
# underlying claim is often bare ("Acquired Fizz Bank (2023)"), so a NEUTRAL
# lexicon reading falls back to the kind's own polarity. Leadership is
# deliberately NOT here: a bare appointment ("Named J. Roe to the board") is a
# neutral fact — only an explicit hire/appointment/promotion (caught by the
# positive lexicon) or a departure (negative lexicon) colours it, so leadership
# gets a real three-way spread instead of an all-green wall. Founding /
# DMA-assessment / generic milestone and routine-regulatory kinds likewise
# stay neutral (the lexicon already flags enforcement, fines and losses).
_KIND_DEFAULT_SIGNAL = {
    "acquisition": "positive",
    "product": "positive",
    "partnership": "positive",
}


def signal_for_kind(text: str, kind: str | None) -> str:
    """Kind-aware polarity: the lexicon reading of ``text``, falling back to
    the event ``kind``'s inherent polarity when the text carries no sentiment
    word of its own.

    Only a NEUTRAL lexicon reading is overridden — an explicit positive or
    negative always wins, so a distressed/forced acquisition or a departed
    executive keeps its true polarity. Kinds absent from the default map
    (milestone, regulatory, regulatory_standing, …) keep the neutral reading.
    """
    base = signal(text)
    if base != "neutral":
        return base
    return _KIND_DEFAULT_SIGNAL.get((kind or "").strip().lower(), "neutral")


def is_event(text: str) -> bool:
    """True only for a dated occurrence with an event verb.

    Excludes: negated absences (nothing happened), obligations/baselines
    ("must maintain BSA/AML"), hypotheticals ("would enable", "plans
    to"), analyst notes ("we believe"), undated claims, and negated
    verbs ("did not launch"). This is the timeline promotion gate.
    """
    if not text or not text.strip():
        return False
    if is_negated_absence(text):
        return False
    if _OBLIGATION_RE.search(text) or _ANALYST_NOTE_RE.search(text):
        return False
    if _HYPOTHETICAL_RE.search(text):
        return False
    verb = _EVENT_VERB_RE.search(text)
    if not verb:
        return False
    lookback = text[max(0, verb.start() - 24) : verb.start()]
    if _NEGATOR_RE.search(lookback):
        return False
    _resolved, precision = resolve_event_date(text)
    return precision in {"day", "month", "quarter", "year"}
