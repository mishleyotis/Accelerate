"""Query expansion per facet, and the vendor-name guard.

WHY. One templated query per question is the audit's own query-fidelity
finding (AUD-0074); the plugin's retrieval fuses several differently-shaped
probes per diagnostic question (engine/retrieval.plan_queries), and the
card records which facet queries retrieved a page (`provenance.facet_hints`,
`provenance.query_ids` — CARD-CONTRACT.md §3). And a vendor or platform
name may never be INJECTED into a query: the research must find the
estate, not confirm a guess (DISCOVERY.md §1 "agnostic_lint", §6 last
bullet). The only exception is evidence-led: a name that came from a card
may be followed up, and the card id is recorded beside the exception.

THE RULE.
  expand(): the five facet queries (works / fails / value / contradicts /
  corroborates) — the entity's legal name quoted + the question's content
  words + the facet's committed operators — then `site:` variants for the
  entity's own domains and for the regulator / trade-press pack the caller
  passes, capped at 12, ids Q-01… in that order. Same input, same output.
  guard(): every query is matched, word-bounded and case-insensitive,
  against registry/platform_names.txt. A name with no originating card is
  a violation and the query is dropped; a name the caller maps to a card_id
  is an exception, kept and logged. guard(guard(q)) == guard(q).

Pure: no network, no model.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .contract import FACETS
from .types import EntityRef

_NAMES_PATH = Path(__file__).resolve().parent.parent / "registry" / "platform_names.txt"

MAX_QUERIES = 12

#: One lens word per facet. Measured 2026-10-11 on golden v1 (15 misses):
#: the former OR-chains ("launched OR offers OR deployed OR implemented")
#: surfaced 1 of 15 on SearXNG and 0 on Parallel; the same questions as
#: concise keyword queries surfaced 7 and 2. Parallel's own schema asks for
#: "concise keyword search queries, 3-6 words each"; SearXNG hands a query
#: to Google CSE / Bing, which read OR-chains as noise. Operators are gone;
#: a facet contributes ONE word.
FACET_LENS = {
    "works": "launches",
    "fails": "complaint",
    "value": "results",
    "contradicts": "discontinued",
    "corroborates": "announcement",
}
#: Kept for callers that still read the old name (the lens, not a chain).
FACET_OPERATORS = FACET_LENS

_STOP = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that "
    "the this to was what when where which who with does do did their they "
    "there these those than then into onto over under about after before".split())
#: The graded stems every diagnostic question shares — carrying them makes
#: every probe the same probe (retrieval.plan_queries keeps the same list).
_GENERIC = frozenset(
    "extent formal documented established defined reviewed since today trace "
    "earliest signal refreshes stalls organization organisation well whether "
    "any currently current institution entity".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'&.-]*")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(str(text or "").lower()) if t not in _STOP]


def question_focus(question: str, entity: EntityRef, limit: int = 8) -> str:
    """The question's informative words, in order, minus the entity's own
    tokens and the scaffolding every question shares."""
    ent = set(_tokens(entity.legal_name)) | {t for a in (entity.aliases or ()) for t in _tokens(a)}
    seen: list[str] = []
    for t in _tokens(question):
        if t in ent or t in _GENERIC or t in seen:
            continue
        seen.append(t)
        if len(seen) >= limit:
            break
    return " ".join(seen)


def _quote(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip().replace('"', "")
    return f'"{s}"' if s else ""


def expand(question: str, entity: EntityRef, facet: str | None = None,
           sub_vertical: str | None = None, domains_pack: list[str] | None = None,
           ) -> list[dict]:
    """-> [{query_id, text, facet, kind}] — kind ∈ facet | alias | tail | site_own | site_pack.

    Every query is concise: the entity (quoted legal name, or its short
    alias) plus 2–5 focus words and at most one lens word. Variants differ
    in WHICH words they carry (head of the focus, tail of the focus, the
    alias), not in operators — that is what moved recall (see FACET_LENS)."""
    if facet is not None and facet not in FACETS:
        raise ValueError(f"facet {facet!r} not in {FACETS}")
    facets = [facet] if facet else list(FACETS)
    name = _quote(entity.legal_name)
    focus_terms = question_focus(question, entity).split()
    head = " ".join(focus_terms[:4])
    tail = " ".join(focus_terms[4:8])
    mid = " ".join(focus_terms[2:7])
    out: list[dict] = []

    def add(text: str, f: str, kind: str):
        text = re.sub(r"\s+", " ", text).strip()
        if text and all(q["text"] != text for q in out) and len(out) < MAX_QUERIES:
            out.append({"query_id": f"Q-{len(out) + 1:02d}", "text": text,
                        "facet": f, "kind": kind})

    for f in facets:
        add(" ".join(x for x in (name, head, FACET_LENS[f]) if x), f, "facet")
    own_facet = facet or "works"
    alias = short_alias(entity)
    if alias:
        add(" ".join(x for x in (alias, head or mid) if x), own_facet, "alias")
        if mid and mid != head:
            add(" ".join(x for x in (alias, mid) if x), own_facet, "alias")
    if tail:
        add(" ".join(x for x in (name, tail) if x), own_facet, "tail")
    for d in sorted({_bare(d) for d in (entity.domains or ()) if _bare(d)}):
        add(" ".join(x for x in (f"site:{d}", head) if x), own_facet, "site_own")
    pack_facet = facet or "corroborates"
    for d in [_bare(d) for d in (domains_pack or ()) if _bare(d)]:
        add(" ".join(x for x in (f"site:{d}", alias or name, " ".join(focus_terms[:2])) if x), pack_facet, "site_pack")
    return out


def short_alias(entity: EntityRef) -> str:
    """The shortest alias of 2–12 characters (the initialism or short form
    trade press and app stores use for the entity), or ''."""
    cands = [a.strip() for a in (entity.aliases or ()) if 2 <= len(a.strip()) <= 12]
    cands = [a for a in cands if a.lower() != (entity.legal_name or "").lower()]
    return min(cands, key=len) if cands else ""


def _bare(d) -> str:
    d = str(d or "").strip().lower()
    d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", d).split("/", 1)[0]
    return d[4:] if d.startswith("www.") else d


# ── the guard ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def platform_names() -> tuple[str, ...]:
    names = []
    for line in _NAMES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return tuple(sorted(set(names), key=lambda s: (-len(s), s.lower())))


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, re.Pattern], ...]:
    out = []
    for n in platform_names():
        words = [re.escape(w) for w in n.split()]
        out.append((n, re.compile(r"(?<![A-Za-z0-9])" + r"\s+".join(words) + r"(?![A-Za-z0-9])", re.I)))
    return tuple(out)


def find_names(text: str) -> list[str]:
    """Platform names present in `text`, longest first, each once."""
    found = []
    for n, pat in _patterns():
        if pat.search(text or "") and n not in found:
            found.append(n)
    return found


def guard(queries: list[dict], allow_names_from_cards: dict[str, list[str]] | None = None,
          ) -> tuple[list[dict], list[dict]]:
    """-> (clean_queries, violations). A violation is
    {query_id, text, name, kind: refused} (query dropped) or
    {query_id, text, name, kind: exception, card_id} (query kept)."""
    allow = {k.lower(): list(v) for k, v in (allow_names_from_cards or {}).items()}
    clean: list[dict] = []
    violations: list[dict] = []
    for q in queries:
        names = find_names(q.get("text", ""))
        refused = False
        for n in names:
            cards = allow.get(n.lower())
            if cards:
                violations.append({"query_id": q.get("query_id", ""), "text": q.get("text", ""),
                                   "name": n, "kind": "exception", "card_id": cards[0],
                                   "card_ids": list(cards)})
            else:
                violations.append({"query_id": q.get("query_id", ""), "text": q.get("text", ""),
                                   "name": n, "kind": "refused"})
                refused = True
        if not refused:
            clean.append(dict(q))
    return clean, violations
