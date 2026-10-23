"""Find the institution in the registry that holds it — every sub-vertical,
US and Canada.

WHY (owner, 2026-10-12): "The tool is supposed to be find registrant as we
deal with 9 subverticals in US and Canada." The registrant lookup the plugin
exposed was EDGAR's company search: it answers for a public company and
nothing else, so a private insurance broker, a credit union, a Farm Credit
association or a Canadian insurer came back "no match" — measured on a
private insurance broker, 0 results. The registry that holds an
institution depends on what it is and where:

  credit unions (CU)        NCUA (US) · OSFI federal / provincial (CA)
  retail and commercial
  banking, CIB (RB CL CIB)  FDIC BankFind (US) · OSFI (CA)
  asset and wealth
  management (AM RIA WM)    SEC IAPD + FINRA BrokerCheck (US) · CSA/CIRO (CA)
  insurance (IC IB)         NAIC / state departments (US) · OSFI + provincial (CA)
  Farm Credit (FC)          Farm Credit Administration directory (US)
  any public parent         SEC EDGAR

THE RULE. Each registry with a free, keyless interface is queried directly
(measured reachable 2026-10-12): SEC EDGAR entity search, SEC IAPD, FINRA
BrokerCheck, FDIC BankFind, NCUA's locator and detail API, the FCA's Farm
Credit System directory, OSFI's "who we regulate" list (open.canada.ca CSV).
A registry with no such interface (NAIC CIS is a script app; the CSA National
Registration Search refuses automated reads; provincial credit-union and
insurance regulators publish pages, not APIs) is searched through the
engine's own SearXNG/Parallel fan-out as `site:` probes on that regulator's
hosts, and its hits come back as CANDIDATES with `method: "search"`, never
as a registry record. Each registry's outcome is reported — ok, no_match,
error or not_applicable — so "not found" is an answer with its ladder, not a
silence. A match carries the registry's identifier (CIK, CRD, FDIC cert,
NCUA charter, FCA UNINUM), the record URL a person can open, and the fields
the registry states (status, city, region; for NCUA also assets and members).
Pure apart from the HTTP client it is handed.
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
import time
from dataclasses import dataclass

import httpx

from .textnorm import normalise
from .types import EntityRef

#: the nine sub-verticals by code, with the labels a run may use instead
SUB_VERTICALS = {
    "CU": ("credit union", "credit unions"),
    "RB": ("retail bank", "retail banking", "bank", "banks", "community bank"),
    "CL": ("commercial lending", "lending", "commercial lender"),
    "CIB": ("corporate and investment banking", "investment banking", "corporate banking"),
    "AM": ("asset management", "asset manager"),
    "RIA": ("ria", "wealth", "wealth management", "registered investment adviser", "wm"),
    "IC": ("insurance carrier", "insurance carriers", "insurer", "carrier"),
    "IB": ("insurance brokerage", "insurance broker", "insurance brokerages", "broker"),
    "FC": ("farm credit", "agricultural credit"),
}

#: registry -> what it holds; `direct` registries have a keyless interface
REGISTRIES = {
    "sec_edgar": {"name": "SEC EDGAR", "country": "US", "id": "CIK", "direct": True},
    "sec_iapd": {"name": "SEC Investment Adviser Public Disclosure", "country": "US", "id": "CRD", "direct": True},
    "finra_brokercheck": {"name": "FINRA BrokerCheck", "country": "US", "id": "CRD", "direct": True},
    "fdic": {"name": "FDIC BankFind", "country": "US", "id": "FDIC certificate", "direct": True},
    "ncua": {"name": "NCUA credit union locator", "country": "US", "id": "NCUA charter", "direct": True},
    "fca_us": {"name": "Farm Credit Administration — FCS directory", "country": "US", "id": "UNINUM", "direct": True},
    "osfi": {"name": "OSFI — federally regulated financial institutions", "country": "CA", "id": None, "direct": True},
    "us_insurance_regulators": {"name": "NAIC and state insurance departments", "country": "US", "id": None,
                                "direct": False,
                                "hosts": ["naic.org", "gov"],
                                # an SEC page is EDGAR's record (asked directly), not an insurance regulator's
                                "exclude_hosts": ["sec.gov"]},
    "ca_provincial_regulators": {"name": "Canadian provincial financial regulators", "country": "CA", "id": None,
                                 "direct": False,
                                 "hosts": ["fsrao.ca", "bcfsa.ca", "lautorite.qc.ca", "cudgc.sk.ca",
                                           "fcaa.gov.sk.ca", "ribo.com", "fcnb.ca", "nsbi.ca"]},
    "ca_securities_regulators": {"name": "Canadian Securities Administrators and CIRO", "country": "CA", "id": None,
                                 "direct": False,
                                 "hosts": ["securities-administrators.ca", "ciro.ca", "osc.ca", "bcsc.bc.ca"]},
}

#: which registries hold which sub-vertical, by country; a public parent may
#: file with the SEC whatever it is, so EDGAR is asked for every US entity
ROUTES = {
    "US": {"CU": ["ncua"], "RB": ["fdic"], "CL": ["fdic"], "CIB": ["fdic", "finra_brokercheck"],
           "AM": ["sec_iapd", "finra_brokercheck"], "RIA": ["sec_iapd", "finra_brokercheck"],
           "IC": ["us_insurance_regulators"], "IB": ["us_insurance_regulators", "finra_brokercheck"],
           "FC": ["fca_us"]},
    "CA": {"CU": ["osfi", "ca_provincial_regulators"], "RB": ["osfi"], "CL": ["osfi"], "CIB": ["osfi",
           "ca_securities_regulators"], "AM": ["ca_securities_regulators"], "RIA": ["ca_securities_regulators"],
           "IC": ["osfi", "ca_provincial_regulators"], "IB": ["ca_provincial_regulators"], "FC": []},
}
ALWAYS = {"US": ["sec_edgar"], "CA": []}

FDIC_URL = "https://api.fdic.gov/banks/institutions"
NCUA_SEARCH = "https://mapping.ncua.gov/api/Search/GetSearchLocations"
NCUA_DETAIL = "https://mapping.ncua.gov/api/CreditUnionDetails/GetCreditUnionDetails/{charter}"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
IAPD_SEARCH = "https://api.adviserinfo.sec.gov/search/firm"
BROKERCHECK_SEARCH = "https://api.brokercheck.finra.org/search/firm"
FCA_DIRECTORY = "https://apps.fca.gov/FCSPublicDirectory/PubViewInstitutionsBySysDist.aspx"
OSFI_CSV = ("https://open.canada.ca/data/dataset/b27ec3ef-7338-4e76-a6fd-128339a92df5/resource/"
            "945045fa-2de0-47d4-aad2-144d69467824/download/who_we_regulate_fi_eng.csv")
OSFI_PAGE = "https://www.osfi-bsif.gc.ca/en/supervision/who-we-regulate"

_STOP = frozenset("the of and inc incorporated llc l.l.c corp corporation co company ltd limited plc lp llp "
                  "na n.a fsb group holdings holding".split())
_CONNECTIVES = frozenset({"the", "of", "and"})
#: lists that change rarely are read once per process for this long
LIST_TTL_S = 6 * 3600


def sub_vertical_code(label: str | None) -> str | None:
    s = re.sub(r"[^a-z ]", " ", (label or "").lower()).strip()
    if not s:
        return None
    if s.upper() in SUB_VERTICALS or s.upper() == "WM":
        return "RIA" if s.upper() == "WM" else s.upper()
    for code, names in SUB_VERTICALS.items():
        if any(s == n or n in s for n in names):
            return code
    return None


def name_tokens(name: str) -> list[str]:
    """Lower-case words of a name, legal-form words and single letters
    ("L.P." -> l, p) set aside."""
    return [t for t in re.findall(r"[a-z0-9]+", normalise(name or "")) if t not in _STOP and len(t) > 1]


#: the kind-of-institution tail a registry's own name search does not carry
#: (NCUA lists "EXAMPLE TECHNOLOGY", not "Example Technology Federal Credit Union")
_KIND_TAIL = re.compile(r"\b(?:federal\s+credit\s+union|credit\s+union|fcu|national\s+association|"
                        r"n\.?a\.?|fsb|aca|flca|pca)\b\.?", re.I)


def registry_query(name: str) -> str:
    """The name as a registry's search box wants it: legal form, kind tail
    and punctuation dropped (EDGAR's entity search answered HTTP 500 to a
    comma, measured 2026-10-12)."""
    base = _KIND_TAIL.sub(" ", name or "")
    words = name_tokens(base) or name_tokens(name)
    return " ".join(words)


#: words every institution in a sector shares; two names that agree only on
#: these are different institutions (measured 2026-10-12: "Colonial Farm
#: Credit, ACA" scored 0.6 against "Horizon Farm Credit, ACA" on them)
_SECTOR = frozenset("bank banks bancorp bancshares banking credit union federal fcu financial finance "
                    "insurance insurer assurance life mutual farm aca flca pca agricultural ag trust savings "
                    "national community state capital investment investments advisors advisers advisory "
                    "wealth management asset partners services fund funds america american canada "
                    "canadian first".split())


def names_in(name: str, text: str) -> bool:
    """The name's words, in order and adjacent, somewhere in `text` — a page
    that names the institution, not one that shares its words (measured
    2026-10-12: NAIC papers on Investment Management Agreements came back as
    candidates for a brokerage whose name begins with the same acronym)."""
    def words(t: str, drop: frozenset) -> list[str]:
        return [w for w in re.findall(r"[a-z0-9]+", normalise(t or "")) if w not in drop and len(w) > 1]
    # connectives stay on both sides, so "of the" never glues two words together
    want, have = words(name, _STOP - _CONNECTIVES), words(text, frozenset())
    k = len(want)
    return bool(k) and any(have[i:i + k] == want for i in range(len(have) - k + 1))


def name_score(query: str, candidate: str) -> float:
    """Overlap (Jaccard) of the DISTINCTIVE words — sector words that every
    institution of a kind carries are set aside unless a name has nothing
    else; 1.0 on equality of the full token sets."""
    q, c = set(name_tokens(query)), set(name_tokens(candidate))
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    # the whole-name part compares names with the kind tail set aside: NCUA
    # lists "EXAMPLE TECHNOLOGY" for Example Technology Federal Credit Union
    qk, ck = set(registry_query(query).split()) or q, set(registry_query(candidate).split()) or c
    full = len(qk & ck) / len(qk | ck)
    qd, cd = q - _SECTOR, c - _SECTOR
    if qd:
        if not qd & cd:
            return 0.0
        # the distinctive words decide; the whole name breaks ties, so "Navy
        # Capital Fund 1, LP" no longer reads as "Navy Federal Credit Union"
        return round(0.7 * len(qd & cd) / len(qd | cd) + 0.3 * full, 3)
    return round(full, 3)


def plan(sub_vertical: str | None, country: str | None) -> list[str]:
    """The registries to ask, in order. Unknown sub-vertical: every direct
    registry of the country (the lookup is cheap; a miss costs nothing)."""
    countries = [country.upper()] if country and country.upper() in ROUTES else ["US", "CA"]
    code = sub_vertical_code(sub_vertical)
    out: list[str] = []
    for ctry in countries:
        if code:
            regs = ROUTES[ctry].get(code, [])
        else:
            regs = [r for r, m in REGISTRIES.items() if m["country"] == ctry]
        for r in regs + ALWAYS[ctry]:     # the sub-vertical's own registry first
            if r not in out:
                out.append(r)
    return out


@dataclass
class Match:
    registry: str
    name: str
    identifier: str
    url: str
    score: float
    status: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    detail: dict | None = None

    def to_dict(self) -> dict:
        meta = REGISTRIES[self.registry]
        d = {"registry": self.registry, "registry_name": meta["name"], "identifier_type": meta["id"],
             "identifier": self.identifier, "name": self.name, "status": self.status, "city": self.city,
             "region": self.region, "country": self.country or meta["country"], "record_url": self.url,
             "match_score": self.score, "method": "registry"}
        if self.detail:
            d["registry_fields"] = self.detail
        return d


class Registrants:
    """The lookups, over an injected httpx client (tests pass a MockTransport)."""

    _lists: dict = {}

    def __init__(self, http: httpx.AsyncClient, *, user_agent: str, min_score: float = 0.6,
                 per_registry: int = 3):
        self.http = http
        self.ua = user_agent
        self.min_score = min_score
        self.per_registry = per_registry

    async def _json(self, method: str, url: str, *, retry: bool = False, **kw):
        headers = {"User-Agent": self.ua, "Accept": "application/json", **kw.pop("headers", {})}
        for attempt in (0, 1):
            r = await self.http.request(method, url, headers=headers, **kw)
            if r.status_code >= 500 and retry and attempt == 0:
                await asyncio.sleep(1.0)
                continue
            r.raise_for_status()
            return r.json()

    async def _text(self, url: str) -> str:
        r = await self.http.get(url, headers={"User-Agent": self.ua})
        r.raise_for_status()
        return r.text

    def _keep(self, query: str, rows: list[Match]) -> list[Match]:
        rows = [m for m in rows if m.score >= self.min_score]
        rows.sort(key=lambda m: -m.score)
        seen, out = set(), []
        for m in rows:
            if m.identifier not in seen:
                seen.add(m.identifier)
                out.append(m)
        return out[: self.per_registry]

    # ── the direct registries ───────────────────────────────────────────
    async def sec_edgar(self, name: str) -> list[Match]:
        data = await self._json("GET", EDGAR_SEARCH, params={"keysTyped": registry_query(name)}, retry=True)
        out = []
        for h in (data.get("hits") or {}).get("hits") or []:
            ent = (h.get("_source") or {}).get("entity") or ""
            cik = str(h.get("_id") or "").lstrip("0")
            label = re.sub(r"\s*\([A-Z0-9.\-, ]+\)\s*$", "", ent).strip()
            out.append(Match("sec_edgar", label, cik,
                             f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                             name_score(name, label)))
        return self._keep(name, out)

    async def _finra_style(self, registry: str, url: str, name: str, page: str) -> list[Match]:
        data = await self._json("GET", url, params={"query": registry_query(name), "hl": "false", "nrows": 6, "start": 0,
                                                   "r": 25, "sort": "score+desc", "wt": "json"})
        out = []
        for h in (data.get("hits") or {}).get("hits") or []:
            s = h.get("_source") or {}
            crd = str(s.get("firm_source_id") or "")
            label = s.get("firm_name") or ""
            names = [label] + list(s.get("firm_other_names") or [])
            score = max(name_score(name, n) for n in names if n) if names else 0.0
            scope = s.get("firm_ia_scope") if registry == "sec_iapd" else (s.get("firm_scope") or s.get("firm_ia_scope"))
            addr = {}
            raw = s.get("firm_ia_address_details") or s.get("firm_address_details")
            if isinstance(raw, str):
                import json as _json
                try:
                    addr = (_json.loads(raw) or {}).get("officeAddress") or {}
                except ValueError:
                    addr = {}
            out.append(Match(registry, label, crd, page.format(crd=crd), score, status=scope,
                             city=(addr.get("city") or None), region=(addr.get("state") or None),
                             detail={"sec_number": s.get("firm_ia_full_sec_number") or s.get("firm_bd_full_sec_number")}))
        return self._keep(name, out)

    async def sec_iapd(self, name: str) -> list[Match]:
        return await self._finra_style("sec_iapd", IAPD_SEARCH, name, "https://adviserinfo.sec.gov/firm/summary/{crd}")

    async def finra_brokercheck(self, name: str) -> list[Match]:
        return await self._finra_style("finra_brokercheck", BROKERCHECK_SEARCH, name,
                                       "https://brokercheck.finra.org/firm/summary/{crd}")

    async def fdic(self, name: str) -> list[Match]:
        q = registry_query(name) or name
        data = await self._json("GET", FDIC_URL, params={
            "search": f'NAME:"{q}"', "limit": 10,
            "fields": "NAME,CERT,CITY,STALP,ACTIVE,FED_RSSD,REGAGNT,WEBADDR,ASSET,ESTYMD"})
        out = []
        for row in data.get("data") or []:
            d = row.get("data") or {}
            cert = str(d.get("CERT") or "")
            out.append(Match("fdic", d.get("NAME") or "", cert,
                             f"https://banks.data.fdic.gov/bankfind-suite/bankfind/details/{cert}",
                             name_score(name, d.get("NAME") or ""),
                             status="Active" if d.get("ACTIVE") == 1 else "Inactive",
                             city=d.get("CITY"), region=d.get("STALP"),
                             detail={"primary_regulator": d.get("REGAGNT"), "fed_rssd": d.get("FED_RSSD"),
                                     "website": d.get("WEBADDR"), "total_assets_thousands": d.get("ASSET"),
                                     "established": d.get("ESTYMD")}))
        return self._keep(name, out)

    async def ncua(self, name: str) -> list[Match]:
        data = await self._json("POST", NCUA_SEARCH, json={
            "searchText": registry_query(name) or name, "rdSearchType": "cuname",
            "skip": 0, "take": 25, "sort_direction": "asc", "sort_field": "cuname"})
        best: dict[str, Match] = {}
        for row in data.get("list") or []:
            charter = str(row.get("creditUnionNumber") or "")
            label = row.get("creditUnionName") or ""
            score = name_score(name, label)
            if charter and (charter not in best or row.get("isMainOffice")):
                best[charter] = Match("ncua", label, charter, NCUA_DETAIL.format(charter=charter), score,
                                      city=row.get("city"), region=row.get("state"))
        kept = self._keep(name, list(best.values()))
        for m in kept:              # the detail record states charter type, status, assets, members
            try:
                d = await self._json("GET", NCUA_DETAIL.format(charter=m.identifier))
            except (httpx.HTTPError, ValueError):
                continue
            m.status = d.get("creditUnionStatus")
            m.city, m.region = d.get("creditUnionCity") or m.city, d.get("creditUnionState") or m.region
            m.detail = {k: d.get(v) for k, v in (
                ("website", "creditUnionWebsite"), ("ceo", "creditUnionCeo"),
                ("charter_type", "creditUnionType"), ("chartered", "creditUnionIssuedDate"),
                ("total_assets", "assetsFormatted"), ("members", "membersFormatted"),
                ("field_of_membership", "creditUnionFom"), ("region", "creditUnionRegion")) if d.get(v)}
        return kept

    async def _cached_list(self, key: str, url: str) -> str:
        hit = self._lists.get(key)
        if hit and time.monotonic() - hit[0] < LIST_TTL_S:
            return hit[1]
        text = await self._text(url)
        type(self)._lists[key] = (time.monotonic(), text)
        return text

    async def fca_us(self, name: str) -> list[Match]:
        page = await self._cached_list("fca", FCA_DIRECTORY)
        import html as _html
        cells = [c.strip() for c in re.split(r"<[^>]+>", _html.unescape(page)) if c.strip()]
        out = []
        for i, c in enumerate(cells[:-1]):
            if re.fullmatch(r"\d{6}", c):
                label = cells[i + 1]
                if re.search(r"[A-Za-z]{3}", label):
                    out.append(Match("fca_us", label, c, FCA_DIRECTORY, name_score(name, label)))
        return self._keep(name, out)

    async def osfi(self, name: str) -> list[Match]:
        text = await self._cached_list("osfi", OSFI_CSV)
        out = []
        for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
            label = row.get("Company Name") or ""
            trade = row.get("Canadian Trade Company Name") or ""
            score = max(name_score(name, label), name_score(name, trade) if trade else 0.0)
            out.append(Match("osfi", label, label, OSFI_PAGE, score, status="Federally regulated",
                             city=(row.get("City") or "").title() or None, region=row.get("Province State") or None,
                             country="CA", detail={"type": row.get("FI Type Name"), "group": row.get("FI Group Name"),
                                                   "industry": row.get("FI Industry Name")}))
        return self._keep(name, out)

    # ── the run ───────────────────────────────────────────────────────────
    async def lookup(self, entity: EntityRef, *, sub_vertical: str | None = None, country: str | None = None,
                     search=None) -> dict:
        """-> {matches, registries, candidates, plan}. `search(queries)` is the
        engine's fan-out for the registries without an interface; None skips
        them (recorded as not_run)."""
        names = [n for n in dict.fromkeys([entity.legal_name, *(entity.aliases or ())]) if n and len(n) > 3]
        regs = plan(sub_vertical, country)
        report, matches, fallback = [], [], []

        async def ask(reg: str):
            meta = REGISTRIES[reg]
            if not meta["direct"]:
                fallback.append(reg)
                return
            fn = getattr(self, reg)
            found: list[Match] = []
            try:
                for n in names[:2]:
                    found += await fn(n)
            except (httpx.HTTPError, ValueError, KeyError) as e:
                report.append({"registry": reg, "registry_name": meta["name"], "status": "error",
                               "reason": f"{type(e).__name__}: {str(e)[:160]}"})
                return
            found = self._keep(names[0], found)
            report.append({"registry": reg, "registry_name": meta["name"],
                           "status": "ok" if found else "no_match", "matches": len(found)})
            matches.extend(found)

        await asyncio.gather(*(ask(r) for r in regs))
        candidates = []
        for reg in fallback:
            meta = REGISTRIES[reg]
            if search is None:
                report.append({"registry": reg, "registry_name": meta["name"], "status": "not_run",
                               "reason": "no search backend available for the regulators without a registry API"})
                continue
            from .query import _quote, search_name
            queries = [{"query_id": f"R-{reg}-{i}", "text": f"site:{h} {_quote(search_name(entity))}",
                        "facet": "corroborates", "kind": "site:regulator"}
                       for i, h in enumerate(meta["hosts"])]
            hits = await search(queries)
            keep = [h for h in hits
                    if any(_under_host(h.get("url"), host) for host in meta["hosts"])
                    and not any(_under_host(h.get("url"), x) for x in meta.get("exclude_hosts", ()))
                    and any(names_in(n, f"{h.get('title', '')} {h.get('snippet', '')}") for n in names)]
            for h in keep[: self.per_registry]:
                candidates.append({"registry": reg, "registry_name": meta["name"], "method": "search",
                                   "url": h.get("url"), "title": h.get("title"), "snippet": h.get("snippet")})
            report.append({"registry": reg, "registry_name": meta["name"],
                           "status": "candidates" if keep else "no_match", "matches": len(keep),
                           "hosts_searched": meta["hosts"]})
        order = {r: i for i, r in enumerate(regs)}
        for r in report:            # two records in one registry at the top score: the ET check decides
            tops = [m for m in matches if m.registry == r["registry"]]
            if len(tops) > 1 and tops[0].score == max(m.score for m in tops) and \
                    sum(1 for m in tops if m.score == max(x.score for x in tops)) > 1:
                r["ambiguous"] = True
        report.sort(key=lambda r: order.get(r["registry"], 99))
        matches.sort(key=lambda m: (-m.score, order.get(m.registry, 99)))
        return {"plan": regs, "sub_vertical_code": sub_vertical_code(sub_vertical),
                "matches": [m.to_dict() for m in matches], "candidates": candidates, "registries": report}


def _under_host(url: str | None, host: str) -> bool:
    m = re.match(r"^[a-z]+://(?:www\.)?([^/:?#]+)", url or "", flags=re.I)
    h = (m.group(1) if m else "").lower()
    return h == host or h.endswith("." + host)
