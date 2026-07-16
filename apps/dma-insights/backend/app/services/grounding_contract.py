"""The generation grounding contract (Training Spec Tab 01 §2.3).

The prompt receives only run-scoped extracts, enrichment items, AE notes, and
the field's gold-standard rules; it must cite an E-ID for every factual
clause, mark INFERENCE/HYPOTHESIS-derived clauses, and emit
``REFUSE-INSUFFICIENT-EVIDENCE`` rather than pad. A generated sentence with
no citation and no refusal is auto-rejected pre-render.

``should_refuse`` is the pre-call gate (don't ask the model what the
evidence cannot answer); the existing fabricated-E-ID validator remains the
post-call gate. Refusal probes (``qa_refusal_probes``) must pass >= 98% on
unanswerable questions and 0% false-refusals on answerable controls.
"""
from __future__ import annotations

import re

from app.services.nlp import semantic

REFUSAL_SENTINEL = "REFUSE-INSUFFICIENT-EVIDENCE"

CONTRACT_BLOCK = (
    "Grounding contract: cite a resolving E-ID (or SEC-ID) for every factual "
    "clause. Prefix clauses derived by inference with 'INFERENCE:' and "
    "speculative clauses with 'HYPOTHESIS:'. If the evidence cannot support "
    f"the answer, reply with the single token {REFUSAL_SENTINEL} instead of "
    "padding or generalizing.\n"
)

_QUANTITY_RE = re.compile(
    r"how\s+much|how\s+many|revenue|assets\b|budget|cost\b|number\s+of|"
    r"what\s+%|what\s+percentage|headcount", re.I)

# Field-anchored verification: a quantity/fact question is answerable only
# when a relevant item lexically anchors the asked field (a bundle stating
# "assets of $4.2B" does not establish *revenue*). numeric=True additionally
# requires a digit in the anchoring item.
_FIELD_ANCHORS: list[tuple[re.Pattern, re.Pattern, bool]] = [
    (re.compile(r"revenue|net\s+income|turnover", re.I),
     re.compile(r"revenue|net\s+income|turnover|net\s+interest\s+income", re.I), True),
    (re.compile(r"ticker|stock\s+symbol", re.I),
     re.compile(r"ticker|NYSE|NASDAQ|OTC|traded\s+under|symbol", re.I), False),
    (re.compile(r"how\s+many\s+branches|branches\s+does", re.I),
     re.compile(r"branch(es)?|locations?|offices?", re.I), True),
    (re.compile(r"founded|founding\s+year|established", re.I),
     re.compile(r"found(ed|ing)|establish(ed|ment)|since\s+(18|19|20)\d{2}",
                re.I), True),
    (re.compile(r"\bclouds?\b", re.I),
     re.compile(r"\bAWS\b|Azure|Google\s+Cloud|\bGCP\b", re.I), False),
    (re.compile(r"headcount|employees\b|staff\s+count", re.I),
     re.compile(r"employees?|headcount|staff|FTEs?", re.I), True),
]

_shared_index: semantic.SemanticIndex | None = None


def _relevance(question: str, text: str) -> float:
    global _shared_index
    if _shared_index is None:
        _shared_index = semantic.SemanticIndex()
    return _shared_index.relevance(question, text)


def should_refuse(question: str, bundle: list[dict], *,
                  min_support: float = 0.18,
                  min_items: int = 1) -> tuple[bool, str]:
    """Decide whether the evidence bundle can honestly answer the question.

    Refuses on: an empty bundle; no bundle item topically relevant to the
    question; or a quantity question whose relevant items carry no number.
    """
    rows = [str(r.get("text") or r.get("excerpt") or "").strip()
            for r in (bundle or [])]
    rows = [t for t in rows if t]
    if len(rows) < min_items:
        return True, "empty_bundle"
    scored = [(t, _relevance(question, t)) for t in rows]
    relevant = [t for t, s in scored if s >= min_support]
    if not relevant:
        return True, "no_relevant_evidence"
    for q_re, anchor_re, numeric in _FIELD_ANCHORS:
        if not q_re.search(question or ""):
            continue
        anchored = [t for t in relevant if anchor_re.search(t)]
        if numeric:
            anchored = [t for t in anchored if any(ch.isdigit() for ch in t)]
        if not anchored:
            return True, "fact_not_established"
        return False, ""
    if _QUANTITY_RE.search(question or "") and not any(
            any(ch.isdigit() for ch in t) for t in relevant):
        return True, "quantity_without_numbers"
    return False, ""


def refusal_answer(reason: str) -> str:
    detail = {
        "empty_bundle": "no evidence on file addresses this",
        "no_relevant_evidence": "the evidence on file doesn't cover this",
        "quantity_without_numbers":
            "the evidence on file doesn't state this figure",
    }.get(reason, "the evidence on file can't verify this")
    return (
        f"Not established - {detail}, and I won't infer it. "
        "I can run a targeted enrichment search (G9) to try to resolve this "
        "datapoint, or log it as a discovery question for the next call. "
        f"{REFUSAL_SENTINEL}"
    )
