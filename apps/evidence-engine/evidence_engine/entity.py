"""Entity match: is this page about THIS institution?

WHY. A filing about a related entity may evidence structure and never the
other entity's capability (source_rules "A relation is not a capability"),
and parent and subsidiary, or two credit unions with one word in common,
share tokens. The card therefore carries `entity_match` with a basis a
challenger can check, and only `confirmed` may feed tech-stack /
firmographic surfaces (CARD-CONTRACT.md §3).

THE RULE.
  confirmed  the page is on the entity's own domain; OR the legal name (or
             an alias) appears AND one of {location, charter number, CIK,
             ticker} the EntityRef supplies appears; OR a regulator / filing
             page names the legal name verbatim.
  probable   the legal name or a distinctive alias appears, no second
             identifier.
  ambiguous  shared tokens only ("Example Credit Union" is not "Example
             Federal Credit Union" unless exact or aliased).
Matching is case-insensitive, whitespace-normalised and word-bounded
(textnorm.normalise on both sides). Pure.
"""
from __future__ import annotations

import re

from . import registry
from .textnorm import normalise
from .types import Document, EntityRef

_SECOND_ID_TYPES = ("regulator", "filing")


def _phrase(p: str) -> re.Pattern:
    words = [re.escape(w) for w in normalise(p).split(" ") if w]
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])")


def _present(p: str | None, text: str) -> bool:
    p = normalise(p or "")
    return bool(p) and bool(_phrase(p).search(text))


def _distinctive(alias: str) -> bool:
    """An alias worth a `probable` on its own: two or more words, or one
    word of six or more characters that is not a generic institution noun."""
    a = normalise(alias)
    words = a.split(" ")
    generic = {"bank", "credit", "union", "federal", "financial", "group", "trust",
               "insurance", "capital", "savings", "national", "first", "community"}
    if len(words) >= 2:
        return any(w not in generic for w in words)
    return len(a) >= 6 and a not in generic


def _charter_present(charter: str, text: str) -> bool:
    c = normalise(charter)
    if not c:
        return False
    if re.search(r"charter\s*(?:no\.?|number|#)?\s*:?\s*" + re.escape(c) + r"(?![0-9])", text):
        return True
    return bool(re.search(r"(?<![0-9])" + re.escape(c) + r"(?![0-9])", text)) and "charter" in text


def _cik_present(cik: str, text: str) -> bool:
    digits = re.sub(r"\D", "", cik or "")
    if not digits:
        return False
    stripped = digits.lstrip("0") or "0"
    pat = r"(?<![0-9])0*" + re.escape(stripped) + r"(?![0-9])"
    return bool(re.search(r"cik\W{0,12}" + pat, text)) or (bool(re.search(pat, text)) and "cik" in text)


def match(doc: Document, entity: EntityRef, registry_info: dict | None = None) -> tuple[str, str]:
    """-> (verdict, basis); verdict ∈ confirmed | probable | ambiguous."""
    info = registry_info or {}
    url = doc.final_url or doc.url
    if registry.is_own_host(url, entity) or info.get("source_type") == "entity_owned":
        return "confirmed", f"page is on the entity's own domain ({registry.host_of(url)})"
    text = normalise(" ".join(x for x in (doc.title, doc.text) if x))
    legal = _present(entity.legal_name, text)
    alias_hit = next((a for a in (entity.aliases or ()) if _present(a, text)), None)
    if legal or alias_hit:
        named = "legal name" if legal else f"alias {alias_hit!r}"
        seconds = []
        if entity.location and _present(entity.location, text):
            seconds.append("location")
        if entity.charter and _charter_present(entity.charter, text):
            seconds.append("charter number")
        if entity.cik and _cik_present(entity.cik, text):
            seconds.append("CIK")
        if entity.ticker and _present(entity.ticker, text):
            seconds.append("ticker")
        if seconds:
            return "confirmed", f"{named} and {' + '.join(seconds)} on page"
        if legal and info.get("source_type") in _SECOND_ID_TYPES:
            return "confirmed", f"{info['source_type']} page names the legal name verbatim"
        if legal or (alias_hit and _distinctive(alias_hit)):
            return "probable", f"{named} on page, no second identifier"
    # shared tokens only
    legal_tokens = [t for t in normalise(entity.legal_name).split(" ") if t]
    page_tokens = set(re.findall(r"[a-z0-9]+", text))
    shared = [t for t in legal_tokens if t in page_tokens]
    if shared:
        return "ambiguous", f"shared tokens only: {', '.join(shared)} — legal name not matched"
    return "ambiguous", "entity not named on page"
