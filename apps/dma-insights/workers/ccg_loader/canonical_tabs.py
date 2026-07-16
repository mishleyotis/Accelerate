"""The 25 canonical tabs that appear in every pillar workbook.

Source: §02 of `docs/reference/Zennify Capability Mapping Visualized Schema -
All 4 Pillars.html`. The names below are the *normalized* tab keys (the loader
trims whitespace and normalizes the P-prefix when matching). The schema HTML
shows the order; we lock it here so any drift fails the congruence audit.
"""
from __future__ import annotations

# (key, friendly_name, target_table)
# The `key` is the workbook tab name (after P-prefix normalization). The
# `target_table` is the ccg_* table that receives the rows.
CANONICAL_TABS: list[tuple[str, str, str | None]] = [
    ("1_Overview",                          "Pillar overview & roll-up counts",          "ccg_pillars"),
    ("2_Capability_Map",                    "Categories → L1 → sub-caps",                "ccg_subcaps"),
    ("3_Maturity_Scoring_Bands",            "M1..M5 narratives + features per sub-cap",  "ccg_maturity_descriptors"),
    ("4_L3_Platforms_Reference",            "L3 platform reference",                     "ccg_l3_platforms"),
    ("5_L4_Features",                       "L4 feature matrix",                         "ccg_l4_features"),
    ("6_User_Stories",                      "User stories per sub-cap",                  "ccg_user_stories"),
    ("7_Product_Catalog",                   "Vendor product catalogue",                  "ccg_product_catalog"),
    ("8_Agentforce_Agents",                 "Agentforce / FM agent registry",            "ccg_agentforce_agents"),
    ("9_Platform_Constructs",               "Platform constructs (flow, LWC, etc.)",     "ccg_platform_constructs"),
    ("10_Productized_Offerings",            "Zennify productized offerings",             "ccg_productized_offerings"),
    ("11_Data_Products",                    "Zennify data products",                     "ccg_data_products"),
    ("12_Offering_SubCap_Matrix",           "Offering ↔ sub-cap mapping",                "ccg_offering_subcap_matrix"),
    ("13_DataProduct_SubCap_Matrix",        "Data product ↔ sub-cap mapping",            "ccg_dataproduct_subcap_matrix"),
    ("14_Cross_Pillar_Stories",             "Stories that touch multiple pillars",       "ccg_cross_pillar_stories"),
    ("15_Theme_SubCap_Mapping",             "Themes ↔ sub-caps",                         "ccg_theme_subcap_mapping"),
    ("16_SubCap_Cross_Pillar_Coverage",     "Sub-cap coverage across pillars",           "ccg_subcap_xpillar_coverage"),
    ("17_SubCap_Completeness",              "Per-subcap completeness scores",            "ccg_subcap_completeness"),
    ("18_Toggle_Cascade",                   "Inactive-toggle cascade analysis",          "ccg_toggle_cascade"),
    ("19_Subverticals",                     "9 sub-vertical codes (RB..IB)",             None),  # informational; seeded in 012
    ("20_QA_Gates",                         "Per-pillar QA gates",                       "ccg_qa_gates"),
    ("21_Value_Chain_Mapping",              "Value-chain stages per sub-cap x subvertical","ccg_vc_mapping"),
    ("22_Plan_Revisions",                   "Per-version plan revisions log",            "ccg_plan_revisions"),
    ("_R1_Source_Reference",                "Prior-version alias bridge (renames/splits)","ccg_subcap_aliases"),
    ("_R2_Dropped_Stories",                 "Stories dropped during this revision",      "ccg_dropped_stories"),
    ("_R3_P4_Specific_Backup",              "P4-only backup post CB12 (P4 workbook only)","__noop__"),
]


# ── Canonical-key → actual v7.0 workbook sheet-name aliases ────────────────
#
# The 2026-07 D3 audit root-caused "value chains 0/94": the loader looked for
# the schema-HTML tab names above, but the SHIPPED v7.0 workbooks
# (docs/reference/catalogue/v7.0/Pillar_{1..4}_Comprehensive_Capability_
# Mapping_v7.0.xlsx) drifted on 15 of the 25 canonical tabs — most fatally
# `21_Value_Chain_Mapping` shipping as `21_VC_Mapping_PerSubcap`, which was
# silently reported as `missing_tab` on every load, so ccg_vc_mapping stayed
# empty forever. This table was built by enumerating the REAL sheet names in
# all 4 committed workbooks (they are identical across pillars, +`_R3` on P4)
# and diffing against CANONICAL_TABS. Order matters: the first alias present
# in a workbook wins.
#
# `19_Subverticals` has NO alias on purpose — v7.0 workbooks don't ship it
# (the 9 codes are seeded by migration 012); its target is None anyway.
TAB_ALIASES: dict[str, tuple[str, ...]] = {
    "3_Maturity_Scoring_Bands":        ("6_Maturity_Descriptors",),
    "4_L3_Platforms_Reference":        ("4_L3_Detailed",),
    "5_L4_Features":                   ("5_L4_Detailed_Features",),
    "6_User_Stories":                  ("3_User_Stories_Catalogue",),
    "7_Product_Catalog":               ("7_Product_Catalogue",),
    "8_Agentforce_Agents":             ("8_Agentforce_Agents_List",),
    "9_Platform_Constructs":           ("9_Platform_Constructs_Library",),
    "14_Cross_Pillar_Stories":         ("14_CrossPillar_Stories",),
    "16_SubCap_Cross_Pillar_Coverage": ("16_SubCap_CrossPillar_Coverage",),
    "17_SubCap_Completeness":          ("18_SubCap_Completeness_Profile",),
    "18_Toggle_Cascade":               ("19_Toggle_Cascade_Simulation",
                                        "17_Toggle_Control_Panel"),
    "20_QA_Gates":                     ("Z1_QA_Gates", "20_Final_QA_Report"),
    "21_Value_Chain_Mapping":          ("21_VC_Mapping_PerSubcap",),
    "22_Plan_Revisions":               ("Z2_Plan_Revisions",),
}


def expected_tab_keys() -> set[str]:
    return {t[0] for t in CANONICAL_TABS}


def target_for(tab_key: str) -> str | None:
    for key, _, tgt in CANONICAL_TABS:
        if key == tab_key:
            return tgt
    return None


def resolve_sheet_name(tab_key: str, sheet_names: set[str]) -> str | None:
    """Resolve a canonical tab key to the ACTUAL sheet name in a workbook.

    Exact canonical name wins; otherwise the first present alias. Returns
    None when the workbook carries neither (the caller records
    ``missing_tab`` — informational, unless the tab is parser-registered,
    in which case the loader's zero-row gate applies)."""
    if tab_key in sheet_names:
        return tab_key
    for alias in TAB_ALIASES.get(tab_key, ()):
        if alias in sheet_names:
            return alias
    return None
