#!/usr/bin/env python3
"""Print the Clay enrichment call sequence for one entity.

    python scripts/clay_plan.py --domain amalgamatedbank.com
    python scripts/clay_plan.py --domain x.com --gaps leadership,techstack
    python scripts/clay_plan.py --tier-table

Enrichment is async and costs credits. This prints the standing budget for one
run and the tier each returned data point should be registered at.

The data point -> surface -> tier mapping lives in 02-inputs/clay_taxonomy.json
— the single source this script and 02-inputs/2-clay-enrichment.md both render.
`--tier-table` emits the md's tier table so the two can never drift again.
"""
import argparse, json, sys
from pathlib import Path

TAXONOMY = Path(__file__).resolve().parent.parent / "02-inputs" / "clay_taxonomy.json"
TAX = json.loads(TAXONOMY.read_text(encoding="utf-8"))

COMPANY_DP = [d for d in TAX["data_points"] if d["route"] == "company"]
CONTACT_DP = [d for d in TAX["data_points"] if d["route"] == "contact"]
TITLES = TAX["job_title_keywords"]
EXCLUDE = TAX["job_title_exclude_keywords"]
GAPS = TAX["gaps"]


def _why(dp):
    # A conditional tier prints its condition: T1-T2-when-a-filing-is-behind-it
    # is the tier; T1-T2 alone overstates a modelled value.
    parts = [", ".join(dp["surfaces"])]
    if dp.get("tier_condition"):
        parts.append(f'{dp["tier"]} {dp["tier_condition"]}')
    if dp.get("note"):
        parts.append(dp["note"])
    return ". ".join(parts)


def tier_table_md():
    rows = ["| Data point | Tier | Why |", "|---|---|---|"]
    for dp in TAX["data_points"]:
        tier = f'**{dp["tier"]}**' if dp.get("emphasis") else dp["tier"]
        if dp.get("tier_condition"):
            tier += f' **{dp["tier_condition"]}**'
        rows.append(f'| `{dp["name"]}` | {tier} | {dp.get("note", "")} |')
    c = TAX["custom_rule"]
    head, _, rest = c["tier"].partition(" — ")
    tier = f"{head} — **{rest}**" if rest else head
    rows.append(f'| {c["name"].replace("Custom", "`Custom`")} | {tier} | {c["note"]} |')
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain")
    ap.add_argument("--gaps", default="",
                    help="comma-separated: " + ",".join(GAPS))
    ap.add_argument("--tier-table", action="store_true",
                    help="emit the md tier table rendered from clay_taxonomy.json")
    a = ap.parse_args()
    if a.tier_table:
        print(tier_table_md())
        return 0
    if not a.domain:
        ap.error("the following arguments are required: --domain")
    d = a.domain.strip().lower().replace("https://","").replace("www.","").rstrip("/")

    print(f"\nCLAY ENRICHMENT PLAN — {d}\n" + "="*70)
    print("\nRun this immediately after reading the bundle and BEFORE the heatmap page.")
    print("Enrichment is async; the pages that consume it come later.\n")

    print("STEP 1 — resolve the company")
    print(f'  find-and-enrich-company(companyIdentifier="{d}")  -> taskId\n')
    print("  The domain comes from 01_evidence/entity_profile/, never a guess. A wrong")
    print("  domain attaches a real company's data to the wrong entity.\n")

    print("STEP 2 — company data points, ONE call")
    print("  add-company-data-points(taskId, dataPoints=[")
    for dp in COMPANY_DP: print(f'    {{type:"{dp["name"]}"}},')
    print("  ])\n")

    print("STEP 3 — leadership contacts")
    print(f'  find-and-enrich-contacts-at-company(companyIdentifier="{d}",')
    print( "    contactFilters={ job_title_keywords: [")
    for t in TITLES: print(f'      "{t}",')
    print( "    ], job_title_exclude_keywords: " + str(EXCLUDE) + " })  -> taskId2\n")
    print("  Compound titles stay ONE string. \"VP Finance\" is one keyword, not two.\n")

    print("STEP 4 — contact data points")
    print("  add-contact-data-points(taskId2, dataPoints=[")
    for dp in CONTACT_DP: print(f'    {{type:"{dp["name"]}"}},')
    print("  ])\n")

    print("STEP 5 — POLL. Do not conclude.")
    print("  get-task-context(taskId) ; get-task-context(taskId2)")
    print("  NEVER record an absence from a Clay call without polling first. The search")
    print("  response carries base fields only — an empty panel written before the poll")
    print("  completed is an unfinished call rendered as a finding.\n")

    print("TIER MAP — register at these tiers, citing the SOURCE not the tool")
    print("="*70)
    for dp in COMPANY_DP + CONTACT_DP:
        print(f'  {dp["name"]:<26} {dp["tier"]:<7} {_why(dp)}')

    if a.gaps:
        want = {g.strip().lower() for g in a.gaps.split(",")}
        print("\nTARGETED — only against a gap you have already tried to close by search")
        print("="*70)
        # Taxonomy order, not set order: hash randomisation reordered these
        # lines on every invocation.
        for g in GAPS:
            if g in want: print(f'  {{type:"Custom", customDataPoint:"{GAPS[g]}"}}')
    print("\nOutside the budget above, ask. A DMA needs the leadership tier, not the org chart.\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
