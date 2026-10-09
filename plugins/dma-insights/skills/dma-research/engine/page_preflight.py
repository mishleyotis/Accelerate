#!/usr/bin/env python3
"""The page gates, read against the WORKBOOK before any page agent runs.

    python3 -m engine.page_preflight check --run R --root DIR [--page techstack]
    python3 -m engine.page_preflight not-run --run R --root DIR \\
        --tool clay|vibe --reason '<why the technographic scan could not run>'

WHY THIS EXISTS (owner, 2026-10-07, First Tech): "isn't such enrichment
supposed to happen at prelim and be recorded in the scoring workbook to be
reused for later stages?" It is — and PRELIM signed off a technology baseline
of five web-found rows, because its gate counted rows per layer and nothing
else. The connector then refused the techstack page three times at PAGES_A
(ET-12: no machine technographic scan; CG-40: five products against a floor
of fifteen; CG-50: a product its own cited excerpt never names), thirty hours
and $570 later, in a resumed session that no longer held Clay or Vibe
Prospecting — so nothing could repair it. Every one of those verdicts was
knowable from the workbook at PRELIM.

So the page gates whose inputs live in the workbook are read HERE, from the
same facts, by three callers:

  * PRELIM's `tech_baseline` section will not close while `machine_scan`
    says MISSING — the scan runs in the stage that holds the connectors,
    and its readings are banked in the workbook for every later stage;
  * the driver runs `preflight` before PAGES_A / PAGES_B dispatch a single
    page agent, and stops with the exact repair instead of spending three
    page attempts to learn it;
  * a blocker whose repair needs a connector says so (`needs_connector`),
    so the driver can tell a person "resume in a session holding Clay and
    Vibe" rather than re-dispatching agents that cannot fix it.

The token rules below are the connector's CG-50 rules, copied rather than
imported (the engine ships without apps/mcp); a test holds the two equal.
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import re
import sys

#: The connector's techstack depth floor (apps/mcp DEPTH_FLOORS, CG-40).
TECHSTACK_FLOOR = 15

#: ET-12's scan tools, as the connector matches them. Vibe Prospecting is
#: Explorium's product; the Search_Log names it `vibe` or `explorium`.
_SCAN_TOOL = re.compile(r"clay|vibe|explorium", re.I)
_TECH_QUERY = re.compile(r"tech\s*stack|technograph|technolog", re.I)
#: A logged scan that could not run, or ran and found nothing, in the words
#: the outcome column already uses.
_NOT_RUN = re.compile(r"^\s*(NOT_RUN|EMPTY|REFUSED|FAILED|NO_SOURCE)\b", re.I)

# ── CG-50's token rules, verbatim from apps/mcp/dma_mcp/validation2.py ─────
_GENERIC_PRODUCT_TOKENS = frozenset("""
 cloud platform data suite service services manager management core system
 systems software solution solutions enterprise server edition online pro
 plus premium standard advanced engine hub studio center centre portal app
 apps application applications tool tools api gateway network security
 analytics intelligence experience digital banking finance financial
 customer marketing sales commerce for and the with next gen one
""".split())
_MIN_TOKEN = 3
_NAME_CHECK_EXEMPT_STATUS = frozenset({"ABSENT"})


def _distinctive_tokens(*names) -> list:
    out = []
    for name in names:
        for tok in re.split(r"[^A-Za-z0-9]+", str(name or "")):
            if len(tok) >= _MIN_TOKEN and tok.lower() not in _GENERIC_PRODUCT_TOKENS:
                out.append(tok)
    return out


def _name_phrases(*names) -> list:
    out = []
    for name in names:
        words = [w for w in re.split(r"[^A-Za-z0-9]+", str(name or "")) if w]
        if len(words) >= 2:
            out.append(" ".join(words).lower())
            if len(words) >= 3:
                out.append(" ".join(words[1:]).lower())
    return out


def _clean(v) -> str:
    return str(v or "").strip()


def _ids(v) -> list:
    return [x.strip() for x in re.split(r"[,;\s]+", _clean(v)) if x.strip()]


# ── ET-12: the register rests on a machine technographic scan ──────────────

def machine_scan(wb) -> dict:
    """SCANNED, DECLARED or MISSING — the workbook's answer to ET-12.

    SCANNED   a Tech_Register row cites connector-origin evidence from Clay
              or Vibe Prospecting (the reading the connector looks for).
    DECLARED  no such citation, but the Search_Log records a technographic
              attempt through BOTH Clay and Vibe whose outcome says it could
              not run or found nothing — the NOT_RUN the payload states in
              r_layer.probes_run.
    MISSING   neither: the scan was never run and never declared.
    """
    idx = wb.evidence_index()
    readings = []
    for r in wb.rows("Tech_Register"):
        for e in _ids(r.get("Evidence_IDs")):
            ev = idx.get(e) or {}
            if _clean(ev.get("Origin")).lower() == "connector" and _SCAN_TOOL.search(
                    f"{ev.get('Source_Name')} {ev.get('Access_Status')}"):
                readings.append(e)
    if readings:
        return {"state": "SCANNED", "evidence": sorted(set(readings)),
                "detail": f"{len(set(readings))} connector technographic reading(s) cited"}
    tried = {"clay": [], "vibe": []}
    for s in wb.rows("Search_Log"):
        tool = _clean(s.get("Tool")).lower()
        key = "clay" if tool == "clay" else ("vibe" if tool in ("vibe", "explorium") else None)
        if key and _TECH_QUERY.search(_clean(s.get("Query"))):
            tried[key].append(s)
    declared = {k: [s for s in v if _NOT_RUN.search(_clean(s.get("Outcome")))]
                for k, v in tried.items()}
    if declared["clay"] and declared["vibe"]:
        return {"state": "DECLARED", "evidence": [],
                "detail": "Clay and Vibe technographic scans recorded as not run / empty: "
                          + "; ".join(_clean(v[0].get("Outcome"))[:120]
                                      for v in declared.values())}
    missing = [k for k in ("clay", "vibe") if not tried[k]]
    return {"state": "MISSING", "evidence": [],
            "detail": ("no connector technographic reading is cited on any "
                       "Tech_Register row, and "
                       + (f"no technographic search through {' or '.join(missing)} "
                          f"is logged" if missing else
                          "the logged Clay/Vibe technographic searches neither "
                          "registered a reading nor recorded NOT_RUN"))}


# ── CG-50: every named product appears in the excerpt it cites ─────────────

def unnamed_products(wb) -> list:
    """Register rows whose cited excerpts never name the product or vendor."""
    idx = wb.evidence_index()
    out = []
    for r in wb.rows("Tech_Register"):
        if _clean(r.get("Status")).upper() in _NAME_CHECK_EXEMPT_STATUS:
            continue
        cited = _ids(r.get("Evidence_IDs"))
        if not cited:
            continue
        product, vendor = _clean(r.get("Product")), _clean(r.get("Vendor"))
        toks = _distinctive_tokens(product, vendor)
        phrases = _name_phrases(product, vendor)
        if not toks and not phrases:
            continue
        text = " ".join(_clean((idx.get(e) or {}).get("Excerpt")) for e in cited).lower()
        if any(t.lower() in text for t in toks) or any(p in text for p in phrases):
            continue
        out.append({"ts_id": _clean(r.get("TS_ID")), "product": product,
                    "cited": cited, "searched_for": toks or phrases})
    return out


# ── ET-07 for every page: a cited row resolves to the cells it supports ──

#: Sheets whose Evidence_IDs reach a page, and the page they reach. A row
#: cited from one of these with no SubCap_IDs is the ET-07 refusal the
#: connector gives one page at a time (B1 Bank, 2026-10-08/09: techstack x4,
#: overview x6, context x4 — "finding them page by page cost three separate
#: repair rounds").
#: Firmographics and Financial_Trends are NOT here: the connector's
#: `_IDENTITY_GRAIN` registry passes overview.firmographics and
#: overview.financial_series as evidence about the institution, not a
#: capability, and forcing a cell onto a call-report period file is the
#: misattribution ET-07 exists to reduce.
_CITING_SHEETS = {
    "Tech_Register": ("Evidence_IDs", "techstack"),
    "Entity_Timeline": ("Evidence_IDs", "context"),
    "Issue_Register": ("Evidence_IDs", "context"),
    "Focus_Areas": ("Evidence_IDs", "heatmap"),
    "Report_Narrative": ("Evidence_IDs", "overview"),
}
#: Sheets whose unlinked citations are REPORTED before the page agents run
#: but do not halt the stage: a timeline event is dated history whose cell
#: link the context producer states on the surface (the connector's
#: `_stated_unlinked` exception). Every other citing sheet reasons at cell
#: grain and the connector refuses it outright.
_ET07_ADVISORY_SHEETS = frozenset({"Entity_Timeline"})


#: PRELIM narrative sections whose citations are about the INSTITUTION, not
#: a capability — the connector's `_IDENTITY_GRAIN` exemption by section
#: (overview.firmographics / financial_series / leadership /
#: thought_leadership). A call report cited from the firmographics
#: narrative names no cell because it should not; linking it to one would
#: be the misattribution ET-07 exists to reduce.
_ET07_IDENTITY_SECTIONS = frozenset({"PRELIM-FIRM", "PRELIM-FIN", "PRELIM-LEAD",
                                     "PRELIM-THOUGHT"})


def unlinked_citations(wb, pages) -> dict:
    """{e_id: {page, cited_from}} for every cited row that names no cell."""
    idx = wb.evidence_index()
    out: dict = {}
    for sheet, (col, page) in _CITING_SHEETS.items():
        if page not in pages:
            continue
        for r in wb.rows(sheet):
            if sheet == "Report_Narrative" and \
                    _clean(r.get("Section_ID")).upper() in _ET07_IDENTITY_SECTIONS:
                continue
            for e in _ids(r.get(col)):
                e = e.split(":")[0]
                row = idx.get(e)
                if row is None or _ids(row.get("SubCap_IDs")):
                    continue
                slot = out.setdefault(e, {"page": page, "cited_from": []})
                label = sheet + ":" + _clean(r.get("TS_ID") or r.get("ID") or r.get("Title")
                                             or r.get("Section_ID") or r.get("Field")
                                             or r.get("Metric"))[:30]
                if label not in slot["cited_from"]:
                    slot["cited_from"].append(label)
    return out


#: The workbook floors behind the page gates that refused most often after
#: the techstack three (2026-10-05..09): O7 needs two named leaders, C1 three
#: dated events, O1 a locked peer set, H1 three focus areas with a quote.
_PAGE_FLOORS = (
    ("context", "Entity_Timeline", 3, "CG-14", "dated events on Entity_Timeline",
     "engine.prelim timeline --date … --event … --signal … [--evidence E-…]"),
    ("heatmap", "Focus_Areas", 3, "S9_focus_invalid", "focus areas with a verbatim quote",
     "engine.profile focus … (the PRELIM focus_areas section; a verbatim client quote per row)"),
    ("overview", "Peer_Benchmarks", 1, "CG-18c", "peer rows (a locked peer set)",
     "engine.prelim peers --peer … --basis …"),
)


def page_floors(wb, pages) -> list:
    out = []
    for page, sheet, need, gate, what, fix in _PAGE_FLOORS:
        if page not in pages:
            continue
        n = len([r for r in wb.rows(sheet) if any(str(v or "").strip() for v in r.values())])
        if n < need:
            out.append({"gate": gate, "page": page, "needs_connector": False,
                        "detail": f"{sheet} holds {n} row(s); the {page} page needs "
                                  f">= {need} {what}",
                        "fix": fix})
    return out


# ── the preflight ─────────────────────────────────────────────────────────

def preflight(wb, pages=("techstack",)) -> list:
    """The blockers, as {gate, page, detail, fix, needs_connector}."""
    out = []
    pages = tuple(pages or ())
    for e, u in sorted(unlinked_citations(wb, pages).items()):
        advisory = all(c.split(":")[0] in _ET07_ADVISORY_SHEETS for c in u["cited_from"])
        out.append({
            "gate": "ET-07", "page": u["page"], "needs_connector": False,
            "severity": "warn" if advisory else "block",
            "detail": (f"{e} is cited from {', '.join(u['cited_from'][:3])} and names no "
                       f"capability cell; the connector refuses the page (ET-07)"),
            "fix": (f"`engine.cli attach --e-id {e} --subcap <the cell it supports>` "
                    f"(or retire the citation); link every PRELIM and profile row "
                    f"before PAGES, not one page at a time")})
    out += page_floors(wb, pages)
    if "techstack" not in pages:
        return out
    rows = [r for r in wb.rows("Tech_Register") if _clean(r.get("TS_ID"))]
    scan = machine_scan(wb)
    if rows and scan["state"] == "MISSING":
        out.append({
            "gate": "ET-12", "page": "techstack", "needs_connector": True,
            "detail": scan["detail"],
            "fix": ("in a session holding Clay and Vibe Prospecting, run Clay's "
                    "company Tech Stack and Vibe's enrich-business technographics; "
                    "register each reading (origin connector, technographic, T1) and "
                    "cite it on the rows it detects (`engine.cli techscan record "
                    "--provider clay|explorium ...`). A scan that truly cannot run: "
                    "`engine.page_preflight not-run --tool clay|vibe --reason ...` "
                    "for BOTH tools")})
    live = [r for r in rows if _clean(r.get("Status")).upper() != "ABSENT"]
    if len(live) < TECHSTACK_FLOOR and scan["state"] == "MISSING":
        out.append({
            "gate": "CG-40", "page": "techstack", "needs_connector": True,
            "detail": (f"{len(live)} product(s) against the connector's floor of "
                       f"{TECHSTACK_FLOOR}, and no technographic scan behind the "
                       f"register to state the ladder that would excuse it"),
            "fix": ("the depth comes from the scan: run it (see ET-12) and record "
                    "what it detects; a register still short of the floor after a "
                    "real scan ships with its ladder and passes")})
    for u in unnamed_products(wb):
        out.append({
            "gate": "CG-50", "page": "techstack", "needs_connector": False,
            "detail": (f"{u['ts_id']} {u['product']!r} appears in none of its cited "
                       f"excerpt(s) {', '.join(u['cited'])} (searched for "
                       f"{u['searched_for']})"),
            "fix": (f"`engine.cli techscan restrike --ts {u['ts_id']} ... "
                    f"--evidence-id <an E-id whose excerpt names it>`, or mark the "
                    f"row INFERRED/ABSENT on what the evidence does say")})
    return out


def declare_not_run(wb, *, tool: str, reason: str) -> int:
    """Record that a technographic scan could not run — the NOT_RUN the
    payload states in r_layer.probes_run, banked in the Search_Log."""
    from . import ledger as L
    tool = _clean(tool).lower()
    if tool not in ("clay", "vibe", "explorium"):
        raise ValueError("tool must be clay or vibe")
    if len(_clean(reason)) < 30:
        raise ValueError("say why the scan could not run (>= 30 chars): a NOT_RUN "
                         "with no reason is silence with a label")
    name = ("Clay company Tech Stack" if tool == "clay"
            else "Vibe Prospecting enrich-business technographics")
    return L.append_search(wb, subcap=None, facet=None, prelim=True, tool=tool,
                           query=f"{name} (technographic scan)", hits=0, kept=0,
                           outcome=f"NOT_RUN: {_clean(reason)}")


def main(argv=None) -> int:
    from . import runstate
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "not-run"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        if name == "check":
            p.add_argument("--page", action="append")
        else:
            p.add_argument("--tool", required=True)
            p.add_argument("--reason", required=True)
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, a.root)
    wb = run.open()
    if a.cmd == "not-run":
        print(json.dumps({"seq": declare_not_run(wb, tool=a.tool, reason=a.reason)}))
        return 0
    out = preflight(wb, tuple(a.page or ("techstack",)))
    print(json.dumps({"scan": machine_scan(wb), "blockers": out}, indent=2))
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
