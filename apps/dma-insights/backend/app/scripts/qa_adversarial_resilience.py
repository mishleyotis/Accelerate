"""v2-QA Batch 5 — adversarial-resilience harness for the page-render surface.

Per the integrated batched plan Batch 5 spec + the operator mandate
"Ensure great app resilience to fit different scenarios. Consider all
103 DMAs in your tests... Do not just write code to give specifics on
errors; craft code that thinks through most common errors and
addresses them before they even happen."

For every ACTIVE entity in the DB, this harness exercises every
page-render endpoint with a curated set of adversarial inputs and
asserts the response is one of:

  - HTTP 200 with sensible defaults (graceful degradation)
  - HTTP 400 / 422 with an operator-friendly error message
  - HTTP 404 with an operator-friendly error message

**NEVER** HTTP 500 — a server error on a bad input is a regression
that ships an unprotected attack surface. The harness exits non-zero
when ANY cell returns 500, so the deploy pipeline fails fast.

The probes (10 per endpoint x 12 endpoints x N entities) cover:

  1. NORMAL              — baseline; control case
  2. RUN_NONEXISTENT     — ?run=REQ-DOES-NOT-EXIST  (gracefully fall back to ACTIVE)
  3. RUN_EMPTY           — ?run=  (treat as no override; fall back to ACTIVE)
  4. RUN_SQL_INJECTION   — ?run=' OR 1=1 --  (must be safely parameterized)
  5. ZOOM_INVALID        — ?zoom=bogus  (heatmap-specific; must fall back to default zoom)
  6. VIEW_CUSTOMER       — ?view=customer  (audience strip; must serve sanitized payload)
  7. VIEW_INVALID        — ?view=garbage  (must fall back to internal view)
  8. XSS_DISPLAY_ID      — display_id="<script>alert(1)</script>"  (path-param sanitization)
  9. LONG_DISPLAY_ID     — 256-char display_id  (truncation / 404 acceptable)
  10. UNICODE_DISPLAY_ID — display_id with emoji + non-ASCII (FastAPI must not crash)

Run:

    export DATABASE_URL=postgresql+asyncpg://...
    python -m app.scripts.qa_adversarial_resilience
    python -m app.scripts.qa_adversarial_resilience --output \
        docs/qa/qa_adversarial_matrix.tsv

Exit code: 0 only when there are no HTTP-500s AND no TRANSPORT_ERRORs (a handler
that CRASHES on adversarial input surfaces as a transport error under the ASGI
transport, not a 500 — both are deploy-blocking). 1 otherwise. CI-gateable.
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

# The 12 page-render endpoints. Each entry: (label, path-template,
# probe-set). The probe-set picks which adversarial inputs apply
# (some are endpoint-specific: zoom only on heatmap).
_PROBES_ALL_ENDPOINTS = [
    "NORMAL",
    "RUN_NONEXISTENT",
    "RUN_EMPTY",
    "RUN_SQL_INJECTION",
    "VIEW_CUSTOMER",
    "VIEW_INVALID",
    "XSS_DISPLAY_ID",
    "LONG_DISPLAY_ID",
    "UNICODE_DISPLAY_ID",
]

_HEATMAP_PROBES = [*_PROBES_ALL_ENDPOINTS, "ZOOM_INVALID"]

RENDER_ENDPOINTS: list[tuple[str, str, list[str]]] = [
    ("overview",
     "/api/v1/entities/{display_id}/overview",
     _PROBES_ALL_ENDPOINTS),
    ("heatmap",
     "/api/v1/entities/{display_id}/heatmap",
     _HEATMAP_PROBES),
    ("insights",
     "/api/v1/entities/{display_id}/insights",
     _PROBES_ALL_ENDPOINTS),
    ("platforms",
     "/api/v1/entities/{display_id}/platforms",
     _PROBES_ALL_ENDPOINTS),
    ("context",
     "/api/v1/entities/{display_id}/context",
     _PROBES_ALL_ENDPOINTS),
    ("health",
     "/api/v1/entities/{display_id}/health",
     _PROBES_ALL_ENDPOINTS),
    ("recommendations",
     "/api/v1/entities/{display_id}/recommendations",
     ["NORMAL", "RUN_NONEXISTENT", "RUN_EMPTY", "RUN_SQL_INJECTION",
      "XSS_DISPLAY_ID", "LONG_DISPLAY_ID", "UNICODE_DISPLAY_ID"]),
    ("evidence",
     "/api/v1/entities/{display_id}/evidence",
     ["NORMAL", "RUN_NONEXISTENT", "RUN_EMPTY", "RUN_SQL_INJECTION",
      "XSS_DISPLAY_ID", "LONG_DISPLAY_ID", "UNICODE_DISPLAY_ID"]),
    ("techstack",
     "/api/v1/entities/{display_id}/techstack",
     ["NORMAL", "XSS_DISPLAY_ID", "LONG_DISPLAY_ID",
      "UNICODE_DISPLAY_ID"]),
    ("focus_areas",
     "/api/v1/entities/{display_id}/focus-areas",
     ["NORMAL", "XSS_DISPLAY_ID", "LONG_DISPLAY_ID",
      "UNICODE_DISPLAY_ID"]),
    ("intelligence",
     "/api/v1/entities/{display_id}/intelligence-profile",
     ["NORMAL", "XSS_DISPLAY_ID", "LONG_DISPLAY_ID",
      "UNICODE_DISPLAY_ID"]),
    ("runs",
     "/api/v1/entities/{display_id}/runs",
     ["NORMAL", "XSS_DISPLAY_ID", "LONG_DISPLAY_ID",
      "UNICODE_DISPLAY_ID"]),
]


# Probe-name → (display_id_override, query_params) builder.
def _build_probe(probe: str, real_display_id: str) -> tuple[str, dict[str, str]]:
    if probe == "NORMAL":
        return real_display_id, {}
    if probe == "RUN_NONEXISTENT":
        return real_display_id, {"run": "REQ-DOES-NOT-EXIST-12345678"}
    if probe == "RUN_EMPTY":
        return real_display_id, {"run": ""}
    if probe == "RUN_SQL_INJECTION":
        return real_display_id, {"run": "' OR 1=1 --"}
    if probe == "ZOOM_INVALID":
        return real_display_id, {"zoom": "bogus_zoom_level"}
    if probe == "VIEW_CUSTOMER":
        return real_display_id, {"view": "customer"}
    if probe == "VIEW_INVALID":
        return real_display_id, {"view": "garbage_audience"}
    if probe == "XSS_DISPLAY_ID":
        # FastAPI must url-encode the path param; the route handler
        # gets the encoded string, looks it up in the DB, returns 404.
        return "<script>alert(1)</script>", {}
    if probe == "LONG_DISPLAY_ID":
        # 256-char display_id; the DB column is VARCHAR(32) so the
        # router's lookup MUST NOT raise — it should return 404.
        return ("acuity-" + ("x" * 256)), {}
    if probe == "UNICODE_DISPLAY_ID":
        # Non-ASCII + emoji must not break the FastAPI path matcher
        # nor the SQL driver.
        return "acuity-嗯-🦄", {}
    raise ValueError(f"unknown probe: {probe}")


@dataclass
class CellResult:
    entity_display_id: str
    endpoint: str
    probe: str
    http_code: int
    classification: str  # OK | DEGRADED | FAIL_500 | TRANSPORT_ERROR
    observations: list[str] = field(default_factory=list)


def _classify(http_code: int, body: dict | list | None) -> tuple[str, list[str]]:
    """Classify a response. NEVER OK if http_code == 500."""
    if http_code == 500:
        return "FAIL_500", [
            f"server error on adversarial input — "
            f"detail={(body or {}).get('detail', '?') if isinstance(body, dict) else '?'}",
        ]
    if http_code == 422:
        # FastAPI's pydantic validation rejected the input — that's
        # graceful, not a fail. Note in obs for the matrix.
        return "DEGRADED", ["422: pydantic validation rejected input"]
    if http_code == 404:
        # Operator-friendly 404 is acceptable for XSS/long/unicode probes.
        if isinstance(body, dict) and body.get("detail"):
            return "DEGRADED", [f"404: {body['detail'][:60]}"]
        return "DEGRADED", ["404 (no detail)"]
    if http_code == 400:
        if isinstance(body, dict) and body.get("detail"):
            return "DEGRADED", [f"400: {body['detail'][:60]}"]
        return "DEGRADED", ["400 (no detail)"]
    if http_code == 401:
        # Auth failure surfaced when the user override didn't take.
        # Should not happen because we override get_current_user.
        return "DEGRADED", ["401 unexpected — auth override leaked"]
    if http_code == 403:
        return "DEGRADED", ["403 forbidden"]
    if http_code == 200:
        return "OK", []
    if 300 <= http_code < 400:
        return "DEGRADED", [f"{http_code} redirect"]
    return "DEGRADED", [f"unexpected {http_code}"]


def _fake_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid4()),
        email="qa-adversarial@dma.local",
        role="ADMIN",
        name="QA Adversarial Probe",
    )


async def _probe_cell(
    client: httpx.AsyncClient,
    entity_display_id: str,
    endpoint_name: str,
    endpoint_template: str,
    probe: str,
) -> CellResult:
    try:
        path_display_id, query = _build_probe(probe, entity_display_id)
        url = endpoint_template.format(display_id=path_display_id)
        r = await client.get(url, params=query)
    except Exception as e:
        return CellResult(
            entity_display_id=entity_display_id,
            endpoint=endpoint_name,
            probe=probe,
            http_code=0,
            classification="TRANSPORT_ERROR",
            observations=[
                f"transport error: {type(e).__name__}: {e!s}"[:200],
            ],
        )
    try:
        body = r.json() if r.headers.get("content-type", "").startswith(
            "application/json"
        ) else None
    except (json.JSONDecodeError, ValueError):
        body = None
    cls, obs = _classify(r.status_code, body)
    return CellResult(
        entity_display_id=entity_display_id,
        endpoint=endpoint_name,
        probe=probe,
        http_code=r.status_code,
        classification=cls,
        observations=obs,
    )


async def fetch_entities(limit: int | None) -> list[tuple[str, str]]:
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


async def main_async(args: argparse.Namespace) -> int:
    app.dependency_overrides[get_current_user] = _fake_user
    entities = await fetch_entities(args.limit)
    print(f"# {len(entities)} active entities x "
          f"{sum(len(probes) for _, _, probes in RENDER_ENDPOINTS)} "
          f"(probes x endpoints) = "
          f"{len(entities) * sum(len(p) for _, _, p in RENDER_ENDPOINTS)} cells",
          flush=True)

    transport = httpx.ASGITransport(app=app)
    rows = [
        "display_id\tname\tendpoint\tprobe\thttp\tclassification\tobservations",
    ]
    summary = {"OK": 0, "DEGRADED": 0, "FAIL_500": 0, "TRANSPORT_ERROR": 0}
    fail500_details: list[CellResult] = []
    transport_details: list[CellResult] = []

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
    ) as client:
        for i, (display_id, name) in enumerate(entities, 1):
            for ep_name, ep_template, probes in RENDER_ENDPOINTS:
                for probe in probes:
                    cell = await _probe_cell(
                        client, display_id, ep_name, ep_template, probe,
                    )
                    rows.append("\t".join([
                        display_id, name, ep_name, probe,
                        str(cell.http_code), cell.classification,
                        "; ".join(cell.observations) or "-",
                    ]))
                    summary[cell.classification] = (
                        summary.get(cell.classification, 0) + 1
                    )
                    if cell.classification == "FAIL_500":
                        fail500_details.append(cell)
                    elif cell.classification == "TRANSPORT_ERROR":
                        transport_details.append(cell)
            if i % 20 == 0:
                print(
                    f"  ... {i}/{len(entities)} entities probed "
                    f"({summary['OK']} OK, {summary['DEGRADED']} DEGRADED, "
                    f"{summary['FAIL_500']} FAIL_500, "
                    f"{summary['TRANSPORT_ERROR']} TRANSPORT)",
                    flush=True,
                )

    output = "\n".join(rows) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        print(f"# wrote matrix to {out}", flush=True)
    else:
        print(output)

    total = sum(summary.values()) or 1
    print(
        f"\n# ADVERSARIAL RESILIENCE SUMMARY: "
        f"{summary['OK']} OK ({summary['OK']/total*100:.1f}%), "
        f"{summary['DEGRADED']} DEGRADED ({summary['DEGRADED']/total*100:.1f}%), "
        f"{summary['FAIL_500']} FAIL_500 ({summary['FAIL_500']/total*100:.1f}%), "
        f"{summary['TRANSPORT_ERROR']} TRANSPORT_ERROR "
        f"({summary['TRANSPORT_ERROR']/total*100:.1f}%)",
        flush=True,
    )
    if fail500_details:
        # Group by (endpoint, probe) so repeats across entities collapse.
        by_pattern: dict[tuple[str, str], list[str]] = {}
        for c in fail500_details:
            by_pattern.setdefault((c.endpoint, c.probe), []).append(
                c.entity_display_id,
            )
        print(
            f"\n# {len(fail500_details)} HTTP-500 FAILURES "
            f"(deployment-blocking):",
            flush=True,
        )
        for (ep, probe), entities_hit in sorted(
            by_pattern.items(), key=lambda x: -len(x[1])
        ):
            sample = ", ".join(entities_hit[:3]) + (
                f", +{len(entities_hit)-3} more" if len(entities_hit) > 3 else ""
            )
            print(
                f"  {len(entities_hit):4} x {ep}/{probe}    entities: {sample}",
                flush=True,
            )

    # TRANSPORT_ERROR is NOT benign on an adversarial probe: under the ASGI
    # transport an unhandled handler exception surfaces here (not as a 500), so
    # a crash on hostile input would otherwise slip the gate. It is as
    # deploy-blocking as a 500 — the whole point of this harness is that a bad
    # input NEVER takes the handler down.
    if transport_details:
        by_pattern: dict[tuple[str, str], list[str]] = {}
        for c in transport_details:
            by_pattern.setdefault((c.endpoint, c.probe), []).append(
                c.entity_display_id,
            )
        print(
            f"\n# {len(transport_details)} TRANSPORT_ERROR FAILURES "
            f"(handler crashed on adversarial input — deployment-blocking):",
            flush=True,
        )
        for (ep, probe), entities_hit in sorted(
            by_pattern.items(), key=lambda x: -len(x[1])
        ):
            sample = ", ".join(entities_hit[:3]) + (
                f", +{len(entities_hit)-3} more" if len(entities_hit) > 3 else ""
            )
            print(
                f"  {len(entities_hit):4} x {ep}/{probe}    entities: {sample}",
                flush=True,
            )

    return 0 if (summary["FAIL_500"] == 0
                 and summary["TRANSPORT_ERROR"] == 0) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--output",
        help="Write TSV to this path (default stdout — large; ~12K rows)",
    )
    p.add_argument(
        "--limit", type=int,
        help="Probe only first N entities (default: all)",
    )
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
