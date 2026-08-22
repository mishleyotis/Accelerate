#!/usr/bin/env python3
"""Cross-surface consistency check across a whole run, before promotion.

    python scripts/check_consistency.py run/            # dir of <page>.json
    python scripts/check_consistency.py run/ --strict

Each page passes its own submission independently, so a contradiction BETWEEN
pages survives every per-page gate. This is the check that catches it.
"""
from __future__ import annotations
import argparse, glob, json, os, re, sys

PAGES = ["overview","insights","heatmap","platform","context","techstack"]
BANDS = [(2.0,"Activating"),(3.0,"Building"),(4.0,"Competing"),(99.0,"Differentiating")]

# Codes that name exactly ONE sub-vertical. A T2 variant cell's terminal segment is a
# code plus an ordinal (P1C1.3.IC1); a base cell's is numeric. Family and product codes
# (BK, WM, PEN) are outside this set deliberately — they serve every entity.
SUBVERTICAL_CODES = {"RB","CU","CL","CIB","FC","AM","RIA","IC","IB"}
VARIANT = re.compile(r"^([A-Z]+)([0-9]+)$")

# Keys anywhere in a payload that hold a cell id, scalar or list.
CELL_KEYS = ("subcap_id","linked_subcap_id","anchor_subcap_id","named_gap_subcap_id",
             "linked_subcap_ids","capped_subcap_ids","involved_subcap_ids",
             "affected_subcap_ids","covered_subcap_ids","target_subcap_ids",
             "mapped_subcap_ids","addressable_cells","capability_ids","subcaps")

issues=[]
def bad(sev,label,msg): issues.append((sev,label,msg))

def variant_code(cell_id):
    """The sub-vertical a variant cell belongs to, or None for a base cell, a
    family/product code, or an unrecognised one. None never means 'belongs to no one'."""
    m = VARIANT.match(str(cell_id).rsplit(".",1)[-1])
    if not m: return None
    return m.group(1) if m.group(1) in SUBVERTICAL_CODES else None

def cells_cited(node, path=""):
    """Every cell id the payload cites, with the path that cites it."""
    out=[]
    for key in CELL_KEYS:
        for p,v in dig(node,key,path):
            for item in (v if isinstance(v,list) else [v]):
                if isinstance(item,str): out.append((p,item))
                elif isinstance(item,dict) and isinstance(item.get("subcap_id"),str):
                    out.append((p,item["subcap_id"]))
    return out

def band(s):
    if s is None: return None
    for hi,name in BANDS:
        if s < hi: return name
    return "Differentiating"

def dig(node, key, path=""):
    """Yield (path, value) for every occurrence of key anywhere in the tree."""
    if isinstance(node, dict):
        for k,v in node.items():
            p=f"{path}.{k}" if path else k
            if k==key: yield p,v
            yield from dig(v,key,p)
    elif isinstance(node, list):
        for i,v in enumerate(node): yield from dig(v,key,f"{path}[{i}]")

def num(x):
    try: return float(x)
    except (TypeError,ValueError): return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("rundir"); ap.add_argument("--strict",action="store_true")
    ap.add_argument("--subvertical",metavar="CODE",
                    help="the entity's sub-vertical code (RB CU CL CIB FC AM RIA IC IB). "
                         "Given, a cited variant cell belonging to another sub-vertical "
                         "blocks; omitted, a mixture is reported as a warning.")
    a=ap.parse_args()
    entity_sv=(a.subvertical or "").strip().upper() or None
    if entity_sv and entity_sv not in SUBVERTICAL_CODES:
        print(f"  unknown sub-vertical code {entity_sv!r} — expected one of "
              f"{' '.join(sorted(SUBVERTICAL_CODES))}"); return 2
    P={}
    for p in PAGES:
        f=os.path.join(a.rundir,f"{p}.json")
        if os.path.exists(f):
            try: P[p]=json.load(open(f,encoding="utf-8"))
            except Exception as e: bad("BLOCK",p,f"unreadable: {e}")
    missing=[p for p in PAGES if p not in P]
    if missing: bad("INFO","run",f"pages absent from this check: {', '.join(missing)}")
    print(f"\n  pages loaded: {', '.join(P) or 'none'}\n")

    # ── 1 · composite vs pillar means vs run history
    ov=P.get("overview",{}); hm=P.get("heatmap",{})
    sc=ov.get("scores",{})
    comp=num(sc.get("composite"))

    def pillar_entries(v):
        """The contract declares workbook_scores.pillars as an OBJECT MAP
        keyed by pillar id; overview.scores.pillars is a list. This checker
        read both as lists, so on every real payload it crashed on the map
        and has never completed a run on any client — a checker that has
        never run reads exactly like a checker that always passes. Accept
        both shapes; refuse neither for its spelling."""
        if isinstance(v, dict):
            return [{"pillar_id": pid, **entry}
                    for pid, entry in v.items() if isinstance(entry, dict)]
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        return []

    prows=pillar_entries(sc.get("pillars"))
    pill=[num(x.get("score")) for x in prows if num(x.get("score")) is not None]
    if comp is not None and len(pill)==4:
        # USER ADJUDICATION 2026-08-09: the workbook value governs, and the
        # drift gate compares against the WEIGHTED pillar mean — the
        # workbook's own operator (Run_Metadata weights; 2.759 for the run
        # that raised this) — or it fires on every correct run. The
        # unweighted mean is reported beside it, never the referee alone.
        flat=round(sum(pill)/4,4)
        weights=[num(x.get("weight")) for x in prows]
        cands={"unweighted mean": flat}
        if all(w is not None for w in weights) and abs(sum(weights)-1.0)<0.05:
            cands["weighted mean"]=round(sum(s*w for s,w in zip(pill,weights)),4)
        if not any(abs(v-comp)<=0.03 for v in cands.values()):
            shown=", ".join(f"{k} {v:.2f}" for k,v in cands.items())
            if "weighted mean" in cands:
                bad("BLOCK","O1 ↔ pillars",
                    f"composite {comp} agrees with no pillar rollup ({shown}, "
                    "tolerance 0.03) — including the weighted mean over the "
                    "payload's own weights, so this is drift, not an "
                    "operator difference.")
            else:
                # The one measured false alarm this check ever produced was
                # a BLOCK here: 2.76 against an unweighted 2.82, where the
                # workbook's WEIGHTED mean is 2.759 and the composite was
                # correct. The workbook value governs (user adjudication
                # 2026-08-09); without weights in the payload this checker
                # cannot compute the governing operator, so disagreement
                # with the flat mean alone is a question, never a verdict.
                bad("WARN","O1 ↔ pillars",
                    f"composite {comp} differs from the unweighted pillar "
                    f"mean ({shown}) and the payload carries no weights — "
                    "if the workbook states pillar weights this is likely "
                    "the weighted mean and correct; verify against "
                    "Run_Metadata rather than rewriting the composite.")
    elif comp is not None:
        bad("WARN","O1",f"composite present with {len(pill)} pillar scores — expected 4")

    # ── 2 · hero composite vs heatmap rollup
    ws=hm.get("workbook_scores",{})
    hp={x.get("pillar_id"):num(x.get("score")) for x in pillar_entries(ws.get("pillars"))}
    for x in prows:
        pid,s=x.get("pillar_id"),num(x.get("score"))
        if pid in hp and s is not None and hp[pid] is not None and abs(hp[pid]-s)>0.005:
            bad("BLOCK","O1 ↔ H4",f"{pid}: hero {s} vs grid {hp[pid]}")

    # ── 3 · band words vs raw scores
    for path,v in dig(ov,"posture"):
        if v=="LEADING" and comp is not None and comp<3.0:
            bad("WARN","O1 posture",
                f"posture LEADING beside a composite of {comp}, which bands as {band(comp)}. "
                "If the peer position justifies it, say so in the framing sentence.")
    if comp is not None:
        for path,v in dig(ov,"band"):
            if isinstance(v,str) and v!=band(comp):
                bad("BLOCK","O1 band",f"{path} says {v}; {comp} bands as {band(comp)}")
    for page,pay in P.items():
        for path,v in dig(pay,"synthesis"):
            if isinstance(v,str) and "transformational" in v.lower():
                bad("BLOCK",f"{page} band word",
                    f"{path} writes 'Transformational' — the resolver has four branches and "
                    "anything at or above 4.0 renders as Differentiating")

    # ── 4 · gap rows vs the served grid
    served={}
    for path,cells in dig(hm,"cells"):
        if isinstance(cells,list):
            for c in cells:
                if isinstance(c,dict) and c.get("subcap_id"): served[c["subcap_id"]]=num(c.get("score"))
    for path,rows in dig(P.get("platform",{}),"gaps"):
        if not isinstance(rows,list): continue
        for r in rows:
            if not isinstance(r,dict): continue
            sid,cur=r.get("subcap_id"),num(r.get("current_score"))
            if sid and cur is not None and sid in served and served[sid] is not None:
                if abs(served[sid]-cur)>0.05:
                    bad("BLOCK","P1 ↔ H2",f"{sid}: gap row {cur} vs served {served[sid]} (Δ>0.05)")
            if sid and sid not in served and served:
                bad("WARN","P1",f"gap row cites {sid}, which the heatmap payload does not serve")

    # ── 5 · roadmap rec ids resolve
    pl=P.get("platform",{})
    recs=set()
    for path,v in dig(pl,"rec_id"):
        if isinstance(v,str): recs.add(v)
    for path,v in dig(pl,"rec_ids"):
        if isinstance(v,list):
            for r in v:
                if isinstance(r,str) and r not in recs:
                    bad("BLOCK","P3 ↔ P2",f"{path} cites {r}, which no recommendation in the payload describes")

    # ── 6 · alerts vs thin cells
    thin={c["subcap_id"] for _,cells in dig(hm,"cells") if isinstance(cells,list)
          for c in cells if isinstance(c,dict) and c.get("thin") and c.get("subcap_id")}
    for path,al in dig(hm,"alerts"):
        if isinstance(al,list):
            for x in al:
                sid=x.get("subcap_id") if isinstance(x,dict) else None
                if sid and thin and sid not in thin:
                    bad("WARN","H3 ↔ H2",f"alert on {sid}, which the payload does not mark thin")

    # ── 7 · landscape counts reconcile to the register
    ts=P.get("techstack",{}).get("techstack",{})
    items=ts.get("items") or []
    if items:
        from collections import Counter
        cnt=Counter(i.get("status") for i in items if isinstance(i,dict))
        want={"CONFIRMED":cnt.get("CONFIRMED",0),"INFERRED":cnt.get("INFERRED",0),
              "CLAIMED":cnt.get("CLAIMED",0),"GAPS":cnt.get("ABSENT",0)}
        for path,tiles in dig(P.get("insights",{}),"tiles"):
            if not isinstance(tiles,list): continue
            for t in tiles:
                if isinstance(t,dict) and t.get("kind") in want:
                    got=num(t.get("count"))
                    if got is not None and int(got)!=want[t["kind"]]:
                        bad("BLOCK","T2 ↔ T1",
                            f"landscape {t['kind']} count {int(got)} but the register holds "
                            f"{want[t['kind']]} — recompute from the register, never store it")
        for i in items:
            if isinstance(i,dict) and not i.get("status"):
                bad("BLOCK","T1",f"{i.get('ts_id','item')} has no status — the strip is uncomputable without it")

    # ── 8 · O8 ↔ C6 financial series identity
    o8=ov.get("financial_series",{}).get("series")
    c6=P.get("context",{}).get("financial_series",{}).get("series")
    if o8 and c6 and o8!=c6:
        bad("BLOCK","O8 ↔ C6","the Context trajectory differs from the Overview series — "
            "C6 renders O8's section and cannot hold its own values")

    # ── 9 · confidence earned by evidence count
    for _,cells in dig(hm,"cells"):
        if not isinstance(cells,list): continue
        for c in cells:
            if not isinstance(c,dict): continue
            n=len(c.get("items") or []) or num(c.get("grounded_on")) or 0
            if str(c.get("confidence","")).upper()=="HIGH" and n and n<3:
                bad("WARN","H2 confidence",
                    f"{c.get('subcap_id')} is HIGH confidence on {int(n)} item(s) — confidence "
                    "is earned by the evidence count")

    # ── 10 · one constraint across pages
    def words(t): return set(re.findall(r"[a-z]{5,}", (t or "").lower()))
    fr=words(sc.get("framing"))
    fnd=P.get("overview",{}).get("findings",{}).get("findings") or []
    if fr and fnd and isinstance(fnd[0],dict):
        top=words(fnd[0].get("title"))
        if top and not (fr & top):
            bad("WARN","O1 ↔ O6",
                "the framing sentence and the top finding share no significant vocabulary — "
                "they should be about the same constraint, or the reader cannot tell what the "
                "meeting is about")

    # ── 11 · narrative thread present per page
    for page,pay in P.items():
        if not any(True for _ in dig(pay,"narrative_thread")):
            bad("WARN",page,"no narrative_thread — a page is not a container for surfaces")

    # ── 12 · sub-vertical scoping: the workbook scores cells this run may not serve
    cited={}                       # code -> [(page, path, cell_id), ...]
    for page,pay in P.items():
        for path,cid in cells_cited(pay):
            code=variant_code(cid)
            if code: cited.setdefault(code,[]).append((page,path,cid))
    if cited:
        shape=", ".join(f"{c}×{len(v)}" for c,v in sorted(cited.items()))
        if entity_sv:
            for code,rows in sorted(cited.items()):
                if code!=entity_sv:
                    ex="; ".join(f"{p}:{cid}" for p,_,cid in rows[:3])
                    bad("BLOCK","sub-vertical scope",
                        f"{len(rows)} cited cell(s) are {code} variants on a {entity_sv} run — "
                        f"they resolve in the workbook and render nowhere ({ex})")
        elif len(cited)>1:
            bad("WARN","sub-vertical scope",
                f"cited variant cells span more than one sub-vertical ({shape}). One of them "
                "is the entity's and the rest render nowhere — pass --subvertical to resolve")

    # ── 13 · every served cell opens a drawer that says something
    ce=hm.get("cell_evidence",{})
    rows=[c for _,cl in dig(ce,"cells") if isinstance(cl,list) for c in cl if isinstance(c,dict)]
    drawer={c["subcap_id"]:c for c in rows if isinstance(c.get("subcap_id"),str)}
    known=set(drawer)
    for key in ("subcap_scores","cells","subcaps"):
        for _,v in dig(hm,key):
            if isinstance(v,list):
                for c in v:
                    if isinstance(c,dict) and isinstance(c.get("subcap_id"),str) \
                       and num(c.get("score")) is not None:
                        known.add(c["subcap_id"])
    if known:
        silent=sorted(k for k in known if not str(drawer.get(k,{}).get("synthesis") or "").strip())
        if silent:
            bad("WARN","H2 coverage",
                f"{len(silent)} of {len(known)} served cell(s) carry no synthesis "
                f"({', '.join(silent[:5])}{' …' if len(silent)>5 else ''}). Every cell is "
                "clickable: cited, inherited or declared, but never silent")
    # a cell another surface sent the reader to must be cited grade
    elsewhere={}
    for page,pay in P.items():
        if page=="heatmap": continue
        for path,cid in cells_cited(pay): elsewhere.setdefault(cid,set()).add(page)
    for cid,pages in sorted(elsewhere.items()):
        if variant_code(cid) and entity_sv and variant_code(cid)!=entity_sv: continue
        d=drawer.get(cid)
        if d is None and known:
            bad("BLOCK","H2 ↔ pages",
                f"{cid} is cited on {', '.join(sorted(pages))} and has no cell_evidence row — "
                "the reader was sent to a drawer that says nothing")
        elif d is not None and not (d.get("e_ids") or d.get("items")):
            bad("WARN","H2 ↔ pages",
                f"{cid} is cited on {', '.join(sorted(pages))} but its drawer carries no "
                "evidence — a cell good enough to carry an argument elsewhere is cited grade here")

    # ── 14 · O10's denominator is the heatmap's cell set
    cov=ov.get("evidence_coverage",{})
    tot=sum(int(num(p.get("cells_total")) or 0) for p in (cov.get("per_pillar") or []))
    if tot and known and tot!=len(known):
        bad("BLOCK","O10 ↔ H2",
            f"coverage counts {tot} cells; the heatmap payload serves {len(known)}. Coverage is "
            "computed over the SAME cell set the grid renders, after sub-vertical scoping")

    # ── 15 · one constraint, five anchors
    anchors={}
    if fnd and isinstance(fnd[0],dict):
        anchors["top finding"]=f"{fnd[0].get('title','')} {fnd[0].get('consequence','')}"
    cards=P.get("insights",{}).get("insights",{}).get("cards") or []
    act=[c for c in cards if isinstance(c,dict)
         and str(c.get("severity","")).lower() in ("critical","high")] or \
        [c for c in cards if isinstance(c,dict)][:1]
    if act: anchors["act-now"]=" ".join(f"{c.get('title','')} {c.get('what_text','')}" for c in act[:2])
    ph=P.get("platform",{}).get("roadmap",{}).get("phases") or []
    if ph and isinstance(ph[0],dict):
        anchors["roadmap phase 1"]=f"{ph[0].get('phase','')} {ph[0].get('rationale','')}"
    story=P.get("context",{}).get("timeline",{}).get("storyline")
    if story: anchors["timeline storyline"]=story
    if fr and anchors:
        miss=[k for k,v in anchors.items() if not (fr & words(v))]
        for k in miss:
            bad("WARN","run thesis",
                f"the hero framing and the {k} share no significant vocabulary — the run's "
                "constraint should be recognisable at every anchor")
        if len(miss)>=3:
            bad("BLOCK","run thesis",
                f"{len(miss)} of {len(anchors)} anchors share no vocabulary with the framing "
                "sentence. Six coherent pages describing three assessments is the failure no "
                "per-page gate can see — write the thesis, then the pages")

    order={"BLOCK":0,"WARN":1,"INFO":2}
    issues.sort(key=lambda x:(order[x[0]],x[1]))
    b=sum(1 for s,*_ in issues if s=="BLOCK"); w=sum(1 for s,*_ in issues if s=="WARN")
    print(f"  blocking: {b}   warnings: {w}\n")
    for sev,label,msg in issues:
        print(f"  [{sev:5s}] {label}\n            {msg}")
    if not issues:
        print("  clean — the run reconciles across pages.")
    return 1 if b or (a.strict and w) else 0

if __name__=="__main__":
    sys.exit(main())
