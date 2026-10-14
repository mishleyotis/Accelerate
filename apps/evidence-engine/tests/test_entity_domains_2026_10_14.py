"""An entity's domain reaches the engine whole (AAA WCNY, 2026-10-14).

`str.lstrip("www.")` strips the characters w and '.', so
`westerncentralnyaaa.com` became `esterncentralnyaaa.com`: every `site:`
probe asked about a domain that does not exist and the club's own pages
stopped matching as its own. These pin the prefix-only behaviour."""
from __future__ import annotations

import pytest

from evidence_engine import registry
from evidence_engine.tools import entity_ref


@pytest.mark.parametrize("given,want", [
    ("westerncentralnyaaa.com", "westerncentralnyaaa.com"),
    ("www.westerncentralnyaaa.com", "westerncentralnyaaa.com"),
    ("WWW.Webster.com", "webster.com"),
    ("wsfsbank.com", "wsfsbank.com"),
    ("https://www.wintrust.com/about", "wintrust.com"),
    (".w.example.com", ".w.example.com"),
])
def test_a_leading_w_survives_and_only_the_www_prefix_goes(given, want):
    ref = entity_ref({"legal_name": "X", "domains": [given]})
    assert ref.domains == [want]


def test_the_entitys_own_page_is_its_own_host():
    ref = entity_ref({"legal_name": "AAA Western and Central New York",
                      "domains": ["westerncentralnyaaa.com"]})
    assert registry.is_own_host("https://westerncentralnyaaa.com/insurance", ref)
    assert registry.is_own_host("https://www.westerncentralnyaaa.com/about", ref)
    # a sister club is not this club
    assert not registry.is_own_host("https://northeast.aaa.com/", ref)
