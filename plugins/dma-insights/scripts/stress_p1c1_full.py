#!/usr/bin/env python3
"""P1C1 to completion: every subcap researched, gated, reported, packaged,
then parsed by the app's own readers. The production shape, one category.

    python3 plugins/dma-insights/scripts/stress_p1c1_full.py \
        --toolkits <dir with the four Pillar*_Scoring_Toolkit.xlsx> \
        --workdir  <scratch dir for the throwaway run>

PASS criteria per stage are the pipeline's own: the floors gate must PASS
(not merely run), the validator must find 0 FAILS, both reports must
render — and must REFUSE an accusatory body first — the package must
verify, and the app-side parsers must keep every evidence linkage.
19/19 measured 2026-08-29 against the production toolkits (P1C1: 47
subcaps, 141 evidence items, 0 unURLed).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ENGINE = REPO / "plugins/dma-insights/skills/dma-research"
_ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
_ap.add_argument("--toolkits", required=True)
_ap.add_argument("--workdir", required=True)
_a = _ap.parse_args()
TOOLKITS = Path(_a.toolkits)
ROOT = Path(_a.workdir) / "p1c1-run"
RUN = "R-P1C1-FULL"
CAT = "P1C1"
RESULTS = []

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO / "apps" / "worker"))

from engine import contract as C, ledger as L, runstate, floors_gate  # noqa: E402
from engine import report_spec as RS, reports, memory as M  # noqa: E402


def stage(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def cli(*args, family=None):
    return subprocess.run(
        [sys.executable, "-m", f"engine.{family}" if family else "engine.cli",
         *args], cwd=ENGINE, capture_output=True, text=True)


def sha_dir(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(d).glob("*.xlsx"))}


def evidence_for(wb, sub, k):
    """Three UNIQUE sources per subcap; figures the synthesis will reuse."""
    name = sub.replace(".", " ")
    out = []
    for i in range(3):
        out.append(L.append_evidence(
            wb,
            source_name=f"{sub} source {i} — 2025 board review",
            source_url=f"https://stress.example/{sub.lower()}/doc{i}",
            tier="T2",
            excerpt=(f"The {name} programme at Stress Credit Union was stood "
                     f"up in Q2 2024; coverage was measured at {40+k} percent "
                     f"in the 2025 board review and restated at {41+k} "
                     f"percent later in 2025, item {i}."),
            subcaps=[sub], published="2025-06-01"))
    return out


def synthesis_for(sub, k, eids, *, contradiction=False):
    name = sub.replace(".", " ")
    cite = " ".join(f"[{e}:F1]" for e in eids[:2])
    rec = {
        "Dominant_Claim": (f"Stress Credit Union operates the {name} "
                           f"capability with board-reviewed coverage."),
        "Claim_Label": "FACT",
        "What_We_Found": (
            f"The {name} programme went live in Q2 2024 {cite} and the 2025 "
            f"board review measures coverage at {40+k} percent, restated at "
            f"{41+k} percent later in 2025. The review cadence is quarterly "
            f"and the figure is owned by a named executive sponsor."),
        "Facet_Coverage": "works, value, corroborates",
        "DQ_Works": (f"Live since Q2 2024 with coverage {40+k} percent per "
                     f"the 2025 board review {cite}."),
        "DQ_Fails": ("NOT_RUN: the fails volley surfaced no outage, "
                     "complaint or abandonment artefact for this capability."),
        "DQ_Value": (f"Coverage of {40+k} percent is reviewed quarterly and "
                     f"feeds the 2025 planning baseline."),
        "DQ_Corroborates": (f"A second board item restates the figure at "
                            f"{41+k} percent in 2025 {cite}."),
        "DQ_Contradicts": ("NOT_RUN: the contradicts volley surfaced no "
                           "disconfirming source for this capability."),
        "Triangulation": (f"Two independent board items agree on the launch "
                          f"window and the coverage figure {cite}."),
        "Ceiling_Reasoning": ("Deployment plus a measured, owned figure "
                              "supports Competing; a single review body "
                              "keeps it below Differentiating."),
        "Why_It_Matters": ("A measured coverage figure means the 2026 "
                           "programme can sequence on evidence rather than "
                           "assertion — the review cadence already exists "
                           "to carry it."),
        "DMA_Impact": ("Holds this capability at Competing on measured "
                       "utilisation; the corroborated figure is what a "
                       "peer-median comparison can anchor on."),
        "Ceiling_Band": "Competing",
        "Uncertainty": 0.3,
        "Challenge_Verdict": "PASS",
    }
    if contradiction:
        rec["DQ_Contradicts"] = (
            f"A 2025 member-forum thread reports the {name} portal "
            f"unavailable during the March maintenance window {cite}.")
        rec["Contradiction_Disposition"] = (
            "OPEN — the outage report is anecdotal against two board items; "
            "held open pending the INT-Q on incident logs.")
        rec["Facet_Coverage"] = "works, value, corroborates, contradicts"
    return rec


def main():
    t0 = time.time()
    if ROOT.exists():
        shutil.rmtree(ROOT)
    before = sha_dir(TOOLKITS)

    tax = C.taxonomy()
    cells = sorted(c for c in tax.selected("CU", "FULL")
                   if c.startswith(CAT + "."))
    run = runstate.start(
        run_id=RUN, entity_name="Stress Credit Union",
        entity_id="stress-cu", sub_vertical="CU", scope_mode="FULL",
        reference_date="2026-08-29", root=ROOT, selected=cells,
        evidence_mode="PUBLIC",
        sv_basis="NCUA-chartered federal credit union; single retail LOB",
        mode_basis="stress engagement grants public-only evidence review")
    stage("start: P1C1-only engagement seeded", len(cells) == 47,
          f"{len(cells)} cells")

    r = cli("build", "--run", RUN, "--root", str(ROOT),
            "--toolkits", str(TOOLKITS), family="kg")
    ok = r.returncode == 0
    stage("kg build over the P1C1 selection", ok,
          json.loads(r.stdout)["counts"].__repr__() if ok else r.stderr[-200:])

    stage("toolkits byte-identical after build (template never written)",
          sha_dir(TOOLKITS) == before)

    wb = run.open()
    wb.autosave = False

    # Subcap 1 goes through the MEMORY path — note, consolidate — exactly as
    # an agent works; the remaining 46 write through the ledger directly.
    first = cells[0]
    for i in range(3):
        M.note(run, category=CAT, subcap=first, facet="works",
               kind="evidence",
               claim=f"{first} live with measured coverage, item {i}",
               excerpt=(f"The {first.replace('.', ' ')} programme at "
                        f"Stress Credit Union was stood up in Q2 2024; "
                        f"coverage was measured at 40 percent in the "
                        f"2025 board review and restated at 41 percent "
                        f"later in 2025, item {i}."),
               url=f"https://stress.example/{first.lower()}/doc{i}",
               source_name=f"{first} source {i} — 2025 board review",
               tier="T2", published="2025-06-01")
    mem = M.consolidate(run, CAT)
    wb = run.open(); wb.autosave = False
    stage("memory path: 3 notes consolidated into Evidence_Detail",
          len([r_ for r_ in wb.rows("Evidence_Detail")
               if first in str(r_.get("SubCap_IDs"))]) == 3,
          json.dumps({k: (len(v) if isinstance(v, list) else v)
                      for k, v in mem.items()})[:120])

    volleys = [("primary", "capability overview"),
               ("works", "programme live measured"),
               ("fails", "outage complaint abandoned descoped"),
               ("value", "coverage percent board review"),
               ("contradicts", "portal unavailable incident regulator complaint"),
               ("corroborates", "independent second source restates figure")]
    n_ok = 0
    for k, sub in enumerate(cells):
        for facet, q in volleys:
            L.append_search(wb, subcap=sub, facet=facet,
                            query=f"\"Stress Credit Union\" {sub} {q}",
                            tool="web_search", hits=6, kept=2)
        eids = ([r_["E_ID"] for r_ in wb.rows("Evidence_Detail")
                 if first in str(r_.get("SubCap_IDs"))]
                if sub == first else evidence_for(wb, sub, k))
        rec = synthesis_for(sub, 0 if sub == first else k, eids,
                            contradiction=(k == 1))
        L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")
        L.record_challenge(
            wb, sub, verdict="PASS", actor="finding-challenger",
            dimensions={d: "PASS" for d in C.CHALLENGE_DIMENSIONS},
            rationale=("Launch window and coverage figure carried by two "
                       "independent board items; contradicts volley logged "
                       "and empty or held OPEN; ceiling stops at Competing."),
            ceiling_band_delta="0")
        n_ok += 1
    wb.save()
    stage("all 47 subcaps: volleys logged, evidence banked, synthesised, "
          "independently challenged", n_ok == 47, f"{n_ok}/47")

    wb.append("Entity_Timeline", {
        "Event_Date": "2024-06-01",
        "Title": "Digital programme go-live",
        "Kind": "PLATFORM", "Signal": "POSITIVE",
        "Signal": "EXPANSION", "SubCap_IDs": first, "Evidence_IDs": "E-0001"})
    wb.save()

    gate = floors_gate.run(wb, CAT, require_synthesis=True, qa_dir=run.qa_dir)
    stage("floors gate PASSES the finished category",
          gate.get("gate") == "PASS",
          json.dumps(gate)[:160] if gate.get("gate") != "PASS" else "")

    r = cli("validate", "--run", RUN, "--root", str(ROOT))
    stage("validator: 0 FAILS on the finished workbook", r.returncode == 0,
          (r.stdout + r.stderr).strip()[-160:] if r.returncode else "")

    r = cli("handoff", "--run", RUN, "--root", str(ROOT))
    stage("handoff builds and names the workbook as authority",
          r.returncode == 0, r.stderr[-160:] if r.returncode else "")

    # techscan: two detections + a laddered absence, rendered
    for a in (["record", "--run", RUN, "--root", str(ROOT), "--product",
               "Alkami", "--vendor", "Alkami Technology", "--layer", "CUST",
               "--status", "CONFIRMED", "--method", "public_document",
               "--basis", "named in the 2025 board review coverage item",
               "--subcap", first, "--evidence-id",
               wb.rows("Evidence_Detail")[0]["E_ID"]],
              ["record", "--run", RUN, "--root", str(ROOT), "--product",
               "Snowflake", "--vendor", "Snowflake", "--layer", "DATA",
               "--status", "ABSENT", "--method", "technographic_scan",
               "--basis", "careers, engineering blog and builtwith scan "
                          "returned 0 hits 2023-2026"]):
        rr = cli(*a, family="techscan")
        assert rr.returncode == 0, rr.stderr
    r = cli("render", "--run", RUN, "--root", str(ROOT), family="techscan")
    stage("techscan renders the fourth deliverable", r.returncode == 0,
          r.stderr[-120:] if r.returncode else "")

    # ── the P1C1 deep-dive write-up ───────────────────────────────────────
    wb = run.open(); wb.autosave = False
    all_eids = [r_["E_ID"] for r_ in wb.rows("Evidence_Detail")]

    def body(section_theme, i=0):
        e1, e2 = all_eids[(i * 2) % len(all_eids)], all_eids[(i * 2 + 1) % len(all_eids)]
        para = (
            f"{section_theme}. The P1C1 evidence base shows the digital "
            f"strategy programme live since Q2 2024 with coverage measured "
            f"at 40 percent in the 2025 board review and restated at 41 "
            f"percent later in 2025 [{e1}:F1]. The review cadence is "
            f"quarterly and each figure is owned by a named executive "
            f"sponsor [{e2}:F1]. Coverage at this level means the 2026 "
            f"programme can sequence on evidence rather than assertion; the "
            f"cadence that would carry a broader measurement already "
            f"exists, so extending it is an extension of working practice "
            f"rather than a new discipline. Where the volleys returned "
            f"nothing — no outage, complaint or abandonment artefact — the "
            f"absence is stated with the searches that establish it, and "
            f"the one member-forum contradiction is held OPEN against two "
            f"board items rather than resolved toward the friendlier "
            f"source. ")
        return para * 6

    for spec in RS.SPECS.values():
        for sec in spec.sections:
            n = RS.INSIGHT_CARD_MIN if sec.kind == "insight_card" else 1
            for i in range(n):
                wb.append("Report_Narrative", {
                    "Report": spec.key, "Section_ID": sec.id,
                    "Heading": (f"{sec.heading} {i+1}" if n > 1
                                else sec.heading),
                    "Body": body(sec.heading, i),
                    "Evidence_IDs": all_eids[i % len(all_eids)],
                    "Kind": sec.kind, "Author": "research-p1c1-producer",
                    "Written_At": "2026-08-29T00:00:00Z"}, save=False)
    wb.save()

    # First: the language gate must REFUSE an accusatory body, live.
    probe = ROOT / "probe.xlsx"
    shutil.copy(wb.path, probe)
    from engine.workbook import RunWorkbook
    pwb = RunWorkbook(probe)
    pwb.append("Report_Narrative", {
        "Report": "assessment", "Section_ID": "5",
        "Heading": "Findings extra",
        "Body": ("Leadership failed to invest and the data programme is "
                 "woefully behind its peers. " * 30) + f"[{all_eids[0]}]",
        "Evidence_IDs": all_eids[0], "Kind": "finding",
        "Author": "probe", "Written_At": "2026-08-29T00:00:00Z"})
    try:
        reports.render(pwb, RS.SPECS["assessment"], ROOT / "probe-out")
        stage("render REFUSES an accusatory finding body", False,
              "rendered anyway")
    except SystemExit as e:
        msg = str(e)
        stage("render REFUSES an accusatory finding body",
              "verdict about people" in msg or "opportunity" in msg,
              msg.splitlines()[-1][:140])

    rendered = []
    for spec in RS.SPECS.values():
        rendered.append(reports.render(wb, spec, run.deliverables))
    stage("both reports render from the clean narrative",
          all(x["path"].endswith(".docx") for x in rendered),
          "; ".join(Path(x["path"]).name for x in rendered))

    r = cli("package", "--run", RUN, "--root", str(ROOT),
            "--out", str(ROOT / "pkg"), family="assemble")
    stage("assemble package builds and verifies '<Entity> - DMA'",
          r.returncode == 0, (r.stdout + r.stderr).strip()[-200:])

    # ── the app-side parse ────────────────────────────────────────────────
    from dma_worker.classification import classify
    from dma_worker import workbook_parser as WP
    pkg_dirs = list((ROOT / "pkg").glob("* - DMA"))
    stage("package folder carries the client-DMA name shape",
          len(pkg_dirs) == 1, pkg_dirs[0].name if pkg_dirs else "none")
    pkg = pkg_dirs[0]
    files = sorted(p.name for p in pkg.rglob("*") if p.is_file())
    classified = {f: classify(f) for f in files}
    unclassified = [f for f, c in classified.items()
                    if c is None and f.endswith((".xlsx", ".docx", ".json"))
                    and "manifest" not in f]
    stage("every artefact in the package classifies",
          not unclassified, f"{len(files)} files; unclassified={unclassified}")

    wb_path = next(pkg.glob("DMA_Scoring_Workbook_*.xlsx"))
    obs = []
    parsed = WP.parse_research_workbook(str(wb_path), obs)
    ev = parsed.get("ledger") or []
    links = [x for x in parsed.get("links") or []
             if str(x.get("subcap_id") or "").startswith(CAT)]
    pairs = sum(len(x.get("e_ids") or []) for x in links)
    stage("app parses the workbook and keeps every P1C1 linkage",
          len(ev) >= 141 and len(links) == 47 and pairs >= 141,
          f"ledger={len(ev)} subcap_links={len(links)} e_id_pairs={pairs}")

    scoring = WP.parse_scoring_workbook(str(wb_path))
    srows = getattr(scoring, "rows", None) or getattr(scoring, "subcaps", [])
    toggled = [r_ for r_ in srows
               if "toggled_out" in str(getattr(r_, "status", "")
                                       or (r_.get("status") if isinstance(r_, dict) else ""))]
    stage("research-stage rows read as in-scope-unscored, never toggled_out",
          not toggled, f"rows={len(srows)} toggled_out={len(toggled)}")

    ts_json = next(pkg.rglob("technographic_scan.json"))
    ts_docx = next(pkg.rglob("Technographic_Scan_*.docx"))
    ts_obs = []
    n_det = WP.parse_technographic_scan(str(ts_json), ts_obs)
    summary = next((o for o in ts_obs
                    if o.kind == "technographic_scan_summary"), None)
    docx_obs = []
    WP.parse_technographic_scan(str(ts_docx), docx_obs)
    stage("techscan sidecar parses to a summary; docx-only is disclosed",
          n_det >= 2 and summary is not None
          and docx_obs and docx_obs[0].kind == "technographic_scan_docx_only",
          f"detections={n_det} "
          f"by_status={summary.detail.get('by_status') if summary else None}")

    # ── field-fill census ─────────────────────────────────────────────────
    rows = wb.scoring_rows()
    fill = {c_: sum(1 for r_ in rows if str(r_.get(c_) or "").strip())
            for c_ in C.PILLAR_COLUMNS}
    research_cols = ("Dominant_Claim", "Claim_Label", "What_We_Found",
                     "DQ_Works", "DQ_Fails", "DQ_Value", "DQ_Corroborates",
                     "DQ_Contradicts", "Triangulation", "Ceiling_Reasoning",
                     "Why_It_Matters", "DMA_Impact", "Ceiling_Band",
                     "Uncertainty", "Evidence_IDs", "Source_URLs",
                     "Challenge_Verdict", "Facet_Coverage", "Retrieved_At")
    assessment_cols = ("Score", "Confidence", "Caps_Applied", "Rationale")
    under = [c_ for c_ in research_cols if fill[c_] < len(rows)]
    leaked = [c_ for c_ in assessment_cols if fill[c_] > 0]
    stage("census: every research column filled on all 47 rows",
          not under, f"underfilled={under}")
    stage("census: assessment columns untouched (column D belongs to "
          "dma-assessment)", not leaked, f"leaked={leaked}")

    fails = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS)-len(fails)}/{len(RESULTS)} stages passed "
          f"in {time.time()-t0:.0f}s")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
