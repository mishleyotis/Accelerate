"""NER wrappers: PERSON/ORG/TITLE/MONEY/PERCENT/DATE/CARDINAL + FSI patterns.

Why: leadership rosters, acquisition frames, ticker scoping and
firmographics recovery all need the same entity extraction, and the
audits showed each script re-inventing it (667 leadership rows with
parentheticals in names, acquisition FPs, garbled regulator values).
spaCy NER is the primary tier; MONEY/PERCENT always come from
deterministic regexes (spaCy's spans drop the ``$`` and offsets drift),
and executive TITLES are pure patterns because ``en_core_web_sm`` has no
TITLE label. Every item carries ``{text, start, end, norm}`` where
``norm`` is the machine-usable value (float USD for money, float for
percents, ISO date string, canonical title acronym).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.nlp.dates import resolve_event_date

_KEYS = ("persons", "orgs", "titles", "money", "percents", "dates", "cardinals")

_MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:MM|K|M|B|T|bn|k|m|mm|tn"
    r"|billion|million|thousand|trillion)?\b\+?|\$\s?\d[\d,]*(?:\.\d+)?",
)
_PCT_RE = re.compile(r"[+\-~≈]?\d+(?:\.\d+)?\s?%")

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

# --- executive titles -----------------------------------------------------

_CSUITE_ACRONYMS = (
    "CEO|CFO|CTO|CIO|COO|CMO|CRO|CISO|CHRO|CDO|CAO|CCO|CLO|CPO|CXO"
)
_TITLE_RE = re.compile(
    r"\b("
    r"Chief\s+[A-Z][a-zA-Z]+(?:\s+(?:and\s+|&\s+)?[A-Z][a-zA-Z]+)?\s+Officer"
    rf"|{_CSUITE_ACRONYMS}"
    r"|(?:Executive|Senior)\s+Vice\s+President(?:\s+of\s+[A-Z][\w &]*)?"
    r"|Vice\s+President(?:\s+of\s+[A-Z][\w &]*)?"
    r"|EVP|SVP|VP(?:\s+of\s+[A-Z][\w &]*)?"
    r"|Managing\s+Director|Director(?:\s+of\s+[A-Z][\w &]*)?"
    r"|President|Chairman|Chairwoman|General\s+Counsel"
    r"|Head\s+of\s+[A-Z][\w &]*"
    r")\b"
)

# "Jane Doe, CTO" / "Jane Q. Doe, Chief Risk Officer" — apposition ties a
# person to a title even when the NER model misses one of them.
_APPOSITION_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)+)\s*,\s*"
    r"(?:the\s+)?(?=(?:Chief|C[A-Z]{1,3}\b|EVP|SVP|VP|Executive|Senior|Vice|Managing|"
    r"Director|President|Head\b))"
)

_TITLE_CANON: dict[str, str] = {
    "chief executive officer": "CEO",
    "chief financial officer": "CFO",
    "chief technology officer": "CTO",
    "chief information officer": "CIO",
    "chief operating officer": "COO",
    "chief marketing officer": "CMO",
    "chief risk officer": "CRO",
    "chief information security officer": "CISO",
    "chief human resources officer": "CHRO",
    "chief data officer": "CDO",
    "chief digital officer": "CDO",
    "executive vice president": "EVP",
    "senior vice president": "SVP",
    "vice president": "VP",
}

# --- regex fallbacks (spaCy unavailable) ----------------------------------

_ORG_SUFFIX_RE = re.compile(
    r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4}\s+"
    r"(?:Bank|Bancorp|Bancshares|Credit\s+Union|Financial|Insurance|Holdings|Group|"
    r"Inc\.?|Corp\.?|Corporation|Company|Co\.?|LLC|LLP|Ltd\.?|Partners|Capital|Trust))\b"
)
_DATE_FALLBACK_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
    r"(?:\s+\d{1,2},?)?\s+\d{4}\b"
    r"|\bQ[1-4]\s*(?:FY)?\s*\d{4}\b|\bFY\s?\d{4}\b|\b(?:19|20)\d{2}\b"
)
_CARDINAL_FALLBACK_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b")


def _nlp() -> Any:  # deferred — avoids circular import at package init
    from app.services.nlp import get_nlp

    return get_nlp()


def parse_money(text: str) -> float | None:
    """Normalize a money span to float USD ("$2.4M" → 2400000.0), else None."""
    if not text:
        return None
    m = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s?(MM|K|M|B|T|bn|k|m|mm|tn|billion|million|thousand|trillion)?",
        text,
    )
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    return value * _MULTIPLIERS.get(suffix, 1.0)


def parse_percent(text: str) -> float | None:
    """Normalize a percent span to a signed float ("+23.8%" → 23.8)."""
    m = re.search(r"([+\-]?)\s?(\d+(?:\.\d+)?)\s?%", text or "")
    if not m:
        return None
    value = float(m.group(2))
    return -value if m.group(1) == "-" else value


def parse_number(text: str) -> float | None:
    """Normalize a cardinal span ("1,800" → 1800.0), else None."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _canon_title(text: str) -> str:
    key = re.sub(r"\s+", " ", text.strip()).lower()
    for phrase, acronym in _TITLE_CANON.items():
        if key.startswith(phrase):
            return acronym
    return text.strip()


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s < end and start < e for s, e in spans)


def _date_norm(span_text: str) -> str | None:
    resolved, precision = resolve_event_date(span_text)
    if resolved is not None and precision in {"day", "month", "quarter", "year"}:
        return resolved.isoformat()
    return None


def extract(text: str) -> dict[str, list[dict]]:
    """Extract all entity families from ``text``.

    Returns ``{persons, orgs, titles, money, percents, dates, cardinals}``
    where every item is ``{text, start, end, norm}``. Never raises;
    empty input → empty lists.
    """
    out: dict[str, list[dict]] = {k: [] for k in _KEYS}
    if not text or not text.strip():
        return out

    taken: list[tuple[int, int]] = []  # money/percent spans — cardinals must not re-match

    for m in _MONEY_RE.finditer(text):
        out["money"].append(
            {"text": m.group(0), "start": m.start(), "end": m.end(),
             "norm": parse_money(m.group(0))}
        )
        taken.append((m.start(), m.end()))
    for m in _PCT_RE.finditer(text):
        out["percents"].append(
            {"text": m.group(0), "start": m.start(), "end": m.end(),
             "norm": parse_percent(m.group(0))}
        )
        taken.append((m.start(), m.end()))

    for m in _TITLE_RE.finditer(text):
        out["titles"].append(
            {"text": m.group(1), "start": m.start(1), "end": m.end(1),
             "norm": _canon_title(m.group(1))}
        )

    seen_persons: set[str] = set()
    for m in _APPOSITION_RE.finditer(text):
        name = m.group(1)
        seen_persons.add(name.lower())
        out["persons"].append(
            {"text": name, "start": m.start(1), "end": m.end(1),
             "norm": re.sub(r"\s+", " ", name)}
        )

    nlp = _nlp()
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            item = {"text": ent.text, "start": ent.start_char, "end": ent.end_char,
                    "norm": None}
            if ent.label_ == "PERSON":
                if ent.text.lower() in seen_persons:
                    continue
                item["norm"] = re.sub(r"\s+", " ", ent.text.strip())
                out["persons"].append(item)
            elif ent.label_ == "ORG":
                # sm-model quirk: "CTO of Acme Bank" gets tagged ORG — keep
                # the org part out of title-led spans.
                if _TITLE_RE.match(ent.text):
                    continue
                item["norm"] = ent.text.strip().rstrip(".,;")
                out["orgs"].append(item)
            elif ent.label_ == "DATE":
                item["norm"] = _date_norm(ent.text)
                out["dates"].append(item)
            elif ent.label_ == "CARDINAL":
                if _overlaps(ent.start_char, ent.end_char, taken):
                    continue
                item["norm"] = parse_number(ent.text)
                out["cardinals"].append(item)
            elif ent.label_ == "MONEY":
                if _overlaps(ent.start_char, ent.end_char, taken):
                    continue
                item["norm"] = parse_money(ent.text)
                out["money"].append(item)
                taken.append((ent.start_char, ent.end_char))
            elif ent.label_ == "PERCENT":
                if _overlaps(ent.start_char, ent.end_char, taken):
                    continue
                item["norm"] = parse_percent(ent.text)
                out["percents"].append(item)
                taken.append((ent.start_char, ent.end_char))
    else:
        for m in _ORG_SUFFIX_RE.finditer(text):
            out["orgs"].append(
                {"text": m.group(1), "start": m.start(1), "end": m.end(1),
                 "norm": m.group(1).strip().rstrip(".,;")}
            )
        date_spans: list[tuple[int, int]] = []
        for m in _DATE_FALLBACK_RE.finditer(text):
            out["dates"].append(
                {"text": m.group(0), "start": m.start(), "end": m.end(),
                 "norm": _date_norm(m.group(0))}
            )
            date_spans.append((m.start(), m.end()))
        for m in _CARDINAL_FALLBACK_RE.finditer(text):
            if _overlaps(m.start(), m.end(), taken) or _overlaps(m.start(), m.end(), date_spans):
                continue
            out["cardinals"].append(
                {"text": m.group(0), "start": m.start(), "end": m.end(),
                 "norm": parse_number(m.group(0))}
            )

    for key in _KEYS:
        out[key].sort(key=lambda item: (item["start"], item["end"]))
    return out
