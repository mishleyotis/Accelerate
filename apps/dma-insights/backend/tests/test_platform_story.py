"""Tests for the deterministic D4 conversation_starter composer (B-1).

The wireframe expects every PlatformCard to render a multi-line
conversation starter that an AE can read into a discovery call. Per
CLAUDE.md "Synthesis persistence + decision gates", surfaces fully
derivable from parsed data go through the `parsed_skipped_llm` gate —
zero tokens — so this composer is pure-logic and deterministic.
"""
from __future__ import annotations

from app.services.platform_story import compose_conversation_starter
from app.services.readiness_index import PrereqCheck


def _check(
    *,
    name: str = "Single customer view",
    sid: str = "P2C1.1.1",
    threshold: float = 3.0,
    status: str = "MET",
    current: float | None = 4.0,
    note: str | None = None,
) -> PrereqCheck:
    return PrereqCheck(
        name=name,
        required_subcap_id=sid,
        threshold=threshold,
        status=status,  # type: ignore[arg-type]
        current_score=current,
        note=note,
    )


def test_no_addressable_subcaps_returns_none() -> None:
    """INSUFFICIENT_EVIDENCE state — wireframe hides starters card."""
    assert (
        compose_conversation_starter(
            platform_name="Salesforce",
            pillar="P2",
            fit_score=0.0,
            addressable_subcap_ids=[],
            prereq_checks=[],
            readiness="amber",
        )
        is None
    )


def test_starter_cites_top_subcap_and_fit_score() -> None:
    out = compose_conversation_starter(
        platform_name="Salesforce",
        pillar="P2",
        fit_score=78.3,
        addressable_subcap_ids=["P2C1.1.1", "P2C2.1.1", "P2C3.1.1"],
        prereq_checks=[_check(status="MET")],
        readiness="green",
    )
    assert out is not None
    first = out.splitlines()[0]
    assert "Salesforce" in first
    assert "pillar P2" in first
    assert "3 subcaps" in first
    assert "P2C1.1.1" in first
    assert "78/100" in first
    assert "ready to land now" in first


def test_starter_includes_three_numbered_steps_plus_next() -> None:
    out = compose_conversation_starter(
        platform_name="Databricks",
        pillar="P4",
        fit_score=42.0,
        addressable_subcap_ids=["P4C1.1.1", "P4C1.2.1"],
        prereq_checks=[_check(status="MET")],
        readiness="green",
    )
    assert out is not None
    lines = out.splitlines()
    assert len(lines) == 5
    assert lines[1].startswith("1. ")
    assert lines[2].startswith("2. ")
    assert lines[3].startswith("3. ")
    assert lines[4].startswith("Next step:")


def test_pain_line_uses_first_unmet_prereq_with_score() -> None:
    out = compose_conversation_starter(
        platform_name="Tableau",
        pillar="P4",
        fit_score=55.0,
        addressable_subcap_ids=["P4C2.1.1"],
        prereq_checks=[
            _check(name="Data quality", sid="P4C2.1.1", status="UNMET",
                   threshold=3.0, current=1.5),
            _check(name="Governance", sid="P1C1.1.1", status="PARTIAL",
                   threshold=3.0, current=2.6),
        ],
        readiness="red",
    )
    assert out is not None
    pain_line = out.splitlines()[2]
    assert pain_line.startswith("2. Pain")
    assert "P4C2.1.1" in pain_line
    assert "1.5" in pain_line
    assert "3.0" in pain_line
    assert "UNMET" in pain_line


def test_pain_line_falls_back_to_partial_when_no_unmet() -> None:
    out = compose_conversation_starter(
        platform_name="Twilio",
        pillar="P2",
        fit_score=60.0,
        addressable_subcap_ids=["P2C2.1.1"],
        prereq_checks=[
            _check(name="Identity", sid="P2C1.1.1", status="PARTIAL",
                   threshold=3.0, current=2.7),
        ],
        readiness="amber",
    )
    assert out is not None
    assert "PARTIAL" in out
    assert "near-ready" in out.splitlines()[0]


def test_all_met_pivots_to_value_capture() -> None:
    out = compose_conversation_starter(
        platform_name="nCino",
        pillar="P3",
        fit_score=88.0,
        addressable_subcap_ids=["P3C1.1.1", "P3C2.1.1"],
        prereq_checks=[_check(status="MET"), _check(status="MET")],
        readiness="green",
    )
    assert out is not None
    pain_line = out.splitlines()[2]
    assert pain_line.startswith("2. Value")
    assert "MET" in pain_line


def test_single_subcap_uses_action_not_sequence_line() -> None:
    out = compose_conversation_starter(
        platform_name="Salesforce",
        pillar="P2",
        fit_score=33.0,
        addressable_subcap_ids=["P2C1.1.1"],
        prereq_checks=[_check(status="MET")],
        readiness="green",
    )
    assert out is not None
    third = out.splitlines()[3]
    assert third.startswith("3. Action:")
    assert "P2C1.1.1" in third
    assert "additional subcap" not in out


def test_missing_prereq_score_renders_dash_not_crash() -> None:
    out = compose_conversation_starter(
        platform_name="Tableau",
        pillar="P4",
        fit_score=10.0,
        addressable_subcap_ids=["P4C1.1.1"],
        prereq_checks=[
            _check(name="X", sid="P4C9.9.9", status="MISSING",
                   threshold=3.5, current=None,
                   note="no score recorded for P4C9.9.9"),
        ],
        readiness="red",
    )
    assert out is not None
    assert "no score recorded" in out
    assert "MISSING" in out


def test_readiness_label_per_branch() -> None:
    base: dict[str, object] = {
        "platform_name": "Salesforce",
        "pillar": "P2",
        "fit_score": 50.0,
        "addressable_subcap_ids": ["P2C1.1.1"],
        "prereq_checks": [_check(status="MET")],
    }
    assert "ready to land now" in compose_conversation_starter(
        readiness="green", **base  # type: ignore[arg-type]
    )
    assert "near-ready" in compose_conversation_starter(
        readiness="amber", **base  # type: ignore[arg-type]
    )
    assert "not ready" in compose_conversation_starter(
        readiness="red", **base  # type: ignore[arg-type]
    )


def test_grammar_singular_vs_plural_subcaps() -> None:
    single = compose_conversation_starter(
        platform_name="X",
        pillar="P1",
        fit_score=1.0,
        addressable_subcap_ids=["P1C1.1.1"],
        prereq_checks=[_check(status="MET")],
        readiness="green",
    )
    plural = compose_conversation_starter(
        platform_name="X",
        pillar="P1",
        fit_score=1.0,
        addressable_subcap_ids=["P1C1.1.1", "P1C2.1.1", "P1C3.1.1"],
        prereq_checks=[_check(status="MET")],
        readiness="green",
    )
    assert single is not None and plural is not None
    assert "1 subcap," in single.splitlines()[0]
    assert "3 subcaps," in plural.splitlines()[0]


# ── v2 starters (Part 7.1: top-opportunity anchor + entity facts) ──────

from app.services.platform_story import (  # noqa: E402
    StarterFacts,
    compose_conversation_starters,
)

_FACTS = StarterFacts(
    entity_name="Alma Bank",
    top_subcap_id="P1C4.1.6",
    top_subcap_name="Change Management Framework",
    top_score=1.0,
    top_peer_median=2.5,
    top_e_ids=["E-040", "E-005"],
    metric_phrases=["loan cycle 12 days [E-236]"],
    peer_names=["Hanover Community Bank", "Synovus"],
    absent_families=["nCino"],
    sequence_after=["Databricks"],
)


def test_v2_starters_anchor_on_top_opportunity_not_sorted_first() -> None:
    """The audit: 98.9% of starters anchored 'P1C1.1.1' because the
    composer took sorted(addressable)[0]. v2 anchors the fit engine's
    top-opportunity subcap."""
    out = compose_conversation_starters(
        platform_name="nCino", pillar="P3", fit_score=72.0,
        addressable_subcap_ids=["P1C1.1.1", "P1C4.1.6", "P3C2.1.1"],
        prereq_checks=[_check(status="MET")], readiness="amber",
        facts=_FACTS,
    )
    assert len(out) == 3
    # The anchor is the top-opportunity subcap, now identified by its NAME —
    # the raw "(P1C4.1.6)" code is cleansed out by text_hygiene (2026-07-09
    # hygiene fix: starters must not leak taxonomy codes to the AE).
    assert "Change Management Framework" in out[0], \
        "anchor must be the top-opportunity subcap (by name)"
    assert "P1C4.1.6" not in out[0], "raw taxonomy code must be cleansed out"
    assert "P1C1.1.1" not in out[0], "sorted-first anchor is the audited bug"


def test_v2_every_starter_carries_an_entity_fact() -> None:
    """Acceptance: zero generic starters — each carries a real score,
    metric, E-ID or named peer."""
    import re
    out = compose_conversation_starters(
        platform_name="nCino", pillar="P3", fit_score=72.0,
        addressable_subcap_ids=["P1C4.1.6"],
        prereq_checks=[_check(status="UNMET", current=1.2)], readiness="red",
        facts=_FACTS,
    )
    fact_rx = re.compile(r"\[E-|\d\.\d|\d+ days|Hanover|Synovus")
    for s in out:
        assert fact_rx.search(s), f"starter lacks an entity fact: {s}"
    # entity name + ONE score anchor + qualitative peer relation + citation in
    # the discovery starter (2026-07-14 mandate: no second "2.5 peer median"
    # number — the relation is stated in words).
    assert "Alma Bank" in out[0]
    assert "1.0" in out[0] and "below the peer median" in out[0]
    assert "2.5" not in out[0]
    assert "[E-040, E-005]" in out[0]
    # confirmed-absent family framing
    assert "nCino" in out[0] and "absent" in out[0]
    # pain starter quantifies with the entity's own evidence metric
    assert "loan cycle 12 days [E-236]" in out[1]
    # peer starter names real cohort peers + the sequencing
    assert "Hanover Community Bank" in out[2] and "Databricks" in out[2]


def test_v2_starters_met_branch_still_quantified() -> None:
    out = compose_conversation_starters(
        platform_name="Tableau", pillar="P4", fit_score=61.0,
        addressable_subcap_ids=["P4C2.1.1"],
        prereq_checks=[_check(status="MET")], readiness="green",
        facts=StarterFacts(
            entity_name="Frost Bank",
            top_subcap_id="P4C2.1.1",
            top_subcap_name="Governed Reporting",
            top_score=2.2,
            metric_phrases=[],
            peer_names=[],
        ),
    )
    # MET branch without a mined metric must still carry the score fact.
    assert "2.2" in out[1]
    assert "Frost Bank" in out[1]
    assert "2.2" in out[2] or "[E-" in out[2]


def test_v2_starters_without_facts_degrade_to_v1_templates() -> None:
    out = compose_conversation_starters(
        platform_name="Twilio", pillar="P2", fit_score=40.0,
        addressable_subcap_ids=["P2C3.1.1"],
        prereq_checks=[], readiness="amber",
        facts=None,
    )
    assert len(out) == 3
    # v1 template degradation — the raw "P2C3.1.1" code is cleansed out of the
    # rendered text; verify the v1 template shape + platform name instead.
    assert "P2C3.1.1" not in out[0]
    assert "Discovery" in out[0] and "Twilio" in out[0]


def test_v2_starters_empty_when_unanchorable() -> None:
    assert compose_conversation_starters(
        platform_name="Twilio", pillar="P2", fit_score=0.0,
        addressable_subcap_ids=[], prereq_checks=[], readiness="red",
        facts=_FACTS,
    ) == []
