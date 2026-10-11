"""dedupe: one press release, three copies, one origin — the non-wire one."""
from __future__ import annotations

import hashlib

from evidence_engine import dedupe
from evidence_engine.search import url_key
from evidence_engine.types import Document

RELEASE = (
    "SPRINGFIELD, Ore. -- Example Federal Credit Union today announced the launch of its new "
    "digital onboarding experience, which lets prospective members open an account in under "
    "five minutes from any device. The experience uses identity verification and electronic "
    "signatures so that a new member never has to visit a branch to join. \"Our members asked "
    "for a faster, simpler way to join, and this delivers it,\" said the chief digital officer. "
    "The credit union serves more than 180,000 members across the state and holds $2.4 billion "
    "in assets. Membership is open to anyone who lives, works, worships or attends school in the "
    "counties the credit union serves. More information is available on the credit union's site."
)
WIRE_BOILERPLATE = " SOURCE Example Federal Credit Union. Related links: https://example-fcu.test. View original content to download multimedia."
EDIT_A = RELEASE.replace("today announced", "announced on Tuesday") + " Reporting by staff."
EDIT_B = "Example Federal Credit Union launches digital onboarding. " + RELEASE.replace("five minutes", "5 minutes")
OTHER = (
    "The National Credit Union Administration board approved a final rule on Thursday amending "
    "the agency's regulations on member business lending. The rule takes effect on the first day "
    "of the quarter after publication in the Federal Register. Board members said the change "
    "reduces burden on federally insured credit unions while keeping safety and soundness "
    "standards in place. The agency also released its quarterly data summary, showing total "
    "assets at federally insured credit unions grew during the quarter. Delinquency rates "
    "moved modestly higher while net worth ratios remained well above the statutory floor."
)


def _doc(url, text, published=None):
    return Document(url=url, final_url=url, text=text, verify_text=text,
                    content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(), published=published)


WIRE = _doc("https://www.prnewswire.com/news-releases/example-fcu-onboarding-301.html", RELEASE + WIRE_BOILERPLATE, "2026-03-03")
TRADE_A = _doc("https://www.cutimes.com/2026/03/04/example-onboarding/", EDIT_A, "2026-03-04")
TRADE_B = _doc("https://www.cuinsight.com/press-release/example-onboarding", EDIT_B, "2026-03-04")
RULE = _doc("https://www.cutimes.com/2026/03/05/ncua-mbl-rule/", OTHER, "2026-03-05")


def test_three_copies_one_cluster_origin_is_non_wire():
    docs = [WIRE, TRADE_A, TRADE_B, RULE]
    mapping = dedupe.cluster(docs)
    assert len(mapping) == 4
    ids = {mapping[url_key(d.url)] for d in (WIRE, TRADE_A, TRADE_B)}
    assert len(ids) == 1
    cid = ids.pop()
    assert cid != mapping[url_key(RULE.url)]
    counts = dedupe.syndication_counts(mapping)
    assert counts[cid] == 3 and counts[mapping[url_key(RULE.url)]] == 1
    smallest = min(url_key(d.url) for d in (WIRE, TRADE_A, TRADE_B))
    assert cid == "OC-" + hashlib.sha256(smallest.encode()).hexdigest()[:8]
    members = dedupe.members(mapping)[cid]
    origin = dedupe.origin_of([d for d in docs if url_key(d.url) in members])
    assert origin.url != WIRE.url
    assert origin.url == TRADE_B.url                # 2026-03-04 tie -> lexical url_key (cuinsight < cutimes)


def test_wire_only_cluster_falls_back_to_earliest_then_lexical():
    w2 = _doc("https://www.globenewswire.com/news-release/2026/03/02/example.html", RELEASE, "2026-03-02")
    assert dedupe.origin_of([WIRE, w2]) is w2
    undated = _doc("https://www.businesswire.com/news/home/x", RELEASE, None)
    assert dedupe.origin_of([undated, WIRE]) is WIRE
    assert dedupe.origin_of([]) is None


def test_two_different_articles_two_clusters():
    mapping = dedupe.cluster([TRADE_A, RULE])
    assert mapping[url_key(TRADE_A.url)] != mapping[url_key(RULE.url)]
    assert dedupe.syndication_counts(mapping) == {mapping[url_key(TRADE_A.url)]: 1, mapping[url_key(RULE.url)]: 1}


def test_exact_duplicate_short_circuits():
    copy = _doc("https://zzz-mirror.test/copy", RELEASE + WIRE_BOILERPLATE)
    mapping = dedupe.cluster([copy, WIRE])
    assert mapping[url_key(copy.url)] == mapping[url_key(WIRE.url)]


def test_determinism_across_input_order():
    docs = [WIRE, TRADE_A, TRADE_B, RULE]
    a = dedupe.cluster(docs)
    b = dedupe.cluster(list(reversed(docs)))
    c = dedupe.cluster([TRADE_B, RULE, WIRE, TRADE_A])
    assert a == b == c


def test_short_and_empty_documents_do_not_crash():
    tiny = _doc("https://tiny.test/a", "Three words only")
    empty = _doc("https://tiny.test/b", "")
    mapping = dedupe.cluster([tiny, empty, RULE])
    assert len(set(mapping.values())) == 3
