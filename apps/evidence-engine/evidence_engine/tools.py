"""The six tools (brief §3), as plain async functions over one Engine.

    research_brief   question(s) → ranked cards + coverage block
    crawl_entity     the institution's own pages → cards + crawl manifest
    filings_evidence 10-K/10-Q/8-K sections + XBRL facts → cards
    expand_context   the sentences around a card's span, on demand
    verify_cards     liveness + verbatim-offset + date re-check
    coverage_report  per-facet / per-label counts, concentration, saturation

Every tool takes a token budget where a budget is meaningful and returns a
`tokens` estimate. The engine never links a cell, labels a claim beyond the
licensed default, or resolves a conflict. When no free source can answer
(every free backend disabled or breaker-open) `research_brief` returns a
structured `needs_spend_approval` result and spends nothing.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import re
import time
from dataclasses import dataclass, field

from . import contract as C
from . import coverage as COV
from . import crawl as CR
from . import entity as E
from . import excerpt as X
from . import filings as F
from . import pipeline as P
from . import query as Q
from . import ratelimit as RL
from . import registry
from . import rank as R
from . import search as S
from .config import settings
from .fetch import HttpFetcher, host_of, url_key
from .store import Store, store as default_store
from .textnorm import normalise
from .types import Document, EntityRef

PAID_SOURCES = ("tavily", "exa", "firecrawl", "brave_api", "mojeek_api")


def _bare_domain(x) -> str:
    """The domain as the caller named it, minus a leading `www.` PREFIX.

    `str.lstrip("www.")` strips the CHARACTERS w and '.', not the prefix:
    measured 2026-10-14 on AAA Western and Central New York, whose domain
    `westerncentralnyaaa.com` became `esterncentralnyaaa.com`. Every
    `site:` probe then asked about a domain that does not exist and
    `registry.is_own_host` stopped recognising the club's own pages, so
    the collectors were handed national-AAA and sister-club cards instead.
    Any client whose domain starts with w (Webster, Wintrust, WSFS …) was
    exposed the same way."""
    d = str(x or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0]
    return d.removeprefix("www.")


def entity_ref(d: dict | None) -> EntityRef | None:
    if not d:
        return None
    return EntityRef(legal_name=str(d.get("legal_name") or d.get("name") or ""),
                     domains=[_bare_domain(x) for x in (d.get("domains") or [])],
                     aliases=list(d.get("aliases") or []), location=d.get("location"),
                     charter=d.get("charter"), cik=d.get("cik"), ticker=d.get("ticker"),
                     sub_vertical=d.get("sub_vertical"))


def _ref_date(v) -> _dt.date | None:
    return C.iso_date(v) if v else None


class _SearchCache:
    """fan_out's get/put over the store's search table (24h TTL)."""

    def __init__(self, store: Store):
        self._s = store

    def get(self, key):
        return self._s.get_search(str(key))

    def put(self, key, value):
        self._s.put_search(str(key), value)


#: Hits per host admitted before the rest of the list is considered.
PER_HOST_CAP = 3
#: Concurrent fetches in a brief's slice (per-host politeness still 1/s).
FETCH_WORKERS = 12


def _host_diverse_order(hits: list[dict], entity: EntityRef | None = None,
                        question: str | None = None) -> list[dict]:
    """Hit order for the fetch slice.

    Measured 2026-10-11 (eval v1 iteration 3): with 18 queries over two
    backends a brief fuses ~140 hits, and 17 of 35 golden URLs were in the
    list — at rank 1 of SOME list in most cases — yet never fetched: a
    twelve-slot slice in fused order fetches one rank-1 page per list and
    the entity-name band no longer discriminates once every query names
    the entity. The order is therefore: the entity's own host, then hits
    naming the entity ranked by how many of the question's terms their
    title + snippet carry, then the rest; within a band the fused order
    holds, and no host takes more than PER_HOST_CAP of the leading slots
    (the overflow back-fills, still in order)."""
    qterms = X.terms(question or "")

    def names_entity(h: dict) -> int:
        if entity is None:
            return 1
        if registry.is_own_host(h.get("url"), entity):
            return 2
        hay = normalise(" ".join(str(h.get(k) or "") for k in ("title", "snippet", "url")))
        names = [entity.legal_name] + list(entity.aliases or [])
        return 1 if any(normalise(n) and normalise(n) in hay for n in names) else 0

    def overlap(h: dict) -> float:
        if not qterms:
            return 0.0
        hay = X.terms(" ".join(str(h.get(k) or "") for k in ("title", "snippet")))
        return len(hay & qterms) / len(qterms)

    banded = sorted(enumerate(hits), key=lambda ih: (-names_entity(ih[1]), -round(overlap(ih[1]), 2), ih[0]))
    seen: dict[str, int] = {}
    head, tail = [], []
    for _, h in banded:
        host = host_of(h["url"])
        n = seen.get(host, 0)
        (head if n < PER_HOST_CAP else tail).append(h)
        seen[host] = n + 1
    return head + tail


#: A `questions[]` entry: a plain string, or an object naming the cells the
#: question is asked for. `facet` on an object is the caller's label (the
#: plugin's primary|works|fails|value|contradicts|corroborates); only the
#: five engine lenses narrow the query expansion — `primary` and anything
#: else widen to every lens, as a call-wide `facet=None` does.
def _question_specs(questions, call_facet: str | None) -> tuple[list[dict], str | None]:
    specs: list[dict] = []
    for i, q in enumerate(questions or []):
        if isinstance(q, dict):
            text = str(q.get("question") or q.get("text") or "").strip()
            cells = [str(c).strip() for c in (q.get("subcap_ids") or q.get("cells") or []) if str(c).strip()]
            label = q.get("facet")
            label = str(label).strip().lower() if label else None
        elif isinstance(q, str):
            text, cells, label = q.strip(), [], None
        else:
            return [], f"questions[{i}] must be a string or an object with `question`"
        if not text:
            continue
        if any(len(c) > 40 or " " in c for c in cells):
            return [], f"questions[{i}].subcap_ids must be short cell ids (no spaces, <= 40 chars)"
        lens = label if label in C.FACETS else call_facet
        specs.append({"index": i, "question": text, "subcap_ids": cells,
                      "facet": label or call_facet, "lens": lens})
    return specs, None


@dataclass
class Engine:
    fetcher: HttpFetcher | None = None
    store: Store | None = None
    searx: S.SearxClient | None = None
    parallel: S.ParallelClient | None = None
    filings_provider: object | None = None
    today: _dt.date | None = None
    registry_pack: list[str] = field(default_factory=list)
    #: the last brief's fused hit list (diagnostics; not returned by any tool)
    last_hits: list[dict] = field(default_factory=list)
    #: the registries' API client (find_registrant), opened on first use
    _registry_http: object | None = None

    def __post_init__(self):
        st = settings()
        if self.store is None:
            self.store = default_store()
        if self.fetcher is None:
            self.fetcher = HttpFetcher()
        if self.searx is None and st.searxng_url:
            import httpx
            from . import gcp_auth
            auth = gcp_auth.MetadataIdTokenAuth(st.searxng_url) if st.searxng_id_token else None
            self.searx = S.SearxClient(gcp_auth.searxng_base(st.searxng_url, st.searxng_path_token),
                                       httpx.AsyncClient(timeout=20, auth=auth),
                                       pool=S.EnginePool(S.engine_rates_from(st.searxng_engines),
                                                         per_query=st.searxng_engines_per_query))
        if self.parallel is None and st.parallel_enabled and st.parallel_mcp_url:
            self.parallel = S.ParallelClient(st.parallel_mcp_url)
        if not self.registry_pack:
            from . import registry as REG
            try:
                reg = REG.load()
                self.registry_pack = []        # resolved per sub-vertical at brief time (registry.site_pack)
            except Exception:  # noqa: BLE001
                self.registry_pack = []

    # ── helpers ─────────────────────────────────────────────────────────
    async def _bucket_wait(self, host: str) -> None:
        await RL.limits().host(host).acquire()

    async def _source_wait(self, source: str) -> None:
        """A SEARCH call's limiter is its SOURCE's bucket (searxng 4/s burst
        4, parallel 1.4/s burst 2 — settings). Until 2026-10-11 the fan-out
        was handed `_bucket_wait`, the per-WEBSITE politeness bucket (1/s,
        burst 1) keyed by the source's name, and the source buckets were
        never acquired at all: every brief searched at 1 call/s per backend
        per instance, and sixteen workflows queued behind it."""
        await RL.limits().source(source).acquire()

    async def _sec_wait(self) -> None:
        await RL.limits().source("sec").acquire()

    def _free_sources_available(self) -> list[str]:
        out = []
        br = RL.breakers()
        if self.searx is not None and br.get("searxng").allow():
            out.append("searxng")
        if self.parallel is not None and br.get("parallel").allow():
            out.append("parallel")
        return out

    def _spend_refusal(self, reason: str) -> dict:
        return {"needs_spend_approval": True, "cards": [], "reason": reason,
                "free_sources": RL.breakers().snapshot(),
                "paid_options": list(PAID_SOURCES),
                "note": "The engine never spends silently. Approve a paid source explicitly "
                        "(owner decision) or wait for a free source's breaker to close."}

    async def _documents_for_hits(self, hits: list[dict], *, limit: int, reference, hits_by_key,
                                  entity: EntityRef | None = None, question: str | None = None) -> tuple[list[Document], list[dict]]:
        """Fetch up to `limit` ATTEMPTED documents from the hit list, in hit order.

        Measured 2026-10-10 (eval v1): the own-domain `site:` query floods the top
        of the fused list with one host, and robots/breaker refusals consumed
        the slots, so a brief could spend its whole slice on a host it could
        never read. Two rules: at most `PER_HOST_CAP` hits per host are taken
        before the rest of the list is considered (the skipped ones back-fill
        when the list is short), and a hit refused before any bytes moved
        (robots, an open breaker, a never-fetch host) refunds its slot."""
        docs: list[Document] = []
        failures: list[dict] = []
        queue = _host_diverse_order(hits, entity, question)
        counted = 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal counted
            while True:
                async with lock:
                    if counted >= limit or not queue:
                        return
                    h = queue.pop(0)
                    counted += 1
                if registry.never_fetch(h["url"]):
                    async with lock:
                        counted -= 1
                    failures.append({"url": h["url"], "reason": "never_fetch host (not evidence-grade; slot refunded)"})
                    continue
                doc, why = await P.fetch_document(h["url"], self.fetcher, self.store,
                                                  hits=hits_by_key.get(h["url_key"], []),
                                                  today=self.today, reference=reference)
                if doc is None:
                    if why and (why.startswith("robots_disallowed") or why.startswith("breaker_open")):
                        async with lock:
                            counted -= 1
                        why = why + " (slot refunded)"
                    failures.append({"url": h["url"], "reason": why})
                else:
                    docs.append(doc)

        if not hits:
            return docs, failures
        tasks = [asyncio.ensure_future(worker()) for _ in range(min(FETCH_WORKERS, max(1, limit)))]
        done, pending = await asyncio.wait(tasks, timeout=settings().fetch_phase_budget_s)
        for tk in pending:
            tk.cancel()
        for tk in done:
            exc = tk.exception()
            if exc is not None:
                failures.append({"url": "?", "reason": f"{type(exc).__name__}: {str(exc)[:80]}"})
        if pending:
            failures.append({"url": f"{len(pending)} worker(s)",
                             "reason": f"fetch_phase_budget: still fetching after {settings().fetch_phase_budget_s:g}s — cancelled"})
        # deterministic order: the hit order, not completion order
        order = {h["url_key"]: i for i, h in enumerate(hits)}
        docs.sort(key=lambda d: order.get(url_key(d.url), 1 << 30))
        return docs, failures

    # ── 1 · research_brief ───────────────────────────────────────────────
    async def research_brief(self, *, run_id: str, entity: dict, questions: list,
                             sub_vertical: str | None = None, facet: str | None = None,
                             subcap_labels: list[str] | None = None, max_cards: int = 8,
                             token_budget: int = 2400, provenance: str = "standard",
                             reference_date: str | None = None,
                             allow_names_from_cards: dict | None = None,
                             fetch_limit: int = 20, source_classes: list[str] | None = None) -> dict:
        """One call for a whole capability batch. `questions` is a list of
        plain strings (one combined brief, as before) or of objects
        `{question, subcap_ids[], facet?}` — one per cell question. With
        objects the engine fans every question's queries out in ONE search
        pass, fetches ONE slice, then ranks and cards PER QUESTION, so each
        card comes back with `item.linked_subcap_ids` = the cells the caller
        named for the question it answered, and `by_question` says which
        questions got no card (the collector's `nothing_found` material).
        `max_cards` and `token_budget` are per question in that mode. The
        engine never invents a cell: the ids are the caller's, echoed.

        `source_classes` (⊆ contract.SOURCE_TYPES) makes it a per-class
        brief: the probes are `site:` over the registry's hosts for those
        classes (registry.class_pack, the sub-vertical's own pack first,
        rotated across questions), and a hit is kept only when it classifies
        into one of them (registry.in_classes) — the plugin's
        find_regulator_record_evidence, find_job_posting_evidence and their
        siblings."""
        t0 = time.monotonic()
        ent = entity_ref(entity)
        if ent is None or not ent.legal_name:
            return {"error": "entity.legal_name is required", "cards": []}
        if facet is not None and facet not in C.FACETS:
            return {"error": f"facet must be one of {C.FACETS}", "cards": []}
        classes = [str(c).strip().lower() for c in (source_classes or ()) if str(c).strip()]
        off = [c for c in classes if c not in C.SOURCE_TYPES]
        if off:
            return {"error": f"source_classes {off} not in {C.SOURCE_TYPES}", "cards": []}
        ref = _ref_date(reference_date)
        specs, bad = _question_specs(questions, facet)
        if bad:
            return {"error": bad, "cards": []}
        if not specs:
            return {"error": "at least one question is required", "cards": []}
        batched = len(specs) > 1 or any(s["subcap_ids"] for s in specs)
        question = " ".join(s["question"] for s in specs).strip()
        # queries, guarded: one pass over every question, each question's
        # share capped so a batch of twelve cells still fits one fan-out
        pack = self.registry_pack or registry.site_pack(sub_vertical)
        cpack = registry.class_pack(classes, sub_vertical) if classes else []
        per_q = Q.per_question_budget(len(specs))
        queries, seen_text = [], set()
        for n, spec in enumerate(specs):
            if classes:
                # rotate the class pack so a batch's questions probe different
                # hosts (two probes per host), and count a question's share
                # AFTER de-duplication: the bare `site:<host> "<name>"` probe
                # is shared across the batch and runs once
                k = (n * max(1, per_q // 2)) % len(cpack) if cpack else 0
                planned = [q for q in Q.expand_for_classes(spec["question"], ent, spec["lens"],
                                                           cpack[k:] + cpack[:k], classes)
                           if q["text"] not in seen_text]
            else:
                planned = Q.expand(spec["question"], ent, spec["lens"], sub_vertical, pack)
            for q in planned[:per_q]:
                if q["text"] in seen_text:
                    continue
                seen_text.add(q["text"])
                q["query_id"] = f"Q-{len(queries) + 1:02d}"
                q["question_index"] = spec["index"]
                queries.append(q)
        queries, violations = Q.guard(queries, allow_names_from_cards)
        free = self._free_sources_available()
        if not free:
            out = self._spend_refusal("no free search source is available: SearXNG and Parallel are "
                                      "disabled or breaker-open")
            out["queries"] = queries
            out["guard_violations"] = violations
            return out
        t_search = time.monotonic()
        fan = await S.fan_out(queries, searx=self.searx if "searxng" in free else None,
                              parallel=self.parallel if "parallel" in free else None,
                              run_id=run_id, bucket_wait=self._source_wait, cache=_SearchCache(self.store),
                              breakers=RL.breakers(), question=question,
                              budget_s=settings().search_phase_budget_s)
        configured = [n for n, c in (("searxng", self.searx), ("parallel", self.parallel)) if c is not None]
        for src in configured:
            if src not in free and f"rerouted_from:{src}" not in fan["rerouted"]:
                fan["rerouted"].append(f"rerouted_from:{src}")
        hits = fan["hits"]
        class_filtered = 0
        if classes:
            kept_hits = [h for h in hits if registry.in_classes(h["url"], ent, classes, cpack)]
            class_filtered = len(hits) - len(kept_hits)
            hits = kept_hits
        # In-process diagnostics only (the eval harness reads it to tell a
        # discovery miss from a fetch loss); never part of the tool answer.
        self.last_hits = [{"url": h["url"], "url_key": h["url_key"], "sources": list(h.get("sources") or [])} for h in hits]
        hits_by_key = {h["url_key"]: h.get("hits", []) for h in hits}
        t_fetch = time.monotonic()
        docs, failures = await self._documents_for_hits(hits, limit=fetch_limit, reference=ref,
                                                        hits_by_key=hits_by_key, entity=ent, question=question)
        if classes:   # a redirect can land off-class: the card's own URL decides
            off_class = [d for d in docs if not registry.in_classes(d.url, ent, classes, cpack)]
            class_filtered += len(off_class)
            docs = [d for d in docs if d not in off_class]
        t_rank = time.monotonic()
        qids = {h["url_key"]: h.get("query_ids", []) for h in hits}
        facets = {h["url_key"]: h.get("facets", []) for h in hits}
        via = {h["url_key"]: ",".join(h.get("sources", [])) for h in hits}
        by_key = {url_key(d.url): d for d in docs}

        def _cards_for(text: str, lens: str | None):
            rk = R.rank_chunks(text, docs, top_k=max_cards * 3, facet_text=lens or "")
            order = []
            for r in rk["ranked"]:
                if r["url_key"] not in order:
                    order.append(r["url_key"])
            ordered = [by_key[k] for k in order if k in by_key] + [d for k, d in by_key.items() if k not in order]
            cs, dr = P.build_cards(ordered, question=text, entity=ent, facet=lens,
                                   query_ids_by_key=qids, facets_by_key=facets, via_by_key=via,
                                   reference=ref, today=self.today, max_cards=max_cards,
                                   rerouted=fan.get("rerouted") or [])
            return rk, cs, dr

        by_question = []
        if not batched:
            ranked, cards, dropped = _cards_for(question, facet)
        else:
            # Rank and card per question over the ONE fetched slice; a card
            # that answers two questions is one card carrying both cells.
            ranked, cards, dropped, index_of = None, [], [], {}
            for spec in specs:
                rk, cs, dr = _cards_for(spec["question"], spec["lens"])
                ranked = ranked or rk
                dropped += dr
                ids = []
                for c in cs:
                    cid = c["card_id"]
                    if cid in index_of:
                        c = cards[index_of[cid]]
                    else:
                        index_of[cid] = len(cards)
                        cards.append(c)
                        c["provenance"]["answers"] = []
                    for cell in spec["subcap_ids"]:
                        if cell not in c["item"]["linked_subcap_ids"]:
                            c["item"]["linked_subcap_ids"].append(cell)
                    if spec["index"] not in c["provenance"]["answers"]:
                        c["provenance"]["answers"].append(spec["index"])
                    ids.append(cid)
                by_question.append({"index": spec["index"], "question": spec["question"],
                                    "subcap_ids": list(spec["subcap_ids"]), "facet": spec["facet"],
                                    "query_ids": [q["query_id"] for q in queries
                                                  if q.get("question_index") == spec["index"]],
                                    "card_ids": ids, "answered": bool(ids)})
        off_entity = 0
        if classes:
            # a per-class card must be ABOUT the entity in its own span: the
            # class filter leaves only pages of that class, and a page that
            # merely lists the entity (a BDC's schedule of investments) would
            # otherwise card an unrelated T1 span (entity.span_names_entity)
            keep = [c for c in cards
                    if c["provenance"].get("entity_match") != "ambiguous"
                    and (c["provenance"].get("source_type_hint") == "entity_owned"
                         or E.span_names_entity(c["item"]["excerpt"], ent))]
            off_entity = len(cards) - len(keep)
            if off_entity:
                kept_ids = {c["card_id"] for c in keep}
                cards = keep
                for row in by_question:
                    row["card_ids"] = [i for i in row["card_ids"] if i in kept_ids]
                    row["answered"] = bool(row["card_ids"])
        projected = [self._project(c, provenance) for c in cards]
        kept, tokens = P.trim_to_budget(projected, token_budget * (len(specs) if batched else 1))
        cards = cards[:len(kept)]
        if by_question:
            kept_ids = {c["card_id"] for c in cards}
            for row in by_question:
                row["card_ids"] = [i for i in row["card_ids"] if i in kept_ids]
                row["answered"] = bool(row["card_ids"])
        for c in cards:
            self.store.put_card(run_id, c)
        state = self.store.run_state(run_id)
        block, new_state = COV.coverage_block(run_state=state, facet=facet, returned=cards, queries=queries,
                                              # a per-class brief searched its class's hosts, not
                                              # the open web: its rungs come from its site: probes
                                              sources_used=[] if classes else
                                              [s for s, v in fan["per_source"].items() if v.get("count")])
        def _upd(s):
            s.update(new_state)
            s.setdefault("queries", []).extend([q["text"] for q in queries])
            s["ladder_rungs"] = sorted(set(s.get("ladder_rungs", [])) | set(block["ladder_searched"]))
            s["cards"] = len(self.store.card_ids(run_id))
            s.setdefault("labels", {})
            for c in cards:
                for lab in (subcap_labels or []):
                    s["labels"].setdefault(c["card_id"], [])
                    if lab not in s["labels"][c["card_id"]]:
                        s["labels"][c["card_id"]].append(lab)
        self.store.update_run_state(run_id, _upd)
        out = {
            "run_id": run_id, "facet": facet, "cards": kept,
            "coverage": block, "tokens": tokens, "rerank": ranked.get("rerank"),
            "search": {"queries": [{"query_id": q["query_id"], "text": q["text"], "facet": q["facet"], "kind": q["kind"]} for q in queries],
                       "per_source": fan["per_source"], "rerouted": fan.get("rerouted", []),
                       "hits": len(hits), "fetched": len(docs), "fetch_failures": failures[:10],
                       # queries cut at the search-phase budget (load): their
                       # questions may read unanswered — re-ask those rows
                       "budget_cut": fan.get("budget_cut", 0),
                       # a per-class brief: the classes asked for, and the
                       # hits dropped because they classified outside them
                       "source_classes": classes, "class_filtered": class_filtered,
                       # per-class cards dropped because the span does not
                       # name the entity (or the page only shares its tokens)
                       "off_entity_dropped": off_entity,
                       "dropped": dropped[:10]},
            "guard_violations": violations,
            "ambiguous_cards": [c["card_id"] for c in cards if c["provenance"].get("entity_match") == "ambiguous"],
            # per-question outcome in batch mode: the cells each question named,
            # its queries, its cards; `answered: false` is nothing_found material
            "by_question": by_question,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            # where the time went: search (fan-out), fetch (the slice), the rest
            # (rank, excerpt, cards, store). An agent reads this to judge a
            # slow backend; the harness reports means per phase.
            "timing_ms": {"search": int((t_fetch - t_search) * 1000), "fetch": int((t_rank - t_fetch) * 1000),
                          "rank_and_cards": int((time.monotonic() - t_rank) * 1000)},
        }
        if not cards:
            out["absence"] = {"ladder_searched": block["ladder_searched"],
                              "note": "zero cards: an absence finding may cite these searched rungs"}
        return out

    #: what each provenance mode returns beside `item` (docs/CARD-CONTRACT.md §6).
    PROVENANCE_KEYS = {
        "minimal": ("url_status", "recency", "entity_match", "origin_cluster", "context_handle"),
        "standard": ("url_status", "recency", "source_type_hint", "entity_match", "origin_cluster",
                     "syndication_count", "context_handle", "ladder_rung", "via", "published_basis",
                     "relevance", "host"),
    }

    @classmethod
    def _project(cls, card: dict, provenance: str) -> dict:
        keys = cls.PROVENANCE_KEYS.get(provenance)
        if keys is None:
            return card
        p = card["provenance"]
        return {"card_id": card["card_id"], "item": card["item"],
                "provenance": {k: p.get(k) for k in keys}}

    # ── 2 · crawl_entity ────────────────────────────────────────────────
    async def crawl_entity(self, *, run_id: str, entity: dict, page_budget: int | None = None,
                           depth: int | None = None, path_focus: list[str] | None = None,
                           question: str = "", max_cards: int = 12, token_budget: int = 1500,
                           reference_date: str | None = None) -> dict:
        ent = entity_ref(entity)
        if ent is None or not ent.domains:
            return {"error": "entity.domains is required for a crawl", "cards": []}
        st = settings()
        pages, manifest = await CR.crawl_entity(ent, self.fetcher, page_budget=page_budget or st.crawl_page_budget,
                                                depth=depth if depth is not None else st.crawl_depth,
                                                path_focus=path_focus, bucket_wait=self._bucket_wait)
        ref = _ref_date(reference_date)
        docs: list[Document] = []
        for pg in pages:
            from .types import FetchResult
            res = FetchResult(url=pg["url"], final_url=pg["final_url"], status=pg["status"],
                              content_type=pg.get("content_type", ""), body=pg["body"],
                              retrieved_at=pg.get("retrieved", ""), via="crawl")
            doc = P.document_from_fetch(res, today=self.today)
            if doc is not None:
                P.store_document(self.store, doc, ref)
                docs.append(doc)
        q = question or f"{ent.legal_name} digital capability announcement launch results"
        ranked = R.rank_chunks(q, docs, top_k=max_cards * 3)
        order = []
        for r in ranked["ranked"]:
            if r["url_key"] not in order:
                order.append(r["url_key"])
        by_key = {url_key(d.url): d for d in docs}
        ordered = [by_key[k] for k in order if k in by_key] + [d for k, d in by_key.items() if k not in order]
        cards, dropped = P.build_cards(ordered, question=q, entity=ent, facet=None, reference=ref,
                                       today=self.today, max_cards=max_cards,
                                       via_by_key={url_key(d.url): "crawl" for d in docs})
        cards, tokens = P.trim_to_budget(cards, token_budget)
        for c in cards:
            self.store.put_card(run_id, c)
        return {"run_id": run_id, "cards": cards, "tokens": tokens, "rerank": ranked.get("rerank"),
                "manifest": {"seen": len(manifest.seen), "fetched": len(manifest.fetched),
                             "skipped": manifest.skipped[:50], "robots_blocked": manifest.robots_blocked,
                             "sitemap_urls": manifest.sitemap_urls, "budget": manifest.budget, "depth": manifest.depth},
                "dropped": dropped[:10]}

    # ── 3 · filings_evidence ────────────────────────────────────────────
    async def filings_evidence(self, *, run_id: str, cik_or_ticker: str, forms: list[str] | None = None,
                               years: list[int] | None = None, topics: list[str] | None = None,
                               max_cards: int = 10, token_budget: int = 1500,
                               reference_date: str | None = None, entity: dict | None = None) -> dict:
        provider = self.filings_provider or F.EdgarProvider(sec_wait=self._sec_wait)
        got = await F.filings_evidence(provider, cik_or_ticker=cik_or_ticker, forms=forms or ["10-K", "10-Q", "8-K"],
                                       years=years, topics=topics or [], today=self.today)
        ref = _ref_date(reference_date)
        ent = entity_ref(entity)
        docs = []
        for d in got["documents"]:
            d = dict(d)
            d.pop("filing", None)
            docs.append(Document(**d))
        q = " ".join(topics or []) or "annual report risk factors technology operations"
        ranked = R.rank_chunks(q, docs, top_k=max_cards * 3)
        order = []
        for r in ranked["ranked"]:
            if r["url_key"] not in order:
                order.append(r["url_key"])
        by_key = {url_key(d.url): d for d in docs}
        ordered = [by_key[k] for k in order if k in by_key] + [d for k, d in by_key.items() if k not in order]
        cards, dropped = P.build_cards(ordered, question=q, entity=ent, facet=None, reference=ref,
                                       today=self.today, max_cards=max_cards, per_doc=2,
                                       via_by_key={url_key(d.url): d.via for d in docs})
        cards, tokens = P.trim_to_budget(cards, token_budget)
        for c in cards:
            self.store.put_card(run_id, c)
        return {"run_id": run_id, "cards": cards, "tokens": tokens, "facts": got["facts"][:50],
                "searched": got["searched"], "dropped": dropped[:10]}

    # ── 4 · expand_context ──────────────────────────────────────────────
    async def expand_context(self, *, context_handle: str, window: int = 2, run_id: str | None = None) -> dict:
        card = self._find_card_by_handle(context_handle, run_id)
        if card is None:
            return {"error": f"unknown context_handle {context_handle}"}
        got = self.store.get_text(card["provenance"]["content_hash"])
        if got is None:
            return {"error": "the cleaned text for this card has expired from the store; re-run research_brief"}
        text, _meta = got
        s, e = card["provenance"]["excerpt_offsets"]
        a, b, ctx = X.context_window(text, s, e, window)
        return {"card_id": card["card_id"], "context_handle": context_handle, "window_sentences": window,
                "context": ctx, "offsets": [a, b], "excerpt_offsets": [s, e],
                "tokens": C.estimate_tokens(ctx)}

    def _find_card_by_handle(self, handle: str, run_id: str | None) -> dict | None:
        runs = [run_id] if run_id else self._all_runs()
        for r in runs:
            for c in self.store.list_cards(r):
                if c["provenance"].get("context_handle") == handle:
                    return c
        return None

    def _all_runs(self) -> list[str]:
        base = self.store.root / "cards"
        return sorted(p.name for p in base.iterdir()) if base.exists() else []

    # ── 5 · verify_cards ────────────────────────────────────────────────
    async def verify_cards(self, *, run_id: str, card_ids: list[str], recheck_liveness: bool = True) -> dict:
        results = []
        for cid in card_ids:
            card = self.store.get_card(run_id, cid)
            if card is None:
                results.append({"card_id": cid, "verdict": "NOT_FOUND"})
                continue
            item, prov = card["item"], card["provenance"]
            checks = {}
            got = self.store.get_text(prov["content_hash"])
            if got is None:
                checks["offsets"] = "text expired from store"
            else:
                text, meta = got
                s, e = prov["excerpt_offsets"]
                checks["offsets"] = "ok" if text[s:e] == item["excerpt"] else "MISMATCH: text[start:end] != excerpt"
                vh = meta.get("verify_hash")
                vt = self.store.get_text(vh)[0] if vh and self.store.get_text(vh) else text
                checks["verbatim_in_connector_text"] = "ok" if normalise(item["excerpt"]) in normalise(vt) else "MISMATCH"
            probs = C.item_problems(item, abbreviations=P.abbreviations())
            checks["contract"] = "ok" if not probs else "; ".join(probs)
            if item.get("published_date"):
                band = C.recency_band(item["published_date"], self.today)
                checks["date"] = "ok" if band != "UNVERIFIED" else "bad: published_date does not parse as ISO or lies in the future"
                checks["recency_now"] = C.recency_band(item["published_date"], self.today)
            else:
                checks["date"] = "undated → UNVERIFIED (not guessed)"
            if recheck_liveness:
                live = await self.fetcher.liveness(item["source_url"])
                checks["liveness"] = "ok" if live.ok or (live.status and 200 <= live.status < 400) else (live.error or f"http {live.status}")
                if checks["liveness"] != "ok" and prov.get("url_status") == "live":
                    snap = await self.fetcher.wayback_snapshot(item["source_url"])
                    checks["archive_available"] = bool(snap)
            bad = [k for k, v in checks.items() if isinstance(v, str) and (v.startswith("MISMATCH") or (k == "liveness" and v != "ok") or (k == "contract" and v != "ok") or (k == "date" and v.startswith("bad")))]
            results.append({"card_id": cid, "verdict": "PASS" if not bad else "FAIL", "failed": bad, "checks": checks})
        summary = {"passed": sum(1 for r in results if r["verdict"] == "PASS"),
                   "failed": sum(1 for r in results if r["verdict"] == "FAIL"),
                   "not_found": sum(1 for r in results if r["verdict"] == "NOT_FOUND")}
        return {"run_id": run_id, "results": results, "summary": summary,
                "note": "confidence only moves down: a FAIL here is final until the card is re-issued"}

    # ── 7 · find_registrant ─────────────────────────────────────────────
    async def find_registrant(self, *, entity: dict, sub_vertical: str | None = None,
                              country: str | None = None, run_id: str | None = None) -> dict:
        """The institution in the registry that holds it, for every
        sub-vertical in the US and Canada (registrants.py). Registries with a
        keyless interface are asked directly; the ones without are searched
        on their own hosts through the paced fan-out and come back as
        candidates. Never a card: a registry record identifies the entity;
        the evidence about it is the record page, read and registered."""
        import httpx

        from . import registrants as REG
        from .tls import trust_context
        ent = entity_ref(entity)
        if ent is None or not ent.legal_name:
            return {"error": "entity.legal_name is required"}
        if self._registry_http is None:
            self._registry_http = httpx.AsyncClient(timeout=25, follow_redirects=True, verify=trust_context())
        lookups = REG.Registrants(self._registry_http, user_agent=settings().sec_user_agent)
        free = self._free_sources_available()

        async def search(queries: list[dict]) -> list[dict]:
            if not free:
                return []
            fan = await S.fan_out(queries, searx=self.searx if "searxng" in free else None,
                                  parallel=self.parallel if "parallel" in free else None,
                                  run_id=run_id or "registrant", bucket_wait=self._source_wait,
                                  cache=_SearchCache(self.store), breakers=RL.breakers(),
                                  budget_s=min(60.0, settings().search_phase_budget_s))
            return [{"url": h["url"], "title": h.get("title", ""), "snippet": h.get("snippet", "")}
                    for h in fan["hits"]]

        t0 = time.monotonic()
        out = await lookups.lookup(ent, sub_vertical=sub_vertical, country=country, search=search)
        out["entity"] = ent.legal_name
        out["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        return out

    # ── 6 · coverage_report ─────────────────────────────────────────────
    async def coverage_report(self, *, run_id: str) -> dict:
        cards = self.store.list_cards(run_id)
        state = self.store.run_state(run_id)
        rep = COV.coverage_report(cards, state, state.get("labels") or {})
        rep["run_id"] = run_id
        rep["ladder_rungs_searched"] = state.get("ladder_rungs", [])
        rep["queries_run"] = len(state.get("queries", []))
        rep["sources_health"] = RL.health()
        pool = getattr(self.searx, "pool", None)
        if pool is not None:
            # this instance's per-engine pacing behind SearXNG: what was sent,
            # what is resting and why (search.EnginePool)
            rep["sources_health"]["searxng_engines"] = pool.snapshot()
        return rep
