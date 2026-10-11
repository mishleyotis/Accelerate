"""Verbatim excerpt selection — the minimal sentence-complete span that
carries the fact, with offsets and a hash, verified twice before it leaves.

THE RULES, AND WHERE EACH COMES FROM.
  * 50–500 characters, verbatim: `register_evidence` and
    `ledger.append_evidence` refuse anything else (invariant 4).
  * Sentence-complete, never a clause cut mid-word: the connector's
    `excerpt_clip.clause_truncated`, and the measured defect behind it (a
    producer read a vendor name out of a span the citable text did not
    contain). The gold index this engine is evaluated against carries 35
    such cuts; the engine emits none.
  * Prefer a figure, a date, a named capability over a generic sentence:
    the brief's excerpt-selection rule and the connector's own specificity
    factor (`register._specificity`: digits mark a quantified claim).
  * Boilerplate and marketing are filtered by a committed anti-pattern list
    (`registry/boilerplate.txt`), extended from measured defects.
  * ≤ 40 words is a preference weight, not a cap (docs/DISCOVERY.md §1).
  * The span must be present in BOTH texts (clean and connector-shaped),
    `doc.text[start:end] == excerpt` exactly, and
    `normalise(excerpt) in normalise(doc.verify_text)`.

Pure: term arithmetic over the sentence segmentation. No model, no network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .contract import EXCERPT_MAX, EXCERPT_MIN, excerpt_word_pressure, sentence_complete
from .textnorm import normalise, sentences, word_count

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
         "is", "are", "was", "were", "be", "as", "at", "it", "its", "this", "that",
         "from", "has", "have", "had", "does", "do", "did", "how", "what", "which",
         "who", "whom", "when", "where", "why", "their", "there", "than", "then",
         "into", "over", "under", "about", "any", "all", "not", "no", "yes", "can",
         "will", "would", "should", "could", "may", "might", "also", "such", "more"}

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-\.']*[a-z0-9]|[a-z0-9]", re.I)
_FIGURE = re.compile(r"(\$|€|£)\s?\d|\d[\d,]*(\.\d+)?\s?(%|percent|million|billion|thousand|bps|basis points)|\b\d{1,3}(,\d{3})+\b|\b(19|20)\d{2}\b|\b\d+(\.\d+)?\s?(members|customers|employees|branches|clients|accounts|users|locations|stars|reviews)\b", re.I)
_DATE_WORD = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b|\bQ[1-4]\b|\bfiscal\b|\b(FY|CY)\s?\d{2,4}\b", re.I)
_QUOTE = re.compile(r"[\"“”]")

_BOILERPLATE: list[re.Pattern] | None = None


def boilerplate_patterns(path: Path | None = None) -> list[re.Pattern]:
    global _BOILERPLATE
    if _BOILERPLATE is not None and path is None:
        return _BOILERPLATE
    p = path or Path(__file__).resolve().parents[1] / "registry" / "boilerplate.txt"
    pats = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pats.append(re.compile(line, re.I | re.M))
    if path is None:
        _BOILERPLATE = pats
    return pats


def boilerplate_match(span: str) -> str | None:
    for pat in boilerplate_patterns():
        if pat.search(span or ""):
            return pat.pattern
    return None


def terms(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "") if t.lower() not in _STOP and len(t) > 1}


@dataclass
class Candidate:
    start: int
    end: int
    text: str
    score: float
    hits: int
    has_figure: bool
    has_date: bool
    words: int
    reasons: list


def _score_sentence(sent: str, qterms: set[str], entity_terms: set[str]) -> tuple[float, int, bool, bool, list]:
    st = terms(sent)
    hits = len(st & qterms)
    ent = len(st & entity_terms)
    has_fig = bool(_FIGURE.search(sent))
    has_date = bool(_DATE_WORD.search(sent))
    reasons = []
    score = 0.0
    if qterms:
        score += 2.0 * hits / max(1, len(qterms))
        reasons.append(f"query_terms={hits}/{len(qterms)}")
    if ent:
        score += 0.5
        reasons.append("names_entity")
    if has_fig:
        score += 1.0
        reasons.append("figure")
    if has_date:
        score += 0.4
        reasons.append("date_word")
    if _QUOTE.search(sent):
        score += 0.2
        reasons.append("quote")
    w = word_count(sent)
    score -= 0.6 * excerpt_word_pressure(sent)
    if w < 6:
        score -= 0.8
        reasons.append("very_short")
    if sent[:1].islower():
        score -= 0.5
        reasons.append("lowercase_start")
    return score, hits, has_fig, has_date, reasons


def select(text: str, verify_text: str, question: str, *, entity_terms: set[str] | None = None,
           max_candidates: int = 5, min_hits: int = 1) -> list[Candidate]:
    """Ranked verbatim spans from `text` that also verify against
    `verify_text`. A span is a sentence, extended to a neighbour only to
    reach EXCERPT_MIN; never beyond EXCERPT_MAX; never through a boilerplate
    sentence; never with fewer than `min_hits` query terms."""
    if not text:
        return []
    qterms = terms(question)
    ent = entity_terms or set()
    spans = sentences(text)
    if not spans:
        return []
    scored = []
    for i, (s, e) in enumerate(spans):
        sent = text[s:e]
        sc, hits, fig, dat, reasons = _score_sentence(sent, qterms, ent)
        bp = boilerplate_match(sent)
        scored.append((i, s, e, sent, sc, hits, fig, dat, reasons, bp))
    norm_verify = normalise(verify_text or "")
    out: list[Candidate] = []
    seen: set[tuple[int, int]] = set()
    order = sorted(scored, key=lambda r: (-r[4], r[1]))
    for i, s, e, sent, sc, hits, fig, dat, reasons, bp in order:
        if bp or hits < min_hits or sc <= 0:
            continue
        if len(sent) > EXCERPT_MAX:
            continue
        start, end = s, e
        # extend to a neighbour until the minimum length is met
        j_prev, j_next = i - 1, i + 1
        while end - start < EXCERPT_MIN:
            choices = []
            if j_prev >= 0 and not scored[j_prev][9]:
                ps = spans[j_prev][0]
                if end - ps <= EXCERPT_MAX:
                    choices.append((scored[j_prev][4], "prev"))
            if j_next < len(spans) and not scored[j_next][9]:
                ne = spans[j_next][1]
                if ne - start <= EXCERPT_MAX:
                    choices.append((scored[j_next][4], "next"))
            if not choices:
                break
            choices.sort(key=lambda c: (-c[0], c[1] != "next"))
            if choices[0][1] == "next":
                end = spans[j_next][1]
                j_next += 1
            else:
                start = spans[j_prev][0]
                j_prev -= 1
        span = text[start:end]
        if not (EXCERPT_MIN <= len(span) <= EXCERPT_MAX):
            continue
        if not sentence_complete(span):
            continue
        if boilerplate_match(span):
            continue
        if (start, end) in seen:
            continue
        if normalise(span) not in norm_verify:
            continue
        seen.add((start, end))
        out.append(Candidate(start, end, span, round(sc, 4), hits, fig, dat,
                             word_count(span), reasons))
        if len(out) >= max_candidates:
            break
    return out


def verify_against_both(text: str, verify_text: str, start: int, end: int, excerpt: str) -> bool:
    """`text[start:end] == excerpt` exactly, and the span is in the
    connector-shaped text under the shared normalisation."""
    if start < 0 or end > len(text or "") or start >= end:
        return False
    if text[start:end] != excerpt:
        return False
    return normalise(excerpt) in normalise(verify_text or "")


def context_window(text: str, start: int, end: int, window_sentences: int = 2) -> tuple[int, int, str]:
    """The surrounding `window_sentences` sentences either side, for
    `expand_context` — on demand, never by default."""
    spans = sentences(text)
    if not spans:
        return start, end, text[start:end]
    idx_s = next((k for k, (s, e) in enumerate(spans) if e > start), 0)
    idx_e = next((k for k, (s, e) in enumerate(spans) if e >= end), len(spans) - 1)
    a = spans[max(0, idx_s - window_sentences)][0]
    b = spans[min(len(spans) - 1, idx_e + window_sentences)][1]
    return a, b, text[a:b]
