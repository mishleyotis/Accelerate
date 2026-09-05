#!/usr/bin/env python3
"""Generate the recording map AND the dual-source section map.

## The question this answers

Owner, 2026-09-03: "revise the agents to ensure each knows where to record on
each template while doing the assessment as well as how to submit the
findings concurrently to the mcp while going through the process such that
when the assessment is done, the client page is live on the app."

Owner, 2026-09-05, on the source of truth: "For some pages and cards on the
web app, the tabs on the scoring sheet would be useful. For others, the
report sections would be more useful; the source of truth should be both
reports and the workbook. The workbook is the primary source ... Ensure
proper coordination of this flow such that the tab contracts and the report
contracts get matched to the right web app resources."

An assessment agent writes into workbook TABS; a report agent writes report
SECTIONS; the connector accepts page SECTIONS. This walks all three and
writes the join, so a producer knows which resource feeds its work and when a
page becomes submittable.

Both halves are already declared in code and read WITHOUT a connector call:

    _TAB_TARGET            tab   -> the app section(s) it feeds   (worker parser)
    report_templates.feeds report -> the app section(s) it feeds  (report contract)
    get_page_contract      page  -> its sections, and which are required (offline
                                    over contracts_data.json — no live connector)

It writes two files, GENERATED, never hand-edited:

  references/tab_recording_map.json  tab-centric (what one tab feeds), the
                                     shape ship.py and the freeze gate read;
  references/section_sources.json    section-centric and DUAL-SOURCE (what
                                     feeds one app section, from the workbook
                                     AND the reports AND enrichment), the shape
                                     the converter and the agents read.

    gen_recording_map.py [--out-tabs P] [--out-sections P]

Run it after any change to `_TAB_TARGET`, a page contract, `report_templates`'
feeds, the enrichment register, or the served allowlist.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "apps" / "worker"))
sys.path.insert(0, str(REPO / "apps" / "mcp"))
sys.path.insert(0, str(REPO / "plugins" / "dma-insights" / "skills" / "dma-research"))

from dma_worker.workbook_parser import _TAB_TARGET          # noqa: E402
from dma_mcp.contracts import get_page_contract              # noqa: E402 (offline)

try:
    from engine import contract as C                         # noqa: E402
    WORKBOOK_CONTRACT = C.WORKBOOK_CONTRACT
    INGEST_ALIASES = dict(getattr(C, "INGEST_ALIASES", {}))
except Exception:                                            # pragma: no cover
    WORKBOOK_CONTRACT = "unknown"
    INGEST_ALIASES = {}

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")

TEMPLATES = REPO / "plugins" / "dma-insights" / "references" / "templates"
REPORT_TEMPLATES = TEMPLATES / "report_templates.json"
ENRICH_REGISTER = REPO / "packages" / "shared" / "enrichment_register.json"
SERVED_SECTIONS = REPO / "plugins" / "dma-insights" / "fixtures" / "served_sections.json"

#: Sections the app derives/join server-side; the agent submits the envelope
#: only. (H9 value chain; the C6 financial re-render is O8's own row.)
SERVER_SECTIONS = {"heatmap.value_chain"}

#: Sections that ARE argued from a challenged report section even where a
#: workbook tab also feeds a figure into them — so they route to the report
#: converter, not a raw tab projection. Everything else with a workbook tab is
#: `workbook`; the challenge already happened at the research layer, so these
#: are formatted, never re-synthesised.
REPORT_SHAPED = {
    "overview.exec_summary", "overview.findings", "overview.opportunity",
    "overview.why_now", "insights.insights",
    "platform.platform_story", "platform.roadmap", "platform.stairstep",
}

DOTTED = re.compile(r"^([a-z_]+)\.([a-z_]+)$")


def _targets(val) -> tuple[list[str], str]:
    """(list of dotted page.section ids, confidence) from a _TAB_TARGET value.
    A prose target names no single section and yields an empty list."""
    tgt = val[0] if isinstance(val, (tuple, list)) else val
    conf = (val[1] if isinstance(val, (tuple, list)) and len(val) > 1
            else "unstated")
    items = tgt if isinstance(tgt, (tuple, list)) else [tgt]
    dotted = [s for s in items if isinstance(s, str) and DOTTED.match(s)]
    return dotted, conf


def _records(val) -> str:
    tgt = val[0] if isinstance(val, (tuple, list)) else val
    if isinstance(tgt, (tuple, list)):
        return ", ".join(str(x) for x in tgt)
    return str(tgt)


def _contract_sections() -> dict[str, dict]:
    """{page.section: {required, surface_id}} read offline from the contract."""
    out = {}
    for p in PAGES:
        secs = get_page_contract(p).get("sections") or {}
        if not secs:
            raise SystemExit(f"{p}: contract unreadable — refusing to write a "
                             f"partial map")
        for name, meta in secs.items():
            m = meta if isinstance(meta, dict) else {}
            out[f"{p}.{name}"] = {
                "required": bool(m.get("required", True)),
                "surface_id": m.get("surface_id"),
            }
    return out


def _report_feeds() -> dict[str, list[str]]:
    """{page.section: [report.section_id, ...]} inverse of report_templates."""
    d = json.loads(REPORT_TEMPLATES.read_text(encoding="utf-8"))
    inv: dict[str, list[str]] = {}
    for rk, rv in d.get("reports", {}).items():
        for s in rv.get("sections", []) or []:
            for surf in s.get("feeds", []) or []:
                inv.setdefault(surf, []).append(f"{rk}.{s['id']}")
    return {k: sorted(v) for k, v in inv.items()}


def _enrichment_surfaces() -> dict[str, list[str]]:
    """{page.section: [source, ...]} from the enrichment register."""
    d = json.loads(ENRICH_REGISTER.read_text(encoding="utf-8"))
    out = {}
    for surf, meta in (d.get("surfaces") or {}).items():
        out[surf] = list((meta or {}).get("sources") or []) or ["ledger"]
    return out


def _served() -> tuple[set[str], set[str]]:
    """(served page.section set, excluded page.section set)."""
    d = json.loads(SERVED_SECTIONS.read_text(encoding="utf-8"))
    served, excluded = set(), set()
    for page, secs in (d.get("pages") or {}).items():
        for s in secs:
            served.add(f"{page}.{s}")
    for page, secs in (d.get("excluded") or {}).items():
        if page.startswith("_"):
            continue
        for s in secs:
            excluded.add(f"{page}.{s}")
    return served, excluded


def _disposition(sec, workbook_tabs, report_sections, enrichment) -> str:
    if sec in SERVER_SECTIONS:
        return "server"
    if workbook_tabs and sec not in REPORT_SHAPED:
        return "workbook"
    if enrichment and not workbook_tabs:
        return "enrichment"
    if report_sections:
        return "report"
    return "synthesis"


def build() -> tuple[dict, dict]:
    contract_secs = _contract_sections()
    report_feeds = _report_feeds()
    enrich = _enrichment_surfaces()
    served, excluded = _served()

    # ── tab-centric rows (backward-compatible tab_recording_map.json) ──
    tab_to_sections: dict[str, list[str]] = {}
    rows = []
    for tab, val in sorted(_TAB_TARGET.items()):
        dotted, conf = _targets(val)
        # keep only sections the contract actually declares
        secs = [s for s in dotted if s in contract_secs]
        tab_to_sections[tab] = secs
        primary = secs[0] if secs else None
        page = primary.split(".", 1)[0] if primary else None
        section = primary.split(".", 1)[1] if primary else None
        rows.append({
            "tab": tab,
            "records": _records(val),
            "confidence": conf,
            "page": page,
            "section": section,
            "sections": secs,
            "required": (contract_secs[primary]["required"] if primary else None),
        })

    by_section = {}
    for sec, meta in contract_secs.items():
        by_section[sec] = {
            "required": meta["required"],
            "fed_by_tabs": sorted(t for t, ss in tab_to_sections.items()
                                  if sec in ss),
        }

    tab_doc = {
        "_readme": [
            "GENERATED by scripts/gen_recording_map.py — do not hand-edit.",
            "",
            "Tab-centric: which workbook TAB feeds which page SECTION(s). A tab",
            "may feed more than one section (`sections` is the full list;",
            "`section` is the primary). `confidence` is `verified` where the",
            "binding was checked field-by-field against get_page_contract,",
            "`proposed` where read off the tab's shape, `not_client_facing`",
            "for a run-config or provenance tab. A row with page: null feeds no",
            "single client section (a worklist or a narrative thread).",
            "",
            "The DUAL-SOURCE view an agent reads to know what feeds ITS section",
            "— workbook tab AND report section AND enrichment — is the",
            "companion references/section_sources.json.",
            "",
            "Ship with: ship_page.py <run> all --sections DIR --incremental.",
        ],
        "workbook_contract": WORKBOOK_CONTRACT,
        "tabs": rows,
        "sections": by_section,
        "counts": {
            "tabs_the_app_reads": len(rows),
            "tabs_bound_to_a_page": sum(1 for r in rows if r["page"]),
            "tabs_bound_to_a_section": sum(1 for r in rows if r["section"]),
            "verified_bindings": sum(1 for r in rows
                                     if r["confidence"] == "verified"),
            "proposed_bindings": sum(1 for r in rows
                                     if r["confidence"] == "proposed"),
            "not_client_facing": sum(1 for r in rows
                                     if r["confidence"] == "not_client_facing"),
            "page_sections": len(by_section),
            "required_page_sections": sum(1 for v in by_section.values()
                                          if v["required"]),
        },
    }

    # ── section-centric dual-source map (section_sources.json) ──
    sections = {}
    for sec, meta in sorted(contract_secs.items()):
        wb_tabs = by_section[sec]["fed_by_tabs"]
        rep = report_feeds.get(sec, [])
        enr = enrich.get(sec, [])
        is_served = sec in served and sec not in excluded
        # confidence for the workbook binding: verified iff a verified tab feeds it
        confs = {r["confidence"] for r in rows if sec in r["sections"]}
        confidence = ("verified" if "verified" in confs
                      else "proposed" if confs else "none")
        sections[sec] = {
            "surface_id": meta["surface_id"],
            "required": meta["required"],
            "served": is_served,
            "disposition": _disposition(sec, wb_tabs, rep, enr),
            "workbook_tabs": wb_tabs,
            "report_sections": rep,
            "enrichment_sources": enr,
            "confidence": confidence,
        }

    served_required = [s for s, v in sections.items()
                       if v["required"] and v["served"]]
    # A served, required section with no producible source at all is the gap
    # this map exists to catch: not a workbook tab, not a report section, not
    # enrichment, and not deliberately server/synthesis.
    unsourced = [s for s in served_required
                 if not sections[s]["workbook_tabs"]
                 and not sections[s]["report_sections"]
                 and not sections[s]["enrichment_sources"]
                 and sections[s]["disposition"] not in ("server", "synthesis")]

    from collections import Counter
    disp_counts = Counter(v["disposition"] for v in sections.values())
    sec_doc = {
        "_readme": [
            "GENERATED by scripts/gen_recording_map.py — do not hand-edit.",
            "",
            "Section-centric and DUAL-SOURCE: for every app page SECTION, the",
            "workbook TAB(s), the report SECTION(s) and the enrichment source",
            "that feed it, plus a `disposition` naming how it is produced:",
            "  workbook   — deterministic projection of workbook tab(s);",
            "               formatted, never re-synthesised or re-challenged",
            "  report     — shaped from a challenged report section (+ figures);",
            "               formatted, never re-synthesised or re-challenged",
            "  enrichment — needs Clay/web enrichment registered as evidence",
            "               first, then a surface producer",
            "  synthesis  — genuinely new client-specific synthesis (a surface",
            "               producer writes it)",
            "  server     — joined/derived server-side; agent submits envelope",
            "The workbook is the PRIMARY source (owner 2026-09-05): a section",
            "with a workbook tab is `workbook` unless it is argued prose the",
            "reports own (REPORT_SHAPED in the generator).",
            "`served: false` marks a section produced but withheld from every",
            "audience by the redaction allowlist — never a client-facing gap.",
        ],
        "workbook_contract": WORKBOOK_CONTRACT,
        "ingest_aliases": INGEST_ALIASES,
        "sections": sections,
        "coverage": {
            "sections_total": len(sections),
            "served": sum(1 for v in sections.values() if v["served"]),
            "served_required": len(served_required),
            "served_required_unsourced": unsourced,
            "by_disposition": dict(sorted(disp_counts.items())),
        },
    }
    return tab_doc, sec_doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ref = REPO / "plugins" / "dma-insights" / "references"
    ap.add_argument("--out-tabs", type=Path, default=ref / "tab_recording_map.json")
    ap.add_argument("--out-sections", type=Path,
                    default=ref / "section_sources.json")
    # The connector serves section_sources.json as an MCP resource, so it is a
    # cross-service contract: written to packages/shared too (deploy.sh stages
    # that into the mcp image, exactly as contracts_data.json is), and the
    # freeze gate asserts the two copies are byte-identical.
    ap.add_argument("--out-shared", type=Path,
                    default=REPO / "packages" / "shared" / "section_sources.json")
    a = ap.parse_args(argv)

    tab_doc, sec_doc = build()
    a.out_tabs.parent.mkdir(parents=True, exist_ok=True)
    a.out_tabs.write_text(json.dumps(tab_doc, indent=1) + "\n", encoding="utf-8")
    sections_text = json.dumps(sec_doc, indent=1) + "\n"
    a.out_sections.write_text(sections_text, encoding="utf-8")
    a.out_shared.parent.mkdir(parents=True, exist_ok=True)
    a.out_shared.write_text(sections_text, encoding="utf-8")

    tc = tab_doc["counts"]
    sc = sec_doc["coverage"]
    print(f"wrote {a.out_tabs}")
    print(f"  {tc['tabs_the_app_reads']} tabs — "
          f"{tc['tabs_bound_to_a_section']} bound to a section, "
          f"{tc['verified_bindings']} verified, "
          f"{tc['proposed_bindings']} proposed")
    print(f"wrote {a.out_sections}")
    print(f"  {sc['sections_total']} sections, {sc['served']} served, "
          f"{sc['served_required']} served+required")
    print(f"  by disposition: {sc['by_disposition']}")
    if sc["served_required_unsourced"]:
        print("  UNSOURCED served+required sections (a real gap): "
              f"{', '.join(sc['served_required_unsourced'])}")
        return 1
    print("  every served+required section resolves to a source or a "
          "server/synthesis disposition")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
