"""Stage 0.4 — load the capability catalogue into the 21 ccg_* tables.

Reads the four pillar workbooks (v7.0 shipped tab names), version-keys
every row, and loads under the migrate identity — the only writer the
catalogue has (role matrix §03). Re-running is idempotent per version:
each table's rows for the version are replaced in one transaction; a
version bump ADDS rows, existing runs keep their pinned version.

Usage:
  python -m ccg_loader --version v7.0 --dir /path/to/xlsx/
  (connection via LOCAL_DATABASE_URL, or the Cloud SQL connector envs)

Grain ids are derived from the Sub_Cap_ID itself (P1C2.3.4 → pillar P1,
category P1C2, capability P1C2.3): the id system IS the taxonomy (V7
schema §03). ccg_value_chains is derived from the VC mapping tab: one
chain per sub-vertical, stages ordered by first appearance over subcaps
sorted by id — deterministic and re-runnable.
"""
import argparse
import re
import sys
from pathlib import Path

import openpyxl

from .db import connect
from .parsers import (
    parse_alias_bridge, parse_capability_map, parse_constructs,
    parse_cross_pillar, parse_data_products, parse_dp_matrix,
    parse_l3, parse_l4, parse_maturity, parse_offering_matrix,
    parse_offerings, parse_products, parse_qa_gates, parse_agents,
    parse_completeness, parse_theme_mapping, parse_toggle_cascade,
    parse_user_stories, parse_vc_mapping,
)

PILLAR_RE = re.compile(r"Pillar[_ ](\d)")

# tab -> (parser, target table, columns)
TABS = {
    "2_Capability_Map": (parse_capability_map, "ccg_subcaps",
        ["subcap_id", "version", "capability_id", "category_id", "pillar_id",
         "name", "weight", "l3_platform_areas", "l4_features"]),
    "6_Maturity_Descriptors": (parse_maturity, "ccg_maturity_descriptors",
        ["version", "subcap_id", "band", "narrative", "features"]),
    "4_L3_Detailed": (parse_l3, "ccg_l3_platforms",
        ["version", "l3_id", "vendor", "platform_name", "category",
         "description", "setup_path", "prerequisites", "detailed_capabilities"]),
    "5_L4_Detailed_Features": (parse_l4, "ccg_l4_features",
        ["version", "subcap_id", "l3_id", "feature_name", "vendor",
         "feature_type", "customization_level", "reference_url"]),
    "3_User_Stories_Catalogue": (parse_user_stories, "ccg_user_stories",
        ["version", "story_key", "subcap_id", "source_type", "source_ref",
         "use_case_ids", "l4_features_used", "match_confidence"]),
    "7_Product_Catalogue": (parse_products, "ccg_products",
        ["version", "vendor", "product_name", "component_type",
         "l3_platform_area", "description", "source_type", "reference_url",
         "lob", "workflow", "status", "agent_id", "anchor_note"]),
    "8_Agentforce_Agents_List": (parse_agents, "ccg_agents",
        ["version", "agent_id", "agent_name", "lob", "workflow", "status",
         "source_type", "parent_l3", "description", "source_url", "usage_note"]),
    "9_Platform_Constructs_Library": (parse_constructs, "ccg_constructs",
        ["version", "construct_name", "vendor", "description", "syntax_hint",
         "docs_url", "used_in_l4_features", "top_subcap_ids"]),
    "10_Productized_Offerings": (parse_offerings, "ccg_offerings",
        ["version", "offering_id", "offering_name", "category", "wrap_around",
         "status", "overview", "industry_challenge", "outcomes",
         "core_capabilities", "tiers", "primary_vendors", "l3_platforms_used",
         "target_personas", "reference_url", "source_evidence",
         "source_doc_section"]),
    "11_Data_Products": (parse_data_products, "ccg_data_products",
        ["version", "module_id", "category", "module_name", "description",
         "typical_pairing", "validation_strength", "reference_url",
         "source_doc_section"]),
    "12_Offering_SubCap_Matrix": (parse_offering_matrix, "ccg_offering_subcap_matrix",
        ["version", "offering_id", "subcap_id", "mapping_rationale",
         "maturity_lift", "capabilities_addressing", "reference_url"]),
    "13_DataProduct_SubCap_Matrix": (parse_dp_matrix, "ccg_dataproduct_subcap_matrix",
        ["version", "module_id", "subcap_id", "mapping_rationale",
         "maturity_lift", "reference_url"]),
    "14_CrossPillar_Stories": (parse_cross_pillar, "ccg_cross_pillar_stories",
        ["version", "pillar_id", "story_key", "origin_pillar",
         "origin_subcap_id", "origin_l1_capability", "themes",
         "confidence_level", "story_title", "story_summary",
         "linked_subcap_ids", "linked_offerings", "source_reference"]),
    "15_Theme_SubCap_Mapping": (parse_theme_mapping, "ccg_theme_subcap_mapping",
        ["version", "theme", "subcap_id", "mapping_rationale", "reference_note"]),
    "18_SubCap_Completeness_Profile": (parse_completeness, "ccg_subcap_completeness",
        ["version", "subcap_id", "stories_count", "l4_count",
         "maturity_complete", "l3_count", "usecase_count", "offering_count",
         "mapped_offerings", "dataproduct_count", "mapped_dataproducts",
         "themes", "crosspillar_stories", "core_score", "extended_score",
         "total_score", "narrative"]),
    "19_Toggle_Cascade_Simulation": (parse_toggle_cascade, "ccg_toggle_cascade",
        ["version", "subcap_id", "user_stories_inactive", "l4_features_inactive",
         "maturity_rows_inactive", "l3_references_affected",
         "offering_mappings_inactive", "dataproduct_mappings_inactive",
         "theme_mappings_inactive", "coverage_rows_inactive",
         "xp_stories_partial", "xp_stories_inactive", "offerings_partial",
         "dataproducts_partial", "total_cascade_footprint", "cascade_severity"]),
    "21_VC_Mapping_PerSubcap": (parse_vc_mapping, "ccg_vc_mapping",
        ["version", "subcap_id", "subvertical_code", "value_chain_stages",
         "phase_categories", "coverage_note"]),
    "_R1_Source_Reference": (parse_alias_bridge, "ccg_aliases",
        ["from_subcap_id", "from_version", "to_subcap_id", "to_version", "reason"]),
    "Z1_QA_Gates": (parse_qa_gates, "ccg_qa_gates",
        ["version", "pillar_id", "gate_id", "category", "title", "status", "detail"]),
}
# Earlier catalogue generations name the same logical tabs differently
# (v5.0 uses the schema-HTML canonical names; v7.0 shipped with drift).
# First present name wins.
TAB_ALIASES: dict[str, tuple[str, ...]] = {
    "6_Maturity_Descriptors": ("3_Maturity_Scoring_Bands",),
    "4_L3_Detailed": ("4_L3_Platforms_Reference",),
    "5_L4_Detailed_Features": ("5_L4_Features",),
    "3_User_Stories_Catalogue": ("6_User_Stories",),
    "7_Product_Catalogue": ("7_Product_Catalog",),
    "8_Agentforce_Agents_List": ("8_Agentforce_Agents",),
    "9_Platform_Constructs_Library": ("9_Platform_Constructs",),
    "14_CrossPillar_Stories": ("14_Cross_Pillar_Stories",),
    "18_SubCap_Completeness_Profile": ("17_SubCap_Completeness",),
    "19_Toggle_Cascade_Simulation": ("18_Toggle_Cascade", "17_Toggle_Control_Panel"),
    "Z1_QA_Gates": ("20_QA_Gates",),
    "21_VC_Mapping_PerSubcap": ("21_Value_Chain_Mapping",),
}

# Tabs with no target table in the 21 (informational or superseded):
SKIPPED = ["1_Overview", "16_SubCap_CrossPillar_Coverage", "17_Toggle_Control_Panel",
           "20_Final_QA_Report", "Z2_Plan_Revisions", "_R2_Dropped_Stories",
           "_R3_P4_Specific_Backup"]

# Tables whose rows repeat identically across the four pillar workbooks;
# first occurrence wins on the natural key.
DEDUP_KEYS = {
    "ccg_l3_platforms": ("version", "l3_id"),
    "ccg_agents": ("version", "agent_id"),
    "ccg_constructs": ("version", "construct_name"),
    "ccg_products": ("version", "vendor", "product_name"),
    "ccg_offerings": ("version", "offering_id"),
    "ccg_data_products": ("version", "module_id"),
    "ccg_offering_subcap_matrix": ("version", "offering_id", "subcap_id"),
    "ccg_dataproduct_subcap_matrix": ("version", "module_id", "subcap_id"),
    "ccg_theme_subcap_mapping": ("version", "theme", "subcap_id"),
    "ccg_maturity_descriptors": ("version", "subcap_id", "band"),
    "ccg_user_stories": ("version", "story_key", "subcap_id"),
    "ccg_subcaps": ("subcap_id", "version"),
    "ccg_aliases": ("from_subcap_id", "from_version"),
    "ccg_vc_mapping": ("version", "subcap_id", "subvertical_code"),
    "ccg_subcap_completeness": ("version", "subcap_id"),
    "ccg_toggle_cascade": ("version", "subcap_id"),
    "ccg_qa_gates": ("version", "pillar_id", "gate_id"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--dir", required=True, help="directory holding the four pillar xlsx files")
    ap.add_argument("--make-current", action="store_true",
                    help="mark this version current (new runs pin to it). "
                         "Loading a HISTORICAL version (e.g. v5.0 behind v7.0) "
                         "must NOT pass this — existing runs keep their pinned "
                         "version and new runs stay on the newest catalogue.")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.xlsx"))
    if len(files) != 4:
        print(f"expected 4 pillar workbooks, found {len(files)}", file=sys.stderr)
        return 2

    collected: dict[str, list[dict]] = {t[1]: [] for t in TABS.values()}
    warnings: list[str] = []
    for path in files:
        m = PILLAR_RE.search(path.name)
        pillar_id = f"P{m.group(1)}" if m else "?"
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for tab, (parser, table, _) in TABS.items():
            actual = next((c for c in (tab, *TAB_ALIASES.get(tab, ())) if c in wb.sheetnames), None)
            if actual is None:
                warnings.append(f"{path.name}: missing tab {tab}")
                continue
            rows, warns = parser(wb[actual], args.version, pillar_id)
            collected[table].extend(rows)
            warnings.extend(f"{path.name}/{tab}: {w}" for w in warns)
        wb.close()
        print(f"parsed {path.name}")

    # Cross-workbook dedup on natural keys (first wins).
    for table, keycols in DEDUP_KEYS.items():
        seen, unique = set(), []
        for row in collected[table]:
            k = tuple(row.get(c) for c in keycols)
            if k in seen:
                continue
            seen.add(k)
            unique.append(row)
        dropped = len(collected[table]) - len(unique)
        if dropped:
            print(f"{table}: {dropped} duplicate rows across workbooks collapsed")
        collected[table] = unique

    # Derive ccg_value_chains from the mapping: one chain per sub-vertical,
    # stages ordered by first appearance over subcaps sorted by id.
    chains: list[dict] = []
    by_sv: dict[str, list] = {}
    for row in sorted(collected["ccg_vc_mapping"], key=lambda r: r["subcap_id"]):
        by_sv.setdefault(row["subvertical_code"], []).append(row)
    for sv, rows in sorted(by_sv.items()):
        order: list[str] = []
        for r in rows:
            for stage in r["value_chain_stages"]:
                if stage not in order:
                    order.append(stage)
        for i, stage in enumerate(order, 1):
            chains.append({"chain_id": f"VC-{sv}-{i:02d}", "version": args.version,
                           "sub_vertical": sv, "name": stage, "stage_order": i})

    conn = connect()
    try:
        cur = conn.cursor()
        # Replace this version's rows, all tables, one transaction.
        for table in list(collected) + ["ccg_value_chains"]:
            col = "to_version" if table == "ccg_aliases" else "version"
            cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (args.version,))
        for tab, (parser, table, cols) in TABS.items():
            rows = collected[table]
            if not rows:
                continue
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO {table} ({', '.join(c if c != 'window' else chr(34)+c+chr(34) for c in cols)}) VALUES ({placeholders})"
            for row in rows:
                cur.execute(sql, tuple(row.get(c) for c in cols))
            print(f"{table}: {len(rows)} rows")
        for c in chains:
            cur.execute(
                "INSERT INTO ccg_value_chains (chain_id, version, sub_vertical, name, stage_order) VALUES (%s,%s,%s,%s,%s)",
                (c["chain_id"], c["version"], c["sub_vertical"], c["name"], c["stage_order"]))
        print(f"ccg_value_chains: {len(chains)} stage rows")

        # The version row: counts computed from what was loaded, current
        # flag moved atomically (exactly one TRUE, by partial unique).
        cells = [r for r in collected["ccg_subcaps"]]
        categories = {r["category_id"] for r in cells}
        cur.execute("SELECT version FROM ccg_versions WHERE is_current")
        row = cur.fetchone()
        current_before = row[0] if row else None
        make_current = args.make_current or current_before in (None, args.version)
        if make_current:
            cur.execute("UPDATE ccg_versions SET is_current = NULL WHERE is_current")
        cur.execute("DELETE FROM ccg_versions WHERE version = %s", (args.version,))
        cur.execute(
            "INSERT INTO ccg_versions (version, loaded_at, cell_count, category_count, is_current) VALUES (%s, now(), %s, %s, %s)",
            (args.version, len(cells), len(categories), True if make_current else None))
        conn.commit()
        state = "current" if make_current else f"historical (current stays {current_before})"
        print(f"ccg_versions: {args.version} {state}, {len(cells)} cells, {len(categories)} categories")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for w in warnings[:20]:
        print("WARN:", w)
    if len(warnings) > 20:
        print(f"... and {len(warnings) - 20} more warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
