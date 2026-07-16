"""Per-page + per-drilldown payload export + completeness gate for all 94.

`export_startup_data` emits the dashboard + directory first-paint. This script
emits the DETAIL-page payloads — one JSON per ACTIVE entity per surface.

SIZE NOTE: the full corpus per-page output is ~58 MB raw (the subcap heatmap
grids dominate), too large to COMMIT as bundled first-paint data. It is therefore
generated at deploy time into the container's ephemeral `startup-data/` (not the
repo), while the committed first-paint stays the lightweight dashboard + directory
snapshot. The live API already serves every detail page fully populated (proven
by `qa_render_validation --strict`, 0 FAIL). The high-value mode here is
`--verify`: the per-page no-empty gate that asserts every REQUIRED surface
renders non-empty for all 94 (complements the HTTP render auditor at the
route-handler/JSON layer).

Parity by construction: each file is the exact response of the SAME route the
live app calls, fetched in-process via FastAPI's ASGI transport with an ADMIN
principal (no re-implemented SQL). Output:

  startup-data/clients/{display_id}/{overview,insights,heatmap,heatmap_pillar,
      heatmap_category,heatmap_value_chain,focus_areas,platforms,
      platforms_roadmap,context,health,techstack,runs,evidence}.json
  startup-data/pages_manifest.json   {generated_at, source_sha, surfaces, clients}

SOURCE_SHA / pack-freshness contract (master plan Part 14 — this gate is REAL):
  `source_sha` in pages_manifest.json is the deploy-gate freshness stamp.
  Resolution order: `--sha` arg > `SOURCE_SHA` env > `local-<git short sha>`
  (when a git checkout is available) > `"unknown"`. The Cloud Build
  `regen-startup-pack` stage passes `SOURCE_SHA=${_IMAGE_SHA}` into the regen
  container and HARD-FAILS on a non-zero exit here; `frontend-image-smoke`
  check 6 then asserts the manifest BAKED into the frontend image carries
  exactly that SHA — so a failed regen (stale committed pack) or a reused old
  image fails the build loud instead of shipping silently. The only escape is
  the `_ALLOW_STALE_PACK=true` substitution (see infra/EXIT_CODES.md +
  docs/DEPLOYMENT.md §26.5). `qa_gemini_surfaces --mode baked` additionally
  stamps `gemini: hot|cold` into the same manifest.

Modes:
  (default / write)  regenerate every per-page file.
  --verify           fail (exit 1) if a REQUIRED surface JSON is empty for any
                     of the 94 (the per-page no-empty-state gate; expected-empty
                     surfaces — roadmap/intelligence — are exempt).

Usage:
  DATABASE_URL=... python -m app.scripts.export_startup_pages --out ../startup-data
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

from app.database import get_sessionmaker
from app.deps import CurrentUser, get_current_user
from app.services.subcap_synthesis import merge_subcap_synthesis

# surface -> URL template. Aggregated heatmap + roadmap are drilldown states.
#
# 2026-07 D3 remediation (Part 6.1/6.2/6.4):
#   - heatmap surfaces bake with peer=true — the committed pack used to bake
#     peer=false, so cold serve rendered 0% peer medians even though 63,210
#     scores carry one.
#   - heatmap_category — category-grain names map; without it the frontend's
#     categoryNamesQ cold-fell-back to heatmap_pillar.json (4 pillar cells)
#     and every category label rendered as its bare id.
#   - heatmap_value_chain — the hm=value_chain zoom=subcap state (buckets
#     only populate at subcap zoom).
#   - focus_areas — the D3 DEFAULT view's data source (incl. grounding +
#     embedded KPIs). It was never a pack surface + useFocusAreas had no
#     snapshot fallback ⇒ cold serve was an empty landing for all 94.
#
# 2026-07-06 evidence-drawer remediation:
#   - evidence — the full per-run evidence_index list at the loosest filter
#     (min_tier=8, limit=500 ≥ the 312-row max run). The drawer was the ONLY
#     surface bypassing pack-first (bare apiGet), so every pack client's
#     drawer 404'd/emptied cold while all 94 cite E-IDs on cards. One baked
#     file serves every drawer scope — tier/subcap/eId filtering is
#     client-side over this snapshot.

# The ASGI-transport sweep issues 14 requests x 94 clients — httpx logs
# each at INFO, flooding the Cloud Build log with >1,200 useless lines
# per invocation (2026-07-05 operator complaint). Real failures still
# surface: non-2xx handling below + WARNING-and-up stay visible.
logging.getLogger("httpx").setLevel(logging.WARNING)

_PAGE_SURFACES: tuple[tuple[str, str], ...] = (
    ("overview", "/api/v1/entities/{d}/overview"),
    ("insights", "/api/v1/entities/{d}/insights"),
    ("heatmap", "/api/v1/entities/{d}/heatmap?zoom=subcap&peer=true"),
    ("heatmap_pillar", "/api/v1/entities/{d}/heatmap?zoom=pillar&peer=true"),
    ("heatmap_category", "/api/v1/entities/{d}/heatmap?zoom=category&peer=true"),
    ("heatmap_value_chain",
     "/api/v1/entities/{d}/heatmap?hm=value_chain&zoom=subcap&peer=true"),
    ("focus_areas", "/api/v1/entities/{d}/focus-areas"),
    ("platforms", "/api/v1/entities/{d}/platforms"),
    ("platforms_roadmap", "/api/v1/entities/{d}/platforms/roadmap"),
    ("context", "/api/v1/entities/{d}/context"),
    ("health", "/api/v1/entities/{d}/health"),
    ("techstack", "/api/v1/entities/{d}/techstack"),
    ("runs", "/api/v1/entities/{d}/runs"),
    ("evidence", "/api/v1/entities/{d}/evidence?min_tier=8&limit=500"),
)
# Surfaces whose emptiness fails --verify (mirrors qa_render_validation strict
# set). roadmap is exempt (honest "no sequenced recs"); intelligence is omitted.
# evidence is REQUIRED: every one of the 94 cites E-IDs on insight cards, so
# an empty evidence bake means the drawer cold-serves nothing resolvable.
_REQUIRED = frozenset({"overview", "insights", "heatmap", "heatmap_pillar",
                       "heatmap_category", "heatmap_value_chain", "focus_areas",
                       "platforms", "context", "techstack", "runs", "evidence"})


def _resolve_source_sha() -> str:
    """Freshness stamp for pages_manifest.json (deploy gate — see docstring).

    `SOURCE_SHA` env (Cloud Build regen passes `${_IMAGE_SHA}`) wins; a local
    run without it stamps a truthful `local-<git short sha>`; only a checkout
    with no git at all falls back to `"unknown"`.
    """
    env_sha = os.environ.get("SOURCE_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if short:
            return f"local-{short}"
    except Exception:
        pass
    return "unknown"


def _exporter_user() -> CurrentUser:
    return CurrentUser(user_id=str(uuid4()), email="startup-pages@exporter.local",
                       role="ADMIN", name="Startup Pages Exporter")


async def _load_subcap_synthesis(
    session, display_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Durable per-subcap synthesis for the grid's baked run.

    Thin wrapper over the SHARED twin (``services.subcap_synthesis.
    load_subcap_synthesis_for_run`` — the same loader the live heatmap
    grid route serves, so pack==live by construction). Keyed by the SAME
    run the heatmap grid resolves (active, else pending/in-progress) via
    the shared ``run_resolver`` so the subcap_ids line up 1:1 with the
    baked cells. Empty dicts when the entity has no run / table absent.
    """
    from app.services.run_resolver import maybe_resolve_entity_run
    from app.services.subcap_synthesis import load_subcap_synthesis_for_run
    try:
        resolved = await maybe_resolve_entity_run(
            session, display_id, run_request_id=None, allow_in_progress=True,
        )
    except Exception:
        await session.rollback()
        return {}, {}
    if resolved is None:
        return {}, {}
    return await load_subcap_synthesis_for_run(session, resolved.id)


def prune_stale_client_entries(clients_root: Path, keep: set[str]) -> list[str]:
    """Remove per-client pack entries NOT in the active ``keep`` set; returns
    the removed names (sorted).

    ``/workspace/startup-data`` is the COMMITTED pack (dirs accumulated across
    prior corpora), NOT a fresh dir — the regen mounts ``APP_ROOT:/workspace``.
    A client re-slugged from a bare acronym to its full legal name
    (``ccu-0001`` → ``consumers-credit-union-0001``, commit c9e874ec) leaves
    the OLD slug's dir behind with no fresh export; ``qa_pack_parity`` samples
    the pack's own dirs, hits the stale one, and fails "pack file absent" for
    every surface. Keeping EXACTLY the ACTIVE display_ids makes the baked pack
    track the live corpus (and stops the frontend baking ghost clients). Safe
    by construction: an ACTIVE client is always in ``keep`` (it was just
    exported), so only genuinely superseded entries are removed.
    """
    removed: list[str] = []
    if not clients_root.is_dir():
        return removed
    for child in sorted(clients_root.iterdir()):
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child)
            removed.append(child.name)
        elif child.is_file() and child.suffix == ".json" and child.stem not in keep:
            # stale first-paint flat file (clients/<old-slug>.json)
            child.unlink()
            removed.append(child.name)
    return removed


def _nonempty(surface: str, body: object) -> bool:
    """Heuristic 'has content' check matching the completeness contract."""
    if not isinstance(body, dict):
        return bool(body)
    if surface in ("overview",):
        return bool(body.get("pillar_scores") or body.get("pillars"))
    if surface in ("heatmap", "heatmap_pillar", "heatmap_category"):
        return bool(body.get("cells") or body.get("subcaps"))
    if surface == "heatmap_value_chain":
        return bool(body.get("value_chain_buckets"))
    if surface == "focus_areas":
        return bool(body.get("items"))
    if surface == "platforms":
        return bool(body.get("cards") or body.get("platforms"))
    if surface == "insights":
        return bool(body.get("items"))
    if surface == "techstack":
        return bool(body.get("items") or body.get("entries"))
    if surface == "runs":
        return bool(body.get("items") or body.get("runs"))
    if surface == "evidence":
        return bool(body.get("items"))
    if surface == "context":
        firmo = body.get("firmographics") or {}
        return bool(body.get("timeline_events") or firmo.get("leadership")
                    or firmo.get("primary_regulator") or body.get("issue_register"))
    return True  # health and others always render


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="Export per-page first-paint JSON")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "startup-data"))
    ap.add_argument("--sha", default=None,
                    help="freshness stamp; default SOURCE_SHA env, else "
                         "local-<git short sha>, else 'unknown'")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--entity", default=None,
                    help="export only this display_id (per-client refresh; "
                         "skips stale-entry pruning)")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    out = Path(args.out).resolve()
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(text(
            # Synthetic CI fixtures (seed_ci's '… (synthetic)') never ship
            # in the committed pack — same guard as export_startup_data.
            "SELECT display_id FROM entities WHERE status='ACTIVE' "
            "AND display_id IS NOT NULL "
            "AND LOWER(COALESCE(name, '')) NOT LIKE '%(synthetic)%' "
            "ORDER BY display_id"
        ))).all()
    display_ids = [r.display_id for r in rows]
    if args.entity:
        display_ids = [d for d in display_ids if d == args.entity]

    # Import the app lazily (heavy) + bypass auth for in-process probing.
    from app.main import app
    app.dependency_overrides[get_current_user] = _exporter_user
    transport = httpx.ASGITransport(app=app)

    written = 0
    empty_required: list[str] = []
    async with sm() as synth_session, \
            httpx.AsyncClient(transport=transport, base_url="http://export") as client:
        for did in display_ids:
            for surface, tmpl in _PAGE_SURFACES:
                try:
                    r = await client.get(tmpl.format(d=did))
                    body = r.json() if r.status_code < 400 else {}
                except Exception:
                    body = {}
                # D3 pack fidelity (2026-07): bake the durable per-subcap
                # synthesis into the heatmap grid snapshot so cold/pack-first
                # serve carries it (the SynthesisDrawer's live per-subcap
                # endpoint is unreachable pack-first). Only the subcap-grain
                # heatmap surface carries the per-subcap cells this keys to.
                # The live grid route now serves the SAME merge (shared twin
                # in services.subcap_synthesis), so this is an idempotent
                # double-apply kept as belt-and-braces for the baked file.
                if surface == "heatmap" and isinstance(body, dict) and not args.verify:
                    per_md, per_meta = await _load_subcap_synthesis(synth_session, did)
                    merge_subcap_synthesis(body, per_md, per_meta)
                if surface in _REQUIRED and not _nonempty(surface, body):
                    empty_required.append(f"{did}/{surface}")
                if not args.verify:
                    dst = out / "clients" / did / f"{surface}.json"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n")
                    written += 1
    app.dependency_overrides.pop(get_current_user, None)

    # ── Prune stale per-client dirs (2026-07-07 pack-parity incident) ──────
    if not args.verify and not args.entity:
        pruned = prune_stale_client_entries(out / "clients", set(display_ids))
        if pruned:
            print(f"# export_startup_pages: pruned {len(pruned)} stale pack "
                  f"entr{'y' if len(pruned) == 1 else 'ies'}: "
                  f"{', '.join(pruned[:12])}"
                  f"{' …' if len(pruned) > 12 else ''}", flush=True)

    if not args.verify:
        source_sha = args.sha or _resolve_source_sha()
        (out / "pages_manifest.json").write_text(json.dumps({
            "generated_at": datetime.now(UTC).isoformat(),
            "source_sha": source_sha,
            "surfaces": [s for s, _ in _PAGE_SURFACES],
            "clients": display_ids,
        }, indent=2, sort_keys=True) + "\n")
        print(f"# pages_manifest.json source_sha={source_sha}", flush=True)

    print(f"# export_startup_pages: clients={len(display_ids)} "
          f"surfaces={len(_PAGE_SURFACES)} files_written={written} "
          f"empty_required={len(empty_required)}"
          + (" [VERIFY]" if args.verify else ""), flush=True)
    for er in empty_required[:20]:
        print(f"  EMPTY_REQUIRED {er}", flush=True)
    return 1 if (args.verify and empty_required) else 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
