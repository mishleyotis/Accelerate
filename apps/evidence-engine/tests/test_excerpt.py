from evidence_engine import excerpt as X
from evidence_engine import textnorm
from evidence_engine.contract import EXCERPT_MAX, EXCERPT_MIN

TEXT = """Example Federal Credit Union reports record growth

ANYTOWN, ST, March 3, 2026 – Example Federal Credit Union today reported that members grew 4.2 percent to 212,000 during 2025. Total assets rose to $6.11 billion, and the credit union opened two branches in the county. The credit union also launched a new mobile application with card controls and instant alerts. We are committed to excellence and innovative solutions for our members. Accept all cookies to continue.

Chief Executive Jane Example said the mobile application reached 61 percent of active members within ninety days."""


def _verify():
    return "NAV Home Log in " + TEXT + " FOOTER We use cookies"


def test_selects_the_sentence_with_the_figure():
    cands = X.select(TEXT, _verify(), "mobile application adoption members", entity_terms={"example"})
    assert cands, "no candidate"
    top = cands[0]
    assert TEXT[top.start:top.end] == top.text
    assert EXCERPT_MIN <= len(top.text) <= EXCERPT_MAX
    assert top.has_figure
    assert "61 percent" in top.text or "card controls" in top.text


def test_boilerplate_and_marketing_never_emitted():
    cands = X.select(TEXT, _verify(), "committed excellence innovative solutions members cookies")
    for c in cands:
        assert "innovative solutions" not in c.text.lower()
        assert "cookies" not in c.text.lower()
    assert X.boilerplate_match("We are committed to excellence and innovative solutions.")
    assert X.boilerplate_match("Accept all cookies to continue.")
    assert X.boilerplate_match("Capability P2C3.1.4 scored 3") is not None
    assert X.boilerplate_match("Members grew 4.2 percent to 212,000.") is None


def test_every_candidate_verifies_against_both_texts():
    cands = X.select(TEXT, _verify(), "branches assets growth members")
    assert cands
    for c in cands:
        assert X.verify_against_both(TEXT, _verify(), c.start, c.end, c.text)
        assert textnorm.normalise(c.text) in textnorm.normalise(_verify())


def test_span_absent_from_verify_text_is_dropped():
    verify = "Something else entirely."
    assert X.select(TEXT, verify, "branches assets growth members") == []


def test_short_sentence_extends_to_a_neighbour_never_cuts():
    text = "Assets: $6.1B. Members grew 4.2 percent to 212,000 during 2025, the credit union said."
    cands = X.select(text, text, "assets")
    assert cands
    assert len(cands[0].text) >= EXCERPT_MIN
    assert cands[0].text.endswith(".")
    assert text[cands[0].start:cands[0].end] == cands[0].text


def test_no_query_hit_no_candidate():
    assert X.select(TEXT, _verify(), "quantum chromodynamics") == []


def test_context_window_is_on_demand_only():
    cands = X.select(TEXT, _verify(), "branches assets")
    a, b, ctx = X.context_window(TEXT, cands[0].start, cands[0].end, 1)
    assert a <= cands[0].start and b >= cands[0].end
    assert TEXT[a:b] == ctx
