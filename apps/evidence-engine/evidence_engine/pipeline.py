"""URL → Document → cards. The one place a card is assembled.

`fetch_document` reads a URL through the store (cached text by url key,
TTL by recency class) or the fetcher (live, else Wayback), extracts the
two texts, dates the page, and stores text + sidecar. `build_cards` turns
ranked documents into contract-clean cards: registry hint → tier and
claim default, excerpt selection → verbatim span with offsets, entity
match, origin cluster, recency; a card that fails `contract.item_problems`
is dropped with its reason recorded, never repaired.

No model. No client-specific logic. Every decision is in the card's
`provenance` so a challenger can see it.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from . import contract as C
from . import dates as D
from . import dedupe, entity as E, excerpt as X, extract, registry
from .fetch import canonical_url, host_of, url_key
from .textnorm import normalise, sha256_text
from .types import Document, EntityRef, FetchResult

_ABBR: dict | None = None


def abbreviations() -> dict:
    global _ABBR
    if _ABBR is None:
        p = Path(__file__).resolve().parents[1] / "registry" / "abbreviations.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        _ABBR = {k: v for k, v in d.items() if not k.startswith("_")}
    return _ABBR


_ABBR_RE: re.Pattern | None = None


def expand_label(text: str) -> str:
    """Spell out abbreviations in a LABEL (never in a span) — CG-27."""
    global _ABBR_RE
    ab = abbreviations()
    if _ABBR_RE is None:
        _ABBR_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, ab), key=len, reverse=True)) + r")\b")
    return _ABBR_RE.sub(lambda m: ab[m.group(1)], text or "")


def recency_class(published: str | None, reference: _dt.date | None = None) -> str:
    return C.recency_band(published, reference)


def document_from_fetch(res: FetchResult, *, hits=None, today: _dt.date | None = None) -> Document | None:
    """Extract, date, hash. None when nothing citable came back."""
    if not res.ok:
        return None
    ex = extract.extract(res.body, res.content_type, res.final_url or res.url)
    if ex is None or not ex.text.strip():
        return None
    markup = res.body.decode("utf-8", errors="replace") if ex.kind == "html" else ""
    published, basis = D.published_date(markup, res.final_url or res.url, ex.text, today=today)
    archived = res.via == "archived"
    return Document(
        url=res.url, final_url=res.final_url or res.url, text=ex.text, verify_text=ex.verify_text,
        content_hash=sha256_text(ex.text), title=ex.title, published=published, published_basis=basis,
        content_type=res.content_type, url_status="archived" if archived else "live",
        original_url=res.url if archived else None, archive_timestamp=res.archive_timestamp,
        retrieved=res.retrieved_at or (today or _dt.date.today()).isoformat(),
        hits=list(hits or []), via=res.via)


def document_from_store(store, url: str) -> Document | None:
    key = url_key(url)
    h = store.find_text_by_url(key)
    if not h:
        return None
    got = store.get_text(h)
    if not got:
        return None
    text, meta = got
    vh = meta.get("verify_hash")
    verify = text
    if vh:
        v = store.get_text(vh)
        if v:
            verify = v[0]
    return Document(
        url=meta.get("url") or url, final_url=meta.get("final_url") or url, text=text, verify_text=verify,
        content_hash=h if h.startswith("sha256:") else "sha256:" + h, title=meta.get("title") or "",
        published=meta.get("published"), published_basis=meta.get("published_basis"),
        content_type=meta.get("content_type") or "", url_status=meta.get("url_status") or "live",
        original_url=meta.get("original_url"), archive_timestamp=meta.get("archive_timestamp"),
        retrieved=meta.get("retrieved") or "", via="cache")


def store_document(store, doc: Document, reference: _dt.date | None = None) -> str:
    rc = recency_class(doc.published, reference)
    vh = store.put_text(doc.verify_text, {"kind": "verify", "url": doc.url}, rc) if doc.verify_text != doc.text else None
    meta = {"url": doc.url, "url_key": url_key(doc.url), "final_url": doc.final_url, "title": doc.title,
            "published": doc.published, "published_basis": doc.published_basis,
            "content_type": doc.content_type, "url_status": doc.url_status,
            "original_url": doc.original_url, "archive_timestamp": doc.archive_timestamp,
            "retrieved": doc.retrieved, "verify_hash": vh, "host": host_of(doc.final_url or doc.url)}
    return store.put_text(doc.text, meta, rc)


async def fetch_document(url: str, fetcher, store, *, hits=None, today: _dt.date | None = None,
                         reference: _dt.date | None = None, use_cache: bool = True) -> tuple[Document | None, str | None]:
    """(Document, None) or (None, reason)."""
    url = canonical_url(url)
    if use_cache:
        cached = document_from_store(store, url)
        if cached is not None:
            cached.hits = list(hits or [])
            return cached, None
    res = await fetcher.get_or_archive(url)
    if not res.ok:
        return None, res.error or f"http {res.status}"
    doc = document_from_fetch(res, hits=hits, today=today)
    if doc is None:
        return None, "no extractable text (a scanned PDF, an empty page, or a binary)"
    store_document(store, doc, reference)
    return doc, None


def source_name_for(doc: Document, info: dict) -> str:
    host = host_of(doc.original_url or doc.final_url or doc.url)
    publisher = info.get("publisher") or host
    title = (doc.title or "").strip()
    title = re.sub(r"\s*[|\-–—:]\s*" + re.escape(publisher) + r"\s*$", "", title, flags=re.I)
    name = f"{publisher} — {title}" if title and title.lower() != publisher.lower() else publisher
    name = expand_label(name)
    return name[: C.SOURCE_NAME_MAX].rstrip(" —-")


def entity_terms(entity: EntityRef | None) -> set[str]:
    if entity is None:
        return set()
    words = set()
    for n in [entity.legal_name] + list(entity.aliases or []):
        words |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9&'.-]+", n or "") if len(w) > 2}
    return words - {"the", "and", "credit", "union", "bank", "federal", "inc", "corp", "financial", "group"}


_MATCH_ORDER = {"confirmed": 0, "probable": 0, "ambiguous": 1}


def build_cards(docs: list[Document], *, question: str, entity: EntityRef | None, facet: str | None,
                query_ids_by_key: dict[str, list[str]] | None = None, facets_by_key: dict[str, list[str]] | None = None,
                via_by_key: dict[str, str] | None = None, reference: _dt.date | None = None,
                today: _dt.date | None = None, max_cards: int = 8, per_doc: int = 1,
                rerouted: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """-> (cards, dropped). `docs` arrive in rank order."""
    clusters = dedupe.cluster(docs)
    synd = dedupe.syndication_counts(clusters)
    cards: list[dict] = []
    dropped: list[dict] = []
    seen_ids: set[str] = set()
    own_hosts = {d.lower() for d in (entity.domains if entity else [])}
    ab = abbreviations()
    today = today or _dt.date.today()
    # Rank order within each entity-match class, confirmed/probable first:
    # measured 2026-10-10, 37 % of cards were `ambiguous` (a namesake's
    # newsroom) and displaced probable ones when max_cards bound.
    # An archived page is classified and named by the page it is a copy OF
    # (its original host), never by web.archive.org; a live copy outranks an
    # archived one of the same standing.
    judged = []
    for doc in docs:
        info = registry.classify(doc.original_url or doc.final_url or doc.url, entity, source_name=doc.title)
        em, em_basis = E.match(doc, entity, info) if entity else ("ambiguous", "no entity supplied")
        judged.append(((_MATCH_ORDER.get(em, 9), doc.url_status == "archived"), doc, info, em, em_basis))
    judged.sort(key=lambda j: j[0])
    seen_excerpts: set[str] = set()
    for _, doc, info, em, em_basis in judged:
        key = url_key(doc.url)
        cands = X.select(doc.text, doc.verify_text, question, entity_terms=entity_terms(entity),
                         max_candidates=per_doc)
        if not cands:
            dropped.append({"url": doc.url, "reason": "no verbatim sentence-complete span answers the question"})
            continue
        for cand in cands:
            tier = info["tier"]
            item = C.Item(source_name=source_name_for(doc, info), source_url=doc.final_url or doc.url,
                          excerpt=cand.text, tier=tier, published_date=doc.published)
            item_d = item.__dict__.copy()
            problems = C.item_problems(item_d, own_hosts=own_hosts, abbreviations=ab)
            if problems:
                dropped.append({"url": doc.url, "reason": "; ".join(problems)})
                continue
            cid = C.card_id_for(item.source_url, item.excerpt)
            if cid in seen_ids:
                continue
            # the same words from a syndicated or archived copy are one card,
            # not two: syndication is never counted as corroboration
            if normalise(item.excerpt) in seen_excerpts:
                dropped.append({"url": doc.url, "reason": "same excerpt already carded from another copy (syndication is not corroboration)"})
                continue
            seen_excerpts.add(normalise(item.excerpt))
            seen_ids.add(cid)
            prov = C.Provenance(
                url_status=doc.url_status, original_url=doc.original_url,
                archive_timestamp=doc.archive_timestamp, retrieved=doc.retrieved or today.isoformat(),
                recency=C.recency_band(doc.published, reference), source_type_hint=info["source_type"],
                tier_basis=info["tier_basis"], excerpt_offsets=(cand.start, cand.end),
                content_hash=doc.content_hash,
                context_handle=C.context_handle_for(doc.content_hash, cand.start, cand.end),
                facet_hints=sorted(set((facets_by_key or {}).get(key, []) or ([facet] if facet else []))),
                query_ids=sorted(set((query_ids_by_key or {}).get(key, []))),
                origin_cluster=clusters.get(key, ""), syndication_count=synd.get(clusters.get(key, ""), 1),
                relevance=round(min(1.0, max(0.0, cand.score / 4.0)), 3), entity_match=em,
                entity_match_basis=em_basis, ladder_rung=info["ladder_rung"],
                via=(via_by_key or {}).get(key, doc.via or ""))
            if rerouted:
                prov.via = prov.via + ("," if prov.via else "") + ",".join(rerouted)
            card = C.Card(cid, item, prov).to_dict()
            card["provenance"]["host"] = host_of(doc.original_url or doc.final_url or doc.url)
            card["provenance"]["published_basis"] = doc.published_basis
            card["provenance"]["excerpt_words"] = cand.words
            cards.append(card)
            if len(cards) >= max_cards:
                return cards, dropped
    return cards, dropped


def trim_to_budget(cards: list[dict], token_budget: int | None) -> tuple[list[dict], int]:
    """Keep the leading cards whose compact serialisation fits the budget."""
    if not token_budget:
        return cards, C.estimate_tokens(cards)
    kept: list[dict] = []
    for c in cards:
        if C.estimate_tokens(kept + [c]) > token_budget and kept:
            break
        kept.append(c)
    return kept, C.estimate_tokens(kept)
