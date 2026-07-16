"""Export the repo `startup-data/` snapshot from the seeded database.

WHAT THIS IS
------------
`startup-data/` is the dashboard's first-paint payload + the per-client
score archive the operator asked for ("list the 95 clients ... parsed into
JSON and wired as the startup data to the frontend"). It is a **read-only
snapshot of the live database**, produced AFTER the JSON backfill
(`historical_backfill --dir`) + the §2c derive chain have run.

WHY IT MATCHES THE API EXACTLY
------------------------------
The entity cards + dashboard tiles are produced by calling the SAME route
handlers the live API serves — `app.routers.entities.list_entities` and
`.dashboard` — against the same session. There is no re-implemented SQL
and no hand-rolled score parsing (a naive file scrape is wrong for the
~57 clients whose scores live in subcap-level workbooks that only
`scoring_workbook.py` aggregates). Parity is by construction.

The ingest source of truth is NOT this folder — it is the backfill. This
snapshot exists so the dashboard never paints empty/stale on a cold load;
the live API replaces it on the first refetch.

ARTIFACTS (written under --out, default ../startup-data)
  clients/{display_id}.json  one per ACTIVE scored client (identity +
                             latest_run + scores{overall,pillars,subcaps}
                             + top_platform + open_alerts)
  scores.json                {generated_at, source_sha, clients:[…]}
  dashboard.json             {generated_at, source_sha, dashboard, entity_cards}
  manifest.json              {generated_at, source_sha, client_count, display_ids}
  README.md                  contract note (this folder is a snapshot)

MODES
  (default / write)  regenerate every artifact, deterministically.
  --check            diff vs the committed files. A STRUCTURAL mismatch
                     (different display_id set, missing keys, missing KPI
                     tile kinds) exits 1; value-only drift (scores moved)
                     warns and exits 0 — the API owns live freshness.
  --seed-missing     idempotent summary-grade UPSERT into the DB for any
                     display_id present in the committed clients/*.json but
                     absent from the DB. Degraded-deploy fallback ONLY; full
                     fidelity always comes from `historical_backfill --dir`.

Usage:
  python -m app.scripts.export_startup_data --out ../startup-data \
      --sha $(git rev-parse --short HEAD)
  python -m app.scripts.export_startup_data --check
  STARTUP_DATA_MODE=check python -m app.scripts.export_startup_data   # §2c hook
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker
from app.deps import CurrentUser
from app.routers.entities import dashboard as dashboard_handler
from app.routers.entities import list_entities as list_entities_handler
from app.services.entity_name_sanity import check_institution_name

# A synthetic ADMIN principal so the route handlers return the full,
# unstripped `owner=all` / `scope=all` payload (no audience strip, no
# my-clients gating). user_id is the all-zero UUID — it owns nothing, so
# the my_clients tile is 0 (irrelevant to the snapshot).

# The ASGI-transport sweep issues 13 requests x 94 clients — httpx logs
# each at INFO, flooding the Cloud Build log with >1,200 useless lines
# per invocation (2026-07-05 operator complaint). Real failures still
# surface: non-2xx handling below + WARNING-and-up stay visible.
logging.getLogger("httpx").setLevel(logging.WARNING)

EXPORTER_USER = CurrentUser(
    user_id="00000000-0000-0000-0000-000000000000",
    email="startup-data@exporter.local",
    role="ADMIN",
    name="Startup Data Exporter",
)

# The four KPI kinds the wireframe strip binds. Their presence in
# dashboard.json is a structural invariant (--check fails if any is gone).
REQUIRED_TILE_KINDS = ("assessment_count", "open_alerts", "insight_count", "avg_maturity")
DEFAULT_MIN_CLIENTS = 90


def _resolve_source_sha() -> str:
    """Freshness stamp for scores/dashboard/manifest.json `source_sha`.

    Mirrors export_startup_pages (master plan Part 14): `SOURCE_SHA` env
    wins (the Cloud Build regen stage passes `${_IMAGE_SHA}` — it ALSO
    passes an explicit `--sha`, which takes precedence over this default);
    a local run without the env stamps a truthful `local-<git short sha>`;
    only a git-less checkout falls back to `"unknown"`.
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


def _dumps(obj: object) -> str:
    """Deterministic, diff-friendly JSON: 2-space indent, sorted keys,
    trailing newline."""
    return json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"


async def _fetch_cards(session) -> list:
    resp = await list_entities_handler(
        user=EXPORTER_USER, session=session, owner="all",
        subvertical=None, search=None, limit=500, offset=0,
    )
    return resp.items


async def _fetch_dashboard(session):
    return await dashboard_handler(user=EXPORTER_USER, session=session, scope="all")


async def _fetch_client_detail(session, entity_id: str) -> dict | None:
    """Latest ACTIVE run metadata + its subcap scores for one entity."""
    run = (
        await session.execute(
            text(
                """
                SELECT id::text AS run_id, request_id, status, data_source,
                       evidence_mode, ccg_catalog_version, assessment_date,
                       completed_at, overall_score
                FROM runs
                WHERE entity_id = :eid AND status = 'ACTIVE'
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """
            ),
            {"eid": entity_id},
        )
    ).first()
    if run is None:
        return None
    subcaps = (
        await session.execute(
            text(
                """
                SELECT subcap_id, score, COALESCE(is_thin_evidence, false) AS thin
                FROM subcap_scores
                WHERE run_id = :rid
                ORDER BY subcap_id
                """
            ),
            {"rid": run.run_id},
        )
    ).all()
    return {
        "latest_run": {
            "request_id": run.request_id,
            "status": run.status,
            "data_source": run.data_source,
            "evidence_mode": run.evidence_mode,
            "assessment_date": run.assessment_date.isoformat()
            if run.assessment_date else None,
            "completed_at": run.completed_at.isoformat()
            if run.completed_at else None,
            "ccg_catalog_version": run.ccg_catalog_version,
        },
        "subcaps": [
            {"id": s.subcap_id, "score": round(float(s.score), 2), "thin": bool(s.thin)}
            for s in subcaps
            if s.score is not None
        ],
    }


def _is_synthetic(name: str | None) -> bool:
    """CI fixture entities (seed_ci's 'Richbank Community Trust
    (synthetic)') must never ship in the committed pack — a deploy-sim
    or seed run can leave them ACTIVE in the export DB, and the 94-client
    contract (commit b4cd359) excludes them by name marker."""
    return "(synthetic)" in (name or "").lower()


async def build_snapshot(session, sha: str) -> dict:
    """Build every artifact in memory; returns {relpath: text}."""
    all_cards = await _fetch_cards(session)
    cards = [c for c in all_cards if not _is_synthetic(c.name)]
    dash = await _fetch_dashboard(session)
    n_synth = len(all_cards) - len(cards)
    if n_synth:
        # Keep pack-internal parity (tile == entity_cards == real clients):
        # the dashboard handler counts every ACTIVE entity in the DB,
        # including the excluded synthetics.
        for tile in dash.tiles:
            if tile.kind in ("assessment_count", "recent_completions"):
                tile.value = max(0, int(tile.value) - n_synth)
    generated_at = datetime.now(UTC).isoformat()

    files: dict[str, str] = {}
    scores_clients: list[dict] = []

    # Per-client files — sorted by display_id for deterministic filenames.
    for card in sorted(cards, key=lambda c: c.display_id):
        detail = await _fetch_client_detail(session, card.id)
        pillars = card.pillar_scores or {}
        client_doc = {
            "display_id": card.display_id,
            "identity": {
                "display_id": card.display_id,
                "name": card.name,
                "domain": card.domain,
                "subvertical": card.subvertical,
                "lobs": list(card.lobs or []),
                "hq": card.hq,
            },
            "latest_run": (detail or {}).get("latest_run"),
            "scores": {
                "overall": card.overall_score,
                "pillars": {k: pillars.get(k) for k in ("P1", "P2", "P3", "P4")},
                "subcaps": (detail or {}).get("subcaps", []),
            },
            "top_platform": card.top_platform.model_dump() if card.top_platform else None,
            "open_alerts": card.open_alerts,
        }
        files[f"clients/{card.display_id}.json"] = _dumps(client_doc)
        scores_clients.append({
            "display_id": card.display_id,
            "name": card.name,
            "subvertical": card.subvertical,
            "overall": card.overall_score,
            "pillars": {k: pillars.get(k) for k in ("P1", "P2", "P3", "P4")},
        })

    files["scores.json"] = _dumps({
        "generated_at": generated_at,
        "source_sha": sha,
        "clients": scores_clients,  # already display_id-sorted
    })

    # dashboard.json keeps the API's card order (updated_at DESC) — that is
    # what the live endpoint returns and what the "Recent assessments" grid
    # paints; it is stable within a DB snapshot. mode="json" → ISO datetimes.
    files["dashboard.json"] = _dumps({
        "generated_at": generated_at,
        "source_sha": sha,
        "dashboard": dash.model_dump(mode="json"),
        "entity_cards": [c.model_dump(mode="json") for c in cards],
    })

    display_ids = sorted(c.display_id for c in cards)
    files["manifest.json"] = _dumps({
        "generated_at": generated_at,
        "source_sha": sha,
        "client_count": len(cards),
        "display_ids": display_ids,
    })

    files["README.md"] = _README
    return files


def validate(files: dict[str, str], min_clients: int) -> tuple[list[str], list[str]]:
    """Returns (fatal_errors, warnings). Empty errors = pass.

    FATAL: too few clients; a missing KPI tile kind; a client with NO
    overall or NO pillars at all; a junk institution name; tiles⇄cards
    aggregate mismatch. WARNING: a partial assessment (1-3 of 4 pillars) —
    an honest data gap in that DMA package (e.g. ATB ships no P2 subcaps),
    rendered as an empty mini-bar rather than fabricated.
    """
    errors: list[str] = []
    warnings: list[str] = []
    manifest = json.loads(files["manifest.json"])
    scores = json.loads(files["scores.json"])
    dash = json.loads(files["dashboard.json"])

    n = manifest["client_count"]
    if n < min_clients:
        errors.append(f"client_count {n} < --min-clients {min_clients}")

    tile_kinds = {t["kind"] for t in dash["dashboard"]["tiles"]}
    for kind in REQUIRED_TILE_KINDS:
        if kind not in tile_kinds:
            errors.append(f"dashboard.json missing required KPI tile kind '{kind}'")

    for c in scores["clients"]:
        if c["overall"] is None:
            errors.append(f"{c['display_id']}: missing overall score")
        present = [p for p in ("P1", "P2", "P3", "P4")
                   if (c["pillars"] or {}).get(p) is not None]
        if not present:
            errors.append(f"{c['display_id']}: no pillar scores at all")
        elif len(present) < 4:
            missing = [p for p in ("P1", "P2", "P3", "P4") if p not in present]
            warnings.append(
                f"{c['display_id']}: partial assessment — {len(present)}/4 pillars "
                f"(missing {','.join(missing)}); rendered as a gap, not fabricated"
            )
        is_junk, reason = check_institution_name(c["name"])
        if is_junk:
            errors.append(f"{c['display_id']}: name fails sanity ({reason}): {c['name']!r}")

    # Aggregate parity: the assessment_count tile must equal the number of
    # entity_cards (DISTINCT ACTIVE entities with an ACTIVE run).
    counts = {t["kind"]: t["value"] for t in dash["dashboard"]["tiles"]}
    if counts.get("assessment_count") != len(dash["entity_cards"]):
        errors.append(
            f"assessment_count tile ({counts.get('assessment_count')}) != "
            f"entity_cards ({len(dash['entity_cards'])})"
        )
    return errors, warnings


def _structural_signature(files: dict[str, str]) -> dict:
    """The structure --check guards (display_id set, per-client top-level
    keys, KPI tile kinds, entity_card key set). Value drift is NOT here."""
    manifest = json.loads(files["manifest.json"])
    dash = json.loads(files["dashboard.json"])
    client_keys = {}
    for rel, txt in files.items():
        # Only the sidecar clients/{id}.json (one path segment). The per-page
        # subdir payloads clients/{id}/{page}.json are owned by
        # export_startup_pages and validated by ITS --verify gate; including
        # them here (they only exist on disk, never in this script's fresh
        # output) would spuriously fail --check.
        if rel.startswith("clients/") and rel.count("/") == 1:
            client_keys[rel] = sorted(json.loads(txt).keys())
    card_keys = (
        sorted(dash["entity_cards"][0].keys()) if dash["entity_cards"] else []
    )
    return {
        "display_ids": manifest["display_ids"],
        "tile_kinds": sorted({t["kind"] for t in dash["dashboard"]["tiles"]}),
        "card_keys": card_keys,
        "client_files": sorted(client_keys),
        "client_top_keys": client_keys,
    }


def _read_committed(out: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for p in out.rglob("*"):
        if p.is_file():
            files[p.relative_to(out).as_posix()] = p.read_text()
    return files


async def _seed_missing(session, out: Path) -> int:
    """Summary-grade UPSERT for committed clients absent from the DB.

    Degraded-deploy fallback only — seeds the entity + one ACTIVE run +
    subcap_scores so the page is not empty when the full backfill could
    not run (e.g. Drive unreachable + no corpus mounted). Idempotent:
    skips display_ids already present.
    """
    clients_dir = out / "clients"
    if not clients_dir.is_dir():
        print(f"--seed-missing: no committed {clients_dir} — nothing to do", flush=True)
        return 0
    present = {
        r[0] for r in (
            await session.execute(text("SELECT display_id FROM entities"))
        ).all()
    }
    seeded = 0
    for f in sorted(clients_dir.glob("*.json")):
        doc = json.loads(f.read_text())
        did = doc["display_id"]
        if did in present:
            continue
        ident = doc["identity"]
        scores = doc["scores"]
        run_meta = doc.get("latest_run") or {}
        eid = (await session.execute(
            text(
                """
                INSERT INTO entities (id, display_id, name, domain, subvertical,
                                      lobs, status, created_at, updated_at)
                VALUES (gen_random_uuid(), :did, :name, :domain, :sv,
                        :lobs, 'ACTIVE', NOW(), NOW())
                ON CONFLICT (display_id) DO NOTHING
                RETURNING id
                """
            ),
            {"did": did, "name": ident["name"], "domain": ident.get("domain"),
             "sv": ident.get("subvertical"), "lobs": ident.get("lobs") or []},
        )).scalar_one_or_none()
        if eid is None:
            continue
        rid = (await session.execute(
            text(
                """
                INSERT INTO runs (id, entity_id, request_id, status, data_source,
                                  evidence_mode, ccg_catalog_version, overall_score,
                                  completed_at, created_at, updated_at)
                VALUES (gen_random_uuid(), :eid, :req, 'ACTIVE', 'MANUAL_BACKFILL',
                        :em, :cv, :ov, NOW(), NOW(), NOW())
                RETURNING id
                """
            ),
            {"eid": eid, "req": (run_meta.get("request_id") or f"SEED-{did}")[:64],
             "em": run_meta.get("evidence_mode") or "public",
             "cv": run_meta.get("ccg_catalog_version") or "v7.0",
             "ov": scores.get("overall")},
        )).scalar_one()
        for sc in scores.get("subcaps", []):
            await session.execute(
                text(
                    """
                    INSERT INTO subcap_scores (id, run_id, entity_id, subcap_id,
                                               score, is_thin_evidence, created_at)
                    VALUES (gen_random_uuid(), :rid, :eid, :sid, :score, :thin, NOW())
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"rid": rid, "eid": eid, "sid": sc["id"],
                 "score": sc["score"], "thin": sc.get("thin", False)},
            )
        seeded += 1
        print(f"--seed-missing: seeded {did} ({ident['name']})", flush=True)
    await session.commit()
    print(f"--seed-missing: {seeded} client(s) seeded", flush=True)
    return seeded


_README = """\
# startup-data

A **read-only snapshot of the seeded database**, produced by
`python -m app.scripts.export_startup_data` AFTER the JSON backfill
(`historical_backfill --dir`) + the §2c derive chain have run.

It is the dashboard's first-paint payload so the page never loads empty or
stale; the live API replaces it on the first refetch.

**This folder is NOT the ingest source of truth.** The source of truth is
the DMA package corpus ingested by `historical_backfill`. Do not hand-edit
these files — regenerate them.

Files:
- `clients/{display_id}.json` — one per ACTIVE scored client (identity,
  latest run, scores: overall + P1-P4 pillars + per-subcap; top platform;
  open alerts). Numbers only — no prose/evidence.
- `scores.json` — compact {display_id, name, subvertical, overall, pillars}
  for every client.
- `dashboard.json` — the `/dashboard` response + the `/entities` cards,
  exactly as the API emits them (the first-paint bundle).
- `manifest.json` — client_count + the sorted display_id roster.

Regenerate + verify:
```
python -m app.scripts.export_startup_data --out ../startup-data --sha $(git rev-parse --short HEAD)
python -m app.scripts.export_startup_data --check
```
"""


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="Export startup-data snapshot")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "startup-data"))
    ap.add_argument("--sha", default=None,
                    help="freshness stamp; default SOURCE_SHA env, else "
                         "local-<git short sha>, else 'unknown'")
    ap.add_argument("--min-clients", type=int, default=DEFAULT_MIN_CLIENTS)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seed-missing", action="store_true")
    args = ap.parse_args()

    # §2c hook: STARTUP_DATA_MODE=check forces --check without changing argv.
    if os.environ.get("STARTUP_DATA_MODE", "").lower() == "check":
        args.check = True

    out = Path(args.out).resolve()
    sha = args.sha or _resolve_source_sha()
    sm = get_sessionmaker()

    if args.seed_missing:
        async with sm() as session:
            await _seed_missing(session, out)
        return 0

    async with sm() as session:
        files = await build_snapshot(session, sha)

    errors, warnings = validate(files, args.min_clients)
    for w in warnings:
        print(f"WARN: {w}", flush=True)
    if errors:
        print("FATAL: startup-data validation failed:", flush=True)
        for e in errors:
            print(f"  - {e}", flush=True)
        return 1

    if args.check:
        committed = _read_committed(out)
        if not committed:
            print(f"FATAL --check: no committed snapshot at {out}", flush=True)
            return 1
        fresh_sig = _structural_signature(files)
        # The committed files carry their own (possibly older) sha/timestamp;
        # rebuild the committed signature from disk for an apples-to-apples
        # structural compare.
        comm_sig = _structural_signature(committed)
        if fresh_sig != comm_sig:
            print("FATAL --check: STRUCTURAL mismatch vs committed startup-data:", flush=True)
            if fresh_sig["display_ids"] != comm_sig["display_ids"]:
                added = sorted(set(fresh_sig["display_ids"]) - set(comm_sig["display_ids"]))
                removed = sorted(set(comm_sig["display_ids"]) - set(fresh_sig["display_ids"]))
                print(f"  display_id set changed: +{added} -{removed}", flush=True)
            if fresh_sig["tile_kinds"] != comm_sig["tile_kinds"]:
                print(f"  tile kinds: {comm_sig['tile_kinds']} -> {fresh_sig['tile_kinds']}", flush=True)
            if fresh_sig["card_keys"] != comm_sig["card_keys"]:
                print(f"  card keys: {comm_sig['card_keys']} -> {fresh_sig['card_keys']}", flush=True)
            if fresh_sig["client_files"] != comm_sig["client_files"]:
                fa, ca = set(fresh_sig["client_files"]), set(comm_sig["client_files"])
                print(f"  client files: +{sorted(fa - ca)[:5]} -{sorted(ca - fa)[:5]}", flush=True)
            if fresh_sig["client_top_keys"] != comm_sig["client_top_keys"]:
                diff = [k for k in fresh_sig["client_top_keys"]
                        if comm_sig["client_top_keys"].get(k) != fresh_sig["client_top_keys"][k]]
                print(f"  client top-keys differ in {len(diff)} file(s), e.g. {diff[:3]}", flush=True)
            return 1
        # Structure matches; report value drift as a non-fatal warning.
        drift = sum(
            1 for rel in files
            if rel in committed and files[rel] != committed[rel]
        )
        if drift:
            print(
                f"WARN --check: {drift} file(s) differ in VALUES only "
                "(structure intact; the live API owns freshness).",
                flush=True,
            )
        print(f"OK --check: structure matches; {len(files)} files.", flush=True)
        return 0

    # Write mode.
    out.mkdir(parents=True, exist_ok=True)
    (out / "clients").mkdir(parents=True, exist_ok=True)
    # Remove stale per-client files (clients dropped from the corpus).
    # The committed gold-standard overlays (refinement/) are INPUTS to the
    # countercheck gate, not export products — never garbage-collect them.
    wanted = set(files)
    for p in list(out.rglob("*")):
        if p.is_file():
            rel = p.relative_to(out).as_posix()
            if rel.startswith("refinement/") or rel == "README.md":
                continue
            if rel not in wanted:
                p.unlink()
    for rel, txt in files.items():
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt)
    manifest = json.loads(files["manifest.json"])
    print(
        f"OK: wrote startup-data to {out} — {manifest['client_count']} clients, "
        f"{len(files)} files, sha={sha}",
        flush=True,
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
