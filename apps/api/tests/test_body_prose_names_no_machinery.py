"""The other half of the rule: prose inside an ALLOWED key in a section body.

MEM-0137's fix routed `empty_state` through the walker. Re-measuring
production afterwards left one match standing that the empty-state fix could
not reach: `heatmap.safeguard_gates.data.narrative_thread` naming SG-V4 in a
customer body. `narrative_thread` is an allowed key and its VALUE is where
the id sits, which is the case a key-grain allowlist structurally cannot see.

WHY DEFAULT-DENY WITH AN EXEMPTION, AND NOT A LIST OF PROSE KEYS. The first
design was to name the prose keys. Measured against the five promoted
clients' customer bodies there are 93 distinct keys holding a sentence —
`excerpt` 3,822 times, `source_title` 2,755, `synthesis` 2,435, `reach_note`
1,099, and a long tail. Any hand-written list of those is incomplete the day
it is written and drifts every time the contract grows a field.

So the rule is inverted to match invariant 5's own posture, and the exemption
list was measured rather than guessed. Across the INTERNAL bodies of all five
clients on all five pages — the widest population available — exactly three
keys ever hold a string matching the pattern:

    sources_searched   10 distinct   the empty_state ladder, already handled
    gate_id             2 distinct   SG-S8, SG-V4 — the exemption
    narrative_thread    1 distinct   SG-V4 — the leak

THE KEY IS DROPPED, NOT ITS PARENT, and this is the detail between a fix and
an outage. `internal_ids.scan` reports `gates[0].gate_id`; keying off the
first path segment would delete the whole `gates` array and empty
heatmap.safeguard_gates on every client.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api.redaction import (                    # noqa: E402
    _MACHINERY_EXEMPT_KEYS, _strip_machinery,
)


def safeguard_body():
    """heatmap.safeguard_gates as production serves it, trimmed."""
    return {
        "narrative_thread": ("SG-V4 abstained on this run because the cell "
                             "centroid held fewer than five members."),
        "gates": [
            {"gate_id": "SG-S8", "status": "FAIL",
             "plain_label": "Sentiment rests on a single source, so treat it "
                            "as indicative only"},
            {"gate_id": "SG-V4", "status": "NOT_RUN",
             "plain_label": "Grounding did not run on this run and no claim "
                            "rests on it"},
        ],
        "caps": [{"kind": "tier_ceiling", "reason": "Evidence ceiling applied "
                  "at tier two across this category."}],
    }


# ── the measured leak ─────────────────────────────────────────────────

def test_the_one_remaining_production_match_is_removed():
    body = safeguard_body()
    dropped = _strip_machinery(body)
    assert dropped == ["narrative_thread"]
    assert "SG-V4" not in json.dumps(body.get("narrative_thread"))
    assert "narrative_thread" not in body


def test_the_gates_array_survives_intact():
    """The outage this rule could have caused. `scan` reports
    `gates[0].gate_id`; keying off the first path segment deletes `gates`."""
    body = safeguard_body()
    _strip_machinery(body)
    assert len(body["gates"]) == 2
    assert [g["gate_id"] for g in body["gates"]] == ["SG-S8", "SG-V4"]
    assert all(g["plain_label"] for g in body["gates"]), \
        "the label is what a client actually reads and it must survive"


def test_the_exemption_is_the_measured_one_and_nothing_wider():
    assert _MACHINERY_EXEMPT_KEYS == frozenset({"gate_id", "gate"})


def test_gate_is_exempt_beside_gate_id():
    """The one renderer reads `g.gate_id || g.gate`, so both or neither."""
    body = {"gates": [{"gate": "SG-01"}]}
    assert _strip_machinery(body) == []
    assert body["gates"][0]["gate"] == "SG-01"


# ── prose that must survive ───────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "narrative_thread", "synthesis", "reason", "reach_note", "excerpt",
    "detection_basis", "peer_note", "rationale", "storyline",
])
def test_clean_prose_survives_in_every_prose_key(key):
    """No prose key is special. The rule is about the VALUE."""
    text = ("The bank published a statement describing the conversion of the "
            "acquired platform in under four months.")
    body = {key: text}
    assert _strip_machinery(body) == []
    assert body[key] == text


@pytest.mark.parametrize("prose", [
    "no regulatory gate applies to this institution",
    "the connector between the two core systems was retired in 2021",
    "staged for the next reporting cycle",
    "rated 4.3 over 4,262 ratings on the Android store",
])
def test_ordinary_english_is_not_machinery(prose):
    body = {"synthesis": prose}
    assert _strip_machinery(body) == [], prose
    assert body["synthesis"] == prose


# ── depth, and only the offending key ─────────────────────────────────

def test_a_nested_offender_takes_only_its_own_key():
    body = {"platforms": [
        {"name": "Salesforce", "estate_reach": "They already licence it.",
         "note": "See MEM-0081 for the internal reasoning."},
        {"name": "Snowflake", "estate_reach": "Nothing observed."},
    ]}
    dropped = _strip_machinery(body)
    assert dropped == ["platforms[0].note"]
    assert len(body["platforms"]) == 2
    assert body["platforms"][0]["name"] == "Salesforce"
    assert body["platforms"][0]["estate_reach"] == "They already licence it."
    assert "note" not in body["platforms"][0]
    assert body["platforms"][1] == {"name": "Snowflake",
                                    "estate_reach": "Nothing observed."}


def test_the_paths_reported_are_the_paths_removed():
    body = {"a": {"b": {"c": "get_evidence('platform') was called"}},
            "keep": "ordinary text"}
    assert _strip_machinery(body) == ["a.b.c"]
    assert body == {"a": {"b": {}}, "keep": "ordinary text"}


@pytest.mark.parametrize("token", ["MEM-0081", "REF-0069", "CG-49", "SG-V4",
                                   "CUSTOMER_WITHHELD", "get_page_contract("])
def test_every_pattern_class_is_caught_in_a_body(token):
    body = {"synthesis": f"Held pending {token} — see the note."}
    assert _strip_machinery(body) == ["synthesis"], token


# ── shapes that must not break it ─────────────────────────────────────

@pytest.mark.parametrize("value", [None, {}, [], "text", 3, True, 4.5])
def test_a_non_container_is_handled(value):
    assert _strip_machinery(value) == []


def test_a_body_with_nothing_to_strip_is_untouched():
    body = {"x": ["a", "b"], "y": {"z": "ordinary prose about the estate"}}
    before = json.loads(json.dumps(body))
    assert _strip_machinery(body) == []
    assert body == before


def test_a_non_string_value_is_never_dropped():
    """A gate id is a string; a count is not, and a number cannot name
    machinery however it is read."""
    body = {"detected": 7, "expected": 15, "thin": True, "score": None}
    assert _strip_machinery(body) == []
    assert body == {"detected": 7, "expected": 15, "thin": True, "score": None}


# ── it runs on the customer path, after the allowlist ─────────────────

def test_it_runs_for_the_customer_audience_after_the_allowlist():
    import inspect

    from dma_api import redaction
    src = inspect.getsource(redaction.redact_section)
    assert 'report["machinery_named"] = _strip_machinery(out)' in src
    assert src.index("_apply_allowlist(page, section, out)") < \
        src.index("_strip_machinery(out)"), \
        ("the allowlist decides which keys serve; this decides what the "
         "surviving ones may SAY, so it runs second")


def test_it_uses_the_shared_pattern():
    """CG-49 refuses at submit, this withholds at serve — one rule."""
    import inspect

    from dma_api import redaction
    src = inspect.getsource(redaction._strip_machinery)
    assert "internal_ids.names_machinery(value)" in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
