#!/usr/bin/env python3
"""Print the Clay enrichment call sequence for one entity.

    python scripts/clay_plan.py --domain amalgamatedbank.com
    python scripts/clay_plan.py --domain x.com --gaps leadership,techstack

Enrichment is async and costs credits. This prints the standing budget for one
run and the tier each returned data point should be registered at.
"""
import argparse, sys

COMPANY_DP = [
 ("Tech Stack",       "T1", "T1 register. A machine technographic scan is T1, never T4 — "
                            "filing it at T4 caps the capability and suppresses the score."),
 ("Annual Revenue",   "T1-T2", "O2 firmographics"),
 ("Headcount Growth", "T2", "O2 firmographics, and a capability-trajectory signal"),
 ("Recent News",      "T3", "O3 why-now, C1 timeline, C5 acquisitions"),
 ("Open Jobs",        "T2-T3", "P1 readiness. Hiring is the cheapest capability signal there is."),
 ("Latest Funding",   "T1-T2", "O3 why-now, O8 financial context"),
]
CONTACT_DP = [
 ("Find Thought Leadership", "T2-T3", "O12. T2 for a first-party publication or named "
                                      "conference; T3 for trade press."),
 ("Summarize Work History",  "T3", "O7 tenure and trajectory"),
]
TITLES = ["Chief Executive","Chief Information","Chief Technology","Chief Operating",
          "Chief Risk","Chief Data","Chief Digital","Head of Technology","Head of Digital",
          "EVP","SVP Technology"]
EXCLUDE = ["Intern","Assistant","Coordinator"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--gaps", default="", help="comma-separated: leadership,techstack,thought,news")
    a = ap.parse_args()
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
    for n, _, _ in COMPANY_DP: print(f'    {{type:"{n}"}},')
    print("  ])\n")

    print("STEP 3 — leadership contacts")
    print(f'  find-and-enrich-contacts-at-company(companyIdentifier="{d}",')
    print( "    contactFilters={ job_title_keywords: [")
    for t in TITLES: print(f'      "{t}",')
    print( "    ], job_title_exclude_keywords: " + str(EXCLUDE) + " })  -> taskId2\n")
    print("  Compound titles stay ONE string. \"VP Finance\" is one keyword, not two.\n")

    print("STEP 4 — contact data points")
    print("  add-contact-data-points(taskId2, dataPoints=[")
    for n, _, _ in CONTACT_DP: print(f'    {{type:"{n}"}},')
    print("  ])\n")

    print("STEP 5 — POLL. Do not conclude.")
    print("  get-task-context(taskId) ; get-task-context(taskId2)")
    print("  NEVER record an absence from a Clay call without polling first. The search")
    print("  response carries base fields only — an empty panel written before the poll")
    print("  completed is an unfinished call rendered as a finding.\n")

    print("TIER MAP — register at these tiers, citing the SOURCE not the tool")
    print("="*70)
    for n, tier, why in COMPANY_DP + CONTACT_DP:
        print(f"  {n:<26} {tier:<7} {why}")

    if a.gaps:
        want = {g.strip().lower() for g in a.gaps.split(",")}
        print("\nTARGETED — only against a gap you have already tried to close by search")
        print("="*70)
        m = {"leadership":"Custom: board and executive committee membership",
             "techstack":"Custom: platform migrations announced in the last 24 months",
             "thought":"Custom: conference appearances and published bylines",
             "news":"Custom: regulatory filings and enforcement mentions"}
        for g in want:
            if g in m: print(f'  {{type:"Custom", customDataPoint:"{m[g]}"}}')
    print("\nOutside the budget above, ask. A DMA needs the leadership tier, not the org chart.\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
