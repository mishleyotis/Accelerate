#!/usr/bin/env python3
"""Cross-surface consistency check across a whole run, before promotion.

    python scripts/check_consistency.py run/            # dir of <page>.json
    python scripts/check_consistency.py run/ --strict
    python scripts/check_consistency.py run/ --bundle bundle.json \
        [--catalogue catalogue.json] [--fit platform_fit.json]

Each page passes its own submission independently, so a contradiction BETWEEN
pages survives every per-page gate. This is the check that catches it.

The run directory holds `<page>.json` for each page and, by convention, the
tool output it reconciles against: `bundle.json` (get_report_bundle — the
sub-vertical BINDING, primary plus supplementary, and the peer set),
`catalogue.json` (get_capability_catalogue — the L3 areas per cell) and
`fit.json` (get_platform_fit — the engine's rows). Flags override the
convention. The binding is never typed (MEM-0559): `--supplementary` was a
second copy of it a producer could omit, and omitting it reproduced the
SWBC false block it was added to fix.

Checks 16-27 are the cross-section invariants the contracts name and nothing
executed until the SWBC gold audit (2026-10-04, RC-10 and RC-12): factor
arithmetic, O5 = P1 = engine, tile states, area tabs, the candidate set,
stair-step vs roadmap and platform order, one thin definition per payload,
H6 index completeness, leadership and findings counts, and the identified
peer set.
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

# ── tool output the run is reconciled against ────────────────────────────

def _load_tool_json(explicit, rundir, defaults):
    """A saved tool response: the explicit path, else the first default name
    present in the run directory. A `{"data": {...}}` wrapper (mcp_raw.py's
    shape for some tools) is unwrapped."""
    paths = [explicit] if explicit else [os.path.join(rundir, n) for n in defaults]
    for path in paths:
        if path and os.path.exists(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
            except Exception as e:
                bad("BLOCK", "inputs", f"{path} is unreadable: {e}")
                return {}
            if isinstance(d, dict) and isinstance(d.get("data"), (dict, list)) \
                    and not ({"sub_vertical", "platforms", "subcaps"} & set(d)):
                d = d["data"]
            return d if isinstance(d, (dict, list)) else {}
    return {}


def _connector_subverticals():
    """The connector's own sub-vertical module (apps/mcp/dma_mcp/subverticals.py),
    loaded by path so the checker and ET-05 read one rule (MEM-0559; the
    fix_hint it shares with MEM-0026/MEM-0032). None when no checkout is
    reachable — a plugin install without the repository — and the checker
    falls back to plain VC codes."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.environ.get("DMA_INSIGHTS_REPO"), os.environ.get("DMA_REPO"),
             os.environ.get("CLAUDE_PROJECT_DIR"),
             os.path.abspath(os.path.join(here, *[os.pardir] * 5)), os.getcwd()]
    for root in roots:
        if not root:
            continue
        path = os.path.join(root, "apps", "mcp", "dma_mcp", "subverticals.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("_dma_subverticals", path)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                return None
            return mod
    return None


def _binding(bundle, typed):
    """(primary code, supplementary codes, note) — read from the bundle."""
    sv = _connector_subverticals()

    def resolve(raw):
        if raw is None:
            return None
        if sv is not None:
            return sv.resolve_subvertical(raw)
        code = str(raw).strip().upper()
        return code if code in SUBVERTICAL_CODES else None

    if isinstance(bundle, dict) and ("sub_vertical" in bundle
                                     or "supplementary_sub_verticals" in bundle):
        primary = resolve(bundle.get("sub_vertical"))
        raw_supp = bundle.get("supplementary_sub_verticals")
        if sv is not None:
            supp = set(sv.resolve_supplementary(raw_supp, primary))
        else:
            supp = {resolve(x) for x in (raw_supp or [])} - {None, primary}
        if typed and primary and typed != primary:
            bad("BLOCK", "binding",
                f"--subvertical {typed} disagrees with the bundle's binding "
                f"({primary}) — the bundle is what the connector's ET-05 reads; "
                "fix the entity record or stop typing the code")
        note = (f"binding: {primary or 'unresolved'}"
                + (f"+{','.join(sorted(supp))}" if supp else "") + " (bundle)")
        return primary, supp, note
    if typed:
        bad("WARN", "binding",
            "no bundle in the run directory: the primary is the typed "
            f"--subvertical {typed} and the supplementary binding is unknown, so a "
            "supplementary variant cell will read as foreign (MEM-0559). Save "
            "get_report_bundle's output as bundle.json")
        return typed, set(), f"binding: {typed} (typed; supplementary unknown)"
    return None, set(), "binding unknown — no bundle.json and no --subvertical"


# ── 16-27 · cross-section invariants (SWBC gold audit 2026-10-04) ────────

_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_BAND_WORDS = ("Activating", "Building", "Competing", "Differentiating")
_TILE_STATES_SCORED = (None, "READY", "SCORABLE")


def _as_int(tok):
    tok = str(tok).lower()
    return int(tok) if tok.isdigit() else _NUMBER_WORDS.get(tok)


def _stated_counts(text, nouns):
    """Every '<number> <noun>' a sentence states, as (n, noun)."""
    out = []
    rx = re.compile(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(?:named\s+|"
                    r"senior\s+)?(" + "|".join(nouns) + r")\b", re.I)
    for m in rx.finditer(text or ""):
        n = _as_int(m.group(1))
        if n is not None:
            out.append((n, m.group(2).lower()))
    return out


def _key(name):
    """A platform or area key: the [L3-...] tag when present, else the
    lowercased name without punctuation."""
    s = str(name or "")
    m = re.search(r"\[(L3-[^\]]+)\]", s)
    if m:
        return m.group(1).upper()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tile_keys(t):
    keys = set()
    for f in ("l3_area", "platform", "name"):
        if t.get(f):
            keys.add(_key(t[f]))
            # the name half of "[L3-X] Name" also identifies the area
            rest = re.sub(r"\[[^\]]*\]", "", str(t[f])).strip()
            if rest:
                keys.add(_key(rest))
    return keys - {""}


def _tiles(P):
    ps = P.get("platform", {}).get("platform_story", {})
    return [t for t in (ps.get("platforms") or []) if isinstance(t, dict)], ps


def _factor_total(t):
    fs = [f for f in (t.get("factors") or []) if isinstance(f, dict)]
    vals = [num(f.get("contribution")) for f in fs]
    if not vals or any(v is None for v in vals):
        return None
    return sum(vals)


def _arith(label, name, t, stated):
    total = _factor_total(t)
    if total is None or stated is None:
        return
    rm = num(t.get("readiness_multiplier"))
    rel = num(t.get("relevance"))
    expected = total * 100 * (rm if rm is not None else 1.0) * (rel if rel is not None else 1.0)
    if abs(expected - stated) > 0.051:
        parts = f"factors sum to {total:.4f} → {total * 100:.1f}"
        parts += f" × readiness {rm:g}" if rm is not None else " × no readiness_multiplier"
        parts += f" × relevance {rel:g}" if rel is not None else ""
        bad("BLOCK", label,
            f"{name}: {parts} = {expected:.1f}, and the tile states {stated:g} "
            f"(Δ {abs(expected - stated):.1f}). The breakdown must equal the headline "
            "(O5/P1 contract). If a readiness multiplier applies, carry "
            "readiness_multiplier on the tile — the reader cannot see an r_layer "
            "(SWBC MuleSoft: 69.3 against 58.9, RC-12(a))")


def check_platform_arithmetic(P, fit):
    """16-17 · factor arithmetic; O5 tile = P1 tile = engine."""
    tiles, _ = _tiles(P)
    o5 = [t for t in (P.get("overview", {}).get("opportunity", {}).get("tiles") or [])
          if isinstance(t, dict)]
    for t in tiles:
        _arith("P1 arithmetic", t.get("platform"), t, num(t.get("fit_score")))
    for t in o5:
        _arith("O5 arithmetic", t.get("platform"), t,
               num(t.get("composite", t.get("fit_score"))))
    by_key = {}
    for t in tiles:
        for k in _tile_keys(t):
            by_key.setdefault(k, t)
    for t in o5:
        p1 = next((by_key[k] for k in _tile_keys(t) if k in by_key), None)
        if p1 is None:
            if tiles:
                bad("BLOCK", "O5 ↔ P1",
                    f"opportunity tile {t.get('platform')!r} has no platform_story tile — "
                    "O5 mirrors P1, same factors, same validations")
            continue
        diffs = []
        c, f = num(t.get("composite", t.get("fit_score"))), num(p1.get("fit_score"))
        if c is not None and f is not None and abs(c - f) > 0.051:
            diffs.append(f"composite {c:g} vs fit_score {f:g}")
        if t.get("rank") is not None and p1.get("rank") is not None \
                and num(t["rank"]) != num(p1["rank"]):
            diffs.append(f"rank {t['rank']} vs {p1['rank']}")
        for fld in ("relevance", "readiness_multiplier"):
            a_, b_ = num(t.get(fld)), num(p1.get(fld))
            if a_ is not None and b_ is not None and abs(a_ - b_) > 0.0005:
                diffs.append(f"{fld} {a_:g} vs {b_:g}")
        ca = {str(x.get("name")): num(x.get("contribution")) for x in t.get("factors") or []
              if isinstance(x, dict)}
        cb = {str(x.get("name")): num(x.get("contribution")) for x in p1.get("factors") or []
              if isinstance(x, dict)}
        for n_ in sorted(set(ca) & set(cb)):
            if ca[n_] is not None and cb[n_] is not None and abs(ca[n_] - cb[n_]) > 0.0005:
                diffs.append(f"factor {n_!r} {ca[n_]:g} vs {cb[n_]:g}")
        if diffs:
            bad("BLOCK", "O5 ↔ P1",
                f"{t.get('platform')}: the overview tile and the platform tile disagree — "
                + "; ".join(diffs) + ". O5 copies P1's engine row; one of them is stale")
    rows = (fit.get("platforms") if isinstance(fit, dict) else fit) or []
    eng = {}
    for r in rows:
        if isinstance(r, dict):
            for k in _tile_keys(r):
                eng.setdefault(k, r)
    if not eng:
        return
    for label, group in (("P1 ↔ engine", tiles), ("O5 ↔ engine", o5)):
        for t in group:
            e = next((eng[k] for k in _tile_keys(t) if k in eng), None)
            if e is None:
                continue
            diffs = []
            for fld, tol in (("relevance", 0.005), ("readiness_multiplier", 0.0005)):
                a_, b_ = num(t.get(fld)), num(e.get(fld))
                if a_ is not None and b_ is not None and abs(a_ - b_) > tol:
                    diffs.append(f"{fld} {a_:g} on the tile, {b_:g} from the engine")
            if label.startswith("P1") and t.get("state") and e.get("state") \
                    and t["state"] != e["state"]:
                diffs.append(f"state {t['state']} vs engine {e['state']}")
            if diffs:
                bad("BLOCK", label,
                    f"{t.get('platform')}: " + "; ".join(diffs) + " — engine-owned fields "
                    "are copied from get_platform_fit, never typed (SWBC: relevance 1.0 on "
                    "every tile against 0.971-0.98, D-18)")


def check_platform_states_and_areas(P, bundle, catalogue, entity_sv, supp):
    """18-20 · tile states, recommendation areas, discards and the candidate set."""
    tiles, ps = _tiles(P)
    for t in tiles:
        st = t.get("state")
        if st not in _TILE_STATES_SCORED and (t.get("rank") is not None
                                              or t.get("fit_score") is not None):
            bad("BLOCK", "P1 state",
                f"{t.get('platform')!r} is {st} and still carries rank {t.get('rank')} / "
                f"fit_score {t.get('fit_score')}. A tile the engine cannot score has "
                "rank:null and fit_score:null, or moves to discarded[] (SWBC GRC "
                "TOO_NARROW ranked 8 at 22.8, D-19)")
    tile_keys = set()
    for t in tiles:
        tile_keys |= _tile_keys(t)
    recs = [r for _, rl in dig(P.get("platform", {}), "recommendations")
            if isinstance(rl, list) for r in rl if isinstance(r, dict)]
    if tiles and recs:
        missing = {}
        for r in recs:
            area = r.get("l3_area")
            if not area:
                continue
            rest = re.sub(r"\[[^\]]*\]", "", str(area)).strip()
            if not ({_key(area), _key(rest)} & tile_keys):
                missing.setdefault(str(area), []).append(r.get("rec_id"))
        for area, ids in sorted(missing.items()):
            bad("BLOCK", "P2 ↔ P1",
                f"{', '.join(str(i) for i in ids)} file under {area!r}, which no "
                "platform_story tile carries — the area tab renders empty. Add a tile "
                "(fit_score:null, rank:null and the reason, for an advisory area) or "
                "file the recommendation under the tile whose prerequisite it gates "
                "(P1.md; SWBC REC-01/REC-11, D-19)")
    discards = [d for d in (ps.get("discarded") or []) if isinstance(d, dict)]
    for d in discards:
        if not re.search(r"\b\d+\s+(?:scored\s+|served\s+|in-vertical\s+)?(?:cells?|"
                         r"sub-?capabilit(?:y|ies))\b", str(d.get("reason") or ""), re.I):
            bad("BLOCK", "P1 discards",
                f"discard {d.get('platform')!r} states no cell count — every discard "
                "reason carries the integer count of scored cells the area addresses, "
                "so a reader can see what was set aside (RC-12(g), D-19)")
    cells = (catalogue.get("subcaps") if isinstance(catalogue, dict) else None) or []
    scores = (bundle.get("scores") if isinstance(bundle, dict) else None) or []
    if not (cells and scores and tiles):
        return
    served = {s.get("subcap_id") for s in scores
              if isinstance(s, dict) and num(s.get("score")) is not None}
    if entity_sv:
        served = {c for c in served if not variant_code(c) or variant_code(c) == entity_sv
                  or variant_code(c) in supp}
    from collections import Counter
    count = Counter()
    for c in cells:
        if isinstance(c, dict) and c.get("subcap_id") in served:
            for area in c.get("l3_platform_areas") or []:
                count[area] += 1
    covered = set(tile_keys)
    for d in discards:
        covered |= _tile_keys(d)
    gaps = []
    for area, n in count.most_common(10):
        rest = re.sub(r"\[[^\]]*\]", "", str(area)).strip()
        if not ({_key(area), _key(rest)} & covered):
            gaps.append(f"{rest or area} ({n} cells)")
    if gaps:
        bad("BLOCK", "P1 candidate set",
            "top-10 in-vertical L3 areas by scored-cell count that are neither a tile "
            "nor a discard: " + "; ".join(gaps) + ". The candidate set comes from the "
            "catalogue sweep (get_capability_catalogue), not from the report's "
            "recommendations (SWBC: Tableau Pulse 78, Platform Foundation 82, Flow 58)")


def check_stairstep_order(P):
    """21 · stair-step vs roadmap phase order and the platform order of work."""
    pl = P.get("platform", {})
    st = pl.get("stairstep", {})
    ladder = st.get("ladder") if isinstance(st.get("ladder"), dict) else st
    steps = [s for s in (ladder.get("steps") or []) if isinstance(s, dict)]
    to_level = ladder.get("to_level")
    if isinstance(to_level, str) and to_level.strip() \
            and not any(w.lower() in to_level.lower() for w in _BAND_WORDS):
        bad("WARN", "P4 to_level",
            f"to_level reads {to_level[:80]!r} — a condition, not a level. It names the "
            "target band (one of the four words), with any projection labelled as "
            "inference (D-20)")
    if len(steps) < 2:
        return
    steps = sorted(steps, key=lambda s: num(s.get("step_level")) or 0)
    tiles, _ = _tiles(P)
    tile_keys = set()
    for t in tiles:
        tile_keys |= _tile_keys(t)
    phase_of = {}
    for ph in pl.get("roadmap", {}).get("phases") or []:
        if isinstance(ph, dict):
            for rid in ph.get("rec_ids") or []:
                phase_of[rid] = num(ph.get("phase"))
    recs = [r for r in (pl.get("recommendations", {}).get("recommendations") or [])
            if isinstance(r, dict)]

    def platform_rec(r):
        """Advisory recommendations (no [L3-] tag and no tile) are
        preconditions that may precede any step; the ladder's order is
        argued against the platform recommendations."""
        area = str(r.get("l3_area") or "")
        rest = re.sub(r"\[[^\]]*\]", "", area).strip()
        return "[L3-" in area or bool({_key(area), _key(rest)} & tile_keys)

    seq = []
    for s in steps:
        cov = set(s.get("covered_subcap_ids") or [])
        hits = [(phase_of.get(r.get("rec_id"), num(r.get("phase"))), r.get("rec_id"))
                for r in recs if platform_rec(r)
                and cov & {d.get("subcap_id") for d in r.get("dma_impact") or []
                           if isinstance(d, dict)}]
        hits = [h for h in hits if h[0] is not None]
        if hits:
            seq.append((s, min(hits)))
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            (si, (pi, ri)), (sj, (pj, rj)) = seq[i], seq[j]
            if pj < pi:
                bad("BLOCK", "P4 ↔ P3 order",
                    f"step {si.get('step_level')} ({si.get('label')!r}) is first lifted in "
                    f"roadmap phase {pi:g} ({ri}), and the later step "
                    f"{sj.get('step_level')} ({sj.get('label')!r}) in phase {pj:g} ({rj}). "
                    "Step order == roadmap phase order (P4.md CONSISTENCY, RC-12(b))")

    def dominant(s):
        """The platform a step delivers: the tile whose gap cells it covers
        most; a tie attributes it to none."""
        cov = set(s.get("covered_subcap_ids") or [])
        best, score, tie = None, 0, False
        for t in tiles:
            gaps = {g.get("subcap_id") if isinstance(g, dict) else g
                    for g in (t.get("gaps") or [])}
            if isinstance(t.get("addressable_cells"), list):
                gaps |= {c for c in t["addressable_cells"] if isinstance(c, str)}
            n = len(cov & gaps)
            if n > score:
                best, score, tie = t, n, False
            elif n and n == score:
                tie = True
        return None if tie or score == 0 else best
    owner = [(s, dominant(s)) for s in steps]
    for i, (si, ti) in enumerate(owner):
        if ti is None:
            continue
        deps = {_key(d) for d in ti.get("depends_on") or []}
        for sj, tj in owner[i + 1:]:
            if tj is None or tj is ti:
                continue
            if deps & _tile_keys(tj):
                bad("BLOCK", "P4 ↔ P1 order",
                    f"step {si.get('step_level')} ({si.get('label')!r}) delivers "
                    f"{ti.get('platform')}'s gap cells, and {ti.get('platform')} "
                    f"depends_on {tj.get('platform')}, which the later step "
                    f"{sj.get('step_level')} ({sj.get('label')!r}) delivers. The ladder "
                    "climbs against the platform order of work (SWBC: the customer "
                    "record before the integration route, D-20)")


def check_thin_definition(P):
    """22 · one thin definition per payload. WHICH definition governs is an
    OPEN adjudication (owner question 9: the DB column
    `citable_evidence_count < 1` against the H2 contract 'fewer than three
    linked items, or inherited/declared provenance') and is not resolved
    here."""
    cells = [c for _, cl in dig(P.get("heatmap", {}).get("cell_evidence", {}), "cells")
             if isinstance(cl, list) for c in cl if isinstance(c, dict)]
    neither, follows = [], {"db": [], "contract": []}
    for c in cells:
        if "thin" not in c or c.get("thin_override") or c.get("thin_reason"):
            continue
        items = c.get("items")
        if isinstance(items, list):
            n = len(items)
            citable = sum(1 for x in items if not isinstance(x, dict)
                          or str(x.get("excerpt") or "").strip())
        else:
            n = citable = len(c.get("e_ids") or [])
        prov = str(c.get("provenance") or "").lower()
        db_rule = citable < 1
        contract_rule = n < 3 or prov.startswith(("inherited", "declared"))
        thin = bool(c.get("thin"))
        if thin != db_rule and thin != contract_rule:
            neither.append(c.get("subcap_id"))
        elif db_rule != contract_rule:
            follows["db" if thin == db_rule else "contract"].append(c.get("subcap_id"))
    if neither:
        bad("BLOCK", "H2 thin",
            f"{len(neither)} cell(s) carry a thin flag that NEITHER definition gives "
            f"({', '.join(map(str, neither[:5]))}{' …' if len(neither) > 5 else ''}) — "
            "thin is derived from the cell's own items, never copied (D-21)")
    if follows["db"] and follows["contract"]:
        bad("BLOCK", "H2 thin",
            f"the payload applies two thin definitions: {len(follows['db'])} cell(s) "
            f"follow citable<1 (e.g. {follows['db'][0]}) and {len(follows['contract'])} "
            f"follow fewer-than-three/inherited (e.g. {follows['contract'][0]}). Which "
            "definition governs is an open adjudication — apply one throughout, or "
            "declare thin_override with a reason on the exceptions (RC-12(c), D-21)")
    elif follows["db"] or follows["contract"]:
        which = "citable<1 (the DB column)" if follows["db"] else \
            "fewer-than-three/inherited (the H2 contract)"
        bad("WARN", "H2 thin",
            f"{len(follows['db'] or follows['contract'])} cell(s) are thin by {which} "
            "and not by the other definition; that choice is an open adjudication "
            "(owner question 9) — consistent here, flagged so it is not settled silently")


_EID_LIST_KEYS = ("e_ids", "evidence_ids", "new_evidence_ids", "supporting_e_ids",
                  "cited_e_ids")
_EID_KEYS = ("e_id", "source_e_id", "evidence_id")


def _cited_eids(node, out, where):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _EID_LIST_KEYS and isinstance(v, list):
                for x in v:
                    if isinstance(x, str):
                        out.setdefault(x, set()).add(where)
            elif k in _EID_KEYS and isinstance(v, str):
                out.setdefault(v, set()).add(where)
            else:
                _cited_eids(v, out, where)
    elif isinstance(node, list):
        for v in node:
            _cited_eids(v, out, where)


def check_evidence_index(P):
    """23 · H6 ⊇ every cited e_id; H7 rows ⊆ H6 (RC-12(d), D-27)."""
    hm = P.get("heatmap", {})
    rows = hm.get("evidence", {}).get("evidence")
    if not isinstance(rows, list):
        return
    index = {r.get("e_id") for r in rows if isinstance(r, dict)}
    cited = {}
    for page, pay in P.items():
        for sec, body in (pay.items() if isinstance(pay, dict) else []):
            if page == "heatmap" and sec == "evidence":
                continue
            _cited_eids(body, cited, f"{page}.{sec}")
    missing = sorted(e for e in cited if e not in index)
    if missing:
        ex = "; ".join(f"{e} (cited on {', '.join(sorted(cited[e]))})" for e in missing[:5])
        bad("BLOCK", "H6 index",
            f"{len(missing)} cited e_id(s) are not in heatmap.evidence, so their chips "
            f"open nothing: {ex}{' …' if len(missing) > 5 else ''} (SWBC E-CC-925, D-27)")
    age = [r.get("e_id") for r in hm.get("evidence_age", {}).get("rows") or []
           if isinstance(r, dict)]
    stray = sorted({e for e in age if e and e not in index})
    if stray:
        bad("BLOCK", "H6 index",
            f"{len(stray)} evidence_age row(s) are not in heatmap.evidence: "
            f"{', '.join(stray[:5])} — H7 rows ⊆ H6")


def _whole_row_internal(marks, key):
    rx = re.compile(rf"^{re.escape(key)}\[(\d+)\]$")
    return {int(m.group(1)) for m in (rx.match(str(x)) for x in marks or []) if m}


def check_leadership(P):
    """24 · O7 counts are audience-neutral; tenure derives from appointed_on (D-24)."""
    lead = P.get("overview", {}).get("leadership", {})
    if not isinstance(lead, dict):
        return
    key = next((k for k in ("roster", "rows", "leaders") if isinstance(lead.get(k), list)), None)
    if key is None:
        return
    rows = [r for r in lead[key] if isinstance(r, dict)]
    n_int = len(rows)
    n_cust = n_int - len(_whole_row_internal(lead.get("internal_only"), key))
    text = " ".join(str(lead.get(k) or "") for k in ("narrative_thread", "summary", "synthesis"))
    for n, noun in _stated_counts(text, ("executives", "leaders", "officers", "people",
                                         "seats", "contacts")):
        if n != n_int or n != n_cust:
            bad("BLOCK", "O7 counts",
                f"the leadership text states {n} {noun}; the internal roster serves "
                f"{n_int} row(s) and the customer roster {n_cust}. A count in prose must "
                "hold for every audience that reads it — state the count both see, or "
                "none (SWBC: 'thirteen executives' over 14 rows, D-24)")
    bare = [r.get("name") for r in rows
            if r.get("tenure_months") is not None and not r.get("appointed_on")]
    if bare:
        bad("BLOCK", "O7 tenure",
            f"{len(bare)} row(s) carry tenure_months with no appointed_on "
            f"({', '.join(map(str, bare[:5]))}) — tenure is derived from the "
            "appointment date, so fill appointed_on from the evidence or null the "
            "tenure (D-24)")


def check_findings(P):
    """25 · O6 ranking basis agrees with the alignment scores; counts and chips (D-29)."""
    F = P.get("overview", {}).get("findings", {})
    if not isinstance(F, dict):
        return
    fnd = [f for f in (F.get("findings") or []) if isinstance(f, dict)]
    if not fnd:
        return

    def score(f):
        s = f.get("strategic_alignment_score")
        if s is None and isinstance(f.get("strategic_alignment"), dict):
            s = f["strategic_alignment"].get("score")
        return num(s)
    scored = [(f.get("f_id"), score(f)) for f in fnd]
    if F.get("ranking_basis") == "impact_fallback" and any(s is not None for _, s in scored):
        bad_pairs, seen_null, last = [], None, None
        for fid, s in scored:
            if s is None:
                seen_null = seen_null or fid
                continue
            if seen_null:
                bad_pairs.append(f"{fid} ({s:g}) is ranked below {seen_null} (no score)")
            elif last is not None and s > last[1]:
                bad_pairs.append(f"{fid} ({s:g}) is ranked below {last[0]} ({last[1]:g})")
            last = (fid, s)
        if bad_pairs:
            bad("BLOCK", "O6 ranking",
                "ranking_basis is impact_fallback while "
                f"{', '.join(str(fid) for fid, s in scored if s is not None)} carry "
                f"alignment scores, and {'; '.join(bad_pairs)}. Rank by the scores and "
                "say so, or drop the scores (RC-12(h), D-29)")
    for n, _ in _stated_counts(str(F.get("narrative_thread") or ""), ("findings",)):
        if n != len(fnd):
            bad("BLOCK", "O6 counts",
                f"the findings narrative states {n} findings; the section carries {len(fnd)}")
    if any(f.get("platform_chips") for f in fnd):
        empty = [f.get("f_id") for f in fnd if not f.get("platform_chips")]
        if empty:
            bad("WARN", "O6 chips",
                f"{', '.join(map(str, empty))} carry no platform_chips while the other "
                "findings do — name the platform the finding argues for, or state none (D-29)")


def _peer_key(name):
    m = re.match(r"\W*([A-Za-z0-9]+)", str(name or ""))
    return m.group(1).lower() if m else ""


def identified_peers(P, bundle):
    """The run's NAMED peer set, scored or not (RC-10(a)): the bundle's peer
    table or locked set, or any peer_deployments row on any page.
    {key: display name}, in first-seen order."""
    out = {}

    def add(name):
        k = _peer_key(name)
        if k and k not in out:
            out[k] = str(name).strip()
    if isinstance(bundle, dict):
        for k in ("locked_peer_set", "peer_set", "identified_peers"):
            for x in bundle.get(k) or []:
                if isinstance(x, dict):
                    x = x.get("name") or x.get("peer_name") or x.get("peer")
                add(x)
        for r in bundle.get("peer_table") or []:
            if isinstance(r, dict):
                add(r.get("peer_name") or r.get("peer"))
    for pay in P.values():
        for _, rows in dig(pay, "peer_deployments"):
            for r in rows if isinstance(rows, list) else []:
                if isinstance(r, dict):
                    add(r.get("peer"))
    return out


def check_peers(P, bundle):
    """26-27 · 'identified, not scored' is not 'no peers' (RC-10; D-08, D-17)."""
    peers = identified_peers(P, bundle)
    if not peers:
        return
    names = ", ".join(peers.values())
    tiles, _ = _tiles(P)
    for t in tiles:
        rows = [r for r in (t.get("peer_deployments") or []) if isinstance(r, dict)]
        problems = []
        have = {_peer_key(r.get("peer")) for r in rows}
        missing = [v for k, v in peers.items() if k not in have]
        if missing:
            problems.append(f"no peer_deployments row for {', '.join(missing)}")
        for r in rows:
            if r.get("deployed") not in (True, False, None):
                problems.append(f"{r.get('peer')}: deployed is {r.get('deployed')!r}, "
                                "not true/false/null")
            if not str(r.get("basis") or "").strip():
                problems.append(f"{r.get('peer')}: no basis — a deployed:null row states "
                                "the ladder that could not establish it")
        if not str(t.get("peer_synthesis") or "").strip():
            problems.append("no peer_synthesis")
        if problems:
            bad("BLOCK", "P1 peers",
                f"{t.get('platform')}: " + "; ".join(problems) + ". The run identified "
                f"{names}: every tile carries one row per named peer (deployed:null with "
                "its ladder where unestablished) and a peer_synthesis — identified-not-"
                "scored is still a peer set (SWBC: 6 of 8 tiles bare, D-08)")
    pillars = P.get("overview", {}).get("scores", {}).get("pillars")
    entries = (list(pillars.values()) if isinstance(pillars, dict) else pillars) or []
    silent, unstamped = [], []
    for e in entries:
        if not isinstance(e, dict) or e.get("peer_median") is not None:
            continue
        disc = str(e.get("proxy_disclosure") or "").lower()
        if not any(re.search(rf"\b{re.escape(k)}", disc) for k in peers):
            silent.append(str(e.get("pillar_id")))
        if e.get("peer_basis") is None:
            unstamped.append(str(e.get("pillar_id")))
    if silent:
        bad("BLOCK", "O1 peers",
            f"pillar(s) {', '.join(silent)} disclose no peer median and name none of the "
            f"identified peers ({names}). Name the cohort as 'identified, not scored' "
            "wherever one exists, even with peer_basis cannot_estimate (RC-10(c), D-17)")
    if unstamped:
        bad("BLOCK", "O1 peers",
            f"pillar(s) {', '.join(unstamped)} carry peer_basis null on a run with an "
            "identified peer set — stamp cannot_estimate, so the absence renders with "
            "its reason (RC-10(d))")
    ws = P.get("heatmap", {}).get("workbook_scores")
    if isinstance(ws, dict) and ws:
        blob = json.dumps(ws).lower()
        if not any(k in blob for k in peers) and "not scored" not in blob:
            bad("WARN", "H4 peers",
                f"the grid's peer row has no stated reason naming the identified peers "
                f"({names}) — a peer row of blank boxes reads as 'not researched' "
                "(D-17); state 'identified, not scored' in the section's empty_state")


def check_dating(P):
    """28 · dates that exist are applied (RC-07(e), D-23): an H7 undated
    share above 20% with no dating rung recorded is a pass that was skipped,
    not a measurement (SWBC 41.8% with 41 harvested dates never applied;
    Baxter 0%)."""
    age = P.get("heatmap", {}).get("evidence_age", {})
    pct = num(age.get("undated_pct")) if isinstance(age, dict) else None
    if pct is None or pct <= 20:
        return
    probes = json.dumps((age.get("r_layer") or {}).get("probes_run") or []).lower()
    if not re.search(r"\bdat(e|ed|ing)\b", probes):
        bad("WARN", "H7 dating",
            f"undated_pct is {pct:g}% and r_layer records no dating rung. Harvest the "
            "dates the evidence carries (datelines, filings, page metadata), verify each "
            "against its excerpt and apply them through register_evidence before "
            "reporting the share (RC-07(e))")


def main(argv=None):
    del issues[:]
    ap=argparse.ArgumentParser(); ap.add_argument("rundir"); ap.add_argument("--strict",action="store_true")
    ap.add_argument("--bundle",metavar="JSON",
                    help="get_report_bundle output (default: <rundir>/bundle.json). The "
                         "entity's sub-vertical binding — primary AND supplementary — and "
                         "its peer set are read from it, never typed (MEM-0559).")
    ap.add_argument("--catalogue",metavar="JSON",
                    help="get_capability_catalogue output (default: <rundir>/catalogue.json)")
    ap.add_argument("--fit",metavar="JSON",
                    help="get_platform_fit output (default: <rundir>/fit.json)")
    ap.add_argument("--subvertical",metavar="CODE",
                    help="a CROSS-CHECK only: the code you expect. The bundle is the "
                         "binding; a typed code that disagrees with it blocks. Without a "
                         "bundle it stands in for the primary, and the supplementary "
                         "binding is unknown.")
    ap.add_argument("--supplementary",metavar="CODES",default=None,
                    help=argparse.SUPPRESS)
    a=ap.parse_args(argv)
    if a.supplementary is not None:
        print("  --supplementary is retired: the supplementary binding is read from the "
              "bundle (get_report_bundle → supplementary_sub_verticals), the same place "
              "the connector's ET-05 reads it — MEM-0559. Pass --bundle <file> or put "
              "bundle.json in the run directory.")
        return 2
    bundle=_load_tool_json(a.bundle, a.rundir, ("bundle.json","get_report_bundle.json"))
    catalogue=_load_tool_json(a.catalogue, a.rundir, ("catalogue.json",))
    fit=_load_tool_json(a.fit, a.rundir, ("fit.json","platform_fit.json"))
    typed=(a.subvertical or "").strip().upper() or None
    if typed and typed not in SUBVERTICAL_CODES:
        print(f"  unknown sub-vertical code {typed!r} — expected one of "
              f"{' '.join(sorted(SUBVERTICAL_CODES))}"); return 2
    entity_sv, supp, binding_note = _binding(bundle, typed)
    P={}
    for p in PAGES:
        f=os.path.join(a.rundir,f"{p}.json")
        if os.path.exists(f):
            try: P[p]=json.load(open(f,encoding="utf-8"))
            except Exception as e: bad("BLOCK",p,f"unreadable: {e}")
    missing=[p for p in PAGES if p not in P]
    if missing: bad("INFO","run",f"pages absent from this check: {', '.join(missing)}")
    print(f"\n  pages loaded: {', '.join(P) or 'none'}")
    print(f"  {binding_note}\n")

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
                if code!=entity_sv and code not in supp:
                    ex="; ".join(f"{p}:{cid}" for p,_,cid in rows[:3])
                    bad("BLOCK","sub-vertical scope",
                        f"{len(rows)} cited cell(s) are {code} variants on a {entity_sv} run — "
                        f"they resolve in the workbook and render nowhere ({ex})"
                        + (f" — bound: {entity_sv}+{','.join(sorted(supp))}" if supp else ""))
        elif len(cited)>1:
            bad("WARN","sub-vertical scope",
                f"cited variant cells span more than one sub-vertical ({shape}) and the "
                "binding is unknown — put get_report_bundle's output in the run "
                "directory as bundle.json (or pass --bundle) so primary and "
                "supplementary sub-verticals are read, not guessed")

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
        vc=variant_code(cid)
        if vc and entity_sv and vc!=entity_sv and vc not in supp: continue
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

    # ── 16-27 · the cross-section invariants the contracts name (RC-10, RC-12)
    check_platform_arithmetic(P, fit)
    check_platform_states_and_areas(P, bundle, catalogue, entity_sv, supp)
    check_stairstep_order(P)
    check_thin_definition(P)
    check_evidence_index(P)
    check_leadership(P)
    check_findings(P)
    check_peers(P, bundle)
    check_dating(P)

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
