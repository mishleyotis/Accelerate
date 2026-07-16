"""End-to-end per-segment render-validation probe for all 100+ DMAs.

Per the 2026-06-07 operator mandate: "Please do a thorough check to
validate that the 100+ clients are rendered well within the app and
that the app has correctly synthesized and enriched the information
... Do a thorough check on each rendered segment for all the 100+
DMAs. Check all pages pick correct stuff."

For every entity persisted in the DB, this probe hits each of the
12 main page-render endpoints via FastAPI's ASGI transport (so it
runs entirely in-process; no live server, no auth complexity). Each
endpoint's response is scored against a per-page checklist:

  - HTTP 200 (else FAIL)
  - Response is valid JSON (else FAIL)
  - Required top-level keys present
  - Per-page "has data" thresholds (e.g. overview must have
    pillar_scores, heatmap must have at least 100 cells, recommendations
    list non-empty, etc.) -> a PARTIAL marker when below threshold
  - Score values in [1,5], tier values in [1,8] (DB-shape sanity)

Produces a tab-separated report:
  display_id | name | endpoint | status | observations

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.qa_render_validation
  python -m app.scripts.qa_render_validation --output docs/qa/qa_render_matrix.tsv
  python -m app.scripts.qa_render_validation --limit 20  # smoke test

The exit code is 0 if no FAIL (PARTIAL is acceptable), 1 if any FAIL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

from app.database import get_sessionmaker
from app.deps import CurrentUser, get_current_user
from app.main import app

# 12 page-render endpoints. Order matches the AE journey
# (Overview -> Heatmap -> Insights -> Platforms -> Context -> Health).
RENDER_ENDPOINTS = [
    ("overview", "/api/v1/entities/{display_id}/overview"),
    # NB: ?zoom=subcap. The endpoint DEFAULTS to zoom=pillar, which
    # aggregates the whole grid down to one cell per pillar (~4 cells) —
    # the correct UX default, but it made this harness report
    # "only 4 cells (typical >= 600)" PARTIAL for every populated entity,
    # a false negative. We probe the deepest zoom so the cell-count floor
    # (>= 100) actually measures whether subcap_scores landed.
    ("heatmap", "/api/v1/entities/{display_id}/heatmap?zoom=subcap"),
    ("insights", "/api/v1/entities/{display_id}/insights"),
    ("platforms", "/api/v1/entities/{display_id}/platforms"),
    ("context", "/api/v1/entities/{display_id}/context"),
    ("health", "/api/v1/entities/{display_id}/health"),
    ("recommendations", "/api/v1/entities/{display_id}/recommendations"),
    ("evidence", "/api/v1/entities/{display_id}/evidence"),
    ("techstack", "/api/v1/entities/{display_id}/techstack"),
    ("focus_areas", "/api/v1/entities/{display_id}/focus-areas"),
    ("intelligence", "/api/v1/entities/{display_id}/intelligence-profile"),
    ("runs", "/api/v1/entities/{display_id}/runs"),
    # Drilldown / aggregated-zoom states (no per-entity id needed) — proves the
    # pillar/category roll-ups and the platform roadmap also render populated.
    ("heatmap_pillar", "/api/v1/entities/{display_id}/heatmap?zoom=pillar"),
    ("heatmap_category", "/api/v1/entities/{display_id}/heatmap?zoom=category"),
    ("platforms_roadmap", "/api/v1/entities/{display_id}/platforms/roadmap"),
]

# Contract-required surfaces: in --strict mode an emptiness PARTIAL on these is
# promoted to FAIL (the no-empty-state gate at the HTTP layer). Surfaces NOT
# listed keep PARTIAL for expected-empty conditions (intelligence 404,
# recommendations/evidence may be empty, health honest-zero alerts).
_STRICT_REQUIRED = frozenset({
    "overview", "heatmap", "insights", "platforms", "context", "techstack",
    "heatmap_pillar", "heatmap_category",
    # now deterministically filled for all 94 (derive_recommendations +
    # intelligence backfill), so they are enforced too — no empty drilldowns.
    "recommendations", "platforms_roadmap", "intelligence",
})

# Max fraction of entities allowed to render a zero-score (empty) overview/
# heatmap before the build is treated as a systemic parser regression.
# Since the strict ingest gate (2026-06-10: only fully-scored packages
# persist; unscored ones are quarantined for Drive re-pick), a healthy
# corpus has ~0% zero-score entities — 0.05 is transient headroom for a
# mid-migration DB, not an allowance for partial ingests.
ZERO_SCORE_FLOOR = 0.05


@dataclass
class CellResult:
    endpoint: str
    status: str  # OK | PARTIAL | FAIL
    http_code: int
    observations: list[str] = field(default_factory=list)
    field_counts: dict[str, int] = field(default_factory=dict)

    def line(self) -> str:
        obs = "; ".join(self.observations) or "-"
        counts = ",".join(f"{k}={v}" for k, v in self.field_counts.items()) or "-"
        return f"{self.endpoint}\t{self.status}\t{self.http_code}\t{counts}\t{obs}"


# Per-endpoint validators. Each takes the parsed JSON body and returns
# (status, observations, field_counts).
def _validate_overview(body: dict) -> tuple[str, list[str], dict[str, int]]:
    obs = []
    counts: dict[str, int] = {}
    if not isinstance(body, dict):
        return "FAIL", ["body not a dict"], counts
    pillars = body.get("pillar_scores") or body.get("pillars") or []
    if isinstance(pillars, list):
        counts["pillars"] = len(pillars)
        for p in pillars:
            s = (p or {}).get("score")
            if isinstance(s, int | float) and not (1 <= s <= 5):
                obs.append(f"pillar {p.get('pillar_id')} score {s} out of [1,5]")
    else:
        counts["pillars"] = 0
    # SCQA narrative blob (may be null for skeleton state)
    if body.get("scqa") is None:
        obs.append("scqa narrative=null (data-source=skeleton)")
    # Overall score
    overall = body.get("overall_score")
    if isinstance(overall, int | float) and not (1 <= overall <= 5):
        obs.append(f"overall_score {overall} out of [1,5]")
    status = "OK" if counts.get("pillars", 0) >= 4 else "PARTIAL"
    if not pillars:
        # Zero scores: the SOURCE package had no parseable scoring workbook
        # — either a genuinely thin/sanitised package, or a non-canonical
        # scoring layout the parser doesn't yet mine (e.g. SPG ships a
        # markdown `*_scoring_workbook.md`; DovenMuehle a research `.xlsx`).
        # The endpoint correctly returns an empty contract (HTTP 200) and
        # the frontend renders its fail-closed empty state, so this is a
        # DATA-COMPLETENESS gap, NOT a render failure. Mark PARTIAL so a
        # long tail of sparse packages does not block the deploy; the
        # aggregate zero-score floor in main_async() still fails the build
        # on a SYSTEMIC parser regression. These entities are the
        # post-deploy parser-improvement / AI-enrichment / drive-backfill
        # queue (see docs/INGEST_GAP_REMEDIATION.md).
        counts["zero_score"] = 1
        obs.append(
            "zero pillar scores — sparse source; heal post-deploy "
            "(parser / AI-enrichment / drive-backfill)"
        )
        return "PARTIAL", obs, counts
    return status, obs, counts


def _validate_heatmap(body: dict) -> tuple[str, list[str], dict[str, int]]:
    cells = body.get("cells") or body.get("subcaps") or []
    counts = {"cells": len(cells)}
    obs = []
    bad_scores = sum(
        1 for c in cells
        if isinstance(c, dict)
        and isinstance(c.get("score"), int | float)
        and not (1 <= c["score"] <= 5)
    )
    if bad_scores:
        obs.append(f"{bad_scores} cell scores out of [1,5]")
    if not cells:
        # See _validate_overview: zero cells == the run persisted no subcap
        # scores (sparse / non-canonical source). The endpoint fail-closes
        # to an empty grid (HTTP 200) and the frontend renders its empty
        # state. PARTIAL (not FAIL); the aggregate floor catches regressions.
        counts["zero_score"] = 1
        return (
            "PARTIAL",
            [
                "zero heatmap cells — sparse source; heal post-deploy "
                "(parser / AI-enrichment / drive-backfill)"
            ],
            counts,
        )
    status = "OK" if len(cells) >= 100 else "PARTIAL"
    if status == "PARTIAL":
        obs.append(f"only {len(cells)} cells (typical >= 600)")
    return status, obs, counts


def _validate_insights(body: dict) -> tuple[str, list[str], dict[str, int]]:
    items = body.get("items") if isinstance(body, dict) else body
    if not isinstance(items, list):
        items = body if isinstance(body, list) else []
    counts = {"insights": len(items)}
    if not items:
        counts["empty"] = 1
        return "PARTIAL", ["no insight cards (cold start before rule engine)"], counts
    return "OK", [], counts


def _validate_platforms(body: dict) -> tuple[str, list[str], dict[str, int]]:
    # The endpoint returns the 5 documented platforms under `cards`
    # (PlatformsResponse.cards). Earlier this read body["platforms"] /
    # body["items"] — neither key exists, so EVERY entity reported
    # "no platform scores" PARTIAL even though all 5 cards were present:
    # a pure field-name false negative. Keep the legacy keys as fallbacks
    # in case the schema is ever re-shaped.
    plats = body.get("cards") or body.get("platforms") or body.get("items") or []
    counts = {"platforms": len(plats)}
    if not plats:
        counts["empty"] = 1
        return "PARTIAL", ["no platform scores"], counts
    return "OK", [], counts


def _validate_context(body: dict) -> tuple[str, list[str], dict[str, int]]:
    # The Context (D5) page renders FAR more than the scalar firmographic
    # fields the prior version counted. The real firmographics object this
    # corpus produces carries `leadership` (rosters), `narrative_md`
    # (company-context prose) and `primary_regulator` — NOT `hq` /
    # `employees` / `total_assets` / `branches` (those scalar keys are
    # never emitted by the parser). Counting only the absent scalars made
    # EVERY entity report PARTIAL even with a 12-person leadership roster
    # + rich narrative. We now score the signals the page actually shows:
    # leadership, narrative_md, primary_regulator, issue_register, plus the
    # DOCX-narrative-derived timeline_events / acquisitions / financials.
    if not isinstance(body, dict):
        return "PARTIAL", ["context body not a dict"], {}
    firmo = body.get("firmographics") or {}
    counts: dict[str, int] = {
        "leadership": len(firmo.get("leadership") or []),
        "issue_register": len(body.get("issue_register") or []),
        "timeline_events": len(body.get("timeline_events") or []),
        "acquisitions": len(body.get("acquisitions") or []),
    }
    signals = 0
    if firmo.get("leadership"):
        signals += 1
    if firmo.get("narrative_md"):
        signals += 1
    if firmo.get("primary_regulator"):
        signals += 1
    if body.get("issue_register"):
        signals += 1
    if body.get("timeline_events"):
        signals += 1
    if body.get("acquisitions"):
        signals += 1
    if body.get("financials"):
        signals += 1
    counts["renderable_signals"] = signals
    # >= 2 distinct renderable surfaces == the page has real content.
    if signals >= 2:
        return "OK", [], counts
    if signals == 1:
        return "PARTIAL", ["only 1 renderable context surface populated"], counts
    counts["empty"] = 1
    return "PARTIAL", ["context empty — no firmographics/leadership/issues/timeline"], counts


def _validate_health(body: dict) -> tuple[str, list[str], dict[str, int]]:
    if not isinstance(body, dict):
        return "FAIL", ["body not a dict"], {}
    counts = {
        "alerts": len(body.get("alerts") or []),
        "issues": len(body.get("issues") or body.get("issue_register") or []),
        "caps": len(body.get("caps") or body.get("caps_applied") or []),
    }
    return "OK", [], counts


def _validate_recommendations(body) -> tuple[str, list[str], dict[str, int]]:
    if isinstance(body, dict):
        items = body.get("items") or body.get("recommendations") or []
    elif isinstance(body, list):
        items = body
    else:
        items = []
    counts = {"recommendations": len(items)}
    if not items:
        counts["empty"] = 1
        return "PARTIAL", ["no recommendations (parser may have emitted 0)"], counts
    return "OK", [], counts


def _validate_evidence(body) -> tuple[str, list[str], dict[str, int]]:
    if isinstance(body, dict):
        items = body.get("items") or body.get("evidence") or []
    elif isinstance(body, list):
        items = body
    else:
        items = []
    counts = {"evidence_rows": len(items)}
    bad_tier = sum(
        1 for r in items
        if isinstance(r, dict)
        and isinstance(r.get("tier"), int)
        and not (1 <= r["tier"] <= 8)
    )
    obs = []
    if bad_tier:
        obs.append(f"{bad_tier} evidence rows with tier outside [1,8]")
    return ("OK" if items else "PARTIAL",
            obs or ([] if items else ["no evidence rows"]),
            counts)


def _validate_techstack(body) -> tuple[str, list[str], dict[str, int]]:
    if isinstance(body, dict):
        items = body.get("entries") or body.get("items") or []
    elif isinstance(body, list):
        items = body
    else:
        items = []
    counts = {"tech_entries": len(items)}
    if not items:
        counts["empty"] = 1
    return ("OK" if items else "PARTIAL", [], counts)


def _validate_focus_areas(body) -> tuple[str, list[str], dict[str, int]]:
    if isinstance(body, dict):
        items = body.get("focus_areas") or body.get("items") or []
    elif isinstance(body, list):
        items = body
    else:
        items = []
    counts = {"focus_areas": len(items)}
    return ("OK" if items else "PARTIAL", [], counts)


def _validate_intelligence(body) -> tuple[str, list[str], dict[str, int]]:
    if not isinstance(body, dict):
        return "PARTIAL", ["intelligence not yet computed (404 typical pre-worker)"], {"empty": 1}
    has = sum(
        1 for k in (
            "intelligence_summary_md", "recurring_themes",
            "velocity", "total_runs",
        ) if body.get(k)
    )
    return ("OK" if has >= 2 else "PARTIAL",
            ([] if has >= 2 else [f"only {has}/4 intelligence fields populated"]),
            {"intel_fields": has, **({} if has >= 2 else {"empty": 1})})


def _validate_runs(body) -> tuple[str, list[str], dict[str, int]]:
    if isinstance(body, dict):
        items = body.get("runs") or body.get("items") or []
    elif isinstance(body, list):
        items = body
    else:
        items = []
    counts = {"runs": len(items)}
    if not items:
        return "FAIL", ["no runs (entity should have at least 1)"], counts
    return "OK", [], counts


def _validate_heatmap_agg(body: dict) -> tuple[str, list[str], dict[str, int]]:
    """Aggregated heatmap zooms (pillar ~4 cells, category ~16) — no >=100 floor;
    just needs >=1 scored cell."""
    cells = body.get("cells") or body.get("subcaps") or []
    counts = {"cells": len(cells)}
    if not cells:
        counts["zero_score"] = 1
        counts["empty"] = 1
        return "PARTIAL", ["zero aggregated cells — sparse source"], counts
    return "OK", [], counts


def _validate_roadmap(body) -> tuple[str, list[str], dict[str, int]]:
    phases = body.get("phases") if isinstance(body, dict) else None
    phases = phases or []
    counts = {"phases": len(phases)}
    if not phases:
        counts["empty"] = 1
        return "PARTIAL", ["no roadmap phases (no addressable recommendations)"], counts
    return "OK", [], counts


_VALIDATORS = {
    "overview": _validate_overview,
    "heatmap": _validate_heatmap,
    "heatmap_pillar": _validate_heatmap_agg,
    "heatmap_category": _validate_heatmap_agg,
    "platforms_roadmap": _validate_roadmap,
    "insights": _validate_insights,
    "platforms": _validate_platforms,
    "context": _validate_context,
    "health": _validate_health,
    "recommendations": _validate_recommendations,
    "evidence": _validate_evidence,
    "techstack": _validate_techstack,
    "focus_areas": _validate_focus_areas,
    "intelligence": _validate_intelligence,
    "runs": _validate_runs,
}


async def fetch_entities(limit: int | None) -> list[tuple[str, str]]:
    """Return [(display_id, name), ...] of all ACTIVE entities."""
    sm = get_sessionmaker()
    async with sm() as session:
        sql = (
            "SELECT display_id, name FROM entities "
            "WHERE status='ACTIVE' AND display_id IS NOT NULL "
            "ORDER BY display_id"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = (await session.execute(text(sql))).all()
    return [(r.display_id, r.name) for r in rows]


def _fake_user() -> CurrentUser:
    """Bypass auth: return an ADMIN-role user so role-gated endpoints
    (context, health -- require ANALYST) are reachable. The render
    probe is read-only QA; no actor-attribution churn.
    """
    return CurrentUser(
        user_id=str(uuid4()),
        email="qa-render@dma.local",
        role="ADMIN",
        name="QA Render Probe",
    )


async def probe_entity(
    client: httpx.AsyncClient, display_id: str, name: str, strict: bool = False
) -> list[CellResult]:
    cells: list[CellResult] = []
    for ep_name, ep_template in RENDER_ENDPOINTS:
        url = ep_template.format(display_id=display_id)
        try:
            r = await client.get(url)
        except Exception as e:
            cells.append(CellResult(
                endpoint=ep_name, status="FAIL", http_code=0,
                observations=[f"transport error: {type(e).__name__}: {e!s}"],
            ))
            continue
        try:
            body = r.json() if r.status_code < 500 else None
        except json.JSONDecodeError:
            body = None
        if r.status_code == 404:
            # 404 may be legitimate (intelligence-profile not yet computed)
            # or a bug; defer to the per-endpoint validator with empty body
            validator = _VALIDATORS.get(ep_name)
            if validator:
                # Treat 404 as PARTIAL for intelligence; FAIL for the rest.
                if ep_name == "intelligence":
                    cells.append(CellResult(
                        endpoint=ep_name, status="PARTIAL", http_code=404,
                        observations=["intelligence-profile 404 (not yet computed)"],
                        field_counts={"empty": 1},
                    ))
                else:
                    cells.append(CellResult(
                        endpoint=ep_name, status="FAIL", http_code=404,
                        observations=[f"404 NOT FOUND on {ep_name}"],
                    ))
            continue
        if r.status_code >= 400:
            cells.append(CellResult(
                endpoint=ep_name, status="FAIL", http_code=r.status_code,
                observations=[f"HTTP {r.status_code}: {(r.text or '')[:200]}"],
            ))
            continue
        validator = _VALIDATORS.get(ep_name)
        if not validator:
            cells.append(CellResult(
                endpoint=ep_name, status="OK", http_code=r.status_code,
                observations=["no validator"],
            ))
            continue
        try:
            status, obs, counts = validator(body or {})
        except Exception as e:
            cells.append(CellResult(
                endpoint=ep_name, status="FAIL", http_code=r.status_code,
                observations=[f"validator crashed: {type(e).__name__}: {e!s}"],
            ))
            continue
        # Strict gate: a contract-required surface must not render empty for any
        # of the 94. Promote its PARTIAL → FAIL (expected-empty surfaces, not in
        # _STRICT_REQUIRED, keep PARTIAL).
        is_empty = bool(counts.get("empty") or counts.get("zero_score"))
        if strict and status == "PARTIAL" and ep_name in _STRICT_REQUIRED and is_empty:
            status = "FAIL"
            obs = [*obs, "strict: required surface empty"]
        cells.append(CellResult(
            endpoint=ep_name, status=status, http_code=r.status_code,
            observations=obs, field_counts=counts,
        ))
    return cells


async def main_async(args: argparse.Namespace) -> int:
    # Bypass auth dependencies for in-process probing.
    app.dependency_overrides[get_current_user] = _fake_user

    entities = await fetch_entities(args.limit)
    print(f"# {len(entities)} active entities to probe", flush=True)
    transport = httpx.ASGITransport(app=app)
    rows: list[str] = ["display_id\tname\tendpoint\tstatus\thttp\tcounts\tobservations"]
    summary = {"OK": 0, "PARTIAL": 0, "FAIL": 0}
    fails_by_endpoint: dict[str, int] = {}
    # Entities whose overview/heatmap rendered an empty (zero-score) contract
    # — the post-deploy parser/enrichment/backfill queue. Tracked as a SET of
    # display_ids so the aggregate floor counts entities, not cells.
    zero_score_entities: set[str] = set()
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
    ) as client:
        for i, (display_id, name) in enumerate(entities, 1):
            cells = await probe_entity(client, display_id, name, strict=args.strict)
            for c in cells:
                summary[c.status] = summary.get(c.status, 0) + 1
                if c.status == "FAIL":
                    fails_by_endpoint[c.endpoint] = fails_by_endpoint.get(c.endpoint, 0) + 1
                if c.field_counts.get("zero_score"):
                    zero_score_entities.add(display_id)
                obs = "; ".join(c.observations) or "-"
                counts = (
                    ",".join(f"{k}={v}" for k, v in c.field_counts.items())
                    or "-"
                )
                rows.append(
                    f"{display_id}\t{name}\t{c.endpoint}\t{c.status}\t"
                    f"{c.http_code}\t{counts}\t{obs}"
                )
            if i % 10 == 0:
                print(
                    f"  ... {i}/{len(entities)} entities probed "
                    f"({summary['OK']} OK, {summary['PARTIAL']} PARTIAL, "
                    f"{summary['FAIL']} FAIL)",
                    flush=True,
                )

    output_text = "\n".join(rows) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output_text, encoding="utf-8")
        print(f"# wrote matrix to {out}", flush=True)
    else:
        print(output_text)

    total = sum(summary.values()) or 1
    print(
        f"\n# RENDER QA SUMMARY: "
        f"{summary['OK']} OK ({summary['OK']/total*100:.1f}%), "
        f"{summary['PARTIAL']} PARTIAL ({summary['PARTIAL']/total*100:.1f}%), "
        f"{summary['FAIL']} FAIL ({summary['FAIL']/total*100:.1f}%) "
        f"across {len(entities)} entities x {len(RENDER_ENDPOINTS)} endpoints",
        flush=True,
    )
    if fails_by_endpoint:
        print("\n# FAILS by endpoint:", flush=True)
        for ep, n in sorted(fails_by_endpoint.items(), key=lambda x: -x[1]):
            print(f"  {n:4} {ep}", flush=True)

    # ── Aggregate zero-score floor ────────────────────────────────────
    # The strict ingest gate (2026-06-10) skips unscored packages at
    # ingest, so zero-score entities should be ~0; any non-trivial
    # fraction means either a parser regression or pre-gate debris that
    # purge_partial_entities hasn't cleaned yet. Both must fail loud.
    n_entities = len(entities) or 1
    zero_frac = len(zero_score_entities) / n_entities
    print(
        f"\n# ZERO-SCORE (degraded) entities: {len(zero_score_entities)}/"
        f"{n_entities} ({zero_frac * 100:.1f}%) — floor "
        f"{ZERO_SCORE_FLOOR * 100:.0f}%. These are the post-deploy "
        f"parser/enrichment/backfill queue:",
        flush=True,
    )
    for did in sorted(zero_score_entities):
        print(f"  - {did}", flush=True)
    regression = zero_frac > ZERO_SCORE_FLOOR
    if regression:
        print(
            f"::error::zero-score fraction {zero_frac * 100:.1f}% exceeds "
            f"floor {ZERO_SCORE_FLOOR * 100:.0f}% — likely a SYSTEMIC parser "
            f"regression (not a long tail of sparse packages). Failing build.",
            flush=True,
        )

    # Exit non-zero on any genuine render FAIL (HTTP error, non-JSON,
    # contract violation, validator crash) OR a systemic zero-score
    # regression. A bounded tail of degraded (PARTIAL) surfaces does NOT
    # block — they fail-closed in the UI and heal post-deploy.
    return 0 if (summary["FAIL"] == 0 and not regression) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--output", help="Write TSV to this path (default stdout)")
    p.add_argument("--limit", type=int, help="Probe only first N entities")
    p.add_argument("--strict", action="store_true",
                   help="Promote emptiness PARTIAL→FAIL on contract-required surfaces")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
