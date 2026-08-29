#!/usr/bin/env python3
"""Live stress test of the research pipeline, end to end, on real toolkits.

    python3 plugins/dma-insights/scripts/stress_research_pipeline.py \
        --toolkits <dir with the four Pillar*_Scoring_Toolkit.xlsx> \
        --workdir  <scratch dir for the throwaway run>

Every stage runs through the same CLI the agents use, in the agents' own
order: binding refusal -> start -> kg build/verify/route -> orient card ->
fuse plan -> RRF -> the five volleys logged -> memory notes ->
consolidation (with a deliberately bad note that must BLOCK) ->
attributed synthesis -> self-challenge refusal -> independent challenge ->
honest floors-gate FAIL -> techscan vocabulary -> resume/binding ->
cleanup refusal -> assemble refusal -> watchdog. A stage passes when the
pipeline does the RIGHT thing — which for several stages is a refusal
with a named reason, not a success. 20/20 measured 2026-08-29 against the
production toolkits (CU: 690 subcaps, 6,182 DQs).

Pull the toolkits first: scripts/drive_fetch.py pull-toolkits --dest <dir>.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "skills" / "dma-research"
_ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
_ap.add_argument("--toolkits", required=True)
_ap.add_argument("--workdir", required=True)
_a = _ap.parse_args()
TOOLKITS = Path(_a.toolkits)
ROOT = Path(_a.workdir) / "stress-run"
RUN = "R-STRESS-1"
CAT = "P2C3"
RESULTS = []


def cli(*args, family=None, expect=0, quiet=True):
    cmd = [sys.executable, "-m",
           f"engine.{family}" if family else "engine.cli", *args]
    r = subprocess.run(cmd, cwd=ENGINE, capture_output=True, text=True)
    return r


def stage(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def jout(r):
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    # 1 · start refuses a filler rationale
    r = cli("start", "--run", RUN, "--root", str(ROOT), "--entity",
            "Stress Credit Union", "--entity-id", "stress-cu", "--sv", "CU",
            "--scope", "FULL", "--reference-date", "2026-08-29",
            "--mode", "PUBLIC", "--sv-basis", "tbd", "--mode-basis", "tbd")
    stage("start refuses filler binding rationale",
          r.returncode != 0 and "not a binding rationale" in (r.stderr + r.stdout),
          f"rc={r.returncode}")

    # 2 · start with a real binding
    r = cli("start", "--run", RUN, "--root", str(ROOT), "--entity",
            "Stress Credit Union", "--entity-id", "stress-cu", "--sv", "CU",
            "--scope", "FULL", "--reference-date", "2026-08-29",
            "--mode", "PUBLIC",
            "--sv-basis", "NCUA-chartered federal credit union; single retail LOB",
            "--mode-basis", "stress engagement grants public-only evidence review",
            "--lob-census", "retail deposits and consumer lending; RB rejected: no OCC charter")
    o = jout(r)
    stage("start binds CU FULL and echoes the binding",
          r.returncode == 0 and o.get("selected", 0) > 600
          and o.get("binding", {}).get("sv") == "CU",
          f"selected={o.get('selected')}")

    # 3 · kg build from the real toolkits
    r = cli("build", "--run", RUN, "--root", str(ROOT),
            "--toolkits", str(TOOLKITS), family="kg")
    o = jout(r)
    counts = o.get("counts", {})
    stage("kg build seeds the DQ bank from the four toolkits",
          r.returncode == 0 and counts.get("dqs", 0) > 5000
          and o.get("kg_checksum"),
          f"subcaps={counts.get('subcaps')} dqs={counts.get('dqs')} "
          f"primaries={counts.get('with_toolkit_primary')}")

    # 4 · kg verify (checksum anchors the bank)
    r = cli("verify", "--run", RUN, "--root", str(ROOT), family="kg")
    stage("kg verify matches the stored checksum", r.returncode == 0,
          (r.stdout or r.stderr).strip()[:100])

    # 5 · kg route for the category
    r = cli("route", "--run", RUN, "--root", str(ROOT), "--category", CAT,
            family="kg")
    o = jout(r)
    routed = o.get("categories", {}).get(CAT, {})
    stage("kg route hands the category its worklist",
          r.returncode == 0
          and routed.get("agent") == f"research-{CAT.lower()}-producer"
          and routed.get("dqs", 0) > 100,
          f"subcaps={len(routed.get('subcaps', []))} dqs={routed.get('dqs')} "
          f"deferred={routed.get('deferred')}")

    # 6 · orient serves a mode-filtered card
    r = cli("orient", "--run", RUN, "--root", str(ROOT), "--category", CAT)
    o = jout(r)
    card = o.get("next_card") or {}
    subcap = card.get("id")
    qs = card.get("questions") or []
    has_deferred_key = "deferred_questions" in card
    unbound = "{entity}" in json.dumps(card)
    facets = {q.get("facet") for q in qs}
    stage("orient card: bound entity, all nine facets, deferred visible",
          r.returncode == 0 and subcap and len(qs) == 9 and has_deferred_key
          and not unbound and "contradicts" in facets,
          f"subcap={subcap} questions={len(qs)} facets={len(facets)}")
    if not subcap:
        return summary()

    # 7 · fuse plan produces shaped queries
    r = cli("plan", "--run", RUN, "--root", str(ROOT), "--subcap", subcap,
            "--facet", "works", family="retrieval")
    o = jout(r)
    plans = o.get("queries") or o.get("plans") or []
    stage("fuse plan emits differently-shaped probes",
          r.returncode == 0 and len(plans) >= 2, f"queries={len(plans)}")

    # 8 · RRF fuses two ranked lists; BM25 abstains on noise
    fused_in = ROOT / "fuse.json"
    fused_in.write_text(json.dumps({
        "query": "digital account opening member onboarding credit union",
        "lists": [
            [{"url": "https://a.example/onboarding", "title": "Digital account opening at Stress CU", "snippet": "members open accounts online in minutes"},
             {"url": "https://b.example/press", "title": "Press", "snippet": "Stress CU launches digital onboarding"},
             {"url": "https://noise.example/cats", "title": "Cats", "snippet": "unrelated feline content"}],
            [{"url": "https://b.example/press?utm_source=x", "title": "Press", "snippet": "Stress CU launches digital onboarding"},
             {"url": "https://a.example/onboarding", "title": "Digital account opening", "snippet": "online account opening"}],
        ]}))
    r = cli("fuse", "--in", str(fused_in),
            "--query", "digital account opening member onboarding credit union",
            "--top", "5", family="retrieval")
    o = jout(r)
    ranked = o.get("ranked") or o.get("results") or []
    urls = [x.get("url") for x in ranked]
    noise_low = ("https://noise.example/cats" not in urls[:2]) if urls else False
    dedup = len([u for u in urls if u and "b.example" in u]) <= 1
    stage("RRF consensus + URL dedup + noise not on top",
          r.returncode == 0 and ranked and noise_low and dedup,
          f"top={urls[:3]}")

    # 9 · the five volleys are logged
    for facet, q in [("primary", "onboarding capability overview"),
                     ("works", "digital account opening live"),
                     ("fails", "account opening abandoned complaints outage"),
                     ("value", "onboarding completion rate minutes"),
                     ("contradicts", "manual paper account opening branch only"),
                     ("corroborates", "second source digital onboarding")]:
        r = cli("search", "--run", RUN, "--root", str(ROOT), "--subcap", subcap,
                "--facet", facet, "--query", q, "--hits", "5", "--kept", "2")
        if r.returncode != 0:
            stage(f"search log ({facet})", False, r.stderr[-200:])
            break
    else:
        stage("all volleys logged to the search ledger", True)

    # 10 · notes: evidence ×3, a contradiction, a lead, one deliberately bad
    def note(*args):
        return cli("note", "--run", RUN, "--root", str(ROOT),
                   "--category", CAT, "--subcap", subcap, *args, family="memory")
    good = ("Stress Credit Union launched digital account opening in Q2 2025 "
            "and reports members completing new accounts online in under ten minutes.")
    for i in range(3):
        r = note("--facet", "works", "--kind", "evidence",
                 "--claim", "digital onboarding live with measured completion",
                 "--excerpt", good + f" Restated at figure {i} in the annual report.",
                 "--url", f"https://stress.example/ar25#p{i}",
                 "--source-name", f"Annual Report 2025 p{i}",
                 "--tier", "T2", "--published", "2025-06-01")
        if r.returncode != 0:
            stage("memory note (evidence)", False, r.stderr[-200:]); break
    r1 = note("--facet", "contradicts", "--kind", "contradiction",
              "--claim", "branch-only opening still required for business accounts",
              "--excerpt", "Business membership accounts must be opened at a branch "
                           "with two forms of identification, per the 2025 member handbook.",
              "--url", "https://stress.example/handbook",
              "--source-name", "Member Handbook 2025", "--tier", "T2",
              "--published", "2025-01-15")
    r2 = note("--facet", "works", "--kind", "lead",
              "--claim", "vendor case study likely names the onboarding platform")
    r3 = note("--facet", "works", "--kind", "evidence",
              "--claim", "too short to register",
              "--excerpt", "too short",
              "--url", "https://stress.example/x",
              "--source-name", "X", "--tier", "T3")
    stage("notes land: evidence, contradiction, lead, and one bad note",
          all(x.returncode == 0 for x in (r1, r2, r3)))

    # 11 · consolidate: good notes register, the bad one BLOCKS with the reason
    r = cli("consolidate", "--run", RUN, "--root", str(ROOT), "--category", CAT,
            family="memory")
    o = jout(r)
    blocked = o.get("blocked", 0) if isinstance(o.get("blocked"), int) else len(o.get("blocked", []))
    consolidated = o.get("consolidated", 0) if isinstance(o.get("consolidated"), int) else len(o.get("consolidated", []))
    stage("consolidate registers through the refusals (bad note BLOCKED)",
          r.returncode == 0 and consolidated >= 4 and blocked >= 1,
          f"consolidated={consolidated} blocked={blocked}")

    # 12 · synthesis via CLI requires and records the actor
    eids = []
    wb_json = cli("orient", "--run", RUN, "--root", str(ROOT), "--category", CAT)
    sys.path.insert(0, str(ENGINE))
    from engine import runstate as RS  # noqa: PLC0415
    run_obj = RS.locate(RUN, ROOT)
    wb = run_obj.open()
    erows = wb.rows("Evidence_Detail")
    eids = [row.get("E_ID") or row.get("Evidence_ID") for row in erows][:2]
    rec = {
        "Dominant_Claim": "Stress CU runs digital account opening with measured completion.",
        "Claim_Label": "FACT",
        "What_We_Found": (f"Digital account opening launched Q2 2025 "
                          + " ".join(f"[{e}:F1]" for e in eids)
                          + " and members complete accounts online in under ten minutes; "
                            "business accounts remain branch-only per the 2025 handbook."),
        "Facet_Coverage": "works, value, contradicts",
        "DQ_Works": "Digital account opening live since Q2 2025 with completion under ten minutes.",
        "DQ_Fails": "NOT_RUN: no outage, complaint or abandonment artefact surfaced in the fails volley.",
        "DQ_Value": "Completion under ten minutes is the stated 2025 onboarding figure.",
        "DQ_Corroborates": "NOT_RUN: single primary source; corroboration volley returned no independent second.",
        "DQ_Contradicts": "Business membership accounts remain branch-only per the 2025 member handbook.",
        "Triangulation": "One primary source plus the handbook contradiction; labelled accordingly "
                         + " ".join(f"[{e}:F1]" for e in eids) + ".",
        "Ceiling_Reasoning": "Deployment with a measured figure but one source supports Building, not Competing.",
        "Why_It_Matters": "Onboarding is the acquisition funnel's first drop-off point for 2026 growth.",
        "DMA_Impact": "Holds the onboarding capability at Building pending corroboration.",
        "Ceiling_Band": "Building",
        "Uncertainty": 0.5,
        "Challenge_Verdict": "PASS",
    }
    rec_path = ROOT / "rec.json"
    rec_path.write_text(json.dumps(rec))
    r_no = cli("synthesise", "--run", RUN, "--root", str(ROOT),
               "--subcap", subcap, "--json", str(rec_path))
    r_yes = cli("synthesise", "--run", RUN, "--root", str(ROOT),
                "--subcap", subcap, "--json", str(rec_path),
                "--actor", f"research-{CAT.lower()}-producer")
    stage("synthesise refuses without --actor, records with it",
          r_no.returncode != 0 and "--actor" in r_no.stderr and r_yes.returncode == 0,
          (r_yes.stderr or r_yes.stdout).strip()[:120] if r_yes.returncode else "")

    # 13 · self-challenge refused; independent challenge lands
    from engine import contract as C, ledger as L  # noqa: PLC0415
    wb = run_obj.open()
    try:
        L.record_challenge(wb, subcap, verdict="PASS",
                           actor=f"research-{CAT.lower()}-producer",
                           dimensions={d: "PASS" for d in C.CHALLENGE_DIMENSIONS},
                           rationale="self", ceiling_band_delta="0")
        stage("self-challenge refused", False, "was accepted")
    except Exception as e:
        msg = str(e).lower()
        stage("self-challenge refused",
              "cannot also be its challenger" in msg or "self" in msg
              or "author" in msg, str(e)[:100])
    try:
        L.record_challenge(wb, subcap, verdict="PASS", actor="finding-challenger",
                           dimensions={d: "PASS" for d in C.CHALLENGE_DIMENSIONS},
                           rationale=("Primary source and the handbook contradiction both "
                                      "verified; band stops at Building on single-source."),
                           ceiling_band_delta="0")
        stage("independent challenge recorded", True)
    except Exception as e:
        stage("independent challenge recorded", False, str(e)[:150])

    # 14 · the floors gate FAILS honestly on an unfinished category
    r = cli("gate", "--run", RUN, "--root", str(ROOT), "--category", CAT,
            "--require-synthesis")
    o = jout(r)
    stage("floors gate FAILs the unfinished category and names blockers",
          r.returncode == 1 and o.get("gate") == "FAIL"
          and (o.get("blocking") or o.get("failures") or o.get("blocking_terms")),
          f"gate={o.get('gate')}")

    # 15 · techscan: vocabulary refusals + honest render
    r_bad = cli("record", "--run", RUN, "--root", str(ROOT), "--product",
                "nCino", "--vendor", "nCino", "--layer", "L2", "--status",
                "CONFIRMED", "--method", "public_document", "--basis", "named in AR",
                family="techscan")
    conf_args = ["record", "--run", RUN, "--root", str(ROOT), "--product",
                 "Alkami", "--vendor", "Alkami Technology", "--layer", "CUST",
                 "--status", "CONFIRMED", "--method", "public_document",
                 "--basis", "named in the 2025 annual report onboarding section",
                 "--subcap", subcap]
    for e in eids:
        conf_args += ["--evidence-id", e]
    r_conf = cli(*conf_args, family="techscan")
    r_abs = cli("record", "--run", RUN, "--root", str(ROOT), "--product",
                "Snowflake", "--vendor", "Snowflake", "--layer", "DATA",
                "--status", "ABSENT", "--method", "technographic_scan",
                "--basis", "targeted search across careers, engineering blog and "
                           "builtwith scan returned 0 hits 2023-2026",
                family="techscan")
    r_render = cli("render", "--run", RUN, "--root", str(ROOT), family="techscan")
    stage("techscan refuses L2, takes CONFIRMED-with-eids and laddered ABSENT, renders",
          r_bad.returncode != 0 and "L2" in (r_bad.stderr + r_bad.stdout)
          and r_conf.returncode == 0 and r_abs.returncode == 0
          and r_render.returncode == 0,
          f"bad_rc={r_bad.returncode} conf_rc={r_conf.returncode} "
          f"abs_rc={r_abs.returncode} render_rc={r_render.returncode} "
          f"{(r_conf.stderr or r_abs.stderr or r_render.stderr).strip()[:120]}")

    # 16 · resume knows the binding, the KG and the position
    r = cli("resume", "--run", RUN, "--root", str(ROOT))
    o = jout(r)
    stage("resume reports binding_stated, kg_built, mode",
          o.get("binding_stated") is True and o.get("kg_built") is True
          and o.get("evidence_mode") == "PUBLIC",
          f"binding_stated={o.get('binding_stated')} kg_built={o.get('kg_built')}")

    # 17 · memory cleanup refuses while BLOCKED work exists
    r = cli("cleanup", "--run", RUN, "--root", str(ROOT), "--apply",
            family="memory")
    stage("memory cleanup refuses while notes are BLOCKED",
          r.returncode != 0, (r.stderr or r.stdout).strip()[:140])

    # 18 · assemble package refuses the unshippable folder honestly
    r = cli("package", "--run", RUN, "--root", str(ROOT),
            "--out", str(ROOT / "pkg"), family="assemble")
    stage("assemble package refuses: deliverables missing, and says which",
          r.returncode != 0 and ("missing" in (r.stdout + r.stderr).lower()
                                 or "report" in (r.stdout + r.stderr).lower()),
          (r.stderr or r.stdout).strip()[:140])

    # 19 · the run watchdog states the run's condition
    r = cli("status", "--root", str(ROOT.parent))
    stage("status names the run state",
          r.returncode in (0, 1) and RUN in r.stdout,
          r.stdout.strip()[:160])

    return summary()


def summary():
    fails = [x for x in RESULTS if not x[1]]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} stages passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
