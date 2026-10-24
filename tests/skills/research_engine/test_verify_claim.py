"""The claim verifier, measured on the battery that condemned the drawers.

Measured 28-09-2026 (QA audit F-D04-005) on a promoted run: 12 of 67
claims in the cell drawers had no excerpt behind them — a named CEO
attribution, a committee structure, an after-state ("hours to minutes").
The verifier is lexical and offline; the assertions here are on its RECALL
over those shapes (total) and on what it does NOT refuse (the supported
claims, the mandated score frame), and its two stated limits are pinned as
limits so nobody mistakes a clean result for a proof.
"""
import json

import pytest

from engine import quality as Q
from fixtures import bank_evidence, new_run

E1 = ("Alkami digital banking went live in Q3 2024 and reached 47 percent member "
      "adoption within ninety days, restated at 50 percent in the 2025 report.")
E2 = ("Board committees: Technology Committee (Paul Martin chair, 7 members), "
      "Supervisory Committee, Nominating Governance Committee, Executive Committee")
E3 = ("The credit union reported total assets of $2.4 billion at 31 December 2025 "
      "and 187,000 members, up 4 percent year on year.")
EXCERPTS = [E1, E2, E3]
ENTITY = "Acme Credit Union"

SUPPORTED = [
    "Alkami digital banking went live in Q3 2024 [E-0001:F1].",
    "Member adoption reached 47 percent within ninety days.",
    "A board technology committee chaired by Paul Martin has seven members [E-0002].",
    "Total assets stood at $2.4 billion at the end of 2025, with 187,000 members.",
    "Adoption was later restated at 50 percent in the 2025 report.",
    "Seven board members sit on the Technology Committee, chaired by Paul Martin.",
]
#: The audit's three shapes first, then four more of the same family.
UNSUPPORTED = [
    "CEO Jason Mullins said adoption exceeded every target.",              # named attribution
    "A digital steering committee reviews the roadmap quarterly.",         # committee structure
    "Onboarding time fell from hours to minutes after the Alkami launch.",  # after-state
    "Adoption reached 62 percent of members.",                             # a figure no excerpt carries
    "Members can open accounts in under five minutes on the mobile app.",
    "The 2024 rollout was delayed twice before going live.",
    "Net income rose to $31 million in 2025.",
]
FRAME = "The score sits at 2.5 against a peer median of 3.0, in the Building band."
PARAPHRASE = ("Digital banking adoption grew quickly after launch, according to the "
              "annual report.")


@pytest.mark.parametrize("claim", SUPPORTED)
def test_a_supported_claim_is_entailed(claim):
    r = Q.verify_sentence(claim, EXCERPTS, entity=ENTITY)
    assert r["verdict"] == "entailed", r
    assert r["missing_hard"] == []
    assert r["span"], "the supporting excerpt sentence is named"


@pytest.mark.parametrize("claim", UNSUPPORTED)
def test_recall_is_total_on_the_unsupported_battery(claim):
    r = Q.verify_sentence(claim, EXCERPTS, entity=ENTITY)
    assert r["verdict"] == "not_supported", r
    assert r["missing"] or r["missing_hard"], "the refusal names what is missing"


def test_the_named_attribution_is_refused_for_its_name_not_its_coverage():
    r = Q.verify_sentence(UNSUPPORTED[0], EXCERPTS, entity=ENTITY)
    assert {"jason", "mullin", "ceo"} <= set(r["missing_hard"])


def test_a_missing_figure_alone_refuses_a_sentence_whose_words_are_all_there():
    r = Q.verify_sentence("Adoption reached 62 percent of members.", EXCERPTS)
    assert r["verdict"] == "not_supported" and r["missing_hard"] == ["62"]
    assert r["coverage"] >= Q.ENTAILED_FLOOR, "coverage alone would have passed it"


def test_the_mandated_score_frame_is_not_a_claim():
    r = Q.verify_sentence(FRAME, EXCERPTS)
    assert r["verdict"] == "frame"


def test_the_entity_name_is_exempt():
    assert Q.verify_sentence("Acme Credit Union went live on Alkami in Q3 2024.",
                             EXCERPTS, entity=ENTITY)["verdict"] == "entailed"


def test_a_paraphrase_is_partial_never_not_supported():
    r = Q.verify_sentence(PARAPHRASE, EXCERPTS, entity=ENTITY)
    assert r["verdict"] == "partial", r
    assert Q.PARTIAL_FLOOR <= r["coverage"] < Q.ENTAILED_FLOOR


def test_the_stated_limit_a_true_word_wrong_relation_passes():
    """Every word is in the excerpt; the relation is wrong. The verifier
    reads words; the challenger reads relations. Pinned so the limit is
    documented, not discovered."""
    r = Q.verify_sentence("The Supervisory Committee is chaired by Paul Martin.", EXCERPTS)
    assert r["verdict"] == "entailed"


def test_verify_claim_is_the_worst_sentence_and_counts_the_rest():
    text = " ".join([SUPPORTED[0], FRAME, UNSUPPORTED[2]])
    out = Q.verify_claim(text, EXCERPTS, entity=ENTITY)
    assert out["verdict"] == "not_supported"
    assert out["counts"] == {"entailed": 1, "partial": 0, "not_supported": 1, "frame": 1}
    assert out["floors"] == {"entailed": Q.ENTAILED_FLOOR, "partial": Q.PARTIAL_FLOOR}


def test_verify_cell_reads_the_items_and_spares_a_declared_absence():
    cited = {"subcap_id": "P1C1.1.1", "synthesis": SUPPORTED[0] + " " + UNSUPPORTED[0],
             "items": [{"e_id": "E-1", "excerpt": E1}], "thin": False}
    assert Q.verify_cell(cited, entity=ENTITY)["verdict"] == "not_supported"
    declared = {"subcap_id": "P1C4.1.6", "synthesis": "User acceptance testing leaves "
                "artefacts — test plans, sign-off records — and none is visible.",
                "items": [], "thin": True,
                "sources_searched": ['searched for: "user acceptance testing" — 0 hits'],
                "closure_condition": "A sign-off record from the Elevate rollout."}
    assert Q.verify_cell(declared)["grade"] == "declared"
    uncited = dict(declared, thin=False, sources_searched=[])
    assert Q.verify_cell(uncited)["verdict"] == "not_supported"


def test_the_cli_verifies_against_the_registered_excerpts(tmp_path, capsys):
    from engine import cli
    run = new_run(tmp_path)
    wb = run.open()
    eids = bank_evidence(wb, "P1C1.1.1", n=2)
    rr = ["--run", run.run_id, "--root", str(run.root)]
    assert cli.main(["verify-claim", *rr, "--subcap", "P1C1.1.1",
                     "--claim", "Alkami digital banking went live in Q3 2024."]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "entailed" and set(out["e_ids"]) == set(eids)
    assert cli.main(["verify-claim", *rr, "--e-id", eids[0],
                     "--claim", "CEO Jason Mullins said adoption exceeded every target."]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "not_supported"
    assert cli.main(["verify-claim", *rr, "--claim", "x"]) == 1, "nothing to verify against"
    assert cli.main(["verify-claim", *rr, "--e-id", "E-9999", "--claim", "x"]) == 1
