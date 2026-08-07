"""CG-11 — prose begins as a sentence.

Asked for by name, and mechanical: a prose field on a client surface
begins with a capital. The defective values here are verbatim from a
promoted run — a recommendation prerequisite reading "the chief
technology officer holds this in the current evidence.", four opportunity
"discarded" reasons, seventeen ceiling rows.

The exemption is the point of the gate having a shape at all: a first
word carrying an uppercase letter after its first character — nCino, iOS,
eBay — is the vendor's own orthography and must survive untouched. So
must an id, a hostname, a URL, an enum and, above all, a verbatim
excerpt: editing the first letter of a quotation is the one thing
evidence may never have done to it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_sentence_case, _sentence_case_reason


def test_the_promoted_prerequisite_note_is_refused_with_its_repair():
    body = {"recommendations": [{"rec_id": "REC-001", "prerequisites": [
        {"condition": "Architecture decision owner named for the platform",
         "note": "the chief technology officer holds this in the current "
                 "evidence."}]}]}
    out = _check_sentence_case("recommendations", body)
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-11" and r["severity"] == "block"
    assert r["path"] == "recommendations.recommendations[0].prerequisites[0].note"
    assert "'the'" in r["message"] and "'The'" in r["message"]


def test_the_corrected_note_passes():
    body = {"recommendations": [{"prerequisites": [
        {"note": "The chief technology officer holds this in the current "
                 "evidence."}]}]}
    assert _check_sentence_case("recommendations", body) == []


def test_camel_case_first_words_survive():
    """nCino, iOS and eBay are spellings, not slips. The rule is
    positional: an uppercase letter anywhere after the first character of
    the first word."""
    for text in ("nCino originates the mortgage book and the commercial "
                 "pipeline together.",
                 "iOS adoption outruns Android across the member base.",
                 "eBay-style bidding is not a pattern in this estate."):
        assert _sentence_case_reason("body", text) is None
    # and a genuinely lowercase opener next to them is still refused
    assert _sentence_case_reason(
        "body", "the nCino deployment covers commercial lending only.") == "the"


def test_a_verbatim_excerpt_is_never_touched():
    """A quotation begins where the document begins. Tidying its first
    letter would make it not verbatim, which is the whole of invariant 4."""
    mid_sentence = ("and the board approved a three-year digital programme "
                    "with quarterly checkpoints in place.")
    assert _sentence_case_reason("excerpt", mid_sentence) is None
    assert _sentence_case_reason("quote", mid_sentence) is None
    assert _sentence_case_reason("body", mid_sentence) == "and"


def test_identifiers_hostnames_and_versions_are_not_prose():
    assert _sentence_case_reason("producer_version",
                                 "dma-surface-production@2026-08-05") is None
    assert _sentence_case_reason("source_domain",
                                 "vibeprospecting.explorium.ai") is None
    assert _sentence_case_reason("url", "https://bcu.org/newsroom/2026") is None
    # a single token is never a sentence, whatever its key
    assert _sentence_case_reason("body", "strategy-first-substrate-later") is None


def test_a_fragment_that_renders_inline_after_a_label_is_left_alone():
    """`unit` renders as '1,300 full and part-time employees'. Capitalising
    it mid-sentence is the same defect pointing the other way, so the rule
    fires only on a prose KEY or on a value the producer ended as a
    sentence."""
    assert _sentence_case_reason("unit", "full and part-time employees") is None
    assert _sentence_case_reason(
        "their_system_reference",
        "the announced merger with Healthcare Associates") is None
    # ... but end it as a sentence and it is one
    assert _sentence_case_reason(
        "their_system_reference",
        "the announced merger closes this year.") == "the"


def test_short_strings_and_non_letters_are_out_of_scope():
    assert _sentence_case_reason("body", "no change") is None          # < 25
    assert _sentence_case_reason(
        "excerpt", '"averageUserRating":4.8657799999999') is None      # digit
    assert _sentence_case_reason(
        "rejected_alternative",
        "'The current tool is adequate' was considered and rejected.") is None
