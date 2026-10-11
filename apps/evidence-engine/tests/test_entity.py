"""entity.match: confirmed / probable / ambiguous, and the near-name trap."""
from __future__ import annotations

import hashlib

from evidence_engine import entity, registry
from evidence_engine.types import Document, EntityRef

ENTITY = EntityRef(legal_name="Example Federal Credit Union", domains=["example-fcu.test"],
                   aliases=["Example FCU"], location="Springfield, Oregon", charter="12345",
                   cik="0001234567", ticker="EXFC")


def _doc(url, text, title=""):
    return Document(url=url, final_url=url, text=text, verify_text=text, title=title,
                    content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest())


def _info(url):
    return registry.classify(url, ENTITY)


def test_own_domain_is_confirmed():
    d = _doc("https://example-fcu.test/about", "Welcome to our site.")
    v, basis = entity.match(d, ENTITY, _info(d.url))
    assert v == "confirmed" and "own domain" in basis


def test_legal_name_plus_second_identifier_is_confirmed():
    d = _doc("https://www.cutimes.com/2026/03/04/x/",
             "EXAMPLE   Federal Credit Union, based in Springfield, Oregon, launched onboarding.")
    assert entity.match(d, ENTITY, _info(d.url)) == ("confirmed", "legal name and location on page")
    d2 = _doc("https://springfield-daily.test/x", "Example Federal Credit Union (charter no. 12345) said it will merge.")
    assert entity.match(d2, ENTITY, _info(d2.url))[0] == "confirmed"
    d3 = _doc("https://springfield-daily.test/y", "Example FCU, CIK 0001234567, filed its annual report.")
    v, basis = entity.match(d3, ENTITY, _info(d3.url))
    assert v == "confirmed" and "alias" in basis and "CIK" in basis
    d4 = _doc("https://springfield-daily.test/z", "Shares of Example Federal Credit Union (EXFC) rose.")
    assert entity.match(d4, ENTITY, _info(d4.url))[1].endswith("ticker on page")


def test_regulator_page_naming_legal_name_is_confirmed():
    d = _doc("https://ncua.gov/analysis/x", "Example Federal Credit Union reported total assets of $2.4 billion.")
    v, basis = entity.match(d, ENTITY, _info(d.url))
    assert v == "confirmed" and "regulator page names the legal name verbatim" == basis
    f = _doc("https://www.sec.gov/Archives/edgar/data/1/x.htm", "Registrant: Example Federal Credit Union.")
    assert entity.match(f, ENTITY, _info(f.url))[0] == "confirmed"


def test_legal_name_alone_on_third_party_is_probable():
    d = _doc("https://www.americanbanker.com/news/x", "Example Federal Credit Union picked a new core vendor.")
    assert entity.match(d, ENTITY, _info(d.url)) == ("probable", "legal name on page, no second identifier")
    a = _doc("https://www.americanbanker.com/news/y", "Example FCU picked a new core vendor.")
    v, basis = entity.match(a, ENTITY, _info(a.url))
    assert v == "probable" and "alias" in basis


def test_near_name_trap_is_ambiguous():
    d = _doc("https://www.americanbanker.com/news/x", "Example Credit Union opened a branch in Springfield, Oregon.")
    v, basis = entity.match(d, ENTITY, _info(d.url))
    assert v == "ambiguous" and basis.startswith("shared tokens only") and "example" in basis
    # a different federal credit union sharing words is not this one either
    d2 = _doc("https://www.cutimes.com/x/", "Another Example Federal Credit Union Services LLC was formed.")
    # the full legal name appears verbatim inside a longer name: that is the name, so probable, not ambiguous
    assert entity.match(d2, ENTITY, _info(d2.url))[0] == "probable"
    d3 = _doc("https://www.cutimes.com/y/", "Examples of federal credit unions abound.")
    assert entity.match(d3, ENTITY, _info(d3.url))[0] == "ambiguous"
    d4 = _doc("https://www.cutimes.com/z/", "A story about a bank in Oregon.")
    assert entity.match(d4, ENTITY, _info(d4.url)) == ("ambiguous", "entity not named on page")


def test_location_alone_does_not_confirm_without_the_name():
    d = _doc("https://springfield-daily.test/x", "Springfield, Oregon welcomes a new credit union branch.")
    assert entity.match(d, ENTITY, _info(d.url))[0] == "ambiguous"


def test_title_counts_as_page_text_and_match_is_case_insensitive():
    d = _doc("https://springfield-daily.test/x", "the body says nothing", title="EXAMPLE FEDERAL CREDIT UNION names CEO")
    assert entity.match(d, ENTITY, _info(d.url))[0] == "probable"
