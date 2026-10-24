"""SEC filings as evidence documents (brief §1 Filings, §6 rate limits) — offline.

`FakeProvider` serves an invented issuer, "Example Bancorp Inc", CIK
0000000001. edgartools is never called: a socket guard turns any real
connection attempt into a test failure.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import socket

import pytest

from evidence_engine import filings
from evidence_engine.filings import EdgarProvider, FakeProvider, filings_evidence
from evidence_engine.textnorm import sha256_text
from evidence_engine.types import Document

CIK = "0000000001"
ACC_10K = "0000000001-26-000010"
ACC_10Q = "0000000001-25-000020"
ACC_8K = "0000000001-24-000005"
ACC_OLD_10K = "0000000001-24-000011"

ARCH = "https://www.sec.gov/Archives/edgar/data/1"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted in an offline test")
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


def provider(**kw) -> FakeProvider:
    return FakeProvider(
        companies={
            CIK: {"cik": CIK, "name": "Example Bancorp Inc", "tickers": ["EXBC"], "sic": "6022",
                  "state": "ST", "fiscal_year_end": "1231"},
            "EXBC": {"cik": CIK, "name": "Example Bancorp Inc", "tickers": ["EXBC"], "sic": "6022",
                     "state": "ST", "fiscal_year_end": "1231"},
        },
        filings={CIK: [
            {"accession": ACC_10K, "form": "10-K", "filing_date": "2026-02-27", "period": "2025-12-31",
             "url": f"{ARCH}/000000000126000010/exbc-20251231.htm", "description": "10-K"},
            {"accession": ACC_10Q, "form": "10-Q", "filing_date": "2025-11-05", "period": "2025-09-30",
             "url": f"{ARCH}/000000000125000020/exbc-20250930.htm", "description": "10-Q"},
            {"accession": ACC_8K, "form": "8-K", "filing_date": "2024-07-15", "period": "2024-07-15",
             "url": f"{ARCH}/000000000124000005/exbc-8k.htm", "description": "8-K"},
            {"accession": ACC_OLD_10K, "form": "10-K", "filing_date": "2024-02-28", "period": "2023-12-31",
             "url": f"{ARCH}/000000000124000011/exbc-20231231.htm", "description": "10-K"},
        ]},
        texts={
            ACC_10K: {
                "Item 1 — Business": "Example Bancorp Inc is the holding company for Example Bank. "
                                     "The bank operates 42 branches and a digital banking platform.",
                "Item 1A — Risk Factors": "Cybersecurity incidents could disrupt our operations. "
                                          "We rely on third-party cloud providers for core processing.",
                "Item 7 — Management's Discussion and Analysis": "Net interest income rose 6.1 percent to "
                                                                 "$412 million in 2025.",
                "Item 9A — Controls and Procedures": "Management concluded that internal control over "
                                                     "financial reporting was effective.",
            },
            ACC_10Q: {"full": "Quarterly report. Deposits grew 2.3 percent during the quarter; the digital "
                              "banking platform migration was completed in September 2025."},
            ACC_8K: {"full": "Item 7.01 Regulation FD Disclosure. The company announced a new chief "
                             "technology officer."},
            ACC_OLD_10K: {
                "Item 1 — Business": "Example Bancorp Inc operated 40 branches in 2023.",
                "Item 1A — Risk Factors": "Interest rate risk may reduce net interest margin.",
            },
        },
        facts={CIK: [
            {"concept": "us-gaap:Assets", "label": "Assets", "value": 6110000000, "unit": "USD",
             "period_start": None, "period_end": "2025-12-31", "fy": 2025, "fp": "FY", "form": "10-K",
             "accession": ACC_10K, "filed": "2026-02-27"},
            {"concept": "us-gaap:Deposits", "label": "Deposits", "value": 5020500000.0, "unit": "USD",
             "period_start": None, "period_end": "2025-09-30", "fy": 2025, "fp": "Q3", "form": "10-Q",
             "accession": ACC_10Q, "filed": "2025-11-05"},
            {"concept": "us-gaap:Assets", "label": "Assets", "value": 5800000000, "unit": "USD",
             "period_start": None, "period_end": "2023-12-31", "fy": 2023, "fp": "FY", "form": "10-K",
             "accession": ACC_OLD_10K, "filed": "2024-02-28"},
            {"concept": "dei:EntityCommonStockSharesOutstanding", "label": "Entity Common Stock, Shares Outstanding",
             "value": 31250000, "unit": "shares", "period_start": None, "period_end": "2026-02-15",
             "fy": 2025, "fp": "FY", "form": "10-K", "accession": "0000000001-26-000099", "filed": "2026-02-27"},
        ]},
        **kw,
    )


def run(**kw):
    kw.setdefault("cik_or_ticker", CIK)
    kw.setdefault("forms", ["10-K", "10-Q"])
    kw.setdefault("years", None)
    kw.setdefault("topics", [])
    kw.setdefault("today", dt.date(2026, 10, 10))
    p = kw.pop("provider", None) or provider()
    return asyncio.run(filings_evidence(p, **kw)), p


def filing_docs(out):
    return [d for d in out["documents"] if d["via"] == "edgar"]


def fact_docs(out):
    return [d for d in out["documents"] if d["via"] == "edgar-xbrl"]


def test_form_filter():
    out, _ = run(forms=["10-K"])
    assert {d["filing"]["form"] for d in filing_docs(out)} == {"10-K"}
    assert out["searched"]["filings_considered"] == 2
    assert out["searched"]["forms"] == ["10-K"]


def test_year_filter_on_filing_date_and_facts():
    out, _ = run(forms=["10-K", "10-Q", "8-K"], years=[2024])
    accs = {d["filing"]["accession"] for d in filing_docs(out)}
    assert accs == {ACC_8K, ACC_OLD_10K}
    assert {f["fy"] for f in out["facts"]} == set()  # no fiscal year 2024 facts
    out2, _ = run(forms=["10-K"], years=[2026])
    assert {d["filing"]["accession"] for d in filing_docs(out2)} == {ACC_10K}
    assert out2["searched"]["years"] == [2026]


def test_ticker_resolves_to_company():
    out, p = run(cik_or_ticker="EXBC", forms=["10-K"])
    assert out["searched"]["company"] == {"cik": CIK, "name": "Example Bancorp Inc"}
    assert p.calls[0] == ("company", "EXBC")


def test_section_topic_filter_keeps_matching_sections_only():
    out, _ = run(forms=["10-K"], years=[2026], topics=["cybersecurity", "cloud"])
    d = filing_docs(out)[0]
    assert d["filing"]["sections"] == ["Item 1A — Risk Factors"]
    assert d["text"].startswith("Item 1A — Risk Factors\n\n")
    assert "Net interest income" not in d["text"]
    # a topic naming the section heading also matches
    out2, _ = run(forms=["10-K"], years=[2026], topics=["controls and procedures"])
    assert filing_docs(out2)[0]["filing"]["sections"] == ["Item 9A — Controls and Procedures"]


def test_topic_filter_is_case_insensitive_and_full_text_is_kept_unfiltered():
    out, _ = run(forms=["10-Q"], topics=["NOTHING-MATCHES-THIS"])
    docs = filing_docs(out)
    assert len(docs) == 1 and docs[0]["filing"]["sections"] == ["full"]
    assert docs[0]["text"].startswith("Quarterly report.")
    out2, _ = run(forms=["10-K"], years=[2026], topics=["NOTHING-MATCHES-THIS"])
    assert filing_docs(out2) == []
    assert out2["searched"]["filings_considered"] == 1
    assert out2["searched"]["filings_documented"] == 0


def test_no_topics_keeps_every_section_joined_under_headings():
    out, _ = run(forms=["10-K"], years=[2026])
    d = filing_docs(out)[0]
    assert len(d["filing"]["sections"]) == 4
    assert "\n\nItem 7 — Management's Discussion and Analysis\n\n" in d["text"]


def test_document_dict_fields():
    out, _ = run(forms=["10-K"], years=[2026])
    d = filing_docs(out)[0]
    assert d["url"] == f"{ARCH}/000000000126000010/exbc-20251231.htm"
    assert d["final_url"] == d["url"]
    assert d["verify_text"] == d["text"]
    assert d["content_hash"] == sha256_text(d["text"])
    assert d["title"] == "Example Bancorp Inc Form 10-K 2025-12-31"
    assert d["published"] == "2026-02-27"
    assert d["published_basis"] == "filing date (EDGAR)"
    assert d["content_type"] == "text/html"
    assert d["url_status"] == "live"
    assert d["retrieved"] == "2026-10-10"
    assert d["via"] == "edgar"
    assert d["original_url"] is None and d["archive_timestamp"] is None and d["hits"] == []
    # everything but the `filing` extra builds a types.Document
    doc = Document(**{k: v for k, v in d.items() if k != "filing"})
    assert doc.url == d["url"]


def test_documents_are_whole_not_excerpted():
    out, _ = run(forms=["10-K"], years=[2026])
    d = filing_docs(out)[0]
    assert "42 branches and a digital banking platform." in d["text"]
    assert len(d["text"]) > 500


def test_xbrl_fact_sentence_shape_and_verbatim():
    out, _ = run(forms=["10-K", "10-Q"])
    facts = {f["concept"]: f for f in out["facts"]}
    assets = facts["us-gaap:Assets"]
    assert assets["sentence"] == ("Assets was 6,110,000,000 USD for the period ending 2025-12-31 "
                                  "(Form 10-K, filed 2026-02-27).")
    assert assets["value"] == 6110000000
    assert assets["url"] == f"{ARCH}/000000000126000010/exbc-20251231.htm"
    deposits = facts["us-gaap:Deposits"]
    assert deposits["sentence"].startswith("Deposits was 5,020,500,000 USD for the period ending 2025-09-30")
    docs = {d["filing"]["concept"]: d for d in fact_docs(out)}
    for concept, d in docs.items():
        assert d["text"] == facts[concept]["sentence"]
        assert d["text"] == d["verify_text"]
        assert d["content_hash"] == sha256_text(d["text"])
        assert d["via"] == "edgar-xbrl"
        assert d["published"] == facts[concept]["filed"]
        assert d["published_basis"] == "filing date (EDGAR XBRL)"
        assert d["url"] == facts[concept]["url"]
        assert 50 <= len(d["text"]) <= 500


def test_xbrl_fact_url_falls_back_to_accession_index():
    out, _ = run(forms=["10-K"], years=[2025])
    shares = next(f for f in out["facts"] if f["concept"].startswith("dei:"))
    assert shares["url"] == f"{ARCH}/000000000126000099/0000000001-26-000099-index.html"
    assert shares["sentence"] == ("Entity Common Stock, Shares Outstanding was 31,250,000 shares for the "
                                  "period ending 2026-02-15 (Form 10-K, filed 2026-02-27).")


def test_concepts_narrow_facts():
    out, _ = run(forms=["10-K"], concepts=["Deposits"])
    assert [f["concept"] for f in out["facts"]] == ["us-gaap:Deposits"]


def test_sec_wait_called_once_per_provider_call():
    waits: list[int] = []

    async def sec_wait() -> None:
        waits.append(1)

    out, p = run(forms=["10-K", "10-Q"], sec_wait=sec_wait)
    # company + filings + one filing_text per filing (3) + xbrl_facts
    assert len(p.calls) == 2 + 3 + 1
    assert len(waits) == len(p.calls)


def test_provider_own_sec_wait_also_honoured():
    waits: list[int] = []

    async def sec_wait() -> None:
        waits.append(1)

    p = provider(sec_wait=sec_wait)
    asyncio.run(p.company(CIK))
    asyncio.run(p.filings(CIK, ["10-K"]))
    assert len(waits) == 2


def test_fact_sentence_formatting():
    s = filings.fact_sentence({"label": "Earnings Per Share, Diluted", "value": "3.42", "unit": "USD/shares",
                               "period_end": "2025-12-31", "form": "10-K", "filed": "2026-02-27"})
    assert s == ("Earnings Per Share, Diluted was 3.42 USD per share for the period ending 2025-12-31 "
                 "(Form 10-K, filed 2026-02-27).")
    s2 = filings.fact_sentence({"concept": "us-gaap:Ratio", "value": 0.108, "unit": "pure",
                                "period_end": "2025-12-31", "form": "10-K", "filed": "2026-02-27"})
    assert s2.startswith("Ratio was 0.108 for the period ending")


def test_url_helpers():
    assert filings.cik10("1") == CIK
    assert filings.cik10("CIK0000000001") == CIK
    assert filings.accession_index_url(CIK, ACC_10K) == f"{ARCH}/000000000126000010/{ACC_10K}-index.html"
    assert filings.primary_document_url(1, ACC_10K, "a.htm") == f"{ARCH}/000000000126000010/a.htm"


def test_unknown_company_raises():
    with pytest.raises(LookupError):
        run(cik_or_ticker="NOPE")


def test_edgar_provider_is_lazy_and_offline_at_construction():
    """Constructing the real provider imports nothing and touches no socket;
    its sync bodies are only ever called from the awaited public methods."""
    p = EdgarProvider(sec_wait=None, identity="Example Co test@example.test")
    assert p._mod is None and p.local_storage is False
    assert asyncio.iscoroutinefunction(p.company)
    assert asyncio.iscoroutinefunction(p.filings)
    assert asyncio.iscoroutinefunction(p.filing_text)
    assert asyncio.iscoroutinefunction(p.xbrl_facts)


def test_edgar_provider_awaits_sec_wait_and_runs_body_in_thread(monkeypatch):
    """The real provider's guard, proven with its sync body replaced."""
    waits: list[int] = []

    async def sec_wait() -> None:
        waits.append(1)

    p = EdgarProvider(sec_wait=sec_wait)
    monkeypatch.setattr(p, "_company_sync", lambda ident: {"cik": CIK, "name": "Example Bancorp Inc",
                                                           "tickers": [], "sic": None, "state": None,
                                                           "fiscal_year_end": None})
    monkeypatch.setattr(p, "_filings_sync", lambda cik, forms, years, limit: [])
    assert asyncio.run(p.company("EXBC"))["cik"] == CIK
    assert asyncio.run(p.filings(CIK, ["10-K"])) == []
    assert len(waits) == 2
    assert p._mod is None, "nothing imported edgartools"
