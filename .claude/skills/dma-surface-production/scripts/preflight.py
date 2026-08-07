#!/usr/bin/env python3
"""Print the checklist for starting or resuming a synthesis run.

    python scripts/preflight.py                 # the generic checklist
    python scripts/preflight.py --progress p.json   # against a saved get_run_progress

This does not call the connector — the session does that. It turns the response
into an ordered plan so nothing is re-synthesised that already passed.
"""
import argparse, json, sys

PAGES = ["heatmap", "overview", "insights", "platform", "context", "techstack"]
WHY = {
 "heatmap":   "first — the linkage every other page cites, and the coverage denominators",
 "overview":  "needs the coverage and tier figures that fall out of the heatmap work",
 "insights":  "cards are claims; the landscape counts must reconcile to the register",
 "platform":  "five sections share one recommendation id space — produce them together",
 "context":   "internal-only dashboard, but identity and citation are unchanged",
 "techstack": "one section, two surfaces, plus the detail sub-page",
}

CHECKLIST = [
 ("Orient",  "get_run_progress(run_id) and get_client_state(display_id). Never assume a "
             "run is fresh; staged work survives a dead session."),
 ("Claim",   "Exclusive lease. If refused, another session holds it — do not work in parallel."),
 ("Contract","get_page_contract(page) per page. Read the doc text; do not recall the shape."),
 ("Bundle",  "get_report_bundle(run_id) and get_capability_catalogue(run_id). Cell NAMES come "
             "from the catalogue, never from report prose."),
 ("Standing","Read 01-start-here/1-standing-clauses.md and 01-start-here/2-evidence.md before writing."),
 ("Shape",   "Write down the entity's sub-vertical, size tier, ownership and brand set. They "
             "decide which cells this run may serve, whether the workbook's peer cohort is a "
             "cohort, and which enrichment ladders can return anything. 01-start-here/6-entity-shape.md."),
 ("Thesis",  "After the heatmap, before the overview: one sentence naming the constraint, what "
             "it blocks, where the leverage is and what makes it timely. Every page instantiates it."),
 ("Produce", "Page by page, in the order below. Read the page pack first. Every served cell "
             "gets a synthesis — cited, inherited or declared, never silent."),
 ("Enrich",  "register_evidence BEFORE citing. The server allocates the id."),
 ("Check",   "scripts/check_payload.py locally before every submit; check_consistency.py "
             "--subvertical <CODE> before promotion."),
 ("Submit",  "Read the verdict literally. Repair the cause, not the symptom."),
 ("Promote", "promote_run once every page passes. All six or none."),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--progress", help="a saved get_run_progress response")
    a = ap.parse_args()

    print("\nDMA SURFACE PRODUCTION — PREFLIGHT\n" + "=" * 62)
    for i, (step, note) in enumerate(CHECKLIST, 1):
        print(f"\n{i:>2}. {step}\n    {note}")

    print("\n" + "=" * 62)
    if not a.progress:
        print("\nPAGE ORDER\n")
        for p in PAGES:
            print(f"  {p:<10} {WHY[p]}")
        print("\nRun again with --progress to turn a run's state into a plan.")
        return 0

    prog = json.load(open(a.progress, encoding="utf-8"))
    pages = prog.get("pages", prog)
    print(f"\nRUN STATE\n")
    todo, done = [], []
    for p in PAGES:
        st = (pages.get(p) or {}).get("status", "missing")
        n = (pages.get(p) or {}).get("reasons", 0)
        mark = {"pass": "PASS", "fail": "FAIL", "staged": "STAGED"}.get(st, "MISSING")
        print(f"  [{mark:7s}] {p:<10} " + (f"{n} blocking reason(s)" if n else ""))
        (done if st == "pass" else todo).append((p, st, n))

    print(f"\nPLAN\n")
    if not todo:
        print("  Every page passes. Call promote_run(run_id).")
        return 0
    for p, st, n in sorted(todo, key=lambda x: PAGES.index(x[0])):
        verb = "Repair" if st == "fail" else ("Re-check" if st == "staged" else "Produce")
        print(f"  {verb:<9} {p:<10} — {WHY[p]}")
    if done:
        print(f"\n  Do NOT re-synthesise: {', '.join(p for p, *_ in done)}")
        print("  They already pass. Re-promoting reuses their retained staging rows.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
