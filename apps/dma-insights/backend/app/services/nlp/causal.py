"""WHAT / WHY / SO-WHAT discourse decomposition.

Why: the top-findings audit measured 0/378 findings carrying the
prototype's what/why/so_what blocks, and 97-98% of insight-card why/
so_what fields were one template. This module derives the three blocks
from the source prose itself: WHAT = the leading factual clauses, WHY =
clauses introduced by causal connectives (because, due to, driven by,
reflecting, as a result of, stems from, caused by — plus ``advcl``
dependents when spaCy is loaded), SO-WHAT = action/recommendation
clauses (should, recommend, next step, requires, would enable, must).

Non-destructive: the decomposition re-joins the ORIGINAL clauses into
fluent sentences (capitalized, terminally punctuated) — it never
paraphrases, so every number and entity stays verbatim. Absent blocks
are empty strings, letting callers fall back honestly instead of
emitting filler.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.nlp.segment import sentences

_CAUSAL_RE = re.compile(
    r"\b(?:because(?:\s+of)?|due\s+to|driven\s+by|reflecting|as\s+a\s+result\s+of|"
    r"stem(?:s|med)?\s+from|caused\s+by|owing\s+to|attributable\s+to)\b",
    re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"\b(?:should|recommend(?:s|ed)?|we\s+suggest|next\s+steps?|requires?|"
    r"would\s+enable|must|prioriti[sz]e|needs?\s+to)\b",
    re.IGNORECASE,
)


def _nlp() -> Any:  # deferred — avoids circular import at package init
    from app.services.nlp import get_nlp

    return get_nlp()


def _fluent(pieces: list[str]) -> str:
    """Join clause fragments into readable sentences (verbatim words)."""
    sents: list[str] = []
    for piece in pieces:
        piece = piece.strip(" \t,;:—–-")  # noqa: RUF001
        if not piece:
            continue
        piece = piece[0].upper() + piece[1:]
        if piece[-1] not in ".!?":
            piece += "."
        sents.append(piece)
    return " ".join(sents)


def _advcl_split(sent: str) -> tuple[str, str] | None:
    """spaCy path: split off a causal ``advcl`` subtree ("since …")."""
    nlp = _nlp()
    if nlp is None:
        return None
    doc = nlp(sent)
    for tok in doc:
        if tok.dep_ != "advcl":
            continue
        marks = [c for c in tok.children if c.dep_ == "mark" and c.lower_ in {"because", "since"}]
        if not marks:
            continue
        sub_idx = {t.i for t in tok.subtree}
        mark_idx = {m.i for m in marks}
        why = "".join(
            t.text_with_ws for t in doc if t.i in sub_idx and t.i not in mark_idx
        ).strip()
        main = "".join(t.text_with_ws for t in doc if t.i not in sub_idx).strip()
        if why:
            return main, why
    return None


def decompose(text: str) -> dict:
    """Decompose prose into ``{what, why, so_what}`` strings.

    Each sentence is routed whole-or-split: action cues send it to
    SO-WHAT; a causal connective splits it (effect → WHAT, cause → WHY);
    everything else is WHAT. Empty string per block when absent.
    """
    what_parts: list[str] = []
    why_parts: list[str] = []
    so_what_parts: list[str] = []
    if text and text.strip():
        for sent in sentences(text):
            if _ACTION_RE.search(sent):
                so_what_parts.append(sent)
                continue
            m = _CAUSAL_RE.search(sent)
            if m:
                before = sent[: m.start()].strip(" ,;")
                after = sent[m.end() :].strip(" ,;")
                if before:
                    what_parts.append(before)
                if after:
                    why_parts.append(after)
                continue
            advcl = _advcl_split(sent)
            if advcl:
                main, why = advcl
                if main:
                    what_parts.append(main)
                if why:
                    why_parts.append(why)
                continue
            what_parts.append(sent)
    return {
        "what": _fluent(what_parts),
        "why": _fluent(why_parts),
        "so_what": _fluent(so_what_parts),
    }
