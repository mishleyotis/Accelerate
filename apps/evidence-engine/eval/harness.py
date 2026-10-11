#!/usr/bin/env python3
"""Golden-set evaluation harness (brief §4, Phase D).

    python3 -I eval/harness.py --version v1 --live
    python3 -I eval/harness.py --version v1            # offline metrics only, over a saved run

Reads EVERYTHING about the clients from the golden files under
eval/golden/<version>/ (which legitimately name clients); this file names
none and is scanned by tests/test_no_client_strings.py. Writes
eval/results/<version>-<timestamp>.json and docs/EVAL-REPORT.md.

Metrics (each split tuning vs held-out, gap reported):
  offline  excerpt fidelity · boilerplate leakage (+ golden-negative refusal
           census) · syndication inflation · card size (minimal/standard/full)
  live     URL liveness of produced cards · source recall · token efficiency
           · Parallel rate-limit ramp

The golden set has no question field. A question is DERIVED from each
positive row's excerpt (content words minus the entity's own tokens, stop
words and any platform name the vendor guard would refuse), and the entity
(legal name, own domain, aliases) is DERIVED from the client's rows — the
derivation is recorded in the results so a reader can judge it.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import math
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_DIR = ROOT / "eval" / "golden"
RESULTS_DIR = ROOT / "eval" / "results"
REPORT_PATH = ROOT / "docs" / "EVAL-REPORT.md"

#: The brief's bars (§4). `hard` = a miss is a defect, not a shortfall.
BARS = {
    "excerpt_fidelity": {"bar": 1.00, "kind": "share", "hard": True},
    "boilerplate_leakage": {"bar": 0, "kind": "count", "hard": True},
    "syndication_inflation": {"bar": 0, "kind": "count", "hard": True},
    "card_tokens_item_minimal_mean": {"bar": 120, "kind": "max_target", "hard": False},
    "url_liveness": {"bar": 1.00, "kind": "share", "hard": True},
    "source_recall": {"bar": 0.80, "kind": "share", "hard": False},
    "token_reduction": {"bar": 0.60, "kind": "share", "hard": False},
    "generalisation_gap_points": {"bar": 5.0, "kind": "max", "hard": False},
}

DEFECT_CLASSES = ("hard_clip", "not_sentence_complete", "machine_text", "internal_jargon")

_STOP = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the this to was "
    "what when where which who with does do did their they there these those than then into onto "
    "over under about after before we our us you your he she his her them i me my will would can "
    "could should may might must shall also such more most very just only not no yes but if so "
    "because while during through per via each every both either neither any all some many much "
    "new one two three first second last next now today year years said says say report reported "
    "including include includes across within without between among up down out off over again "
    "further once here there been being am were had having".split())
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'&.-]*")
_INST_SUFFIX = (r"(?:Federal\s+)?(?:Credit\s+Union|Bank|Bancorp|Bancshares|Financial(?:\s+Group)?|"
                r"Insurance|Trust|Investments|Advisors|Mortgage)")
_INST_RE = re.compile(r"((?:[A-Z0-9][A-Za-z0-9&'.-]*\s+){1,4}" + _INST_SUFFIX + r")\b")
#: hosts that are never an institution's own domain, whatever the label says
_SHARED_HOSTS = {"apple.com", "google.com", "linkedin.com", "facebook.com", "youtube.com",
                 "twitter.com", "x.com", "prnewswire.com", "businesswire.com", "globenewswire.com",
                 "archive.org", "wikipedia.org", "glassdoor.com", "indeed.com", "bbb.org"}


# ── golden files ───────────────────────────────────────────────────────────

def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_golden(version: str) -> dict:
    d = GOLDEN_DIR / version
    if not d.is_dir():
        raise SystemExit(f"no golden set at {d}")
    out = {"version": version, "dir": str(d), "manifest": json.loads((d / "manifest.json").read_text(encoding="utf-8")),
           "splits": {}}
    for split in ("tuning", "heldout"):
        out["splits"][split] = {
            "positives": json.loads((d / f"{split}_positives.json").read_text(encoding="utf-8")),
            "negatives": json.loads((d / f"{split}_negatives.json").read_text(encoding="utf-8")),
        }
    return out


def rows_by_client(golden: dict) -> dict[str, dict]:
    """{client: {split, positives, negatives}} — every row of that client."""
    out: dict[str, dict] = {}
    for split, parts in golden["splits"].items():
        for kind in ("positives", "negatives"):
            for r in parts[kind]:
                c = out.setdefault(r["client"], {"split": split, "positives": [], "negatives": []})
                c[kind].append(r)
    return out


def _registrable(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _initials(phrase: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", phrase)).lower()


def derive_entity(client_key: str, rows: list[dict]) -> dict:
    """Legal name, own domain and aliases from the client's rows alone.

    legal_name  the most frequent institution-shaped phrase (…Credit Union /
                Bank / …) in the rows' excerpts + source_names that is LINKED
                to the client: the client key is inside its compacted form,
                or its initials are a host label among the client's rows.
    domains     the registrable domain, among the rows' hosts, whose label is
                the client key, is inside the legal name's compacted form, or
                equals the legal name's initials; the most frequent wins.
    aliases     the initials when they recur in the rows' text, and
                "<first token> FCU|CU" when that recurs.
    Every choice and its evidence is returned under `derivation`."""
    key_c = _compact(client_key)
    text = " ".join(f"{r.get('excerpt') or ''} {r.get('source_name') or ''}" for r in rows)
    hosts = collections.Counter(_registrable(r.get("host") or "") for r in rows if r.get("host"))
    labels = {h.split(".")[0]: h for h in hosts if h}
    phrases = collections.Counter()
    for m in _INST_RE.findall(text):
        p = re.sub(r"^(The|A|An)\s+", "", m.strip())
        p = re.sub(r"^[^A-Za-z0-9]+", "", p)
        if p:
            phrases[p] += 1

    def linked(p: str) -> str | None:
        pc = _compact(p)
        if key_c and key_c in pc:
            return "client key inside the phrase"
        ini = _initials(p)
        if len(ini) >= 3 and ini in labels and labels[ini] not in _SHARED_HOSTS:
            return f"initials '{ini}' are a host label ({labels[ini]})"
        return None

    ranked = sorted(((n, len(p), p) for p, n in phrases.items() if linked(p)), reverse=True)
    legal = ranked[0][2] if ranked else client_key
    legal_c = _compact(legal)
    ini = _initials(legal)
    own: collections.Counter = collections.Counter()
    own_why: dict[str, str] = {}
    for h, n in hosts.items():
        if not h or h in _SHARED_HOSTS:
            continue
        label = h.split(".")[0]
        why = None
        if key_c and (label == key_c or key_c in label):
            why = "label carries the client key"
        elif len(label) >= 4 and label in legal_c:
            why = "label is inside the legal name"
        elif len(ini) >= 3 and label == ini:
            why = "label equals the legal name's initials"
        if why:
            own[h] += n
            own_why[h] = why
    domains = [h for h, _ in own.most_common()]
    aliases: list[str] = []
    if len(ini) >= 3 and len(re.findall(rf"\b{re.escape(ini.upper())}\b", text)) >= 2:
        aliases.append(ini.upper())
    first = legal.split(" ")[0]
    for short in ("FCU", "CU"):
        if len(re.findall(rf"\b{re.escape(first)}\s+{short}\b", text)) >= 1 and f"{first} {short}" != legal:
            aliases.append(f"{first} {short}")
    return {
        "client": client_key,
        "legal_name": legal,
        "domains": domains[:2],
        "aliases": aliases,
        "derivation": {
            "legal_name_candidates": [{"phrase": p, "count": n, "link": linked(p)} for n, _, p in ranked[:5]],
            "legal_name_fallback": not ranked,
            "hosts_seen": dict(hosts.most_common(12)),
            "own_domain_candidates": {h: {"rows": n, "why": own_why[h]} for h, n in own.most_common()},
            "note": ("no own-domain host among this client's rows: the engine gets no site: query "
                     "and can never return entity_match=confirmed for it" if not domains else None),
        },
    }


def entity_tokens(ent: dict) -> set[str]:
    toks = set()
    for s in [ent["legal_name"], ent["client"]] + list(ent.get("aliases") or []):
        toks |= {t.lower() for t in _TOKEN.findall(s or "")}
    toks |= {ent["client"].lower()}
    return toks


def question_for(row: dict, ent: dict, max_terms: int = 7) -> dict:
    """The question for one positive row: the golden row's OWN question when
    the set carries one (golden v2: the subcap's diagnostic question from
    the pillar toolkits), else one derived from the excerpt's vocabulary
    (golden v1), and what was removed."""
    from evidence_engine import query as Q
    if row.get("question"):
        names = Q.find_names(row["question"])
        return {"question": row["question"], "terms": [], "platform_names_stripped": names,
                "question_source": row.get("question_source") or "row"}
    excerpt = row.get("excerpt") or ""
    names = Q.find_names(excerpt)
    name_tokens = {t.lower() for n in names for t in _TOKEN.findall(n)}
    ent_tokens = entity_tokens(ent)
    terms: list[str] = []
    for t in _TOKEN.findall(excerpt):
        tl = re.sub(r"'s$", "", t.lower().strip(".'&-"))
        if not tl or tl in _STOP or tl in ent_tokens or tl in name_tokens:
            continue
        # a number is kept only as a year or a figure with a decimal point;
        # a thousands-separator fragment ("000") is not a term
        if not re.search(r"[a-z]", tl) and not re.fullmatch(r"(19|20)\d{2}|\d+\.\d+", tl):
            continue
        if len(tl) < 3 and not tl.isdigit():
            continue
        if tl in terms:
            continue
        terms.append(tl)
        if len(terms) >= max_terms:
            break
    q = f"What does {ent['legal_name']} report about {' '.join(terms)}?"
    return {"question": q, "terms": terms, "platform_names_stripped": names}


def sample_positives(positives: list[dict], *, max_urls: int | None, seed: int) -> list[dict]:
    """One row per distinct URL (the row with the longest excerpt); when
    `max_urls` is set, that many URLs drawn with `random.Random(seed)` from
    the sorted URL list. Deterministic."""
    by_url: dict[str, list[dict]] = collections.defaultdict(list)
    for r in positives:
        by_url[r["url"]].append(r)
    urls = sorted(by_url)
    if max_urls is not None and len(urls) > max_urls:
        urls = sorted(random.Random(seed).sample(urls, max_urls))
    out = []
    for u in urls:
        rows = sorted(by_url[u], key=lambda r: (-len(r.get("excerpt") or ""), r["golden_id"]))
        out.append(rows[0])
    return out


# ── offline metrics ────────────────────────────────────────────────────────

def _pct(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    return vs[min(len(vs) - 1, math.ceil(0.95 * len(vs)) - 1)]


def excerpt_fidelity(store, cards: list[dict]) -> dict:
    """text[start:end] == excerpt AND normalise(excerpt) in normalise(verify_text),
    re-read from the Store (the connector-shaped text when one was stored)."""
    from evidence_engine import excerpt as X
    from evidence_engine.textnorm import normalise
    ok = 0
    failures = []
    expired = 0
    for c in cards:
        prov = c["provenance"]
        got = store.get_text(prov["content_hash"])
        if got is None:
            expired += 1
            failures.append({"card_id": c["card_id"], "reason": "text expired from store"})
            continue
        text, meta = got
        vh = meta.get("verify_hash")
        vt = text
        if vh:
            v = store.get_text(vh)
            if v:
                vt = v[0]
        s, e = prov["excerpt_offsets"]
        if X.verify_against_both(text, vt, s, e, c["item"]["excerpt"]) and normalise(c["item"]["excerpt"]) in normalise(vt):
            ok += 1
        else:
            failures.append({"card_id": c["card_id"], "reason": "offsets or connector-text mismatch"})
    return {"cards": len(cards), "verified": ok, "share": _pct(ok, len(cards)),
            "expired": expired, "failures": failures[:20]}


def boilerplate_leakage(cards: list[dict]) -> dict:
    from evidence_engine import excerpt as X
    hits = []
    for c in cards:
        pat = X.boilerplate_match(c["item"]["excerpt"])
        if pat:
            hits.append({"card_id": c["card_id"], "pattern": pat})
    return {"cards": len(cards), "matches": len(hits), "hits": hits[:20]}


def negatives_refusal_census(negatives: list[dict]) -> dict:
    """For every golden NEGATIVE row: would the anti-pattern list and the
    contract's excerpt rules have refused its excerpt? Reported per defect
    class so the 'extend from measured defects' claim can be checked."""
    from evidence_engine import contract as C
    from evidence_engine import excerpt as X
    per_class = {d: {"rows": 0, "refused": 0, "by_rule": collections.Counter(), "unrefused": []} for d in DEFECT_CLASSES}
    total_rows = 0
    total_refused = 0
    for r in negatives:
        ex = r.get("excerpt") or ""
        rules = []
        bp = X.boilerplate_match(ex)
        if bp:
            rules.append("boilerplate:" + bp[:40])
        for p in C.item_problems({"source_name": "x", "source_url": r.get("url") or "https://example.invalid/",
                                  "excerpt": ex, "tier": "T3", "claim_type": "INFERENCE"}):
            if p.startswith("excerpt"):
                rules.append(p.split(":", 1)[0])
        considered = [d for d in r.get("defects", []) if d in DEFECT_CLASSES]
        if not considered:
            continue
        total_rows += 1
        if rules:
            total_refused += 1
        for d in considered:
            pc = per_class[d]
            pc["rows"] += 1
            if rules:
                pc["refused"] += 1
                for rule in rules:
                    pc["by_rule"][rule] += 1
            elif len(pc["unrefused"]) < 8:
                pc["unrefused"].append({"golden_id": r["golden_id"], "client": r["client"], "len": len(ex),
                                        "excerpt_head": ex[:120]})
    for d, pc in per_class.items():
        pc["share"] = _pct(pc["refused"], pc["rows"])
        pc["by_rule"] = dict(pc["by_rule"].most_common())
    return {"rows_with_a_considered_defect": total_rows, "refused": total_refused,
            "share": _pct(total_refused, total_rows), "per_class": per_class}


def syndication_inflation(calls: list[dict]) -> dict:
    """Within one research_brief answer, cards sharing an origin_cluster must
    agree on syndication_count and that count must cover every distinct
    url_key in the cluster."""
    from evidence_engine.fetch import url_key
    inflated = []
    clusters_seen = 0
    multi = 0
    for call in calls:
        by_cluster: dict[str, list[dict]] = collections.defaultdict(list)
        for c in call.get("cards_full") or []:
            by_cluster[c["provenance"].get("origin_cluster") or c["card_id"]].append(c)
        for oc, cs in by_cluster.items():
            clusters_seen += 1
            keys = {url_key(c["item"]["source_url"]) for c in cs}
            counts = {c["provenance"].get("syndication_count", 1) for c in cs}
            if len(keys) > 1:
                multi += 1
                if len(counts) != 1 or min(counts) < len(keys):
                    inflated.append({"call": call["golden_id"], "origin_cluster": oc,
                                     "distinct_urls": len(keys), "syndication_counts": sorted(counts)})
    return {"clusters": clusters_seen, "multi_url_clusters": multi, "inflated": len(inflated), "cases": inflated[:20]}


def card_sizes(cards: list[dict]) -> dict:
    from evidence_engine import contract as C
    from evidence_engine.tools import Engine
    out = {}
    for mode in ("minimal", "standard", "full"):
        toks = [C.estimate_tokens(Engine._project(c, mode)) for c in cards]
        out[mode] = {"cards": len(toks), "mean": round(statistics.fmean(toks), 1) if toks else None,
                     "p95": _p95(toks), "min": min(toks) if toks else None, "max": max(toks) if toks else None}
    item_only = [C.estimate_tokens(c["item"]) for c in cards]
    out["item_only"] = {"mean": round(statistics.fmean(item_only), 1) if item_only else None, "p95": _p95(item_only)}
    out["counter"] = "tiktoken cl100k_base" if _tiktoken_present() else "heuristic: 4 chars/token over compact JSON (tiktoken not installed)"
    return out


def answer_tokens(calls: list[dict]) -> dict:
    """Per-call size of the whole research_brief answer (heuristic tokens):
    mean, p95, max, and the share the cards take of it."""
    vals = [c["answer_tokens"] for c in calls if isinstance(c.get("answer_tokens"), int)]
    cards = [c["answer_tokens_cards_only"] for c in calls if isinstance(c.get("answer_tokens_cards_only"), int)]
    if not vals:
        return {"calls": 0}
    return {"calls": len(vals), "mean": round(statistics.mean(vals), 1), "p95": _p95(vals), "max": max(vals),
            "cards_share": round(sum(cards) / max(1, sum(vals)), 3) if cards else None,
            "note": "the full tool answer an agent reads (cards + coverage + search block), heuristic 4 chars/token"}


def _tiktoken_present() -> bool:
    import importlib.util
    return importlib.util.find_spec("tiktoken") is not None


# ── live ───────────────────────────────────────────────────────────────────

def build_engine(data_dir: Path):
    os.environ["EE_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("PARALLEL_ENABLED", "1")
    os.environ["SEARXNG_URL"] = os.environ.get("SEARXNG_URL", "")
    from evidence_engine import config, ratelimit as RL, search as S
    from evidence_engine import store as ST
    from evidence_engine.fetch import HttpFetcher
    from evidence_engine.tools import Engine
    config.reset_settings()
    ST.reset_store()
    RL.reset()
    st = config.settings()
    store = ST.Store(data_dir)
    parallel = S.ParallelClient(st.parallel_mcp_url) if st.parallel_enabled and st.parallel_mcp_url else None
    return Engine(fetcher=HttpFetcher(), store=store, searx=None, parallel=parallel, today=dt.date.today())


def _matches(card: dict, golden_url: str) -> str | None:
    from evidence_engine.fetch import host_of, url_key
    gk = url_key(golden_url)
    cands = [card["item"]["source_url"], card["provenance"].get("original_url")]
    for u in cands:
        if u and url_key(u) == gk:
            return "url_key"
    for u in cands:
        if u and host_of(u) == host_of(golden_url):
            return "host"
    return None


async def run_research(engine, samples: list[dict], entities: dict, *, max_cards: int, token_budget: int,
                       provenance: str, deadline: float, progress=print) -> list[dict]:
    calls = []
    for i, row in enumerate(samples):
        if time.monotonic() > deadline:
            calls.append({"golden_id": row["golden_id"], "client": row["client"], "split": row["split"],
                          "url": row["url"], "skipped": "time budget exhausted"})
            continue
        ent = entities[row["client"]]
        qd = question_for(row, ent)
        run_id = f"eval-{row['client']}"
        rec = {"golden_id": row["golden_id"], "client": row["client"], "split": row["split"], "url": row["url"],
               "golden_tier": row.get("tier"), "question": qd["question"], "terms": qd["terms"],
               "platform_names_stripped": qd["platform_names_stripped"], "run_id": run_id}
        t0 = time.monotonic()
        try:
            out = await engine.research_brief(
                run_id=run_id,
                entity={"legal_name": ent["legal_name"], "domains": ent["domains"], "aliases": ent["aliases"]},
                questions=[qd["question"]], max_cards=max_cards, token_budget=token_budget, provenance=provenance)
        except Exception as e:  # noqa: BLE001 — recorded, never hidden
            rec.update({"error": f"{type(e).__name__}: {str(e)[:300]}", "elapsed_ms": int((time.monotonic() - t0) * 1000)})
            calls.append(rec)
            progress(f"  [{i + 1}/{len(samples)}] {row['golden_id']} ERROR {rec['error'][:80]}")
            continue
        rec["elapsed_ms"] = out.get("elapsed_ms", int((time.monotonic() - t0) * 1000))
        rec["wall_ms"] = int((time.monotonic() - t0) * 1000)
        if out.get("error") or out.get("needs_spend_approval"):
            rec["error"] = out.get("error") or f"needs_spend_approval: {out.get('reason')}"
        cards = out.get("cards") or []
        full = [engine.store.get_card(run_id, c["card_id"]) or c for c in cards]
        rec["cards_full"] = full
        rec["card_ids"] = [c["card_id"] for c in cards]
        rec["tokens"] = out.get("tokens")
        # What the AGENT reads: the whole answer as the tool returns it (cards
        # in the requested provenance + coverage + search block), not just the
        # cards — the figure token consumption is judged on (owner, 2026-10-11).
        from evidence_engine import contract as _C
        rec["answer_tokens"] = _C.estimate_tokens(out)
        rec["answer_tokens_cards_only"] = _C.estimate_tokens(cards)
        rec["rerank"] = out.get("rerank")
        s = out.get("search") or {}
        rec["search"] = {"queries": len(s.get("queries") or []), "hits": s.get("hits"), "fetched": s.get("fetched"),
                         "fetch_failures_shown": len(s.get("fetch_failures") or []),
                         "dropped_shown": len(s.get("dropped") or []),
                         "per_source": s.get("per_source"), "rerouted": s.get("rerouted"),
                         "fetch_failures": s.get("fetch_failures"), "dropped": s.get("dropped")}
        rec["guard_violations"] = out.get("guard_violations") or []
        rec["ambiguous_cards"] = out.get("ambiguous_cards") or []
        rec["entity_match"] = dict(collections.Counter(c["provenance"].get("entity_match") for c in full))
        rec["coverage"] = {k: (out.get("coverage") or {}).get(k) for k in ("novelty", "saturation", "ladder_searched")}
        found = [(c["card_id"], _matches(c, row["url"])) for c in full]
        rec["refound_url_key"] = any(m == "url_key" for _, m in found)
        rec["refound_host"] = any(m in ("url_key", "host") for _, m in found)
        rec["matching_cards"] = [cid for cid, m in found if m]
        rec["matching_cards_exact"] = [cid for cid, m in found if m == "url_key"]
        calls.append(rec)
        progress(f"  [{i + 1}/{len(samples)}] {row['golden_id']} {row['client']} cards={len(cards)} hits={s.get('hits')} "
                 f"fetched={s.get('fetched')} refound={'url' if rec['refound_url_key'] else ('host' if rec['refound_host'] else '-')} "
                 f"{rec['elapsed_ms']} ms")
    return calls


async def warm_repeat(engine, calls: list[dict], entities: dict, **kw) -> list[dict]:
    """The first successful call of each split, repeated: search cache +
    text cache → the warm elapsed time."""
    out = []
    seen = set()
    for c in calls:
        if c.get("error") or c.get("skipped") or c["split"] in seen:
            continue
        seen.add(c["split"])
        ent = entities[c["client"]]
        t0 = time.monotonic()
        res = await engine.research_brief(run_id=c["run_id"],
                                          entity={"legal_name": ent["legal_name"], "domains": ent["domains"], "aliases": ent["aliases"]},
                                          questions=[c["question"]], **kw)
        out.append({"golden_id": c["golden_id"], "split": c["split"], "cold_ms": c["elapsed_ms"],
                    "warm_ms": res.get("elapsed_ms", int((time.monotonic() - t0) * 1000)),
                    "warm_cached_calls": {k: v.get("cached") for k, v in (res.get("search") or {}).get("per_source", {}).items()},
                    "warm_novelty": (res.get("coverage") or {}).get("novelty")})
    return out


async def liveness(engine, calls: list[dict], *, deadline: float) -> dict:
    """verify_cards(recheck_liveness=True) over every produced card, per run."""
    by_run: dict[str, list[str]] = collections.defaultdict(list)
    split_of_run: dict[str, str] = {}
    for c in calls:
        for cid in c.get("card_ids") or []:
            if cid not in by_run[c["run_id"]]:
                by_run[c["run_id"]].append(cid)
        split_of_run[c.get("run_id", "")] = c.get("split", "")
    per_split = {s: {"cards": 0, "live_or_archived": 0, "failed": []} for s in ("tuning", "heldout")}
    verified = 0
    skipped = 0
    for run_id, ids in by_run.items():
        split = split_of_run[run_id]
        for start in range(0, len(ids), 8):
            if time.monotonic() > deadline:
                skipped += len(ids) - start
                break
            batch = ids[start:start + 8]
            v = await engine.verify_cards(run_id=run_id, card_ids=batch, recheck_liveness=True)
            for r in v["results"]:
                verified += 1
                card = engine.store.get_card(run_id, r["card_id"]) or {}
                st = (card.get("provenance") or {}).get("url_status")
                ok = r["checks"].get("liveness") == "ok" or st == "archived"
                per_split[split]["cards"] += 1
                if ok:
                    per_split[split]["live_or_archived"] += 1
                else:
                    per_split[split]["failed"].append({"card_id": r["card_id"], "liveness": r["checks"].get("liveness"),
                                                       "archive_available": r["checks"].get("archive_available"),
                                                       "url": (card.get("item") or {}).get("source_url")})
                r_other = [k for k in r.get("failed", []) if k != "liveness"]
                if r_other:
                    per_split[split].setdefault("other_failures", []).append({"card_id": r["card_id"], "failed": r_other})
    total = sum(p["cards"] for p in per_split.values())
    ok = sum(p["live_or_archived"] for p in per_split.values())
    for p in per_split.values():
        p["share"] = _pct(p["live_or_archived"], p["cards"])
        p["failed"] = p["failed"][:20]
    return {"cards_checked": total, "live_or_archived": ok, "share": _pct(ok, total),
            "skipped_for_time": skipped, "per_split": per_split}


async def token_efficiency(engine, calls: list[dict], *, deadline: float) -> dict:
    """Per sampled golden URL: tokens of the full cleaned page the engine's
    fetcher + extractor produce (the raw-fetch path an agent would read) vs
    tokens of the card(s) the engine returned for that URL (item + minimal
    provenance). Also, per produced card: its source page vs the card."""
    from evidence_engine import contract as C
    from evidence_engine import pipeline as P
    from evidence_engine.tools import Engine
    per_split = {s: {"urls": 0, "urls_refound": 0, "raw_tokens_refound": 0, "card_tokens_refound": 0,
                     "raw_tokens_all": 0, "fetch_failed": 0, "rows": []} for s in ("tuning", "heldout")}
    for c in calls:
        if c.get("skipped"):
            continue
        if time.monotonic() > deadline:
            per_split[c["split"]].setdefault("skipped_for_time", 0)
            per_split[c["split"]]["skipped_for_time"] += 1
            continue
        ps = per_split[c["split"]]
        ps["urls"] += 1
        doc, why = await P.fetch_document(c["url"], engine.fetcher, engine.store, today=engine.today)
        raw = C.estimate_tokens(doc.text) if doc else None
        # exact url_key matches only: a same-host card is another page and
        # would inflate the numerator (runs before 2026-10-10T20:00Z counted
        # host matches too — conservative, never flattering)
        exact = c.get("matching_cards_exact")
        if exact is None:
            exact = c.get("matching_cards") or []
        matching = [card for card in (c.get("cards_full") or []) if card["card_id"] in exact]
        card_tokens = C.estimate_tokens([Engine._project(card, "minimal") for card in matching]) if matching else 0
        row = {"golden_id": c["golden_id"], "raw_tokens": raw, "card_tokens_item_minimal": card_tokens,
               "cards": len(matching), "fetch_error": why, "via": doc.via if doc else None}
        if raw is None:
            ps["fetch_failed"] += 1
        else:
            ps["raw_tokens_all"] += raw
            if matching:
                ps["urls_refound"] += 1
                ps["raw_tokens_refound"] += raw
                ps["card_tokens_refound"] += card_tokens
                row["reduction"] = round(1 - card_tokens / raw, 4) if raw else None
        ps["rows"].append(row)
    # per produced card: the page it came from vs the card
    page_tokens = 0
    card_tokens = 0
    n = 0
    for c in calls:
        for card in c.get("cards_full") or []:
            got = engine.store.get_text(card["provenance"]["content_hash"])
            if not got:
                continue
            n += 1
            page_tokens += C.estimate_tokens(got[0])
            card_tokens += C.estimate_tokens(Engine._project(card, "minimal"))
    out = {"per_split": {}, "per_card": {"cards": n, "source_page_tokens": page_tokens, "card_tokens_item_minimal": card_tokens,
                                         "reduction": round(1 - card_tokens / page_tokens, 4) if page_tokens else None}}
    for s, ps in per_split.items():
        ps["reduction_refound"] = (round(1 - ps["card_tokens_refound"] / ps["raw_tokens_refound"], 4)
                                   if ps["raw_tokens_refound"] else None)
        out["per_split"][s] = ps
    rt = sum(p["raw_tokens_refound"] for p in per_split.values())
    ct = sum(p["card_tokens_refound"] for p in per_split.values())
    out["overall"] = {"urls": sum(p["urls"] for p in per_split.values()),
                      "urls_refound": sum(p["urls_refound"] for p in per_split.values()),
                      "raw_tokens_refound": rt, "card_tokens_refound": ct,
                      "reduction_refound": round(1 - ct / rt, 4) if rt else None,
                      "raw_tokens_all_sampled_urls": sum(p["raw_tokens_all"] for p in per_split.values()),
                      "fetch_failed": sum(p["fetch_failed"] for p in per_split.values())}
    return out


async def parallel_ramp(client, *, phases=((1.0, 30), (2.0, 30)), total_cap_s: float = 60.0) -> dict:
    """web_search through ParallelClient at 1/s for 30 s then 2/s for 30 s;
    stop at the first 429 (one raw probe then reads Retry-After) or at the
    cap. Generic FSI queries, no client, no caching in between."""
    from evidence_engine import search as S
    results: list[dict] = []
    stop: dict = {"hit": None}
    t_start = time.monotonic()
    pending: set = set()
    counter = {"i": 0}

    async def one(i: int, rate: float, due: float):
        now = time.monotonic()
        if due > now:
            await asyncio.sleep(due - now)
        if stop["hit"] is not None:
            return
        t0 = time.monotonic()
        rec = {"i": i, "rate": rate, "at_s": round(t0 - t_start, 2)}
        try:
            hits = await client.search(f"federal credit union mobile banking app launch results {2000 + i}",
                                       [f"credit union digital banking launch {2000 + i}"], run_id="eval-ramp")
            rec.update({"ok": True, "hits": len(hits)})
        except S.SourceError as e:
            rec.update({"ok": False, "kind": e.kind, "detail": e.detail[:200]})
            if e.kind == "429" and stop["hit"] is None:
                stop["hit"] = rec
        except Exception as e:  # noqa: BLE001
            rec.update({"ok": False, "kind": "exception", "detail": f"{type(e).__name__}: {str(e)[:200]}"})
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        results.append(rec)

    offset = 0.0
    for rate, secs in phases:
        for k in range(int(rate * secs)):
            due = t_start + offset + k / rate
            if due - t_start >= total_cap_s:
                break
            pending.add(asyncio.create_task(one(counter["i"], rate, due)))
            counter["i"] += 1
        offset += secs
    while pending:
        done, pending = await asyncio.wait(pending, timeout=0.5)
        if stop["hit"] is not None:
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            pending = set()
    results.sort(key=lambda r: r["i"])
    ok_by_rate = collections.Counter(r["rate"] for r in results if r.get("ok"))
    err_by_rate = collections.Counter(r["rate"] for r in results if not r.get("ok"))
    out = {"calls": len(results), "ok_by_rate": {str(k): v for k, v in ok_by_rate.items()},
           "errors_by_rate": {str(k): v for k, v in err_by_rate.items()},
           "first_429": stop["hit"], "elapsed_s": round(time.monotonic() - t_start, 1),
           "latency_ms_p50": statistics.median([r["latency_ms"] for r in results]) if results else None,
           "latency_ms_p95": _p95([r["latency_ms"] for r in results]),
           "errors": [r for r in results if not r.get("ok")][:10]}
    if stop["hit"] is not None:
        status, retry_after = await _raw_probe(client.url)
        out["raw_probe_after_429"] = {"status": status, "retry_after": retry_after}
        ceiling = stop["hit"]["rate"]
        lower = max((r for r, _ in phases if r < ceiling), default=None)
        out["measured_ceiling_rps"] = lower if lower is not None else "below 1/s"
        out["recommended_EE_PARALLEL_RPS"] = round(lower * 0.7, 2) if lower else "keep 1.0 and re-measure"
    else:
        top = max(r for r, _ in phases)
        out["measured_ceiling_rps"] = f"no 429 observed up to {top:g}/s"
        out["recommended_EE_PARALLEL_RPS"] = round(top * 0.7, 2)
    return out


async def _raw_probe(url: str) -> tuple[int | None, str | None]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                                   "clientInfo": {"name": "evidence-engine-eval", "version": "0"}}},
                             headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
            return r.status_code, r.headers.get("retry-after")
    except Exception as e:  # noqa: BLE001
        return None, f"probe failed: {type(e).__name__}"


# ── assembly ───────────────────────────────────────────────────────────────

def surfaced_but_unreadable(c: dict) -> str | None:
    """The golden URL was in the search results (it reached the fetcher) but
    no card came of it: the fetch failed or no span survived. Read from the
    answer's `fetch_failures` / `dropped` lists (each truncated at 10, so
    this is a lower bound). Returns the reason, else None."""
    from evidence_engine.fetch import url_key
    if c.get("refound_url_key"):
        return None
    gk = url_key(c["url"])
    s = c.get("search") or {}
    for f in s.get("fetch_failures") or []:
        if url_key(f.get("url") or "") == gk:
            return "fetch failed: " + (f.get("reason") or "").split(" — ")[0]
    for d in s.get("dropped") or []:
        if url_key(d.get("url") or "") == gk:
            return "fetched, no span: " + (d.get("reason") or "")
    return None


def recall_table(calls: list[dict]) -> dict:
    per = {}
    for c in calls:
        if c.get("skipped"):
            continue
        k = (c["split"], c["client"])
        d = per.setdefault(k, {"split": c["split"], "client": c["client"], "rows": 0, "refound_url": 0, "refound_host": 0,
                               "surfaced_unreadable": 0, "errors": 0, "zero_cards": 0, "guard_refusals": 0,
                               "unreadable_reasons": collections.Counter()})
        d["rows"] += 1
        d["refound_url"] += bool(c.get("refound_url_key"))
        d["refound_host"] += bool(c.get("refound_host"))
        why = surfaced_but_unreadable(c)
        c["surfaced_but_unreadable"] = why
        if why:
            d["surfaced_unreadable"] += 1
            d["unreadable_reasons"][re.sub(r"\d+", "N", why)[:80]] += 1
        d["errors"] += bool(c.get("error"))
        d["zero_cards"] += not c.get("card_ids")
        d["guard_refusals"] += any(v.get("kind") == "refused" for v in c.get("guard_violations") or [])
    rows = list(per.values())
    for d in rows:
        d["recall_url"] = _pct(d["refound_url"], d["rows"])
        d["recall_host"] = _pct(d["refound_host"], d["rows"])
        d["recall_surfaced"] = _pct(d["refound_url"] + d["surfaced_unreadable"], d["rows"])
        d["unreadable_reasons"] = dict(d["unreadable_reasons"].most_common())
    def agg(ss: list[dict]) -> dict:
        n = sum(d["rows"] for d in ss)
        ru = sum(d["refound_url"] for d in ss)
        su = sum(d["surfaced_unreadable"] for d in ss)
        return {"rows": n, "refound_url": ru, "refound_host": sum(d["refound_host"] for d in ss), "surfaced_unreadable": su,
                "recall_url": _pct(ru, n), "recall_host": _pct(sum(d["refound_host"] for d in ss), n),
                "recall_surfaced": _pct(ru + su, n)}
    by_split = {s: agg([d for d in rows if d["split"] == s]) for s in ("tuning", "heldout")}
    return {"per_client": rows, "per_split": by_split, "overall": agg(rows)}


def _gap(a, b) -> float | None:
    if a is None or b is None:
        return None
    return round(abs(a - b) * 100, 1)


def generalisation(metrics: dict) -> dict:
    g = {}
    r = metrics.get("source_recall", {}).get("per_split", {})
    g["source_recall_url"] = _gap(r.get("tuning", {}).get("recall_url"), r.get("heldout", {}).get("recall_url"))
    g["source_recall_host"] = _gap(r.get("tuning", {}).get("recall_host"), r.get("heldout", {}).get("recall_host"))
    lv = metrics.get("url_liveness", {}).get("per_split", {})
    g["url_liveness"] = _gap(lv.get("tuning", {}).get("share"), lv.get("heldout", {}).get("share"))
    te = metrics.get("token_efficiency", {}).get("per_split", {})
    g["token_reduction"] = _gap(te.get("tuning", {}).get("reduction_refound"), te.get("heldout", {}).get("reduction_refound"))
    ef = metrics.get("excerpt_fidelity", {}).get("per_split", {})
    g["excerpt_fidelity"] = _gap(ef.get("tuning", {}).get("share"), ef.get("heldout", {}).get("share"))
    vals = [v for v in g.values() if v is not None]
    g["max_gap_points"] = max(vals) if vals else None
    g["within_bar"] = (max(vals) <= BARS["generalisation_gap_points"]["bar"]) if vals else None
    return g


def _fmt_share(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _verdict(value, bar: dict) -> str:
    if value is None:
        return "not measured"
    if bar["kind"] == "share":
        return "MEETS" if value >= bar["bar"] else "BELOW"
    if bar["kind"] == "count":
        return "MEETS" if value <= bar["bar"] else "ABOVE"
    if bar["kind"] in ("max", "max_target"):
        return "MEETS" if value <= bar["bar"] else "ABOVE"
    return "?"


def write_report(res: dict, path: Path = REPORT_PATH) -> None:
    m = res["metrics"]
    g = res["golden"]
    L = []
    L.append(f"# Evidence engine — golden-set evaluation report")
    L.append("")
    L.append(f"Run `{res['run_id']}` · {res['started_at']} → {res['finished_at']} ({res['elapsed_s']} s) · "
             f"golden **{g['version']}** (built {g['manifest']['built']}) · mode **{'LIVE' if res['live'] else 'OFFLINE'}** · "
             f"results `{res['results_path']}`")
    L.append("")
    L.append("This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, "
             "not a tuned result. Nothing in this report was adjusted after the run.")
    L.append("")
    L.append("## 1. Scorecard")
    L.append("")
    L.append("| Metric | Measured | Brief's bar | Verdict | Where measured |")
    L.append("|---|---|---|---|---|")
    ef = m.get("excerpt_fidelity", {})
    L.append(f"| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | {_fmt_share(ef.get('share'))} "
             f"({ef.get('verified')}/{ef.get('cards')} cards) | 100% (hard) | {_verdict(ef.get('share'), BARS['excerpt_fidelity'])} | offline, over the live run's cards |")
    bl = m.get("boilerplate_leakage", {})
    L.append(f"| Boilerplate leakage (anti-pattern matches in produced excerpts) | {bl.get('matches')} of {bl.get('cards')} | 0 (hard) | "
             f"{_verdict(bl.get('matches'), BARS['boilerplate_leakage'])} | offline |")
    sy = m.get("syndication_inflation", {})
    L.append(f"| Syndication inflation (clusters whose cards disagree with membership) | {sy.get('inflated')} of {sy.get('multi_url_clusters')} multi-URL clusters "
             f"({sy.get('clusters')} clusters) | 0 (hard) | {_verdict(sy.get('inflated'), BARS['syndication_inflation'])} | offline |")
    cs = m.get("card_sizes", {})
    mn = cs.get("minimal", {})
    L.append(f"| Card size, item + minimal provenance (tokens) | mean {mn.get('mean')} · p95 {mn.get('p95')} | ~120 target | "
             f"{_verdict(mn.get('mean'), BARS['card_tokens_item_minimal_mean'])} | offline ({cs.get('counter')}) |")
    lv = m.get("url_liveness", {})
    L.append(f"| URL liveness of produced cards (live or archived) | {_fmt_share(lv.get('share'))} ({lv.get('live_or_archived')}/{lv.get('cards_checked')}; "
             f"{lv.get('skipped_for_time', 0)} unchecked for time) | 100% (hard) | {_verdict(lv.get('share'), BARS['url_liveness'])} | LIVE |")
    sr = m.get("source_recall", {}).get("overall", {})
    L.append(f"| Source recall, same url_key | {_fmt_share(sr.get('recall_url'))} ({sr.get('refound_url')}/{sr.get('rows')}) | ≥ 80% | "
             f"{_verdict(sr.get('recall_url'), BARS['source_recall'])} | LIVE (baseline) |")
    L.append(f"| Source recall, same host (loose) | {_fmt_share(sr.get('recall_host'))} ({sr.get('refound_host')}/{sr.get('rows')}) | (informational) | — | LIVE |")
    L.append(f"| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | {_fmt_share(sr.get('recall_surfaced'))} "
             f"({sr.get('refound_url')} carded + {sr.get('surfaced_unreadable')} surfaced-unreadable / {sr.get('rows')}) | (diagnostic) | — | LIVE |")
    te = m.get("token_efficiency", {})
    ov = te.get("overall", {})
    L.append(f"| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | {_fmt_share(ov.get('reduction_refound'))} "
             f"({ov.get('card_tokens_refound')} vs {ov.get('raw_tokens_refound')} tokens over {ov.get('urls_refound')} URLs) | ≥ 60% | "
             f"{_verdict(ov.get('reduction_refound'), BARS['token_reduction'])} | LIVE fetch, offline count |")
    pc = te.get("per_card", {})
    L.append(f"| Token efficiency per produced card (its source page → the card) | {_fmt_share(pc.get('reduction'))} "
             f"({pc.get('card_tokens_item_minimal')} vs {pc.get('source_page_tokens')} tokens, {pc.get('cards')} cards) | (informational) | — | offline |")
    ge = m.get("generalisation", {})
    L.append(f"| Generalisation (largest tuning↔held-out gap) | {ge.get('max_gap_points')} points | ≤ 5 points | "
             f"{_verdict(ge.get('max_gap_points'), BARS['generalisation_gap_points'])} | both |")
    rp = m.get("parallel_ramp", {})
    at = res["metrics"].get("answer_tokens") or {}
    if at.get("calls"):
        L.append(f"| research_brief answer size an agent reads (tokens, whole answer) | mean {at['mean']} · p95 {at['p95']} · max {at['max']} (cards {_fmt_share(at.get('cards_share'))} of it) | (informational) | — | offline |")
    L.append(f"| Parallel rate-limit ceiling | {rp.get('measured_ceiling_rps', 'not run')} → recommend `EE_PARALLEL_RPS={rp.get('recommended_EE_PARALLEL_RPS', '?')}` | measured, never assumed | — | LIVE |")
    L.append("")
    L.append("## 2. What was measured live, what offline")
    L.append("")
    L.append("- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only "
             "discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; "
             "`verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the "
             "engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.")
    L.append("- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal "
             "census, syndication consistency, token counts.")
    L.append(f"- Ranking ran **{', '.join(sorted({c.get('rerank') or '?' for c in res['calls'] if not c.get('skipped')}))}** "
             "(no bundled models in this environment: `EE_MODELS_DIR` unset).")
    if res.get("prior_run"):
        n_prior = len(res.get("rows_from_prior") or [])
        L.append(f"- **Two passes over one store**: {n_prior} row(s) were answered live in the prior pass `{res['prior_run']}` "
                 f"(its research phase hit the time deadline before the held-out rows); this pass ran the remaining "
                 f"{sum(1 for c in res['calls'] if not c.get('from_prior') and not c.get('skipped'))} row(s) live and re-ran liveness, "
                 "fetches, offline metrics and the ramp over everything. Cold elapsed times are each row's own first call.")
    L.append("")
    L.append("## 3. Sample")
    L.append("")
    s = res["sample"]
    L.append(f"- Tuning: {s['tuning']['rows']} rows = {s['tuning']['rows']} distinct URLs drawn with seed {s['seed']} from "
             f"{s['tuning']['distinct_urls_available']} distinct positive URLs (one row per URL, the longest excerpt). "
             f"Held-out: {s['heldout']['rows']} rows, {s['heldout']['distinct_urls_available']} distinct URLs — all of them.")
    L.append(f"- research_brief arguments: `max_cards={res['args']['max_cards']}, token_budget={res['args']['token_budget']}, "
             f"provenance={res['args']['provenance']!r}`; time budget {res['args']['time_budget_s']} s.")
    L.append("- The golden set has **no question field**. Each question is derived from the row's excerpt: its content words minus "
             "the entity's name tokens, stop words and any platform name the vendor guard (`query.guard`) would refuse — "
             "an agent does not know the vendor before it finds the evidence — as `What does <entity> report about <terms>?`. "
             f"Platform names were stripped from {s['rows_with_platform_names_stripped']} question(s).")
    L.append("")
    L.append("### Entities derived from the golden rows")
    L.append("")
    L.append("| Client key | Split | Legal name (derived) | Own domain(s) | Aliases | Note |")
    L.append("|---|---|---|---|---|---|")
    for key, e in res["entities"].items():
        L.append(f"| {key} | {res['client_split'][key]} | {e['legal_name']} | {', '.join(e['domains']) or '— (none in rows)'} | "
                 f"{', '.join(e['aliases']) or '—'} | {e['derivation'].get('note') or ''} |")
    L.append("")
    L.append("Derivation: the most frequent institution-shaped phrase (…Credit Union / Bank / …) in the client's excerpts and "
             "source names that is linked to the client key (key inside the phrase, or the phrase's initials are a host label among "
             "the client's rows); the own domain is the registrable domain among the rows' hosts whose label carries the key, sits "
             "inside the legal name, or equals its initials. No location, charter or CIK is available, so `entity_match` can only be "
             "`confirmed` on an own-domain page.")
    L.append("")
    L.append("## 4. Source recall (baseline)")
    L.append("")
    L.append("| Split | Client key | Rows | Re-found (url_key) | Re-found (host) | Surfaced but unreadable | Zero-card answers | Errors |")
    L.append("|---|---|---|---|---|---|---|---|")
    for d in m.get("source_recall", {}).get("per_client", []):
        L.append(f"| {d['split']} | {d['client']} | {d['rows']} | {d['refound_url']} ({_fmt_share(d['recall_url'])}) | "
                 f"{d['refound_host']} ({_fmt_share(d['recall_host'])}) | {d['surfaced_unreadable']} | {d['zero_cards']} | {d['errors']} |")
    ps = m.get("source_recall", {}).get("per_split", {})
    for sp in ("tuning", "heldout"):
        d = ps.get(sp, {})
        L.append(f"| **{sp}** | all | {d.get('rows')} | {d.get('refound_url')} ({_fmt_share(d.get('recall_url'))}) | "
                 f"{d.get('refound_host')} ({_fmt_share(d.get('recall_host'))}) | {d.get('surfaced_unreadable')} | | |")
    L.append("")
    reasons = collections.Counter()
    for d in m.get("source_recall", {}).get("per_client", []):
        for k, v in (d.get("unreadable_reasons") or {}).items():
            reasons[k] += v
    if reasons:
        L.append("\"Surfaced but unreadable\": the search returned the golden URL but the engine emitted no card for it — "
                + "; ".join(f"{k} ×{v}" for k, v in reasons.most_common()) + ". These are fetchability losses, not retrieval losses "
                "(the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).")
        L.append("")
    tiers = collections.Counter((c.get("golden_tier"), bool(c.get("refound_url_key"))) for c in res["calls"] if not c.get("skipped"))
    L.append("Re-found by golden tier: " + "; ".join(
        f"{t}: {tiers.get((t, True), 0)}/{tiers.get((t, True), 0) + tiers.get((t, False), 0)}"
        for t in sorted({t for t, _ in tiers}, key=str)) + ".")
    L.append("")
    L.append("### Per call")
    L.append("")
    L.append("| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c in res["calls"]:
        if c.get("skipped"):
            L.append(f"| {c['golden_id']} | {c['split']} | — | — | — | — | — | — | skipped: {c['skipped']} |")
            continue
        note = c.get("error") or ""
        if c.get("platform_names_stripped"):
            note += (" " if note else "") + f"stripped {len(c['platform_names_stripped'])} platform name(s)"
        if c.get("search", {}).get("rerouted"):
            note += " " + ",".join(c["search"]["rerouted"])
        L.append(f"| {c['golden_id']} | {c['split']} | {len(c.get('card_ids') or [])} | {c.get('search', {}).get('hits')} | "
                 f"{c.get('search', {}).get('fetched')} | {'url' if c.get('refound_url_key') else ('host' if c.get('refound_host') else '—')} | "
                 f"{json.dumps(c.get('entity_match') or {})} | {c.get('elapsed_ms')} ms | {note[:120]} |")
    L.append("")
    L.append("## 5. Timing, counts, breakers")
    L.append("")
    tm = res["timing"]
    L.append(f"- research_brief elapsed: mean {tm.get('research_mean_ms')} ms · p95 {tm.get('research_p95_ms')} ms · "
             f"max {tm.get('research_max_ms')} ms over {tm.get('research_calls')} calls. Warm repeats: " +
             ("; ".join(f"{w['split']} cold {w['cold_ms']} ms → warm {w['warm_ms']} ms (cached search calls {w['warm_cached_calls']})"
                        for w in res.get("warm", [])) or "none"))
    L.append(f"- Totals: hits {tm.get('hits_total')} · fetched {tm.get('fetched_total')} · cards {tm.get('cards_total')} · "
             f"fetch failures shown {tm.get('fetch_failures_shown')} · dropped shown {tm.get('dropped_shown')} "
             "(the tool truncates both lists at 10 per answer, so these are lower bounds).")
    L.append(f"- Phase wall time (s): {json.dumps(tm.get('phases'))}")
    h = res.get("health") or {}
    L.append(f"- Breakers open at the end: {h.get('open') or []}. Parallel breaker: {json.dumps((h.get('breakers') or {}).get('parallel'))}. "
             f"Coalescer: {json.dumps(h.get('coalescer'))}.")
    errs = [c for c in res["calls"] if c.get("error")]
    L.append(f"- Errors: {len(errs)}" + ("".join(f"\n  - {c['golden_id']}: {c['error'][:200]}" for c in errs[:10])))
    drop_reasons = collections.Counter()
    for c in res["calls"]:
        for d in (c.get("search") or {}).get("dropped") or []:
            drop_reasons[re.sub(r"\d+", "N", d.get("reason", ""))[:90]] += 1
    L.append("- Drop reasons (shown subset): " + ("; ".join(f"{k} ×{v}" for k, v in drop_reasons.most_common(8)) or "none"))
    fail_reasons = collections.Counter()
    for c in res["calls"]:
        for d in (c.get("search") or {}).get("fetch_failures") or []:
            fail_reasons[re.sub(r"\d+", "N", (d.get("reason") or "").split(" — ")[0])[:70]] += 1
    L.append("- Fetch-failure reasons (shown subset): " + ("; ".join(f"{k} ×{v}" for k, v in fail_reasons.most_common(8)) or "none"))
    L.append("")
    L.append("## 6. Boilerplate: produced cards and the golden-negative census")
    L.append("")
    L.append(f"Produced excerpts matching an anti-pattern: **{bl.get('matches')}** of {bl.get('cards')}.")
    L.append("")
    nc = m.get("negatives_refusal_census", {})
    L.append(f"Golden NEGATIVE rows with a considered defect ({', '.join(DEFECT_CLASSES)}): {nc.get('rows_with_a_considered_defect')}; "
             f"the anti-pattern list + `contract.item_problems` excerpt rules would have refused **{nc.get('refused')}** "
             f"({_fmt_share(nc.get('share'))}).")
    L.append("")
    L.append("| Defect class | Golden rows | Refused | Share | By rule |")
    L.append("|---|---|---|---|---|")
    for dcls, pc_ in (nc.get("per_class") or {}).items():
        L.append(f"| {dcls} | {pc_['rows']} | {pc_['refused']} | {_fmt_share(pc_['share'])} | "
                 f"{'; '.join(f'{k} ×{v}' for k, v in list(pc_['by_rule'].items())[:5])} |")
    L.append("")
    unref = {d: pc_["unrefused"] for d, pc_ in (nc.get("per_class") or {}).items() if pc_["unrefused"]}
    if unref:
        L.append("Rows a defect class marks that NO rule refuses (gaps to extend the list from; golden ids only — excerpts in the results JSON):")
        for d, rows_ in unref.items():
            L.append(f"- {d}: " + ", ".join(f"{r['golden_id']} ({r['len']} chars)" for r in rows_))
        L.append("")
    L.append("## 7. Card size")
    L.append("")
    L.append("| Projection | Cards | Mean tokens | p95 | Min | Max |")
    L.append("|---|---|---|---|---|---|")
    for mode in ("minimal", "standard", "full"):
        d = cs.get(mode, {})
        L.append(f"| item + {mode} provenance | {d.get('cards')} | {d.get('mean')} | {d.get('p95')} | {d.get('min')} | {d.get('max')} |")
    io = cs.get("item_only", {})
    L.append(f"| item only | | {io.get('mean')} | {io.get('p95')} | | |")
    L.append("")
    L.append(f"Counter: {cs.get('counter')}.")
    L.append("")
    L.append("## 8. Token efficiency")
    L.append("")
    L.append("Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, "
             "trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path "
             "would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). "
             "Measured only on URLs the engine re-found (a URL with no card has nothing to compare).")
    L.append("")
    L.append("| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |")
    L.append("|---|---|---|---|---|---|---|")
    for sp, d in (te.get("per_split") or {}).items():
        L.append(f"| {sp} | {d.get('urls')} | {d.get('urls_refound')} | {d.get('raw_tokens_refound')} | {d.get('card_tokens_refound')} | "
                 f"{_fmt_share(d.get('reduction_refound'))} | {d.get('fetch_failed')} |")
    L.append(f"| **all** | {ov.get('urls')} | {ov.get('urls_refound')} | {ov.get('raw_tokens_refound')} | {ov.get('card_tokens_refound')} | "
             f"{_fmt_share(ov.get('reduction_refound'))} | {ov.get('fetch_failed')} |")
    L.append("")
    L.append(f"Secondary (every produced card against its own source page): {_fmt_share(pc.get('reduction'))} reduction, "
             f"{pc.get('cards')} cards. Raw tokens of ALL sampled golden pages the fetcher could read: {ov.get('raw_tokens_all_sampled_urls')}.")
    L.append("")
    L.append("## 9. Generalisation (tuning vs held-out, points)")
    L.append("")
    for k, v in ge.items():
        L.append(f"- {k}: {v}")
    L.append("")
    L.append("## 10. Parallel rate-limit ramp")
    L.append("")
    if rp:
        L.append(f"- {rp.get('calls')} `web_search` calls in {rp.get('elapsed_s')} s; ok by rate {json.dumps(rp.get('ok_by_rate'))}; "
                 f"errors by rate {json.dumps(rp.get('errors_by_rate'))}; latency p50 {rp.get('latency_ms_p50')} ms, p95 {rp.get('latency_ms_p95')} ms.")
        L.append(f"- First 429: {json.dumps(rp.get('first_429'))}; raw probe after it: {json.dumps(rp.get('raw_probe_after_429'))}.")
        L.append(f"- Measured ceiling: **{rp.get('measured_ceiling_rps')}** → recommended `EE_PARALLEL_RPS={rp.get('recommended_EE_PARALLEL_RPS')}` "
                 "(measured × 0.7; the engine's default stays 1.0 until this is adopted).")
        if rp.get("errors"):
            L.append(f"- Non-429 errors (first 10): {json.dumps(rp['errors'])[:800]}")
    else:
        L.append("- not run")
    L.append("")
    L.append("## 11. Limitations — read before quoting a number")
    L.append("")
    for lim in res["limitations"]:
        L.append(f"- {lim}")
    L.append("")
    L.append("## 12. Golden-set version deltas")
    L.append("")
    L.append(f"- {g['version']} is the first version; no previous run to diff against.")
    L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def limitations_for(res: dict) -> list[str]:
    m = res["metrics"]
    ents = res["entities"]
    out = [
        "Discovery ran on ONE free source (Parallel Search MCP, anonymous). SearXNG — the brief's primary backend — is not "
        "deployed in this environment, so recall is the recall of Parallel alone through the engine's five facet queries and "
        "its own-domain `site:` query; the registry `site_pack` is empty, so no regulator/trade-press `site:` probes ran.",
        "Questions are DERIVED from golden excerpts (no question field exists). A derived question carries the excerpt's own "
        "vocabulary, which favours re-finding the page the excerpt came from; a diagnostic question an agent asks would not. "
        "Treat recall as an upper-ish bound of the retrieval path, not as the recall of the research protocol.",
        "Platform names in an excerpt were stripped from the question (the vendor guard refuses them; an agent does not know the "
        "vendor in advance), so golden rows whose fact IS a vendor relationship are asked about as capability terms only.",
        "Entities are derived from the golden rows alone: no location, charter number or CIK, so `entity_match` is `probable` at best "
        "off the own domain; " + "; ".join(f"`{k}` has no own-domain host in its rows (no `site:` query, no `confirmed` match)"
                                            for k, e in ents.items() if not e["domains"]) + ".",
        "Token counts use the 4-chars-per-token heuristic over compact JSON (`tiktoken` is not installed); the ~120 target and the "
        "reduction figures are heuristic tokens, not a tokenizer's.",
        "Token efficiency is tokens of content (cleaned page vs card), not a transcript measurement of an agent's turn; the "
        "denominator excludes the search hits an agent would also read.",
        "Ranking was BM25-only (`EE_MODELS_DIR` unset): the dense + cross-encoder rerank the design expects was not exercised.",
        "The research_brief answer truncates `fetch_failures` and `dropped` at 10, so drop/failure totals are lower bounds.",
        "Liveness is one GET (first chunk) per card URL at the time of the run; a WAF that answers a browser UA differently "
        f"later is not captured. {m.get('url_liveness', {}).get('skipped_for_time', 0)} card(s) were not checked because the "
        "time budget ran out." if m.get("url_liveness") else "Liveness was not measured (offline run).",
        "The golden-negative census applies only the EXCERPT rules (anti-pattern list, length, clause clip at 140, sentence "
        "completeness) to rows the golden builder tagged; `hard_clip` in the golden set covers widths 80/100/120/140 while the "
        "connector's `clause_truncated` signature is 140 only, so an 80/100/120 clip is refused only when it also fails sentence "
        "completeness.",
        "Tuning positives were sampled (one row per distinct URL, seeded); a golden URL with several rows was asked ONE question.",
        f"Held-out positives: {res['sample']['heldout']['rows']} rows from one client — the held-out split is small, so its recall "
        "moves in steps of ~8 points and the generalisation gap is coarse.",
        "The Parallel ramp is a polite, short measurement (≤ 90 calls, ≤ 60 s) from one network location; a free anonymous tier's "
        "ceiling may differ by hour and by origin.",
    ]
    if res.get("sample", {}).get("tuning", {}).get("skipped"):
        out.append(f"{res['sample']['tuning']['skipped']} tuning call(s) were skipped for time.")
    return out


# ── main ───────────────────────────────────────────────────────────────────

async def _main_async(a) -> dict:
    golden = load_golden(a.version)
    by_client = rows_by_client(golden)
    entities = {c: derive_entity(c, d["positives"] + d["negatives"]) for c, d in by_client.items()}
    client_split = {c: d["split"] for c, d in by_client.items()}
    tun = golden["splits"]["tuning"]["positives"]
    held = golden["splits"]["heldout"]["positives"]
    for r in tun:
        r["split"] = "tuning"
    for r in held:
        r["split"] = "heldout"
    samples = sample_positives(tun, max_urls=a.max_tuning_urls, seed=a.seed) + sample_positives(held, max_urls=None, seed=a.seed)
    started = dt.datetime.now(dt.timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{a.version}-{stamp}"
    data_dir = Path(a.data_dir) if a.data_dir else Path(os.environ.get("EE_DATA_DIR") or (ROOT / ".eval-data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine(data_dir)
    from evidence_engine import ratelimit as RL
    t_all = time.monotonic()
    deadline = t_all + a.time_budget_s
    phases = {}
    calls: list[dict] = []
    warm: list[dict] = []
    metrics: dict = {}
    print(f"[harness] {run_id} · {len(samples)} questions · data_dir={data_dir} · live={a.live}")
    for c, e in entities.items():
        print(f"[entity] {c}: {e['legal_name']!r} domains={e['domains']} aliases={e['aliases']}")
    prior_calls: dict[str, dict] = {}
    prior_id = None
    if a.prior:
        prior = json.loads(Path(a.prior).read_text(encoding="utf-8"))
        prior_id = prior.get("run_id")
        for c in prior.get("calls") or []:
            if not c.get("skipped") and not c.get("error") and c.get("elapsed_ms") is not None:
                prior_calls[c["golden_id"]] = dict(c, from_prior=prior_id)
        print(f"[harness] prior run {prior_id}: {len(prior_calls)} answered rows reused (same store, cold timings kept)")
    try:
        if a.live:
            t = time.monotonic()
            research_deadline = t_all + a.time_budget_s * 0.55
            todo = [s for s in samples if s["golden_id"] not in prior_calls]
            fresh = {c["golden_id"]: c for c in await run_research(
                engine, todo, entities, max_cards=a.max_cards, token_budget=a.token_budget,
                provenance=a.provenance, deadline=research_deadline)}
            calls = [prior_calls.get(s["golden_id"]) or fresh[s["golden_id"]] for s in samples]
            phases["research"] = round(time.monotonic() - t, 1)
            t = time.monotonic()
            if time.monotonic() < deadline:
                warm = await warm_repeat(engine, calls, entities, max_cards=a.max_cards, token_budget=a.token_budget,
                                         provenance=a.provenance)
            phases["warm_repeat"] = round(time.monotonic() - t, 1)
            t = time.monotonic()
            metrics["url_liveness"] = await liveness(engine, calls, deadline=t_all + a.time_budget_s * 0.80)
            phases["liveness"] = round(time.monotonic() - t, 1)
            t = time.monotonic()
            metrics["token_efficiency"] = await token_efficiency(engine, calls, deadline=t_all + a.time_budget_s * 0.92)
            phases["token_efficiency"] = round(time.monotonic() - t, 1)
        else:
            # offline: re-read the cards already in the store for these runs
            for row in samples:
                run = f"eval-{row['client']}"
                full = engine.store.list_cards(run)
                found = [(c["card_id"], _matches(c, row["url"])) for c in full]
                calls.append({"golden_id": row["golden_id"], "client": row["client"], "split": row["split"], "url": row["url"],
                              "golden_tier": row.get("tier"), "run_id": run, "offline": True,
                              "question": question_for(row, entities[row["client"]])["question"],
                              "cards_full": full, "card_ids": [c["card_id"] for c in full],
                              "refound_url_key": any(m == "url_key" for _, m in found),
                              "refound_host": any(m for _, m in found), "matching_cards": [cid for cid, m in found if m],
                              "search": {}, "elapsed_ms": None})
        # offline metrics over whatever cards exist
        all_cards: dict[str, dict] = {}
        for c in calls:
            for card in c.get("cards_full") or []:
                all_cards[card["card_id"]] = card
        cards = list(all_cards.values())
        ef = excerpt_fidelity(engine.store, cards)
        ef["per_split"] = {}
        for sp in ("tuning", "heldout"):
            sub = {card["card_id"]: card for c in calls if c.get("split") == sp for card in (c.get("cards_full") or [])}
            ef["per_split"][sp] = excerpt_fidelity(engine.store, list(sub.values()))
        metrics["excerpt_fidelity"] = ef
        metrics["boilerplate_leakage"] = boilerplate_leakage(cards)
        negatives = golden["splits"]["tuning"]["negatives"] + golden["splits"]["heldout"]["negatives"]
        metrics["negatives_refusal_census"] = negatives_refusal_census(negatives)
        metrics["syndication_inflation"] = syndication_inflation(calls)
        metrics["card_sizes"] = card_sizes(cards)
        metrics["answer_tokens"] = answer_tokens(calls)
        metrics["source_recall"] = recall_table(calls)
        metrics["generalisation"] = generalisation(metrics)
        if a.live and a.ramp and engine.parallel is not None:
            t = time.monotonic()
            print("[harness] Parallel ramp …")
            metrics["parallel_ramp"] = await parallel_ramp(engine.parallel)
            phases["ramp"] = round(time.monotonic() - t, 1)
        elif a.prior and (prior.get("metrics") or {}).get("parallel_ramp"):
            # measured once per day is polite enough; the prior pass's ramp stands
            metrics["parallel_ramp"] = dict(prior["metrics"]["parallel_ramp"], measured_in=prior_id)
        health = RL.health()
    finally:
        await engine.fetcher.aclose()
    finished = dt.datetime.now(dt.timezone.utc)
    done_calls = [c for c in calls if c.get("elapsed_ms") is not None]
    el = [c["elapsed_ms"] for c in done_calls]
    timing = {"research_calls": len(done_calls), "research_mean_ms": int(statistics.fmean(el)) if el else None,
              "research_p95_ms": _p95(el), "research_max_ms": max(el) if el else None,
              "hits_total": sum((c.get("search") or {}).get("hits") or 0 for c in calls),
              "fetched_total": sum((c.get("search") or {}).get("fetched") or 0 for c in calls),
              "cards_total": len({cid for c in calls for cid in (c.get("card_ids") or [])}),
              "fetch_failures_shown": sum((c.get("search") or {}).get("fetch_failures_shown") or 0 for c in calls),
              "dropped_shown": sum((c.get("search") or {}).get("dropped_shown") or 0 for c in calls),
              "phases": phases}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = RESULTS_DIR / f"{run_id}.json"
    res = {
        "run_id": run_id, "live": a.live, "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"), "elapsed_s": round(time.monotonic() - t_all, 1),
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()},
        "golden": {"version": golden["version"], "dir": golden["dir"], "manifest": golden["manifest"]},
        "entities": entities, "client_split": client_split,
        "sample": {"seed": a.seed,
                   "tuning": {"rows": sum(1 for s in samples if s["split"] == "tuning"),
                              "distinct_urls_available": len({r["url"] for r in tun}),
                              "skipped": sum(1 for c in calls if c.get("skipped") and c["split"] == "tuning")},
                   "heldout": {"rows": sum(1 for s in samples if s["split"] == "heldout"),
                               "distinct_urls_available": len({r["url"] for r in held})},
                   "rows_with_platform_names_stripped": sum(1 for c in calls if c.get("platform_names_stripped")),
                   "golden_ids": [s["golden_id"] for s in samples]},
        "calls": calls, "warm": warm, "metrics": metrics, "timing": timing, "health": health,
        "prior_run": prior_id, "rows_from_prior": sorted(prior_calls) if prior_calls else [],
        "results_path": str(results_path.relative_to(ROOT)),
        "data_dir": str(data_dir),
    }
    res["limitations"] = limitations_for(res)
    # the stored copy carries the full cards; the report only summarises them
    results_path.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    write_report(res, Path(a.report) if a.report else REPORT_PATH)
    print(f"[harness] results → {results_path}")
    print(f"[harness] report  → {a.report or REPORT_PATH}")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="golden set version directory under eval/golden/")
    ap.add_argument("--live", action="store_true", help="run research_brief, liveness, fetches and the ramp against the network")
    ap.add_argument("--no-ramp", dest="ramp", action="store_false", help="skip the Parallel rate-limit ramp")
    ap.add_argument("--max-tuning-urls", type=int, default=25)
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--max-cards", type=int, default=8)
    ap.add_argument("--token-budget", type=int, default=20000)
    ap.add_argument("--provenance", default="full", choices=("minimal", "standard", "full"))
    ap.add_argument("--time-budget-s", type=float, default=1500.0, help="whole-run wall-clock cap; later phases shrink to fit")
    ap.add_argument("--data-dir", default=None, help="engine store (default: $EE_DATA_DIR or ./.eval-data)")
    ap.add_argument("--report", default=None, help="markdown path (default docs/EVAL-REPORT.md)")
    ap.add_argument("--prior", default=None,
                    help="a previous results JSON over the SAME store: its answered rows are reused (cold timings kept) "
                         "and only the rows it skipped or never reached run live")
    a = ap.parse_args(argv)
    asyncio.run(_main_async(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
