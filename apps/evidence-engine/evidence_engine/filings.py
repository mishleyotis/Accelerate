"""SEC filings as evidence documents — brief §1 (Filings) and §6 (rate limits).

WHY. An issuer's 10-K/10-Q/8-K is the one place its technology, risk and
operating narrative is stated under signature, and its XBRL facts are
exact figures with a period, a unit and a filing behind them. Both are
T1 "filing" sources for the card layer (which classifies sec.gov; tier
and registry are not this module's concern).

THE RULE. The engine links `edgartools` (MIT) in-process behind ONE seam,
`EdgarProvider`, so that (a) every SEC call runs in a worker thread
behind the global SEC bucket — `await sec_wait()` before EVERY provider
call, 8 requests/second ceiling (DISCOVERY §4: SEC states 10/s; the engine
runs at 0.8 × that) — and (b) tests never touch the network: they inject
`FakeProvider`, which serves canned filings and facts. Nothing here
excerpts: `filings_evidence` returns whole Document-like dicts (section
text joined under headings, verify_text identical to text) and one
single-sentence document per XBRL fact so that the card pipeline can
select a verbatim span from either. Dates are the FILING date (what EDGAR
states), never today's; `retrieved` is the only field that carries today.

edgartools 5.61.1 calls used (introspected 2026-10-10, see DISCOVERY §4):
  `edgar.set_identity(str)`; `edgar.use_local_storage(path)` (guarded by
  getattr — absent builds fall back to edgartools' own cache);
  `Company(cik_or_ticker)` → `.cik .name .tickers .sic .fiscal_year_end
  .not_found .data.state_of_incorporation`; `Company.get_filings(form=,
  year=)` → iterable of `EntityFiling` (`accession_number form filing_date
  report_date primary_document primary_doc_description base_dir`);
  `edgar.get_by_accession_number(acc)` → `Filing`; `Filing.obj()` → `TenK`
  with `.get("Item 1A")` for item text; `Filing.text()` for the whole
  primary document; `Company.get_facts()` → `EntityFacts`, with
  `.query().by_concept(c).execute()` and `.get_all_facts()` returning
  `FinancialFact(concept label value numeric_value unit period_start
  period_end fiscal_year fiscal_period filing_date form_type accession)`.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from .config import settings
from .textnorm import sha256_text

SecWait = Callable[[], Awaitable[None]]

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

#: The 10-K items the engine reads when the filing exposes sections
#: (brief: 1, 1A, 7, 7A, 9A; 1C — cybersecurity — added because the
#: capability catalogue asks for it directly). Label = EDGAR's own title.
TENK_ITEMS: tuple[tuple[str, str], ...] = (
    ("Item 1", "Business"),
    ("Item 1A", "Risk Factors"),
    ("Item 1C", "Cybersecurity"),
    ("Item 7", "Management's Discussion and Analysis"),
    ("Item 7A", "Quantitative and Qualitative Disclosures About Market Risk"),
    ("Item 9A", "Controls and Procedures"),
)


def accession_digits(accession: str) -> str:
    return re.sub(r"[^0-9]", "", accession or "")


def cik10(cik: str | int) -> str:
    """Zero-padded ten-digit CIK, the form EDGAR URLs and JSON use."""
    return str(int(re.sub(r"[^0-9]", "", str(cik)) or "0")).zfill(10)


def accession_index_url(cik: str | int, accession: str) -> str:
    """The sec.gov Archives index page of one accession (edgartools'
    `Filing.homepage_url`; the shorter /data/<cik>/<acc>-index.html form
    answers 403)."""
    return f"{SEC_ARCHIVES}/{int(cik10(cik))}/{accession_digits(accession)}/{accession}-index.html"


def primary_document_url(cik: str | int, accession: str, primary_document: str) -> str:
    """The sec.gov Archives URL of a filing's primary document."""
    return f"{SEC_ARCHIVES}/{int(cik10(cik))}/{accession_digits(accession)}/{primary_document}"


def _iso(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    s = str(v).strip()
    try:
        return _dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return s


# ── the provider seam ─────────────────────────────────────────────────────

class FilingsProvider(Protocol):
    async def company(self, identifier: str) -> dict: ...
    async def filings(self, cik: str, forms: list[str], years: list[int] | None = None,
                      limit: int = 20) -> list[dict]: ...
    async def filing_text(self, accession: str) -> dict[str, str]: ...
    async def xbrl_facts(self, cik: str, concepts: list[str] | None = None,
                         years: list[int] | None = None) -> list[dict]: ...


class EdgarProvider:
    """Thin, lazy wrapper over edgartools. Construct once per process.

    `sec_wait` (optional) is awaited before every call this object makes
    — pass it HERE when the provider is used directly, or to
    `filings_evidence(..., sec_wait=)` when going through that function;
    the tools layer passes it in exactly one of the two places.
    """

    def __init__(self, *, sec_wait: SecWait | None = None, identity: str | None = None,
                 data_dir: str | Path | None = None, local_storage: bool = True) -> None:
        self.sec_wait = sec_wait
        s = settings()
        self._identity = identity or s.sec_user_agent
        self._data_dir = Path(data_dir) if data_dir is not None else s.edgar_data_dir
        self._want_local = local_storage
        self.local_storage = False
        self._mod: Any = None

    # -- lazy import: nothing SEC-shaped happens at module import --------
    def _edgar(self):
        if self._mod is None:
            import edgar  # type: ignore  # noqa: WPS433 (deliberately lazy)
            edgar.set_identity(self._identity)
            use_local = getattr(edgar, "use_local_storage", None)
            if self._want_local and callable(use_local):
                try:
                    self._data_dir.mkdir(parents=True, exist_ok=True)
                    use_local(str(self._data_dir))
                    self.local_storage = True
                except Exception:  # noqa: BLE001 — fall back to edgartools' default cache
                    self.local_storage = False
            self._mod = edgar
        return self._mod

    async def _call(self, fn, *args):
        if self.sec_wait is not None:
            await self.sec_wait()
        return await asyncio.to_thread(fn, *args)

    # -- public API (async; every call behind the SEC bucket) ------------
    async def company(self, identifier: str) -> dict:
        return await self._call(self._company_sync, identifier)

    async def filings(self, cik: str, forms: list[str], years: list[int] | None = None,
                      limit: int = 20) -> list[dict]:
        return await self._call(self._filings_sync, cik, list(forms), years, limit)

    async def filing_text(self, accession: str) -> dict[str, str]:
        return await self._call(self._filing_text_sync, accession)

    async def xbrl_facts(self, cik: str, concepts: list[str] | None = None,
                         years: list[int] | None = None) -> list[dict]:
        return await self._call(self._xbrl_facts_sync, cik, concepts, years)

    # -- sync bodies (worker thread) ---------------------------------------
    def _company_sync(self, identifier: str) -> dict:
        edgar = self._edgar()
        c = edgar.Company(identifier)
        if getattr(c, "not_found", False):
            raise LookupError(f"EDGAR: no company for {identifier!r}")
        data = getattr(c, "data", None)
        return {
            "cik": cik10(c.cik),
            "name": getattr(c, "name", "") or "",
            "tickers": list(getattr(c, "tickers", None) or []),
            "sic": getattr(c, "sic", None),
            "state": getattr(data, "state_of_incorporation", None),
            "fiscal_year_end": getattr(c, "fiscal_year_end", None),
        }

    def _filings_sync(self, cik: str, forms: list[str], years: list[int] | None,
                      limit: int) -> list[dict]:
        edgar = self._edgar()
        c = edgar.Company(cik)
        kw: dict = {"form": forms or None}
        if years:
            kw["year"] = list(years)
        rows: list[dict] = []
        for f in c.get_filings(**kw):
            acc = getattr(f, "accession_number", None) or getattr(f, "accession_no", "")
            primary = getattr(f, "primary_document", "") or ""
            rows.append({
                "accession": acc,
                "form": getattr(f, "form", ""),
                "filing_date": _iso(getattr(f, "filing_date", None)),
                "period": _iso(getattr(f, "report_date", None)),
                "url": primary_document_url(c.cik, acc, primary) if primary
                else accession_index_url(c.cik, acc),
                "description": getattr(f, "primary_doc_description", "") or "",
            })
        rows.sort(key=lambda r: (r["filing_date"] or "", r["accession"]), reverse=True)
        return rows[: max(0, int(limit))] if limit else rows

    def _filing_text_sync(self, accession: str) -> dict[str, str]:
        edgar = self._edgar()
        filing = edgar.get_by_accession_number(accession)
        if filing is None:
            raise LookupError(f"EDGAR: no filing {accession!r}")
        form = str(getattr(filing, "form", "") or "")
        if form.startswith("10-K"):
            try:
                report = filing.obj()
            except Exception:  # noqa: BLE001 — unparsable → whole text below
                report = None
            getter = getattr(report, "get", None)
            if callable(getter):
                out: dict[str, str] = {}
                for item, title in TENK_ITEMS:
                    try:
                        text = getter(item)
                    except Exception:  # noqa: BLE001
                        text = None
                    if text and str(text).strip():
                        out[f"{item} — {title}"] = str(text)
                if out:
                    return out
        return {"full": str(filing.text() or "")}

    def _xbrl_facts_sync(self, cik: str, concepts: list[str] | None,
                         years: list[int] | None) -> list[dict]:
        edgar = self._edgar()
        c = edgar.Company(cik)
        facts = c.get_facts()
        if facts is None:
            return []
        if concepts:
            raw = []
            seen: set = set()
            for concept in concepts:
                for f in facts.query().by_concept(concept).execute():
                    key = (f.concept, str(f.value), _iso(f.period_end), f.accession)
                    if key not in seen:
                        seen.add(key)
                        raw.append(f)
        else:
            raw = list(facts.get_all_facts())
        rows = []
        for f in raw:
            fy = getattr(f, "fiscal_year", None)
            if years and fy not in set(years):
                continue
            rows.append({
                "concept": getattr(f, "concept", ""),
                "label": getattr(f, "label", "") or getattr(f, "concept", ""),
                "value": getattr(f, "value", None),
                "unit": getattr(f, "unit", "") or "",
                "period_start": _iso(getattr(f, "period_start", None)),
                "period_end": _iso(getattr(f, "period_end", None)),
                "fy": fy,
                "fp": getattr(f, "fiscal_period", "") or "",
                "form": getattr(f, "form_type", "") or "",
                "accession": getattr(f, "accession", "") or "",
                "filed": _iso(getattr(f, "filing_date", None)),
            })
        rows.sort(key=lambda r: (r["period_end"] or "", r["concept"], r["accession"]))
        return rows


class FakeProvider:
    """Canned provider for tests (no network). Subclass freely.

    `companies`: identifier → company dict (every alias of one company may
    point at the same dict); `filings`: cik → list of filing dicts (the
    same shape `EdgarProvider.filings` returns); `texts`: accession →
    {section → text}; `facts`: cik → list of fact dicts.
    """

    def __init__(self, *, companies: dict | None = None, filings: dict | None = None,
                 texts: dict | None = None, facts: dict | None = None,
                 sec_wait: SecWait | None = None) -> None:
        self.companies = companies or {}
        self._filings = filings or {}
        self.texts = texts or {}
        self._facts = facts or {}
        self.sec_wait = sec_wait
        self.calls: list[tuple] = []

    async def _guard(self, *call):
        self.calls.append(call)
        if self.sec_wait is not None:
            await self.sec_wait()

    async def company(self, identifier: str) -> dict:
        await self._guard("company", identifier)
        key = str(identifier).strip()
        for k, v in self.companies.items():
            same_name = k.lower() == key.lower()
            same_cik = k.isdigit() and key.isdigit() and cik10(k) == cik10(key)
            if same_name or same_cik:
                return dict(v)
        raise LookupError(f"fake EDGAR: no company for {identifier!r}")

    async def filings(self, cik: str, forms: list[str], years: list[int] | None = None,
                      limit: int = 20) -> list[dict]:
        await self._guard("filings", cik, tuple(forms), tuple(years or ()), limit)
        rows = [dict(r) for r in self._filings.get(cik10(cik), [])
                if (not forms or r["form"] in forms)
                and (not years or int(str(r["filing_date"])[:4]) in set(years))]
        rows.sort(key=lambda r: (r["filing_date"] or "", r["accession"]), reverse=True)
        return rows[: max(0, int(limit))] if limit else rows

    async def filing_text(self, accession: str) -> dict[str, str]:
        await self._guard("filing_text", accession)
        if accession not in self.texts:
            raise LookupError(f"fake EDGAR: no filing {accession!r}")
        return dict(self.texts[accession])

    async def xbrl_facts(self, cik: str, concepts: list[str] | None = None,
                         years: list[int] | None = None) -> list[dict]:
        await self._guard("xbrl_facts", cik, tuple(concepts or ()), tuple(years or ()))
        rows = []
        for f in self._facts.get(cik10(cik), []):
            if concepts and not any(c.lower() in str(f["concept"]).lower() for c in concepts):
                continue
            if years and f.get("fy") not in set(years):
                continue
            rows.append(dict(f))
        rows.sort(key=lambda r: (r.get("period_end") or "", r["concept"], r.get("accession", "")))
        return rows


# ── documents ─────────────────────────────────────────────────────────────

def _fmt_value(value) -> str:
    """Exact, human-readable rendering: integers with thousands separators,
    decimals as stated, strings verbatim."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,}"
    s = str(value).strip()
    if re.fullmatch(r"-?\d+", s):
        return f"{int(s):,}"
    if re.fullmatch(r"-?\d+\.\d+", s):
        f = float(s)
        return f"{int(f):,}" if f.is_integer() else f"{f:,}"
    return s


def _unit_word(unit: str) -> str:
    u = (unit or "").strip()
    if not u or u.lower() == "pure":
        return ""
    if "/" in u:  # USD/shares → "USD per share"
        num, den = u.split("/", 1)
        den = den.rstrip("s")
        return f"{num} per {den}"
    return u


def fact_sentence(fact: dict) -> str:
    """One complete sentence per XBRL fact, so a verbatim excerpt exists."""
    label = (fact.get("label") or fact.get("concept") or "").strip()
    label = re.sub(r"^[a-z\-]+:", "", label) if ":" in label and " " not in label else label
    value = _fmt_value(fact.get("value"))
    unit = _unit_word(fact.get("unit") or "")
    period_end = fact.get("period_end") or "an unstated date"
    form = fact.get("form") or "unknown form"
    filed = fact.get("filed") or "an unstated date"
    amount = f"{value} {unit}".strip()
    return (f"{label} was {amount} for the period ending {period_end} "
            f"(Form {form}, filed {filed}).")


def _topic_match(name: str, text: str, topics: list[str]) -> bool:
    if not topics:
        return True
    hay = (name + "\n" + text).lower()
    return any(t.strip().lower() in hay for t in topics if t and t.strip())


def _document(*, url: str, text: str, title: str, published: str | None,
              published_basis: str, retrieved: str, via: str, filing: dict) -> dict:
    return {
        "url": url,
        "final_url": url,
        "text": text,
        "verify_text": text,
        "content_hash": sha256_text(text),
        "title": title,
        "published": published,
        "published_basis": published_basis,
        "content_type": "text/html",
        "url_status": "live",
        "original_url": None,
        "archive_timestamp": None,
        "retrieved": retrieved,
        "hits": [],
        "via": via,
        #: extra, not a `types.Document` field — the card layer pops it.
        "filing": filing,
    }


async def filings_evidence(provider: FilingsProvider, *, cik_or_ticker: str,
                           forms: list[str], years: list[int] | None,
                           topics: list[str], sec_wait: SecWait | None = None,
                           limit: int = 20, concepts: list[str] | None = None,
                           today: _dt.date | None = None) -> dict:
    """Filings + XBRL facts for one issuer as Document-like dicts.

    Returns {documents: [...], facts: [...], searched: {forms, years,
    filings_considered, filings_documented, topics}}. `sec_wait` (when
    given) is awaited before EVERY provider call. `topics` keeps only the
    sections (name or body, case-insensitive) that mention one; a filing
    that exposes no sections keeps its full text. `concepts` narrows the
    XBRL facts (None = every fact in `years`)."""
    retrieved = (today or _dt.date.today()).isoformat()
    forms = [f for f in (forms or []) if f]
    years_l = [int(y) for y in (years or [])] or None

    async def call(method, *args, **kwargs):
        if sec_wait is not None:
            await sec_wait()
        return await method(*args, **kwargs)

    company = await call(provider.company, cik_or_ticker)
    cik = cik10(company["cik"])
    name = company.get("name") or cik_or_ticker
    filings = await call(provider.filings, cik, forms, years_l, limit)

    documents: list[dict] = []
    documented = 0
    url_by_accession: dict[str, str] = {}
    for f in filings:
        url_by_accession[f["accession"]] = f["url"]
        sections = await call(provider.filing_text, f["accession"])
        if not sections:
            continue
        exposes_sections = list(sections.keys()) != ["full"]
        kept: list[tuple[str, str]] = []
        for sec_name, sec_text in sections.items():
            if not sec_text or not str(sec_text).strip():
                continue
            if exposes_sections and not _topic_match(sec_name, str(sec_text), topics):
                continue
            kept.append((sec_name, str(sec_text).strip()))
        if not kept:
            continue
        if exposes_sections:
            text = "\n\n".join(f"{n}\n\n{t}" for n, t in kept)
        else:
            text = kept[0][1]
        period = f.get("period") or f.get("filing_date") or ""
        documents.append(_document(
            url=f["url"], text=text,
            title=f"{name} Form {f['form']} {period}".strip(),
            published=f.get("filing_date"), published_basis="filing date (EDGAR)",
            retrieved=retrieved, via="edgar",
            filing={"accession": f["accession"], "form": f["form"], "period": f.get("period"),
                    "filing_date": f.get("filing_date"), "sections": [n for n, _ in kept],
                    "description": f.get("description", "")}))
        documented += 1

    facts_rows = await call(provider.xbrl_facts, cik, concepts, years_l)
    facts: list[dict] = []
    for fact in facts_rows:
        acc = fact.get("accession") or ""
        url = url_by_accession.get(acc) or (accession_index_url(cik, acc) if acc else "")
        row = dict(fact)
        row["url"] = url
        row["sentence"] = fact_sentence(fact)
        facts.append(row)
        documents.append(_document(
            url=url, text=row["sentence"],
            title=f"{name} XBRL fact {fact.get('concept', '')} {fact.get('period_end') or ''}".strip(),
            published=fact.get("filed"), published_basis="filing date (EDGAR XBRL)",
            retrieved=retrieved, via="edgar-xbrl",
            filing={"accession": acc, "form": fact.get("form"), "period": fact.get("period_end"),
                    "filing_date": fact.get("filed"), "sections": ["xbrl"],
                    "concept": fact.get("concept"), "unit": fact.get("unit"),
                    "value": fact.get("value")}))

    return {
        "documents": documents,
        "facts": facts,
        "searched": {
            "forms": forms,
            "years": years_l or [],
            "topics": list(topics or []),
            "filings_considered": len(filings),
            "filings_documented": documented,
            "company": {"cik": cik, "name": name},
        },
    }
