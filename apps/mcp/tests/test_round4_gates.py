"""Five ways a payload passed every gate and still read wrong on the page.

Every one was reported from a rendered surface, by a person, after the
connector had said PASS. That is the shape these gates exist for: the contract
was satisfied and the page was still wrong.

  AG-11  a why-now signal that recaps this assessment's own scores
  AG-12  a conversation starter that opens on an accusation
  CG-26  two thought-leadership entries citing one document
  CG-27  an abbreviation reaching a client surface unexplained
  CG-28  an executive dropped because contact enrichment found nothing

Each test carries the measured text where there is one, so a future reader
can see what the gate was written against rather than a paraphrase.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import validation as V  # noqa: E402


def _sig(text, wn="WN-4", field="trigger"):
    return {"signals": [{"wn_id": wn, field: text}]}


# ── AG-11 · why-now is an event, not a recap ───────────────────────────

# Promoted verbatim on the reference client, and every figure in it is this
# assessment's own output.
WN4 = ("A five-member same-sub-vertical cohort read on 19 August 2026 sits at "
       "2.52, 2.70, 2.50 and 2.36 across the four pillars against this run's "
       "1.60, 1.52, 1.75 and 1.43.")


def test_a_signal_that_recaps_the_run_s_own_scores_is_refused():
    out = V._check_why_now_is_an_event("why_now", _sig(WN4))
    assert [r["gate_id"] for r in out] == ["AG-11"]
    assert "OUTSIDE" in out[0]["message"]


def test_the_pattern_matches_a_two_decimal_score():
    """The first version could not match "2.52" — a trailing word boundary
    failed against the second decimal — so it read the very sentence it was
    written for as clean. A gate that cannot see its own founding case is
    worse than no gate, because it is believed."""
    assert V._check_why_now_is_an_event("why_now", _sig("The composite is 2.52 against a cohort at 2.70."))


def test_a_dated_external_event_passes():
    for text in [
        "Quinte and Logix announced on 9 June 2026 that CaseHUB has been the "
        "central hub for fraud investigations for more than a decade.",
        "Logix reported $9.688 billion of assets to the National Credit Union "
        "Administration for the June 2026 cycle.",
        "Logix appointed Clark Dilley Senior Vice President and Chief "
        "Information Officer in February 2024.",
    ]:
        assert V._check_why_now_is_an_event("why_now", _sig(text)) == [], text


def test_the_recap_is_caught_in_any_prose_field_of_the_signal():
    for field in ("trigger", "headline", "so_what", "metric"):
        assert V._check_why_now_is_an_event("why_now", _sig(WN4, field=field)), field


def test_one_signal_raises_one_reason_not_four():
    """A signal that recaps in three fields is one thing to fix."""
    out = V._check_why_now_is_an_event("why_now", {"signals": [
        {"wn_id": "WN-4", "trigger": WN4, "headline": WN4, "so_what": WN4}]})
    assert len(out) == 1


# ── AG-12 · a starter opens on an opportunity ──────────────────────────

def test_an_accusatory_starter_is_refused():
    # Promoted verbatim.
    out = V._check_starter_tone("starters", {"starters": [
        {"text": "Two things you have told the market do not quite line up, "
                 "and I think the gap is worth money to you."}]})
    assert [r["gate_id"] for r in out] == ["AG-12"]
    assert "contradicted itself" in out[0]["message"]


def test_the_same_fact_as_an_opening_passes():
    assert V._check_starter_tone("starters", {"starters": [
        {"text": "Your app does the transactional work well — deposits, bill "
                 "pay, card controls. The next thing it could do is answer a "
                 "question, and that is where the contact-centre cost sits."}]}) == []


def test_every_accusatory_move_is_covered():
    for text in [
        "What it cannot do is answer a question.",
        "You do not measure contact-centre deflection.",
        "Your weakness is model governance.",
        "You fall behind the cohort on data.",
        "Your analytics lags the market.",
    ]:
        assert V._check_starter_tone("starters", {"starters": [{"text": text}]}), text


def test_the_followup_question_is_read_too():
    """A consultative opening followed by an accusatory question is still an
    accusation; the reader meets both."""
    assert V._check_starter_tone("starters", {"starters": [
        {"text": "Your fraud casework runs on a platform a decade deep.",
         "followup_question": "Why do you not track loss per member?"}]})


# ── CG-26 · one entry per source document ──────────────────────────────

def test_two_entries_citing_one_document_are_refused():
    out = V._check_thought_leadership_unique("thought_leadership", {"entries": [
        {"url": "https://docs.house.gov/HHRG-119-BA20-Wstate-FonsecaA.pdf",
         "quote": "crossing the arbitrary $10 billion threshold"},
        {"url": "https://docs.house.gov/HHRG-119-BA20-Wstate-FonsecaA.pdf/",
         "quote": "$517,000 for exam readiness reviews"},
    ]})
    assert [r["gate_id"] for r in out] == ["CG-26"]
    assert "Merge" in out[0]["message"]


def test_different_documents_pass():
    assert V._check_thought_leadership_unique("thought_leadership", {"entries": [
        {"url": "https://docs.house.gov/a.pdf"},
        {"url": "https://www.finopotamus.com/post/b"},
        {"url": "https://www.prosightfa.org/insights/c/"},
    ]}) == []


def test_an_entry_with_no_url_is_not_a_duplicate_of_another():
    assert V._check_thought_leadership_unique("thought_leadership", {"entries": [
        {"quote": "a"}, {"quote": "b"}]}) == []


# ── CG-27 · spell it out the first time ────────────────────────────────

def test_an_abbreviation_in_authored_prose_is_refused():
    out = V._check_no_bare_abbreviations("overview", "firmographics", {
        "note": "The NCUA call report shows the credit union above nine "
                "billion in assets."})
    assert [r["gate_id"] for r in out] == ["CG-27"]


def test_a_verbatim_field_is_never_rewritten():
    """An excerpt is a byte-for-byte span of a fetched artefact (invariant 4)
    and a quote is what someone said. Expanding an abbreviation inside either
    would misquote the source and break the verifier that compares the excerpt
    against the bytes it came from."""
    assert V._check_no_bare_abbreviations("overview", "thought_leadership", {
        "excerpt": "For an institution like Logix, crossing the threshold that "
                   "subjects us to greater CFPB scrutiny has a cost.",
        "quote": "Logix FCU has utilised CaseHUB for more than a decade.",
        "source_title": "Testimony of Ana Fonseca, President & CEO, Logix FCU",
        "author_role": "President and CEO",
    }) == []


def test_spelling_it_out_once_licenses_the_short_form():
    assert V._check_no_bare_abbreviations("overview", "firmographics", {
        "note": "The National Credit Union Administration (NCUA) dictionary "
                "defines no revenue account, so the NCUA figure is absent."}) == []


def test_the_gate_names_a_handful_not_a_wall():
    body = {f"f{i}": "The NCUA and the CFPB and the CU all appear here."
            for i in range(40)}
    assert len(V._check_no_bare_abbreviations("overview", "x", body)) <= 6


# ── CG-28 · an executive is not dropped for want of a phone number ─────

def test_serving_fewer_seats_than_were_identified_is_refused():
    out = V._check_roster_keeps_uncontactable("leadership", {
        "seats_identified": 8,
        "roster": [{"name": "A"}, {"name": "B"}, {"name": "C"}]})
    assert [r["gate_id"] for r in out] == ["CG-28"]
    assert "contact enrichment returned nothing" in out[0]["message"]


def test_a_seat_marked_dropped_is_refused_even_when_the_count_agrees():
    out = V._check_roster_keeps_uncontactable("leadership", {
        "seats_identified": 2,
        "roster": [{"name": "A"}, {"name": "B", "dropped_for_no_contact": True}]})
    assert len(out) == 1


def test_a_complete_roster_passes():
    assert V._check_roster_keeps_uncontactable("leadership", {
        "seats_identified": 3,
        "roster": [{"name": "A", "email": "a@x"}, {"name": "B"},
                   {"name": "C", "phone": None}]}) == []


def test_a_roster_that_declares_no_count_is_not_second_guessed():
    """The gate reads what the payload states. Inventing a count would make it
    fire on every run that simply does not declare one."""
    assert V._check_roster_keeps_uncontactable("leadership", {
        "roster": [{"name": "A"}]}) == []
