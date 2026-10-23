"""find_registrant: the registry that holds the institution, every
sub-vertical, US and Canada (owner, 2026-10-12). Mocked registries with the
response shapes measured live the same day."""
from __future__ import annotations

import asyncio
import json

import httpx

from evidence_engine import registrants as REG
from evidence_engine.types import EntityRef

OSFI_CSV = ('"Company Name","FI Type Name","FI Group Name","FI Industry Name","Canadian Trade Company Name",'
            '"Representative Name","Title","Address Line 1","Address Line 2","City","Province State",'
            '"Postal ZIP Code","Authorized Insurance Classes"\n'
            '"Example Life Assurance Company","Federally Regulated Financial Institutions","Life Insurance Companies",'
            '"Canadian Life Insurance Companies","","A B","CEO","1 Main","","TORONTO","Ontario","M5J 0A8","Life"\n')
FCA_HTML = ("<table><tr><td>720345</td><td>Example Valley Farm Credit, ACA</td><td>A CEO</td></tr>"
            "<tr><td>720143</td><td>Colonial Farm Credit, ACA</td><td>B CEO</td></tr></table>")


def transport(calls: list):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        host, path = req.url.host, req.url.path
        if host == "efts.sec.gov":
            if "," in req.url.params.get("keysTyped", ""):
                return httpx.Response(500)            # measured: EDGAR 500s on a comma
            return httpx.Response(200, json={"hits": {"hits": [
                {"_id": "0001673769", "_source": {"entity": "Example Holdings Group, Inc."}},
                {"_id": "0001658088", "_source": {"entity": "Example Capital Fund 1, LP"}}]}})
        if host == "api.fdic.gov":
            return httpx.Response(200, json={"data": [{"data": {
                "NAME": "Example Bank", "CERT": 30788, "CITY": "Kalispell", "STALP": "MT", "ACTIVE": 1,
                "REGAGNT": "FDIC", "FED_RSSD": "2634191", "ASSET": 31577225}}]})
        if host == "mapping.ncua.gov" and path.endswith("GetSearchLocations"):
            body = json.loads(req.content)
            assert body["searchText"] == "example technology"     # the kind tail is dropped
            return httpx.Response(200, json={"list": [
                {"creditUnionNumber": 23521, "creditUnionName": "EXAMPLE TECHNOLOGY", "city": "Branchville",
                 "state": "MA", "isMainOffice": False}]})
        if host == "mapping.ncua.gov":
            return httpx.Response(200, json={"creditUnionStatus": "Active", "creditUnionType": "FCU",
                                             "creditUnionCity": "San Jose", "creditUnionState": "CA",
                                             "assetsFormatted": "$27,875,912,054", "membersFormatted": "1,870,858"})
        if host in ("api.adviserinfo.sec.gov", "api.brokercheck.finra.org"):
            return httpx.Response(200, json={"hits": {"hits": [{"_source": {
                "firm_source_id": "104510", "firm_name": "EXAMPLE WEALTH PARTNERS", "firm_ia_scope": "ACTIVE",
                "firm_ia_full_sec_number": "801-55196",
                "firm_ia_address_details": json.dumps({"officeAddress": {"city": "SANTA CLARA", "state": "CA"}})}}]}})
        if host == "apps.fca.gov":
            return httpx.Response(200, text=FCA_HTML)
        if host == "open.canada.ca":
            return httpx.Response(200, text=OSFI_CSV)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def lookup(entity, **kw):
    calls = []
    REG.Registrants._lists = {}

    async def go():
        async with httpx.AsyncClient(transport=transport(calls)) as http:
            return await REG.Registrants(http, user_agent="test").lookup(entity, **kw)
    return asyncio.run(go()), calls


def test_every_sub_vertical_routes_to_the_registry_that_holds_it():
    assert REG.plan("CU", "US") == ["ncua", "sec_edgar"]
    assert REG.plan("credit union", "CA") == ["osfi", "ca_provincial_regulators"]
    assert REG.plan("RB", "US")[0] == "fdic"
    assert REG.plan("wealth management", "US")[:2] == ["sec_iapd", "finra_brokercheck"]
    assert REG.plan("insurance brokerage", "US")[0] == "us_insurance_regulators"
    assert REG.plan("FC", "US") == ["fca_us", "sec_edgar"]
    both = REG.plan("IC", None)
    assert "us_insurance_regulators" in both and "osfi" in both
    for code in REG.SUB_VERTICALS:
        assert code in REG.ROUTES["US"] and code in REG.ROUTES["CA"]


def test_sector_words_alone_never_make_a_match():
    assert REG.name_score("Horizon Farm Credit, ACA", "Colonial Farm Credit, ACA") == 0.0
    assert REG.name_score("Horizon Farm Credit, ACA", "Horizon Farm Credit, ACA") == 1.0
    assert REG.name_score("Navy Federal Credit Union", "Navy Capital Fund 1, LP") < 1.0
    assert REG.name_score("Edelman Financial Engines", "Edelman Financial Engines, L.P.") == 1.0
    assert REG.registry_query("Example Technology Federal Credit Union") == "example technology"
    assert REG.registry_query("Example Holdings Group, Inc.") == "example"


def test_a_credit_union_is_found_at_ncua_with_its_stated_fields():
    out, calls = lookup(EntityRef(legal_name="Example Technology Federal Credit Union"),
                        sub_vertical="CU", country="US")
    m = out["matches"][0]
    assert m["registry"] == "ncua" and m["identifier"] == "23521" and m["match_score"] == 1.0
    assert (m["city"], m["region"]) == ("San Jose", "CA")             # the HQ, not the branch
    assert m["registry_fields"]["members"] == "1,870,858"
    assert m["record_url"].endswith("/23521")
    assert {r["registry"]: r["status"] for r in out["registries"]}["ncua"] == "ok"


def test_a_private_firm_is_found_in_edgar_without_a_comma_500():
    out, calls = lookup(EntityRef(legal_name="Example Holdings Group, Inc."), sub_vertical="IB", country="US")
    edgar = [m for m in out["matches"] if m["registry"] == "sec_edgar"]
    assert edgar and edgar[0]["identifier"] == "1673769" and edgar[0]["match_score"] == 1.0
    assert all("%2C" not in c for c in calls if "efts" in c)
    # the insurance regulators have no API: without a search backend they say so
    status = {r["registry"]: r for r in out["registries"]}
    assert status["us_insurance_regulators"]["status"] == "not_run"


def test_regulators_without_an_api_come_back_as_candidates_not_records():
    async def search(queries):
        assert all(q["text"].startswith("site:") for q in queries)
        return [{"url": "https://www.fsrao.ca/licensee/123", "title": "Example Life Assurance Company — licence",
                 "snippet": "Example Life Assurance Company is licensed"},
                {"url": "https://www.fsrao.ca/news/other", "title": "Unrelated notice", "snippet": "nothing"},
                {"url": "https://blog.example.test/x", "title": "Example Life Assurance Company", "snippet": ""}]
    calls = []
    REG.Registrants._lists = {}

    async def go():
        async with httpx.AsyncClient(transport=transport(calls)) as http:
            return await REG.Registrants(http, user_agent="t").lookup(
                EntityRef(legal_name="Example Life Assurance Company"), sub_vertical="IC", country="CA",
                search=search)
    out = asyncio.run(go())
    assert out["matches"][0]["registry"] == "osfi" and out["matches"][0]["country"] == "CA"
    cands = out["candidates"]
    assert [c["url"] for c in cands] == ["https://www.fsrao.ca/licensee/123"]   # on the regulator's host, naming it
    assert cands[0]["method"] == "search"


def test_a_registry_error_is_reported_never_silent():
    def boom(req):
        return httpx.Response(503)
    REG.Registrants._lists = {}

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
            return await REG.Registrants(http, user_agent="t").lookup(
                EntityRef(legal_name="Example Bank"), sub_vertical="RB", country="US")
    out = asyncio.run(go())
    st = {r["registry"]: r["status"] for r in out["registries"]}
    assert st == {"fdic": "error", "sec_edgar": "error"} and out["matches"] == []


def test_farm_credit_uses_the_fca_directory():
    out, _ = lookup(EntityRef(legal_name="Example Valley Farm Credit, ACA"), sub_vertical="FC", country="US")
    fca = [m for m in out["matches"] if m["registry"] == "fca_us"]
    assert [m["identifier"] for m in fca] == ["720345"]                      # Colonial is not a match


def test_a_candidate_must_name_the_institution_not_share_its_words():
    """Measured 2026-10-12 on the live engine: for an insurance brokerage
    named by an acronym, NAIC papers on agreements sharing that acronym and
    the firm's own SEC Form D came back as insurance-regulator candidates."""
    assert REG.names_in("Example Financial Group, Inc.", "Form D — Example Financial Group, Inc. Kansas")
    assert not REG.names_in("Example Financial Group, Inc.", "an Example of the Financial Analysis Handbook")

    async def search(queries):
        return [{"url": "https://content.naic.org/x.pdf", "title": "Investment Management Update",
                 "snippet": "an Example agreement reviewed in the Financial Analysis Handbook"},
                {"url": "https://www.sec.gov/Archives/edgar/data/1/primary_doc.xml", "title": "SEC FORM D",
                 "snippet": "Example Financial Group, Inc. Jurisdiction of Incorporation"},
                {"url": "https://insurance.example.gov/licensee/9", "title": "Licensee search",
                 "snippet": "Example Financial Group, Inc. — resident producer agency, active"}]
    REG.Registrants._lists = {}

    async def go():
        async with httpx.AsyncClient(transport=transport([])) as http:
            return await REG.Registrants(http, user_agent="t").lookup(
                EntityRef(legal_name="Example Financial Group, Inc."), sub_vertical="IB", country="US",
                search=search)
    out = asyncio.run(go())
    assert [c["url"] for c in out["candidates"]] == ["https://insurance.example.gov/licensee/9"]


def test_a_one_shared_word_namesake_is_not_reported():
    """Measured 2026-10-12: a credit union lookup listed two EDGAR filers that
    share one word with it ("<Person> Navy E.", "Something Navy LLC") at 0.5."""
    assert REG.name_score("Example Federal Credit Union", "Something Example LLC") < 0.6
    assert REG.name_score("Example Federal Credit Union", "Example Capital Fund 1, LP") >= 0.6   # kept, flagged < 1.0
