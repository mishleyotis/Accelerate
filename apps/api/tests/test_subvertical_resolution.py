"""The check that never ran, in the module whose whole job is the check.

`serves()` hides a T2 variant cell belonging to another sub-vertical. It needs
to know which sub-vertical the ENTITY is, and `resolve_subvertical` answers
that. It used to be an exact lookup of the entire normalised string:

    _ALIAS_INDEX.get(_norm(raw))

which resolves `"SV2"` and `"Credit Unions"` and almost nothing else. The form
an assessment manifest actually writes is COMPOUND — `"SV5 — RIAs &
Broker-Dealers (Canada)"`, `"SV1 — Regional Banks"` — and every one of those
returned None.

None is not a failure here. `serves()` treats it as "keep everything",
deliberately, because not knowing who you are is not grounds for hiding scores.
So the exclusion did not break loudly on those entities: it silently did
NOTHING, and an unscoped run is indistinguishable from a correctly scoped one
at every layer above it. `CHECK_NEVER_RAN_READS_AS_UNKNOWN`.

Measured across the 120 assessment manifests in the corpus: 61 distinct
spellings, 17 resolved. The live case is the second client, whose stated
sub-vertical is `"SV5 — RIAs & Broker-Dealers (Canada)"` — so nothing was ever
scoped for it, and ET-05 (the connector's citation gate, which reads the same
function) never fired for it either. The reference client only worked because
its directory row happens to carry the bare `"SV2"`.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import (resolve_subvertical, scope_status,  # noqa: E402
                                  serves, variant_subvertical)


# ── the forms that used to miss ───────────────────────────────────────
def test_the_compound_manifest_form_resolves():
    """Every one of these returned None before. The first is the live case."""
    assert resolve_subvertical("SV5 — RIAs & Broker-Dealers (Canada)") == "RIA"
    assert resolve_subvertical("SV1 — Regional Banks") == "RB"
    assert resolve_subvertical("SV2 — Credit Unions (Corporate CU sub-type)") == "CU"
    assert resolve_subvertical("SV3 - Commercial Lending") == "CL"
    assert resolve_subvertical("SV6 - Asset Management") == "AM"
    assert resolve_subvertical("SV7_Insurance_Brokers") == "IB"
    assert resolve_subvertical("SV-04 — Community Bank") is None  # SV4 vs RB


def test_the_forms_that_already_worked_still_do():
    assert resolve_subvertical("SV2") == "CU"
    assert resolve_subvertical("Credit Unions") == "CU"
    assert resolve_subvertical("RIAs & Broker-Dealers") == "RIA"
    assert resolve_subvertical("Insurance Brokerages") == "IB"


def test_label_only_and_parenthesised_code_forms():
    assert resolve_subvertical("Regional / Community Banks (RB)") == "RB"
    assert resolve_subvertical("Corporate Credit Union (CU)") == "CU"
    assert resolve_subvertical("Commercial Lending — Mortgage (CL)") == "CL"
    assert resolve_subvertical("Regional Bank") == "RB", "singular is a spelling"


# ── what must still refuse ────────────────────────────────────────────
def test_two_readings_that_disagree_resolve_to_neither():
    """A real corpus value names two sub-verticals. Taking whichever the code
    checked first would resolve a contradiction by ordering — the same mistake
    as averaging two disagreeing figures. Ambiguity keeps every cell, which is
    the safe direction."""
    assert resolve_subvertical("Insurance & Wealth — mutual/fraternal (IC/AM)") is None
    assert resolve_subvertical("Commercial Lending — Farm Credit (CL)") is None
    st = scope_status("Insurance & Wealth — mutual/fraternal (IC/AM)")
    assert st["scoped"] is False and "AM" in st["reason"] and "IC" in st["reason"]


def test_a_mis_keyed_or_placeholder_value_is_not_a_sub_vertical():
    """`'HIGH'` and `'TBD - Step 1.4'` are real corpus values — a confidence
    grade and a to-do that landed in a sub-vertical field."""
    for junk in ("HIGH", "TBD - Step 1.4", "Lending", "lending", "BL-IMB", ""):
        assert resolve_subvertical(junk) is None, junk
    assert resolve_subvertical(None) is None


def test_a_family_code_is_not_a_sub_vertical():
    """`WM` spans AM and RIA; resolving it to either would scope a run to half
    of what it is."""
    assert resolve_subvertical("WM (Wealth Management)") is None


def test_sv_tokens_are_bounded():
    """`SV12` must not read as SV1, and a bare digit must not read at all."""
    assert resolve_subvertical("SV12") is None
    assert resolve_subvertical("Tier 5 institution") is None
    assert resolve_subvertical("SV 5") == "RIA", "a space is still the token"
    assert resolve_subvertical("SV-04") == "CIB", "a hyphen and a zero too"


# ── the silence is now visible ────────────────────────────────────────
def test_scope_status_distinguishes_unscoped_from_fully_scoped():
    """The permissive fallback is right and it was INVISIBLE: a run serving
    every variant because it did not resolve looked exactly like one serving
    every variant because they all belong to it. Nothing branches on this; it
    reports, so an audit can tell them apart."""
    ok = scope_status("SV5 — RIAs & Broker-Dealers (Canada)")
    assert ok == {"scoped": True, "code": "RIA", "reason": None}
    bad = scope_status("HIGH")
    assert bad["scoped"] is False and bad["code"] is None
    assert "unrecognised" in bad["reason"] and "HIGH" in bad["reason"]
    assert "serves" in bad["reason"], "say what the consequence is"
    none = scope_status(None)
    assert none["scoped"] is False and "no sub-vertical" in none["reason"]


# ── and the rule it feeds still holds ─────────────────────────────────
def test_the_live_client_now_actually_excludes_foreign_variants():
    """End to end for the entity this was measured on: an RIA firm must hide
    the insurance-carrier and credit-union variants and keep its own."""
    code = resolve_subvertical("SV5 — RIAs & Broker-Dealers (Canada)")
    assert code == "RIA"
    assert serves("P2C4.6.RIA1", code) is True, "its own variant"
    assert serves("P1C1.3.2", code) is True, "a base cell always serves"
    assert serves("P1C2.7.BK1", code) is True, "a family code is not a claim"
    assert serves("P1C1.3.IC1", code) is False, "insurance carrier"
    assert serves("P1C1.3.CU1", code) is False, "credit union"
    assert variant_subvertical("P1C1.3.IC1") == "IC"


def test_an_unresolved_entity_still_keeps_everything():
    """The one-sided choice is deliberate and must not be tightened by
    accident: over-excluding hides a score the assessment actually made."""
    assert serves("P1C1.3.IC1", resolve_subvertical("HIGH")) is True
