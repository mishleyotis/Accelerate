"""Firmographics completeness contract + the regulator self-heal.

Two deploy-QA regressions this pins:

  1. The firmographics panel contract required `aum_usd IS NOT NULL` for EVERY
     active entity — wrong for a balance-sheet-less entity (Payments Canada is a
     member-funded payments utility with no AUM and no revenue line; its scale is
     headcount + transaction-volume highlights). The contract now accepts
     aum_usd OR revenue_usd OR headcount as the scale figure.

  2. heal_entity applies the subvertical-default `primary_regulator` from the DB
     subvertical ALONE — so it must fire even when the package can't be resolved
     (a name/layout mismatch must not leave the regulator NULL → a panel gap).
"""
from __future__ import annotations

import re

from app.services.completeness_contract import _SURFACE_GAP_SQL
from app.services.entity_healing import SUBVERTICAL_REGULATOR


def test_firmographics_contract_accepts_headcount_scale():
    sql = _SURFACE_GAP_SQL["firmographics"]
    # the scale clause must accept any of aum_usd / revenue_usd / headcount …
    assert "f.aum_usd IS NOT NULL" in sql
    assert "f.revenue_usd IS NOT NULL" in sql
    assert "f.headcount IS NOT NULL" in sql
    # … combined with OR (a balance-sheet-less entity passes on headcount) …
    scale = sql[sql.index("primary_regulator"):]
    assert " OR " in scale
    # … and the regulator is still mandatory.
    assert "primary_regulator" in sql and "<>''" in sql


def test_subvertical_regulator_covers_the_deploy_gap_classes():
    # The 5 entities that failed the deploy contract — their subverticals must all
    # resolve to a default regulator so heal_entity can fill the panel field.
    for sv in ("RB", "CL", "IB", "CIB", "AM", "CU", "RIA"):
        assert SUBVERTICAL_REGULATOR.get(sv)


def test_default_regulator_is_geography_aware():
    from app.services.entity_healing import _default_regulator
    # US default for a US entity …
    assert _default_regulator("RB", "Sunflower Bank, N.A.") == "FDIC"
    # … but a clearly-Canadian entity gets the Canadian framework, not US.
    ca = _default_regulator("CIB", "Payments Canada (The Canadian Payments Association)")
    assert "Canada" in ca and "Federal Reserve" not in ca
    assert _default_regulator("RB", "Some Canadian Bank") == "OSFI"
    # unknown subvertical → no fabricated regulator.
    assert _default_regulator("ZZ", "Whatever") is None
    assert _default_regulator(None, "Whatever") is None


def test_heal_entity_applies_regulator_before_package_guard():
    # The subvertical-default regulator fill must sit BEFORE the `pkg is None`
    # early return in heal_entity, so a package-resolution miss still fills the
    # regulator (the bug: the early return skipped the fallback entirely).
    import inspect

    from app.services import entity_healing
    src = inspect.getsource(entity_healing.heal_entity)
    reg_fill = src.index("_default_regulator(sv, name)")
    early_return = re.search(r"if pkg is None and not ext", src)
    assert early_return is not None, "early return should guard on `pkg is None and not ext`"
    assert reg_fill < early_return.start(), (
        "subvertical-default regulator must be applied before the pkg-None return"
    )


def test_heal_entity_classifies_subvertical_before_regulator_default():
    # THE deploy regression: the regulator default keys off the subvertical, so a
    # NULL subvertical must be CLASSIFIED before the regulator is computed — not
    # after. The old order (heal_all_stages classified AFTER heal_entity ran)
    # left every fresh-seed NULL-subvertical entity without a regulator →
    # `GAP firmographics: 5` on deploy. heal_entity now classifies first.
    import inspect

    from app.services import entity_healing
    src = inspect.getsource(entity_healing.heal_entity)
    classify = src.index("classify_subvertical(")
    set_sv = src.index("UPDATE entities SET subvertical")
    reg_fill = src.index("_default_regulator(sv, name)")
    # classify + persist the subvertical, THEN compute the regulator default.
    assert classify < reg_fill, "must classify the subvertical before the regulator default"
    assert set_sv < reg_fill, "must persist the classified subvertical before the regulator default"
    # heal_entity reports the resolved subvertical back to its callers so the
    # wave-8 gate can count classifications without re-doing the work.
    assert "subvertical_classified" in src and '"subvertical": sv' in src


def test_regulator_is_garbled_matches_the_deploy_failures():
    # THE second deploy regression (GAP firmographics: 5): the report parser
    # extracted a GARBLED regulator for 5 entities — a regex that ran off the
    # field end (unbalanced parens) or a sentinel — heal stored it (fill-if-
    # empty), the sanitize pass nulled it, and nothing re-filled it. These are
    # the VERIFIED strings from the deploy DB; the predicate must flag them.
    from app.services.startup_enrich import regulator_is_garbled
    garbled = [
        "State DOIs (NAIC-aligned, all 50 states via producer licenses +",  # OneDigital
        "State banking/mortgage regulators (via NMLS), CFPB (large",        # LoanDepot
        "Bank of Canada (FMI oversight under Payment Clearing and",         # Payments Canada
        "Role",                                                             # Sunflower (sentinel)
        "FDIC (state-",                                                     # truncated parenthetical
        "N/A", "Unknown", "{'regulator': 'FDIC'}",                          # sentinel + dict-repr
    ]
    for g in garbled:
        assert regulator_is_garbled(g), f"should flag garbled regulator: {g!r}"
    # …and must NOT flag well-formed regulators (incl. rich balanced-paren ones).
    clean = [
        "FDIC", "SEC", "NCUA", "State financial regulator / CFPB",
        "State Insurance Department (NAIC)", "Bank of Canada / OSFI",
        "FDIC (Cert 413), Federal Reserve (Fed ID 661308), NYSDFS",
    ]
    for c in clean:
        assert not regulator_is_garbled(c), f"should NOT flag clean regulator: {c!r}"
    assert regulator_is_garbled(None) is False  # non-str → not garbled


def test_sanitize_uses_the_shared_garble_predicate():
    # sanitize_firmographics and heal_entity must agree on what "garbled" means
    # (single source of truth), so a value heal keeps can never be one sanitize
    # would strip.
    import inspect

    from app.services import startup_enrich
    src = inspect.getsource(startup_enrich.sanitize_firmographics)
    assert "regulator_is_garbled(" in src, "sanitize must use the shared predicate"


def test_heal_entity_rejects_garbled_regulator_and_falls_back_to_default():
    # heal_entity must DROP a garbled extracted/current regulator and fall back
    # to the clean subvertical default — never store a value the sanitize pass
    # will later null (the deploy GAP firmographics regression).
    import inspect

    from app.services import entity_healing
    src = inspect.getsource(entity_healing.heal_entity)
    assert src.count("regulator_is_garbled(") >= 2, (
        "heal_entity must reject BOTH a garbled extracted regulator and a garbled "
        "current (parser-stored) regulator before the subvertical default applies"
    )
    drop_ext = src.index('ext.pop("primary_regulator"')
    default = src.index("_default_regulator(sv, name)")
    assert drop_ext < default, "garbled extracted regulator must be dropped before the default fills"


def test_heal_all_stages_no_longer_classifies_after_healing():
    # heal_all_stages must NOT carry its own classify-after-heal block any more
    # (that was the bug — it healed against the NULL subvertical first). The
    # classification now lives once, inside heal_entity, BEFORE the heal.
    import inspect

    from app.scripts import heal_all_stages
    src = inspect.getsource(heal_all_stages._amain)
    assert "classify_subvertical" not in src, (
        "heal_all_stages must delegate subvertical classification to heal_entity, "
        "not re-classify AFTER healing (the deploy GAP firmographics regression)"
    )
    # it counts classifications from heal_entity's report instead.
    assert "subvertical_classified" in src
