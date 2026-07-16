"""The quality gate every enrichment passes before it is stored.

The operator contract: an enrichment must read like consultant prose, stay
grounded, and NEVER brush a contradiction under the rug. So each enrichment's
human text is:

  * CLEANED — ingest annotation stripped, whitespace normalized, no trailing
    debris (reuses evidence_hygiene.clean_finding_text);
  * DE-ESCALATED IN TONE — accusatory / editorializing words a Zennify AE would
    never say to a prospect ("failure", "negligent", "poor", "lagging", "guilty")
    are rewritten to neutral, factual consultant language;
  * CONTRADICTION-CHECKED — when an enriched figure conflicts with a value the
    client corpus already asserts, the conflict is SURFACED (a note the caller
    stores / logs), not silently dropped or silently overwritten.

Pure + dependency-light so it runs in any enrichment persist path and in tests.
"""
from __future__ import annotations

import re

from app.services.nlp.evidence_hygiene import clean_finding_text

# Accusatory / editorializing term → neutral, factual consultant phrasing. The
# AE is pitching a prospect: findings are framed as opportunities and gaps, never
# as blame. Word-boundary, case-insensitive; the replacement keeps the sentence
# grammatical.
_TONE_MAP: tuple[tuple[str, str], ...] = (
    (r"\bfailures?\b", "gaps"),
    (r"\bfailing\b", "underperforming"),
    (r"\bfailed to\b", "has not yet"),
    (r"\bnegligent(?:ly)?\b", "under-resourced"),
    (r"\bnegligence\b", "under-investment"),
    (r"\bincompeten(?:t|ce)\b", "capability gaps"),
    (r"\bpoor(?:ly)?\b", "limited"),
    (r"\blagging\b", "trailing peers"),
    (r"\blags\b", "trails peers"),
    (r"\bguilty\b", "responsible"),
    (r"\bwrongdoing\b", "the issue"),
    (r"\bmismanag(?:ed|ement)\b", "under-managed"),
    (r"\bterrible\b", "materially limited"),
    (r"\bawful\b", "materially limited"),
    (r"\bdisastrous\b", "high-risk"),
    (r"\bneglected\b", "deprioritized"),
    (r"\bbroken\b", "not yet functional"),
)
_TONE_RES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.I), r) for p, r in _TONE_MAP)
# A number (optionally $ / % / unit) for the contradiction magnitude check.
_NUM_RE = re.compile(r"-?\$?\s*([\d,]+(?:\.\d+)?)\s*([bmkt%]|billion|million|thousand)?",
                     re.I)
_MULT = {"b": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6,
         "k": 1e3, "thousand": 1e3, "t": 1e12}


def tone_flags(text: str) -> list[str]:
    """The accusatory terms present in ``text`` (empty ⇒ already consultant-grade)."""
    return sorted({m.group(0).lower()
                   for rx, _ in _TONE_RES for m in rx.finditer(text or "")})


def soften_tone(text: str) -> str:
    """Rewrite accusatory / editorializing language to neutral consultant phrasing.
    Preserves the fact; only the framing changes."""
    out = text or ""
    for rx, repl in _TONE_RES:
        out = rx.sub(repl, out)
    return re.sub(r"\s{2,}", " ", out).strip()


def vet_text(text: str | None) -> tuple[str, list[str]]:
    """Clean + de-escalate one enrichment string. Returns (consultant_grade_text,
    tone_flags_found). The flags let the caller log WHAT was softened (audit /
    storyline review) rather than hiding it."""
    cleaned = clean_finding_text(text)
    flags = tone_flags(cleaned)
    return soften_tone(cleaned), flags


def _as_number(s: str | None) -> float | None:
    m = _NUM_RE.search(str(s or ""))
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return n * _MULT.get((m.group(2) or "").lower(), 1.0)


def contradiction(enriched: str | None, known: str | None,
                  *, tol: float = 0.15) -> str | None:
    """Surface a conflict between an enriched value and a value the corpus already
    asserts. Returns a human note when they disagree beyond ``tol`` (relative, for
    numbers) or differ as non-empty text, else None. The caller STORES the note so
    the contradiction is visible — never silently resolved."""
    e, k = (enriched or "").strip(), (known or "").strip()
    if not e or not k:
        return None
    en, kn = _as_number(e), _as_number(k)
    if en is not None and kn is not None:
        if kn == 0:
            return None
        if abs(en - kn) / abs(kn) > tol:
            return (f"CONTRADICTION: enriched value '{e}' conflicts with the "
                    f"corpus value '{k}' (>{tol:.0%} apart) — surfaced for review, "
                    f"the existing value was kept.")
        return None
    # non-numeric: a genuine textual disagreement (not one containing the other)
    if e.lower() not in k.lower() and k.lower() not in e.lower():
        return (f"CONTRADICTION: enriched '{e}' differs from corpus '{k}' — "
                f"surfaced for review.")
    return None
