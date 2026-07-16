"""Guards for the evidence→subcap similarity linker's precision contract."""
from app.scripts import link_evidence_subcaps as m
from app.services.nlp.similarity import LexicalIndex


def test_placeholder_subcap_names_excluded():
    # un-named catalogue rows must never be link targets (they ground nothing)
    assert m._PLACEHOLDER_NAME.match("capability dimension 27")
    assert m._PLACEHOLDER_NAME.match("Capability Dimension 5")
    assert not m._PLACEHOLDER_NAME.match("Payment Processing Automation")
    assert not m._PLACEHOLDER_NAME.match("FFIEC Governance")


def test_conservative_floor():
    # precision over recall: a real floor, not the library's 0.08 default
    assert m._MIN_SCORE >= 0.15
    assert m._TOP_K <= 2


def test_lexical_link_matches_relevant_subcap_over_floor():
    idx = LexicalIndex()
    idx.fit([
        ("P3C1.2.2", "Payment Processing Automation. Automates payment rails "
                     "including FedNow, RTP and traditional payment flows."),
        ("P1C1.1.1", "Digital Strategy Document. Aligns digital strategy with "
                     "the enterprise vision."),
    ])
    hits = idx.top_k(
        "Finzly single-API platform consolidates FedNow + RTP + traditional "
        "payment processing", k=2, min_score=m._MIN_SCORE)
    assert hits and hits[0][0] == "P3C1.2.2"
    # an off-topic query links to nothing above the floor
    assert not idx.top_k("Presented at KubeCon NA 2024 in Salt Lake City",
                         k=2, min_score=m._MIN_SCORE)
