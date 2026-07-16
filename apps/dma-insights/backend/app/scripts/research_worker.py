"""Deep-research worker: answers the clarification queue by crawling the web.

The composers file clarifications (``research_queue.jsonl``) when a claim
needs knowledge the run doesn't hold — this worker is the research tier
that ANSWERS them. For each open question it runs a bounded web search
(DuckDuckGo lite HTML — no API key), fetches the top result pages, and
extracts candidate sentences that actually address the question (dated
sentences for G2 date-verification; capability-term matches for G3
corroboration). Findings are written as CANDIDATE material with full
citation (url, title, excerpt, retrieved_at) to
``research_answers.jsonl`` and the queue row moves to
``answered_pending_review`` — never auto-asserted into the evidence
store (the same review discipline as the mapping ladder: a human or the
CI warm tier promotes candidates).

Crawl discipline: ≤1 request/second, per-run request cap, page-size cap,
honest User-Agent, graceful degradation (a blocked provider yields
outcome='provider_unavailable', never a crash), content-hash dedup.
Every answered row logs a crawler-engine trigger firing under Tab-01.

Usage:
    python -m app.scripts.research_worker [--max-rows 10] [--grounds G2,G3]
        [--queue PATH] [--answers PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import UTC, datetime

_HERE = os.path.dirname(__file__)
_BENCH = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "benchmarks"))
DEFAULT_QUEUE = os.path.join(_BENCH, "research_queue.jsonl")
DEFAULT_ANSWERS = os.path.join(_BENCH, "research_answers.jsonl")

_UA = ("Mozilla/5.0 (X11; Linux x86_64) DMA-Insights-Research/1.0 "
       "(clarification worker; contact: ops)")
_SEARCH_URL = "https://lite.duckduckgo.com/lite/?q={q}"
_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*class="result-link"[^>]*>'
    r"(?P<title>.*?)</a>", re.S)
_ALT_RESULT_RE = re.compile(
    r'<a[^>]+rel="nofollow"[^>]+href="(?P<href>(?:https?:)?//[^"]+)"[^>]*>'
    r"(?P<title>.*?)</a>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MAX_PAGE_BYTES = 400_000
_REQ_GAP_SEC = 1.1
# A row that came back empty this many times is exhausted — the web has
# been asked; selection skips it so batches always reach fresh work.
_MAX_ATTEMPTS = 3
_STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on",
         "needed", "event", "timeline", "with", "real", "date", "its",
         "this", "run", "no", "textual", "prose", "cited", "evidence",
         "finding", "backs", "corroborating", "category"}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get(url: str, timeout: float = 12.0, retries: int = 0) -> str | None:
    import httpx
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout,
                          follow_redirects=True)
            if r.status_code == 200:
                return r.text[:_MAX_PAGE_BYTES]
            # 202 is the provider's soft anti-bot answer — worth one
            # backed-off retry; hard statuses are not.
            if r.status_code != 202:
                return None
        except Exception:
            pass
        if attempt < retries:
            time.sleep(3.0 * (attempt + 1))
    return None


def _search(query: str) -> list[tuple[str, str]] | None:
    """[(url, title)] from the lite provider.

    Returns None when the provider itself is unreachable/blocked (fetch
    failed), [] when it answered but no results parsed — callers count
    those as different outcomes (provider_unavailable vs no_material).
    """
    page = _http_get(_SEARCH_URL.format(q=urllib.parse.quote_plus(query)),
                     retries=1)
    if not page:
        return None
    out: list[tuple[str, str]] = []
    for rx in (_RESULT_RE, _ALT_RESULT_RE):
        for m in rx.finditer(page):
            href = html.unescape(m.group("href"))
            if href.startswith("//"):
                href = "https:" + href
            if "duckduckgo.com" in href and "uddg=" in href:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = (q.get("uddg") or [href])[0]
            title = _TAG_RE.sub("", m.group("title")).strip()
            if href.startswith("http") and title:
                out.append((href, html.unescape(title)))
        if out:
            break
    seen: set[str] = set()
    uniq = []
    for u, t in out:
        d = urllib.parse.urlparse(u).netloc
        if d and d not in seen:
            seen.add(d)
            uniq.append((u, t))
    return uniq[:4]


# charter-type vocabulary every financial institution shares — never a
# distinctive entity anchor ('credit union' matches the whole industry)
_GENERIC_FI = {
    "bank", "banks", "credit", "union", "unions", "financial", "insurance",
    "mutual", "federal", "savings", "trust", "company", "group", "holdings",
    "holding", "limited", "corp", "corporation", "inc", "capital", "wealth",
    "partners", "services", "the", "1st", "first", "national", "community",
}
# company-directory / boilerplate-analysis mills — aggregated filler, not
# a primary source for an entity's stated objectives
_MILL_RE = re.compile(
    r"incfact|zoominfo|dnb\.com|pitchbook|crunchbase|craft\.co|"
    r"pestel-analysis|storyboard|globaldata|owler|lead411", re.I)

# forward-looking objective language — the shape a strategic-objective
# sentence takes in annual reports, investor decks, and interviews
_OBJECTIVE_RE = re.compile(
    r"\b(?:strateg\w+|priorit\w+|invest\w+|expand\w*|launch\w*|plan(?:s|ned|ning)?|"
    r"transform\w*|moderniz\w*|accelerat\w*|initiative\w*|roadmap|"
    r"aims?\b|will\b|goals?\b|focus(?:ed|ing)?\b|commit\w*)", re.I)


def _source_kind(url: str, title: str) -> str:
    """Coarse source-type tag so a focus answer shows its diversity —
    investor material, news, interview, report, or general web."""
    u = f"{url} {title}".lower()
    if re.search(r"investor|\bir\.|sec\.gov|10-k|annual[- ]report|proxy", u):
        return "investor"
    if re.search(r"interview|podcast|q&a|fireside|transcript", u):
        return "interview"
    if re.search(r"news|press|prnewswire|businesswire|banker|journal|"
                 r"reuters|bloomberg|finextra", u):
        return "news"
    if re.search(r"report|whitepaper|study", u):
        return "report"
    return "web"


def _terms(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z][\w&'-]{2,}", text)
            if w.lower() not in _STOP}


# Navigation/boilerplate debris that survives tag-stripping: subscription
# walls, cookie banners, menu crumbs, social chrome. A candidate matching
# this (or dominated by one repeated short phrase) is site chrome, not
# content — filtered at mining time AND re-checked at promotion time
# (promote_research_answers), so pre-gate answers can't leak debris into
# the evidence store either.
_DEBRIS_RE = re.compile(
    r"subscribe (?:to see|now|today|for)|sign (?:in|up) (?:to|for)|"
    r"cookies? (?:policy|settings|preferences)|accept all cookies|"
    r"javascript is (?:disabled|required)|enable javascript|"
    r"all rights reserved|privacy policy|terms of (?:use|service)|"
    r"skip to (?:main )?content|related articles|share this article|"
    r"follow us on|click here to|"
    # inline script/style bodies that survive tag-stripping
    r"function\s*\(|=>\s*\{|console\.log|gtm\.js|dataLayer|"
    r"var\s+\w+\s*=|window\.\w+\s*=|"
    # JSON-LD / schema.org structured-data blobs
    r"\"@(?:type|id|context)\"|schema\.org|inLanguage", re.I)


def is_nav_debris(sentence: str) -> bool:
    """True when a mined sentence is site chrome rather than content:
    boilerplate phrases, or one short token-run repeated to fill it."""
    s = str(sentence or "").strip()
    if not s:
        return True
    if _DEBRIS_RE.search(s):
        return True
    # repetition test: a 3-token shingle recurring 3+ times and covering
    # half the sentence is a rendered menu/paywall, not prose
    toks = s.lower().split()
    if len(toks) >= 9:
        shingles = [" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)]
        top = max(map(shingles.count, set(shingles)))
        if top >= 3 and top * 3 >= len(toks) * 0.5:
            return True
    return False


def _candidate_sentences(page_text: str, subject_terms: set[str],
                         entity_terms: set[str],
                         want_date: bool,
                         min_subj: int | None = None,
                         ent_credit: int = 0,
                         want_digit: bool = False) -> list[tuple[float, str]]:
    """Scored [(score, sentence)] — subject-term hits weigh double
    entity-name hits, so boilerplate that merely name-drops the
    institution ranks below prose about the event itself. A sentence
    must hit ≥1 subject term and ≥2 terms total; G2 rows additionally
    need a real textual date (that IS the question).

    ``min_subj`` overrides the rich-subject rule: question-driven rows
    keep the ≥2-hit demand for ≥4-term subjects (a name-drop plus a date
    is how founding dates masquerade as event dates), but surface PLANS
    seed a wide OR-vocabulary ('founded established chartered…') where
    ONE hit is the signal — they pass min_subj=1 explicitly.

    ``ent_credit`` grants implicit entity attribution: an institution's
    OWN pages say 'our', not the institution's full legal name, so the
    entity-hit requirement zeroes exactly the best sources. Callers pass
    1 for a page that already passed the strict entity-anchor head check.
    ``want_digit`` keeps only quantified sentences — a revenue/headcount/
    founding answer without a number in it isn't an answer."""
    text = _TAG_RE.sub(" ", page_text)
    text = html.unescape(re.sub(r"\s+", " ", text))
    sents = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        if 40 <= len(s) <= 400:
            sents.append(
                (s, {w.lower()
                     for w in re.findall(r"[A-Za-z][\w&'-]{2,}", s)}))
    # rarity weighting within the page: a subject term that appears in
    # half the page's sentences ('credit' on a consumer-finance site)
    # is near-worthless as a discriminator; the event-specific tokens
    # ('versatile', 'acquired') carry the score.
    import math
    weight = {t: 2.0 / (1.0 + math.log1p(
        sum(1 for _, toks in sents if t in toks)))
        for t in subject_terms}
    scored: list[tuple[float, str]] = []
    for s, stoks in sents:
        if is_nav_debris(s):
            continue
        if want_digit and not re.search(r"\d", s):
            continue
        hit_subj = subject_terms & stoks
        n_ent = len(entity_terms & stoks) + ent_credit
        # rich subjects (≥4 distinct terms) must hit ≥2 of them — one
        # name-drop plus a date is how founding dates masquerade as
        # event dates.
        _min = min_subj if min_subj is not None else (
            2 if len(subject_terms) >= 4 else 1)
        if len(hit_subj) < _min or (len(hit_subj) + n_ent) < 2:
            continue
        if want_date:
            from app.services.nlp.dates import resolve_event_date
            d, prec = resolve_event_date(s)
            if prec in ("none", "publish_fallback"):
                continue
        scored.append((sum(weight[t] for t in hit_subj) + 0.5 * n_ent, s))
    scored.sort(key=lambda t: -t[0])
    return scored[:2]


def _load_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _plan_for(row: dict, entity_words: str, subject: str) -> dict | None:
    """Default query set + mining posture for a queue row's SURFACE.

    Every routed surface carries purpose-built query variants (what a
    researcher would actually type) and a subject SEED that points the
    sentence miner at the material — the filed question's own prose
    ("…is not on file — a public filing is needed") would otherwise score
    sentences about filings, not about the fact.

    Returns None for question-driven rows, which keep the original
    single-query flow: cards/findings always, and any row a COMPOSER
    filed with a specific subject (a deepen-filed timeline G2 names ONE
    event — sweeping generic news for it would answer the wrong
    question). Plans apply to focus_area rows from any filer (the
    multi-source objective sweep) and to the generic census rows
    route_empty_surfaces files.
    """
    surface = row.get("surface") or ""
    ctx = (row.get("context") or "").strip()
    e = entity_words
    if surface != "focus_area" and row.get("filed_by") != "route_empty_surfaces":
        return None
    if surface == "focus_area":
        yr = _now()[:4]
        return {
            "variants": (f"{e} strategic priorities {yr}",
                         f"{e} annual report strategy",
                         f"{e} CEO interview digital strategy",
                         f"{e} investor news initiative"),
            "want_date": False, "objective_only": True, "anchor": True,
            "per_variant": 3, "need_domains": 3, "max_sources": 4,
            "min_subj": None,
            "subject": (f"strategic priorities plan initiative investment "
                        f"transformation digital {subject}")[:160],
            "label": f"{e} strategic objectives (multi-source)"}
    if surface == "firmographics":
        table = {
            "founded": ((f"{e} founded year history", f"{e} about company"),
                        "founded established founding chartered "
                        "incorporated since history"),
            "hq_address": ((f"{e} headquarters address",
                            f"{e} corporate office location"),
                           "headquartered headquarters office located "
                           "address main campus"),
            "headcount": ((f"{e} number of employees",
                           f"{e} employees workforce size"),
                          "employees employs workforce staff people "
                          "team full-time"),
            "revenue_usd": ((f"{e} annual revenue results",
                             f"{e} financial results report"),
                            "revenue income results reported fiscal "
                            "million billion assets"),
        }
        variants, seed = table.get(
            ctx, ((f"{e} company profile",), "company profile overview"))
        return {"variants": variants, "want_date": False,
                "objective_only": False, "anchor": True, "per_variant": 3,
                "need_domains": 2, "max_sources": 3, "min_subj": 1,
                # a founding/headcount/revenue answer needs the number
                "want_digit": ctx in ("founded", "headcount", "revenue_usd"),
                # directory mills are legitimate SECONDARY sources for
                # identity facts (they exist to aggregate exactly these);
                # the objective sweep still excludes them.
                "allow_mills": True,
                "subject": seed[:160], "label": f"{e} firmographics:{ctx}"}
    if surface == "leadership":
        return {"variants": (f"{e} CEO", f"{e} executive leadership team"),
                "want_date": False, "objective_only": False, "anchor": True,
                "per_variant": 3, "need_domains": 2, "max_sources": 3, "min_subj": 1,
                "subject": ("chief executive officer president cfo coo cto "
                            "chairman appointed named leads"),
                "label": f"{e} leadership"}
    if surface == "timeline":
        return {"variants": (f"{e} announcement news",
                             f"{e} acquisition launch partnership"),
                "want_date": True, "objective_only": False, "anchor": True,
                "per_variant": 3, "need_domains": 2, "max_sources": 3, "min_subj": 1,
                "subject": ("announced completed launched acquired "
                            "partnership expansion opened introduced"),
                "label": f"{e} timeline milestones"}
    if surface == "tech_stack":
        return {"variants": (f"{e} technology platform vendor",
                             f"{e} Salesforce core banking digital"),
                "want_date": False, "objective_only": False, "anchor": True,
                "per_variant": 3, "need_domains": 2, "max_sources": 3, "min_subj": 1,
                "subject": ("salesforce ncino fiserv temenos platform "
                            "technology core banking crm deployed selected "
                            "implementation vendor"),
                "label": f"{e} tech stack"}
    if surface == "focus_kpi":
        return {"variants": (f"{e} investor presentation results",
                             f"{e} annual report key metrics"),
                "want_date": False, "objective_only": False, "anchor": True,
                "per_variant": 3, "need_domains": 2, "max_sources": 3, "min_subj": 1,
                "want_digit": True,
                "subject": (f"grew increased results percent members "
                            f"customers assets ratio {subject}")[:160],
                "label": f"{e} disclosed metrics"}
    return None


def run(queue_path: str, answers_path: str, max_rows: int,
        grounds: set[str], dry_run: bool) -> dict:
    from app.services.enrichment_triggers import Trigger, TriggerFiring, log_firing
    rows = _load_rows(queue_path)
    # Selection discipline (live-batch diagnosis: three consecutive batches
    # answered 0 because the queue HEAD is legacy no-material rows that stay
    # open and get re-chewed forever, never reaching fresh work):
    #   - rows exhausted by _MAX_ATTEMPTS fruitless tries are skipped;
    #   - planned rows (census + focus sweeps) rank before question-driven
    #     ones, fewest-attempts first, so every batch reaches new material.
    open_rows = [r for r in rows
                 if r.get("status") == "open" and r.get("ground") in grounds
                 and int(r.get("attempts") or 0) < _MAX_ATTEMPTS]
    open_rows.sort(key=lambda r: (
        0 if (r.get("filed_by") == "route_empty_surfaces"
              or r.get("surface") == "focus_area") else 1,
        int(r.get("attempts") or 0)))
    answered = provider_down = no_material = underspecified = 0
    dirty = False
    for r in open_rows[:max_rows]:
        entity_words = r["entity"].replace("-", " ")
        entity_words = re.sub(r"\b\d{4}\b", "", entity_words).strip()
        # display_ids are TRUNCATED slugs ('1st-security-bank-of-was') —
        # census questions carry the entity's REAL name as their prefix
        # ('1st Security Bank of Washington: founding year …'); a query
        # built from the full name finds what the stump can't.
        if r.get("filed_by") == "route_empty_surfaces":
            m = re.match(r"^([^:]{3,70}):\s", r.get("question") or "")
            if m:
                entity_words = m.group(1).strip()
        subject = re.sub(r"^.*?'(.*?)'.*$", r"\1", r["question"])
        # queue subjects are elided at filing time — drop the ellipsis
        # and any half-word it cut through.
        subject = re.sub(r"\S*[…]+\S*\s*$", "", subject).strip()
        # Routed surfaces carry a purpose-built query PLAN (multi-source
        # sweep, 2026-07-12 directive): the material surfaces across
        # financials, news, interviews and investor pages, and one query
        # angle won't find it all. Each variant contributes its top hits;
        # domains dedup ACROSS variants so the answer cites DIVERSITY.
        plan = _plan_for(r, entity_words, subject)
        if plan is None:
            # question-driven rows (cards/findings): a stub subject
            # ('AssuredPartners agreed') matches anything the entity ever
            # agreed to — augment from the filed context, and if still
            # under-specified refuse honestly rather than answer wrong
            if len(_terms(subject) - _terms(entity_words)) < 2:
                subject = f"{subject} {(r.get('context') or '')[:120]}".strip()
            if len(_terms(subject) - _terms(entity_words)) < 2:
                underspecified += 1
                r["attempts"] = int(r.get("attempts") or 0) + 1
                r["last_attempt_at"] = _now()
                dirty = True
                continue
        is_focus = r.get("surface") == "focus_area"
        if plan is not None:
            results = []
            _fail = 0
            _seen_dom: set[str] = set()
            for _q in plan["variants"]:
                _hits = _search(_q)
                time.sleep(_REQ_GAP_SEC)
                if _hits is None:
                    _fail += 1
                    continue
                for u, t in _hits[:plan["per_variant"]]:
                    d = urllib.parse.urlparse(u).netloc
                    if d and d not in _seen_dom:
                        _seen_dom.add(d)
                        results.append((u, t))
            if _fail == len(plan["variants"]):
                results = None
        else:
            query = f"{entity_words} {subject}"[:120]
            results = _search(query)
            time.sleep(_REQ_GAP_SEC)
        if results is None:
            provider_down += 1
            time.sleep(8.0)  # soft-block cooldown before the next row
            continue
        if not results:
            no_material += 1
            r["attempts"] = int(r.get("attempts") or 0) + 1
            r["last_attempt_at"] = _now()
            dirty = True
            continue
        # G2 timeline questions need a real textual date (that IS the
        # question); G2 strategic-objective/identity-fact validation
        # doesn't — the statement itself is the material, and recency
        # rides on the source page rather than an in-sentence date.
        if plan is not None:
            want_date = plan["want_date"]
            query = plan["label"]
            # the plan's subject SEED points the miner at the material
            subject = plan["subject"]
        else:
            want_date = (r.get("ground") == "G2"
                         and r.get("surface") != "focus_area")
        subject_terms = _terms(subject)
        entity_terms = _terms(entity_words) - subject_terms
        scored_sources: list[tuple[float, dict]] = []
        _ent_anchor = _terms(entity_words)
        for url, title in results:
            page = _http_get(url, retries=1)
            time.sleep(_REQ_GAP_SEC)
            if not page:
                continue
            if plan is not None and plan["anchor"]:
                # entity anchoring: generic industry strategy content
                # passes term scoring on FI-generic tokens ('credit
                # union'), and directory mills aggregate every company —
                # the page must carry a DISTINCTIVE entity token (the
                # proper name, not the charter type) and not be a mill.
                if _MILL_RE.search(url) and not plan.get("allow_mills"):
                    continue
                _head = html.unescape(_TAG_RE.sub(" ", page[:3000])).lower()
                _blob = f"{_head} {title.lower()}"
                _distinct = _ent_anchor - _GENERIC_FI
                if _distinct and not any(t in _blob for t in _distinct):
                    continue
                if sum(1 for t in _ent_anchor if t in _blob) < min(
                        2, len(_ent_anchor)):
                    continue
            # A page that PASSED the strict entity-anchor head check has
            # established whose page it is — its sentences carry implicit
            # entity attribution ('our', not the legal name; an
            # institution's own site zeroed the per-sentence entity gate
            # on exactly the best sources).
            _credit = 1 if (plan is not None and plan["anchor"]) else 0
            for score, s in _candidate_sentences(
                    page, subject_terms, entity_terms, want_date,
                    min_subj=(plan.get("min_subj")
                              if plan is not None else None),
                    ent_credit=_credit,
                    want_digit=bool(plan.get("want_digit"))
                    if plan is not None else False):
                if is_focus:
                    if _OBJECTIVE_RE.search(s):
                        score += 2.0
                    else:
                        continue  # focus answers must be objective-shaped
                scored_sources.append((score, {
                    "url": url, "title": title[:140],
                    "excerpt": s[:400], "retrieved_at": _now(),
                    "source_kind": _source_kind(url, title)}))
            # enough distinct pages contributing — stop crawling early
            _need_domains = plan["need_domains"] if plan is not None else 2
            if len({d["url"] for _, d in scored_sources}) >= _need_domains \
                    and len(scored_sources) >= _need_domains + 1:
                break
        scored_sources.sort(key=lambda t: -t[0])
        # a straggler scoring under half the best hit is boilerplate
        # that merely shares vocabulary — don't ship it as support.
        if scored_sources:
            floor = scored_sources[0][0] / 2
            scored_sources = [t for t in scored_sources if t[0] >= floor]
        # one excerpt per URL: a page's second-best sentence is noise,
        # not corroboration — corroboration means a DIFFERENT source.
        seen_urls: set[str] = set()
        sources = []
        for _, d in scored_sources:
            if d["url"] in seen_urls:
                continue
            seen_urls.add(d["url"])
            sources.append(d)
        if not sources:
            no_material += 1
            r["attempts"] = int(r.get("attempts") or 0) + 1
            r["last_attempt_at"] = _now()
            dirty = True
            continue
        key_hash = hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode()).hexdigest()[:12]
        if not dry_run:
            with open(answers_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "key": r["key"], "question": r["question"],
                    "entity": r["entity"], "ground": r["ground"],
                    "sources": sources[:plan["max_sources"] if plan is not None
                                       else 3], "content_hash": key_hash,
                    "confidence": "candidate",
                    "status": "pending_review", "answered_at": _now(),
                }) + "\n")
            r["status"] = "answered_pending_review"
            log_firing(TriggerFiring(
                trigger=(Trigger.G2_STALENESS if want_date
                         else Trigger.G3_CORROBORATION),
                query=query[:200], engine="crawler", outcome="crawled",
                entity_id=r["entity"], field=r.get("surface")))
        answered += 1
    if not dry_run and (answered or dirty):
        with open(queue_path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return {"open": len(open_rows), "attempted": min(len(open_rows), max_rows),
            "answered": answered, "no_material": no_material,
            "underspecified": underspecified,
            "provider_unavailable": provider_down}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="clarification research worker")
    ap.add_argument("--queue", default=DEFAULT_QUEUE)
    ap.add_argument("--answers", default=DEFAULT_ANSWERS)
    ap.add_argument("--max-rows", type=int, default=10)
    ap.add_argument("--grounds", default="G2,G3")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    rep = run(args.queue, args.answers, args.max_rows,
              set(args.grounds.split(",")), args.dry_run)
    print(f"# research_worker: {json.dumps(rep)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
