"""svc_mcp — the DMA Insights connector (stage 2), streamable HTTP.

Twelve tools in four groups: read tools are free and idempotent; write
tools are the only path into served content (invariant 2). The service
connects DIRECT to Cloud SQL in session mode — promote holds locks — and
bundles the embedding model in-image for V4 (local, deterministic, at
submit; the serving path never touches it).

Access: the endpoint is a capability URL — /mcp/{MCP_PATH_TOKEN}/...
with the token from Secret Manager. Rotating the secret rotates the URL.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from mcp.server import MCPServer

from dma_mcp import bundle as bundle_mod
from dma_mcp import claims as claims_mod
from dma_mcp import evidence_tools
from dma_mcp import gates as gates_mod
from dma_mcp import promote as promote_mod
from dma_mcp import register as register_mod
from dma_mcp import submit as submit_mod
from dma_mcp.contracts import get_page_contract as page_contract

_ENCODER = None


def _encoder():
    """The bundled 384-dim encoder, loaded once, lazily — absent model =
    V4 abstains (recorded NOT_RUN), never a crash."""
    global _ENCODER
    if _ENCODER is None and os.environ.get("EMBED_MODEL_DIR"):
        try:
            from dma_mcp.encoder import minilm_encoder
            _ENCODER = minilm_encoder(os.environ["EMBED_MODEL_DIR"])
        except Exception as e:
            # V4 is an extra guard, never a fail-closed on a missing
            # model: a load failure means abstention, not a crash
            print(f"encoder unavailable ({e}); V4 will abstain")
            os.environ.pop("EMBED_MODEL_DIR", None)
    return _ENCODER


@contextmanager
def _conn():
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        url = os.environ["LOCAL_DATABASE_URL"]
        host = url.split("@")[1].split(":")[0]
        c = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                 password="local", host=host, port=5432,
                                 database="dma_insights")
    else:
        from google.cloud.sql.connector import Connector
        c = Connector().connect(
            os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
            user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
            enable_iam_auth=True, ip_type="PRIVATE")
    try:
        yield c
    finally:
        c.close()


def _fetch(url: str):
    """Excerpt-verification fetcher: plain GET, text out, None on failure."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read(2_000_000).decode("utf-8", "replace")
    except Exception:
        return None


token = os.environ.get("MCP_PATH_TOKEN", "dev").strip()
mcp = MCPServer("dma-insights")


# ── read and discover ───────────────────────────────────────────────────
@mcp.tool()
def get_report_bundle(run_id: str) -> dict:
    """The parsed assessment: scores with source cells and all four grain
    ids, stated pillar/category grains, evidence, the twelve report
    sections, recommendations, peers, raw tables and value chains."""
    with _conn() as c:
        return bundle_mod.get_report_bundle(c, run_id)


@mcp.tool()
def get_capability_catalogue(run_id: str) -> dict:
    """Canonical cell ids and NAMES for the run's pinned catalogue version,
    plus the alias bridge. Resolve every cell id and name through this —
    never copy a name out of report prose."""
    with _conn() as c:
        return bundle_mod.get_capability_catalogue(c, run_id)


@mcp.tool()
def get_page_contract(page: str) -> dict:
    """Field tuples AND per-field doc text, verbatim. The doc is part of
    the contract: for list-of-object fields it is the only place the item
    keys are stated."""
    return page_contract(page)


@mcp.tool()
def get_evidence(run_id: str, e_ids: list) -> dict:
    """The three-way split: found / not_found / foreign. Foreign is the
    dangerous bucket — a real row belonging to another institution; stop,
    quarantine, escalate."""
    with _conn() as c:
        return evidence_tools.get_evidence(c, run_id, e_ids)


@mcp.tool()
def get_run_progress(run_id: str) -> dict:
    """Per-page status, what is blocking, and the current claim — so a
    resuming session sees where it left off. Pages already passing must
    not be re-synthesised."""
    with _conn() as c:
        return claims_mod.get_run_progress(c, run_id)


@mcp.tool()
def get_client_state(display_id: str) -> dict:
    """What is currently served and every prior run — a rerun produced as
    though it were a first run silently empties the longitudinal surfaces."""
    with _conn() as c:
        return bundle_mod.get_client_state(c, display_id)


@mcp.tool()
def list_pending_runs() -> dict:
    """Runs awaiting synthesis (INGESTED/CLAIMED/SYNTHESISING), oldest
    first, with their claim state."""
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            SELECT r.id, e.display_id, e.legal_name, r.request_id,
                   enum_label(r.status), r.completed_at,
                   cl.held_by, cl.expires_at > now()
              FROM runs r
              JOIN entities e ON e.id = r.entity_id
              LEFT JOIN run_claims cl ON cl.run_id = r.id
             WHERE r.status IN ('INGESTED','CLAIMED','SYNTHESISING')
             ORDER BY r.completed_at NULLS LAST""")
        return {"pending": [
            {"run_id": str(r[0]), "display_id": r[1], "entity_name": r[2],
             "request_id": r[3], "status": r[4],
             "completed_at": r[5].isoformat() if r[5] else None,
             "claim": None if r[6] is None else
                      {"held_by": r[6], "live": bool(r[7])}}
            for r in cur.fetchall()]}


# ── claim ───────────────────────────────────────────────────────────────
@mcp.tool()
def claim_run(run_id: str, session_id: str, producer_version: str) -> dict:
    """Exclusive expiring lease — one session per run. Refused while
    another session's lease is live; staged work survives a lapse."""
    with _conn() as c:
        return claims_mod.claim_run(c, run_id, session_id, producer_version)


# ── write ───────────────────────────────────────────────────────────────
@mcp.tool()
def register_evidence(run_id: str, item: dict) -> dict:
    """Mint before you cite. The server allocates the id and computes the
    rank score; dedup is by content, scoped to the entity; the excerpt is
    verified verbatim against the fetched artefact."""
    with _conn() as c:
        return register_mod.register_evidence(c, run_id, item, fetch=_fetch)


@mcp.tool()
def submit_page_payload(run_id: str, page: str, payload: dict,
                        provenance: str = "producer",
                        producer_version: str = "") -> dict:
    """Validate (both passes), supersede the live row, stage, return the
    verdict. Reasons name the gate, the JSON path and the arithmetic;
    SG results disclose in warnings and never block."""
    with _conn() as c:
        return submit_mod.submit_page_payload(
            c, run_id, page, payload, provenance=provenance,
            producer_version=producer_version, encoder=_encoder())


@mcp.tool()
def promote_run(run_id: str) -> dict:
    """All six pages, one transaction, all or nothing. incomplete_run
    names the missing and unpassed pages; re-promotion is idempotent."""
    with _conn() as c:
        return promote_mod.promote_run(c, run_id)


# ── inspect ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_validation_verdict(submission_id: str) -> dict:
    """A prior submission's verdict, with superseded state."""
    with _conn() as c:
        return submit_mod.get_validation_verdict(c, submission_id)


@mcp.tool()
def explain_gate(gate_id: str) -> dict:
    """A gate's definition and threshold history — direction of movement
    visible."""
    with _conn() as c:
        return gates_mod.explain_gate(c, gate_id)


def build_app():
    """Streamable-HTTP app on the capability path (stateless: Cloud Run
    may serve consecutive requests from different instances)."""
    return mcp.streamable_http_app(
        streamable_http_path=f"/mcp/{token}", stateless_http=True,
        json_response=True, host="0.0.0.0")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
