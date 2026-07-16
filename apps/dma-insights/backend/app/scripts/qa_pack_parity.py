"""Value-level DB↔pack parity gate (QA-gates workstream, plan Parts 3.1/13.1).

The committed `startup-data/clients/*/` snapshot is what AEs see cold — it
must be byte-equivalent in SUBSTANCE to what the live routes serve. This gate
samples 8 clients (stratified across the sorted directory) x the 10 page
surfaces, fetches the SAME route the exporter (`export_startup_pages`) uses —
in-process via the ASGI transport, no re-implemented SQL — and diffs each
response against the committed file:

  structural  recursive key-set diff (dict keys missing on either side;
              list-length mismatches; id-keyed lists aligned by "id")
  drift       numeric leaves on score-like keys (score / *_score / peer_median
              / peer_gap / fit / maturity_lift / overall / pillar values)
              differing by more than ε (default .01)

Prints a per-surface diff summary. `--strict` exits nonzero on ANY finding —
that is the regen-chain gate (`… → export_startup_pages → qa_pack_parity`)
proving pack==DB after a bake. Run WITHOUT --strict against a stale pack to
see how far the DB has moved (pre-regen the committed pack is expected to
drift — the counters gate in qa_startup_audit owns that story).

Usage:
  source env with DATABASE_URL, then
  python -m app.scripts.qa_pack_parity [--clients-dir DIR] [--sample 8]
         [--clients a-0001,b-0001] [--surfaces overview,context] [--eps .01]
         [--strict] [--json]

Exit codes: 0 ok/report-only · 1 strict-mode findings · 2 environment error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

# The exporter's surface→route map is the single source of truth; consuming it
# here means a new baked surface is parity-checked the moment it ships.

# The ASGI-transport sweep issues 13 requests x 94 clients — httpx logs
# each at INFO, flooding the Cloud Build log with >1,200 useless lines
# per invocation (2026-07-05 operator complaint). Real failures still
# surface: non-2xx handling below + WARNING-and-up stay visible.
logging.getLogger("httpx").setLevel(logging.WARNING)

try:
    from app.scripts.export_startup_pages import _PAGE_SURFACES
    from app.scripts.qa_coverage_contract import PAGE_FILES
except ImportError:  # pragma: no cover - direct-run fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.scripts.export_startup_pages import _PAGE_SURFACES
    from app.scripts.qa_coverage_contract import PAGE_FILES

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "startup-data", "clients",
)
_SURFACE_ROUTES: dict[str, str] = dict(_PAGE_SURFACES)

# volatile per-request fields — never a parity defect
_IGNORE_KEYS = frozenset({"last_refreshed_at", "generated_at"})
_SCORE_KEY_TOKENS = ("score", "median", "peer_gap", "fit", "maturity_lift", "overall")
_PILLAR_KEYS = frozenset({"P1", "P2", "P3", "P4"})


def _is_score_key(key: str, parent_key: str) -> bool:
    k = key.lower()
    if key in _PILLAR_KEYS and parent_key in ("pillars", "pillar_scores"):
        return True
    return any(tok in k for tok in _SCORE_KEY_TOKENS)


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _align_lists(pack: list, live: list) -> list[tuple[str, Any, Any]]:
    """Pair list elements — by 'id' when both sides are id-keyed dicts,
    positionally otherwise (up to the shorter length)."""
    if (pack and live and all(isinstance(x, dict) and "id" in x for x in pack)
            and all(isinstance(x, dict) and "id" in x for x in live)):
        by_id = {x["id"]: x for x in live}
        return [(f"[id={p['id']}]", p, by_id[p["id"]]) for p in pack if p["id"] in by_id]
    return [(f"[{i}]", p, v) for i, (p, v) in enumerate(zip(pack, live, strict=False))]


def diff_surface(pack: Any, live: Any, *, eps: float = 0.01,
                 path: str = "") -> tuple[list[str], list[dict]]:
    """Recursive (structural, drift) diff of one surface. Pure — unit-tested
    against synthetic dicts, no DB. Structural entries are strings
    ('missing_in_live:cards[0].fit_breakdown'); drift entries are
    {path, pack, live, delta}."""
    structural: list[str] = []
    drift: list[dict] = []
    if isinstance(pack, dict) and isinstance(live, dict):
        for k in sorted((set(pack) | set(live)) - _IGNORE_KEYS):
            p = f"{path}.{k}" if path else str(k)
            if k not in live:
                structural.append(f"missing_in_live:{p}")
            elif k not in pack:
                structural.append(f"missing_in_pack:{p}")
            else:
                pv, lv = pack[k], live[k]
                if _is_num(pv) and _is_num(lv):
                    if _is_score_key(str(k), path.rsplit(".", 1)[-1]) \
                            and abs(pv - lv) > eps:
                        drift.append({"path": p, "pack": pv, "live": lv,
                                      "delta": round(abs(pv - lv), 4)})
                else:
                    s, d = diff_surface(pv, lv, eps=eps, path=p)
                    structural.extend(s)
                    drift.extend(d)
    elif isinstance(pack, list) and isinstance(live, list):
        if len(pack) != len(live):
            structural.append(f"list_len:{path}:{len(pack)}!={len(live)}")
        for suffix, pv, lv in _align_lists(pack, live):
            s, d = diff_surface(pv, lv, eps=eps, path=f"{path}{suffix}")
            structural.extend(s)
            drift.extend(d)
    elif type(pack) is not type(live) and not (_is_num(pack) and _is_num(live)):
        structural.append(f"type:{path}:{type(pack).__name__}!={type(live).__name__}")
    return structural, drift


def stratified_sample(display_ids: list[str], k: int) -> list[str]:
    """Deterministic every-n/kth sample across the sorted directory."""
    ids = sorted(display_ids)
    if k >= len(ids):
        return ids
    step = len(ids) / k
    return [ids[int(i * step)] for i in range(k)]


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="DB↔pack value-level parity gate")
    ap.add_argument("--clients-dir", default=os.path.normpath(_DEFAULT_DIR))
    ap.add_argument("--sample", type=int, default=8)
    ap.add_argument("--clients", default=None,
                    help="comma-separated display_ids (overrides --sample)")
    ap.add_argument("--surfaces", default=",".join(PAGE_FILES),
                    help="comma-separated surfaces (default: the 10 page files)")
    ap.add_argument("--eps", type=float, default=0.01)
    ap.add_argument("--strict", action="store_true",
                    help="exit nonzero on any structural diff or score drift")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", type=int, default=5, help="examples per surface")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set (source the env first)", file=sys.stderr)
        return 2
    clients_dir = Path(args.clients_dir).resolve()
    if not clients_dir.is_dir():
        print(f"ERROR: clients dir not found: {clients_dir}", file=sys.stderr)
        return 2
    surfaces = [s.strip() for s in args.surfaces.split(",") if s.strip()]
    unknown = [s for s in surfaces if s not in _SURFACE_ROUTES]
    if unknown:
        print(f"ERROR: unknown surface(s) {unknown}; known: {sorted(_SURFACE_ROUTES)}",
              file=sys.stderr)
        return 2
    all_ids = [p.name for p in clients_dir.iterdir() if p.is_dir()]
    ids = ([c.strip() for c in args.clients.split(",") if c.strip()]
           if args.clients else stratified_sample(all_ids, args.sample))

    import httpx  # heavy imports deferred so --help stays instant

    from app.deps import CurrentUser, get_current_user
    from app.main import app

    def _parity_user() -> CurrentUser:
        return CurrentUser(user_id=str(uuid4()), email="qa-pack-parity@exporter.local",
                           role="ADMIN", name="QA Pack Parity")

    app.dependency_overrides[get_current_user] = _parity_user
    transport = httpx.ASGITransport(app=app)

    per_surface: dict[str, dict] = {
        s: {"clients": 0, "structural": 0, "drift": 0, "missing_pack_file": 0,
            "live_error": 0, "examples": []} for s in surfaces}
    async with httpx.AsyncClient(transport=transport, base_url="http://parity") as client:
        for did in ids:
            for surface in surfaces:
                rep = per_surface[surface]
                pack_path = clients_dir / did / f"{surface}.json"
                if not pack_path.exists():
                    rep["missing_pack_file"] += 1
                    rep["examples"].append(f"{did}: pack file absent")
                    continue
                try:
                    pack = json.loads(pack_path.read_text())
                except (OSError, json.JSONDecodeError) as e:
                    rep["missing_pack_file"] += 1
                    rep["examples"].append(f"{did}: pack unreadable ({type(e).__name__})")
                    continue
                try:
                    r = await client.get(_SURFACE_ROUTES[surface].format(d=did))
                    live = r.json() if r.status_code < 400 else None
                except Exception:
                    live = None
                if live is None:
                    rep["live_error"] += 1
                    rep["examples"].append(f"{did}: live route failed")
                    continue
                structural, drift = diff_surface(pack, live, eps=args.eps)
                rep["clients"] += 1
                rep["structural"] += len(structural)
                rep["drift"] += len(drift)
                for s in structural[:2]:
                    if len(rep["examples"]) < args.show * 2:
                        rep["examples"].append(f"{did}: {s}")
                for d in drift[:2]:
                    if len(rep["examples"]) < args.show * 2:
                        rep["examples"].append(
                            f"{did}: drift {d['path']} pack={d['pack']} live={d['live']}")
    app.dependency_overrides.pop(get_current_user, None)

    total_structural = sum(r["structural"] for r in per_surface.values())
    total_drift = sum(r["drift"] for r in per_surface.values())
    total_errors = sum(r["missing_pack_file"] + r["live_error"]
                       for r in per_surface.values())

    if args.json:
        print(json.dumps({
            "clients": ids, "eps": args.eps, "strict": args.strict,
            "surfaces": {s: {k: v for k, v in r.items() if k != "examples"}
                         for s, r in per_surface.items()},
            "total_structural": total_structural, "total_drift": total_drift,
            "total_errors": total_errors,
        }, indent=2))
    else:
        print(f"\n# qa_pack_parity — {len(ids)} clients x {len(surfaces)} surfaces "
              f"(ε={args.eps}{', STRICT' if args.strict else ''})")
        print(f"  sample: {', '.join(ids)}\n")
        for surface in surfaces:
            r = per_surface[surface]
            flag = "OK " if not (r["structural"] or r["drift"] or r["missing_pack_file"]
                                 or r["live_error"]) else "DIFF"
            print(f"  [{flag}] {surface:20} structural={r['structural']:<6} "
                  f"drift={r['drift']:<5} pack_missing={r['missing_pack_file']} "
                  f"live_err={r['live_error']}")
            for ex in r["examples"][: args.show]:
                print(f"         ↳ {ex}")
        verdict = "PASS" if not (total_structural or total_drift or total_errors) else (
            "FAIL" if args.strict else "DRIFT (report-only; --strict gates)")
        print(f"\n# RESULT: {verdict} — structural={total_structural} "
              f"drift={total_drift} errors={total_errors}")

    if args.strict and (total_structural or total_drift or total_errors):
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
