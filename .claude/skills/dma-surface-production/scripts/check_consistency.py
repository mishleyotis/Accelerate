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
issues=[]
def bad(sev,label,msg): issues.append((sev,label,msg))

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
    a=ap.parse_args()
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
    pill=[num(x.get("score")) for x in (sc.get("pillars") or []) if num(x.get("score")) is not None]
    if comp is not None and len(pill)==4:
        mean=round(sum(pill)/4,2)
        if abs(mean-comp)>0.005:
            bad("BLOCK","O1 ↔ pillars",
                f"composite {comp} but the mean of the four pillar means is {mean}. "
                "The composite is the mean of PILLAR means, not a flat mean over cells.")
    elif comp is not None:
        bad("WARN","O1",f"composite present with {len(pill)} pillar scores — expected 4")

    # ── 2 · hero composite vs heatmap rollup
    ws=hm.get("workbook_scores",{})
    hp={x.get("pillar_id"):num(x.get("score")) for x in (ws.get("pillars") or [])}
    for x in (sc.get("pillars") or []):
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
