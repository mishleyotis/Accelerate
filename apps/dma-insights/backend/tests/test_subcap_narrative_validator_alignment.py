"""Regression: `subcap_narrative_extractor.validate()` covers V1 + V2.

The grounding hard rule (CLAUDE.md "Hard rules") says:
> Do NOT serve un-validated Gemini output to AEs. Every surface runs
> the post-generation validator and falls back to template-fill on
> any flag.

The canonical implementation is `app.services.grounding_validator.validate_response`
with three flag families:
  V1 — cited E-IDs MUST be a subset of the retrieved bundle's E-IDs
  V2 — emitted subcap_ids MUST be a subset of the catalogue's real IDs
  V3 — content guards (token budget, response structure)

`app.services.parsers.subcap_narrative_extractor.validate()` uses an
INLINE validator instead -- documented as an exception in
`tests/test_grounding_no_bypass.py::_DOCUMENTED_EXCEPTIONS`. The
exception is only acceptable as long as the inline path covers V1 +
V2 at minimum. This test pins that contract:

  - A LLM response with a FABRICATED subcap_id ("P9C9.9.9" -- not in
    the catalogue we passed) must be stripped from the survivor list
    AND surfaced in `rejected_subcap_ids` (V2).
  - A LLM response with a FABRICATED evidence anchor ("E-9999" -- not
    in the bundle we passed) must be stripped from the survivor's
    `evidence_anchors` AND surfaced in `rejected_evidence_ids` (V1).
  - A clean response (every subcap_id + E-ID in the input sets) must
    survive untouched; rejected lists empty.
  - The omitted-evidence-ids-list state (valid_evidence_ids=None) is
    permitted -- V1 then short-circuits since the caller has no bundle
    to validate against (legitimate path when extractor is called for
    pre-flight structural validation, not citation-grounded synthesis).

If a future refactor of the inline validator drops V1 or V2 coverage,
this test fails loud and the grounding-no-bypass exception entry should
be removed from `_DOCUMENTED_EXCEPTIONS` too.
"""
from __future__ import annotations


def test_v2_fabricated_subcap_id_is_stripped() -> None:
    """LLM emits a subcap_id not in valid_subcap_ids -- validator must
    reject it AND surface the rejection in rejected_subcap_ids."""
    from app.services.parsers.subcap_narrative_extractor import validate

    raw = {
        "per_subcap_narrative": [
            {
                "subcap_id": "P1C1.1.1",  # real, kept
                "narrative_md": "real",
                "evidence_anchors": [],
            },
            {
                "subcap_id": "P9C9.9.9",  # fabricated, must be stripped
                "narrative_md": "fake",
                "evidence_anchors": [],
            },
        ],
    }
    kept, rejected_subs, _re = validate(
        raw=raw,
        valid_subcap_ids=["P1C1.1.1", "P1C1.1.2"],
        valid_evidence_ids=None,
    )
    kept_ids = {item.subcap_id for item in kept}
    assert "P1C1.1.1" in kept_ids, "real subcap_id must survive"
    assert "P9C9.9.9" not in kept_ids, (
        "V2 violation: fabricated subcap_id slipped past the inline "
        "validator -- the grounding-no-bypass exception entry for "
        "subcap_narrative_extractor is now unsafe"
    )
    assert "P9C9.9.9" in rejected_subs, (
        "V2 audit trail broken: fabricated subcap_id was dropped but "
        "not surfaced in rejected_subcap_ids -- the hallucination "
        "alert path can't fire without this"
    )


def test_v1_fabricated_evidence_anchor_is_stripped() -> None:
    """LLM emits an evidence_anchor E-ID not in valid_evidence_ids --
    validator must strip the anchor (keep the subcap, drop the
    fabricated E-ID) AND surface the rejection."""
    from app.services.parsers.subcap_narrative_extractor import validate

    raw = {
        "per_subcap_narrative": [
            {
                "subcap_id": "P1C1.1.1",
                "narrative_md": "real narrative",
                "evidence_anchors": ["E-001", "E-9999"],  # 9999 fabricated
            },
        ],
    }
    kept, _rs, rejected_eids = validate(
        raw=raw,
        valid_subcap_ids=["P1C1.1.1"],
        valid_evidence_ids=["E-001", "E-002", "E-003"],
    )
    assert len(kept) == 1, "subcap with a partial-fabrication should survive"
    survivor = kept[0]
    survivor_anchors = set(survivor.evidence_anchors or [])
    assert "E-001" in survivor_anchors, (
        "valid E-ID was wrongly stripped by the validator"
    )
    assert "E-9999" not in survivor_anchors, (
        "V1 violation: fabricated E-ID slipped past the inline "
        "validator -- citation-grounding contract is broken"
    )
    assert "E-9999" in rejected_eids, (
        "V1 audit trail broken: fabricated E-ID was dropped but not "
        "surfaced in rejected_evidence_ids"
    )


def test_clean_response_survives_untouched() -> None:
    """When every subcap_id + E-ID is in the input sets, the validator
    is a pure pass-through (defence: a stricter validator that
    over-strips would silently delete real grounding)."""
    from app.services.parsers.subcap_narrative_extractor import validate

    raw = {
        "per_subcap_narrative": [
            {
                "subcap_id": "P1C1.1.1",
                "narrative_md": "n1",
                "evidence_anchors": ["E-001"],
            },
            {
                "subcap_id": "P1C1.1.2",
                "narrative_md": "n2",
                "evidence_anchors": ["E-002", "E-003"],
            },
        ],
    }
    kept, rs, re_ = validate(
        raw=raw,
        valid_subcap_ids=["P1C1.1.1", "P1C1.1.2"],
        valid_evidence_ids=["E-001", "E-002", "E-003"],
    )
    assert len(kept) == 2
    assert rs == []
    assert re_ == []


def test_omitted_evidence_id_list_skips_v1() -> None:
    """When valid_evidence_ids is None the caller is using the
    extractor for pre-flight structural validation, not citation-
    grounded synthesis. Every anchor passes through untouched (V1
    short-circuits) but V2 must STILL fire."""
    from app.services.parsers.subcap_narrative_extractor import validate

    raw = {
        "per_subcap_narrative": [
            {
                "subcap_id": "P1C1.1.1",
                "narrative_md": "n",
                "evidence_anchors": ["E-001", "E-9999"],  # both pass through
            },
            {
                "subcap_id": "P9C9.9.9",  # V2: still stripped
                "narrative_md": "fake",
                "evidence_anchors": ["E-001"],
            },
        ],
    }
    kept, rejected_subs, rejected_eids = validate(
        raw=raw,
        valid_subcap_ids=["P1C1.1.1"],
        valid_evidence_ids=None,
    )
    survivor_subs = {item.subcap_id for item in kept}
    assert survivor_subs == {"P1C1.1.1"}, (
        "V2 must fire even when V1 is skipped"
    )
    assert "P9C9.9.9" in rejected_subs
    # V1 short-circuited -> rejected_eids stays empty
    assert rejected_eids == [], (
        "When valid_evidence_ids is None, V1 short-circuits and no "
        "E-ID is ever rejected by the inline path"
    )
