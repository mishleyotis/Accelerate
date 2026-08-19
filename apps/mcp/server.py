"""svc_mcp — the DMA Insights connector (stage 2), streamable HTTP.

Fifteen production tools in four groups (read · claim · write · inspect):
read tools are free and idempotent; write tools are the only path into
served content (invariant 2). The service connects DIRECT to Cloud SQL in
session mode — promote holds locks — and bundles the embedding model
in-image for V4 (local, deterministic, at submit; the serving path never
touches it).

A page too large to emit in one tool call arrives in parts
(open_payload / append_payload_part, assembled server-side at submit —
MEM-0030). That is a transport, not a second door: a part is inert until
the whole assembles, and the assembled whole goes through the same two
validation passes an inline payload always has.

Eleven more tools serve the FINDINGS MEMORY (`remember`, below): the store
of what went wrong, how it was measured, what was changed about it and
whether the change held. They write no serving content and are for agents
— QA agents reporting, a rectifier agent asking "have we seen this
before", a weekly pass reading what came back.

Access: the endpoint is a capability URL — /mcp/{MCP_PATH_TOKEN}/...
with the token from Secret Manager. Rotating the secret rotates the URL.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from mcp.server import MCPServer

from dma_mcp import bundle as bundle_mod
from dma_mcp import rejections
from dma_mcp import claims as claims_mod
from dma_mcp import evidence_tools
from dma_mcp import feedback as feedback_mod
from dma_mcp import gaps as gaps_mod
from dma_mcp import gates as gates_mod
from dma_mcp import ledger as ledger_mod
from dma_mcp import memory as memory_mod
from dma_mcp import promote as promote_mod
from dma_mcp import register as register_mod
from dma_mcp import fit as fit_mod
from dma_mcp import staged as staged_mod
from dma_mcp import submit as submit_mod
from dma_mcp import transport as transport_mod
from dma_mcp import withdraw as withdraw_mod
from dma_mcp.contracts import get_page_contract as page_contract
from dma_mcp.fetching import _fetch  # excerpt verification; see that module

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


def _traced(fn):
    """Log the full traceback of any tool failure to stdout before the SDK
    wraps it into an isError result — a verdict-shaped error the client can
    read is useless for defects the SERVER caused (42P18-class driver
    surprises land here, not in any gate)."""
    import functools
    import traceback

    @functools.wraps(fn)
    def _w(*a, **k):
        try:
            return fn(*a, **k)
        except Exception:
            print(f"TOOL ERROR in {fn.__name__}:\n{traceback.format_exc()}")
            raise
    return _w

token = os.environ.get("MCP_PATH_TOKEN", "dev").strip()
mcp = MCPServer("dma-insights")


# ── read and discover ───────────────────────────────────────────────────
@mcp.tool()
@_traced
def get_report_bundle(run_id: str) -> dict:
    """The parsed assessment: scores with source cells and all four grain
    ids, stated pillar/category grains, evidence, the twelve report
    sections, recommendations, peers, raw tables and value chains."""
    with _conn() as c:
        return bundle_mod.get_report_bundle(c, run_id)


@mcp.tool()
@_traced
def get_capability_catalogue(run_id: str) -> dict:
    """Canonical cell ids and NAMES for the run's pinned catalogue version,
    plus the alias bridge. Resolve every cell id and name through this —
    never copy a name out of report prose."""
    with _conn() as c:
        return bundle_mod.get_capability_catalogue(c, run_id)


@mcp.tool()
@_traced
def get_platform_fit(run_id: str, candidates: list) -> dict:
    """The fit score for each candidate platform, computed here and READ by
    you — never recomputed, never re-ranked (the contract's rule, and the
    same one `register_evidence` applies to the rank score).

    You supply judgement only, per candidate:
      `platform`         the platform's name as a client would say it
      `l3_area`          the catalogue L3 area it belongs to; the cells it
                         addresses are resolved from this, not from a list
                         you write
      `alignment`        0..1, how well it serves an objective the ENTITY
                         states. Quote that objective in `alignment_quote`.
                         OMIT it where you could not establish one — omitting
                         renormalises to the three-term blend and reports
                         `impact_fallback`, which is the contract's
                         instruction; sending 0 says you established that it
                         serves nothing, which is a different claim.
      `readiness`        green | amber | red, from the prerequisite checks

    Everything else is the run's: which cells the area reaches, each cell's
    distance from the target band, the severity of the issues on it, how well
    it is evidenced, and whether the register calls the family absent.

    Readiness MULTIPLIES rather than adding, so a platform whose prerequisites
    are red cannot reach the hot band. That is deliberate: a 2026-06 audit
    found 95 of 470 cards scoring hot with every prerequisite failing.
    """
    with _conn() as c:
        return fit_mod.platform_fit(c, run_id, candidates)


@mcp.tool()
@_traced
def get_page_contract(page: str) -> dict:
    """Field tuples AND per-field doc text, verbatim. The doc is part of
    the contract: for list-of-object fields it is the only place the item
    keys are stated."""
    return page_contract(page)


@mcp.tool()
@_traced
def get_evidence(run_id: str, e_ids: list) -> dict:
    """The three-way split: found / not_found / foreign. Foreign is the
    dangerous bucket — a real row belonging to another institution; stop,
    quarantine, escalate."""
    with _conn() as c:
        return evidence_tools.get_evidence(c, run_id, e_ids)


@mcp.tool()
@_traced
def get_run_progress(run_id: str) -> dict:
    """Per-page status, what is blocking, and the current claim — so a
    resuming session sees where it left off. Pages already passing must
    not be re-synthesised."""
    with _conn() as c:
        return claims_mod.get_run_progress(c, run_id)


@mcp.tool()
@_traced
def get_staged_payload(run_id: str, page: str, section: str = "",
                       submission_id: str = "", part: int = 0) -> dict:
    """What you last submitted for a page — STAGED, verbatim, unredacted.

    The read half of submit, and what makes the one-card repair the skill
    documents actually possible across sessions: retention keeps the staged
    row, this hands it back, you edit the one section and resubmit.

    Without a `section` you get the index — every section's name, byte size
    and top-level keys. Ask for the one you are repairing. A section over the
    inline budget is DESCRIBED rather than returned, because a truncated copy
    resubmitted would silently empty a complete section.

    `part` reads an OVERSIZE section in numbered chunks: call once without it
    to learn `parts`, then part=1..N, concatenate the `chunk` strings in order
    and json.loads the result. The read half of the chunked write, and for the
    same reason — a section you can submit in parts you must be able to read
    in parts, or a resubmit that drops one strands it.

    `submission_id` reads a SUPERSEDED submission instead of the live one.
    That is the recovery route for the one trap this tool has: a resubmit
    supersedes, so if your new payload omitted a section the old one carried
    — most easily because the section was over the inline budget and the read
    DESCRIBED it rather than returning it — the resubmit fails on CG-01 and
    the content is behind a row you can no longer reach. Nothing is lost from
    the database; pass the old id (`get_run_progress` had it) and read it back.

    This is not the served projection: the serve layer strips `internal_only`
    and redacts for audience, and a payload with those removed cannot be
    resubmitted — it would promote the redaction."""
    with _conn() as c:
        return staged_mod.get_staged_payload(c, run_id, page, section,
                                             submission_id, part)


@mcp.tool()
@_traced
def get_client_state(display_id: str) -> dict:
    """What is currently served and every prior run — a rerun produced as
    though it were a first run silently empties the longitudinal surfaces."""
    with _conn() as c:
        return bundle_mod.get_client_state(c, display_id)


@mcp.tool()
@_traced
def list_open_rejections(display_id: str = "", page: str = "",
                         limit: int = 200) -> dict:
    """Every payload this connector has REFUSED and nobody has repaired.

    Read this FIRST in any producer session, before choosing a run. A
    refused submission supersedes the passing row for its page and then sits
    there: `get_run_progress` shows it, but only for one run and only if you
    already know to ask, so a session that ends leaves no trace anything is
    outstanding. Measured three times in one day on this build — a heatmap
    that dropped `cell_evidence` and failed CG-01, an overview refused on
    ET-07 and again on ET-09 — and every one was found by a person reading a
    verdict rather than by the system saying so.

    Each row carries a stable `rejection_id` keyed on (run, page, gate,
    path). Submit a refined payload for that page and the rows it clears are
    the rows it was opened against — `submit_page_payload` returns them under
    `rejections.closed`, so "did the repair land" is answerable without
    diffing payloads.

    `attempts` is the number to read first. Past two it means the repair is
    not landing and the next attempt should CHANGE APPROACH rather than
    repeat: three identical fixes for one gate is the loop this field exists
    to make visible.

    Safeguard (SG) results never appear here. The charter says a failing
    safeguard discloses and still promotes, so it is not an outstanding
    repair.
    """
    with _conn() as c:
        rows = rejections.open_corpus_wide(c, display_id, page, limit)
    return {"rejections": rows, **rejections.summary(rows)}


@mcp.tool()
@_traced
def list_pending_runs() -> dict:
    """Runs awaiting synthesis (INGESTED/CLAIMED/SYNTHESISING), oldest
    first, with their claim state."""
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            SELECT r.id, e.display_id, e.legal_name, r.request_id,
                   enum_label(r.status), r.completed_at,
                   cl.held_by, cl.expires_at > now(), r.run_seq
              FROM runs r
              JOIN entities e ON e.id = r.entity_id
              LEFT JOIN run_claims cl ON cl.run_id = r.id
             WHERE r.status IN ('INGESTED','CLAIMED','SYNTHESISING')
             ORDER BY r.completed_at NULLS LAST""")
        rows = cur.fetchall()
        # HOW MANY RUNS THIS REQUEST HAS, said rather than left to be derived.
        #
        # Measured 2026-08-16: 105 of 171 entities carried more than one
        # pending run, every other field identical — same request id, same
        # composite, same cell count, same completed_at. The answer then was
        # to expose `run_seq` so a caller could at least pick the latest.
        # Measured again 2026-08-19: 109 of 287 pending runs are surplus, 101
        # request ids carry more than one, and on 100 of those 101 every run
        # shares one completed_at.
        #
        # `run_seq` alone makes the duplicate CHOOSABLE and leaves it
        # invisible: a caller reading one row cannot tell it is one of two,
        # and has to group the whole list to find out. So the row says so.
        # `is_latest_for_request` is the one a producer should work;
        # `runs_for_request` above 1 is a condition to report, not a
        # preference to exercise quietly (MEM-0092).
        per_request: dict = {}
        for r in rows:
            per_request.setdefault((r[1], r[3]), []).append(r[8])
        return {"pending": [
            {"run_id": str(r[0]), "display_id": r[1], "entity_name": r[2],
             "request_id": r[3], "status": r[4],
             "completed_at": r[5].isoformat() if r[5] else None,
             "run_seq": r[8],
             "runs_for_request": len(per_request[(r[1], r[3])]),
             "is_latest_for_request": r[8] == max(per_request[(r[1], r[3])]),
             "claim": None if r[6] is None else
                      {"held_by": r[6], "live": bool(r[7])}}
            for r in rows],
            # The corpus-level number, so a scheduler about to fan out over
            # this list knows what share of it is duplicate before it starts.
            "duplicate_requests": sum(1 for v in per_request.values() if len(v) > 1),
            "surplus_runs": sum(len(v) - 1 for v in per_request.values()),
        }


# ── claim ───────────────────────────────────────────────────────────────
@mcp.tool()
@_traced
def claim_run(run_id: str, session_id: str, producer_version: str) -> dict:
    """Exclusive expiring lease — one session per run. Refused while
    another session's lease is live; staged work survives a lapse."""
    with _conn() as c:
        return claims_mod.claim_run(c, run_id, session_id, producer_version)


# ── write ───────────────────────────────────────────────────────────────
@mcp.tool()
@_traced
def register_evidence(run_id: str, item: dict) -> dict:
    """Mint before you cite. The server allocates the id and computes the
    rank score; dedup is by content, scoped to the entity; the excerpt is
    verified verbatim against the fetched artefact."""
    with _conn() as c:
        return register_mod.register_evidence(c, run_id, item, fetch=_fetch)


@mcp.tool()
@_traced
def open_payload(run_id: str, page: str, producer_version: str = "") -> dict:
    """Open a CHUNKED upload for a page too large to emit in one call, and get
    back the connector-allocated `upload_id` every part is sent against.

    A contract-complete heatmap does not fit inline: measured 2026-08-08,
    1,128,742 bytes for Frost Bank and 1,598,147 for Fisher Investments, with
    `cell_evidence` alone 862,351 / 1,208,289 across ~700 served cells. Rule 17
    wants a drawer row for EVERY served cell, so that is the contract's size —
    do not cut the served set to fit. Read
    `get_page_contract(page)["transport"]` for the byte limits and the exact
    step list.

    The upload is bound to this run and page at open, so no part can be
    misrouted into another page's payload later, and the id is server-allocated
    (invariant 10) so no producer can append into an upload it does not own.
    """
    with _conn() as c:
        return transport_mod.open_payload(c, run_id, page,
                                          producer_version=producer_version)


@mcp.tool()
@_traced
def append_payload_part(upload_id: str, part: int, parts_total: int,
                        path: str = "", items: list = None,
                        fields: dict = None, item_count: int = 0) -> dict:
    """Send one part of a chunked payload. Returns a receipt, never a verdict —
    nothing is validated until the whole assembles.

    Exactly one body per part:
      fields={...}  shallow-MERGES an object at `path` (path '' is the payload
                    root, so a whole small section is one part)
      items=[...]   APPENDS to the list at `path`, e.g.
                    path="cell_evidence.cells"

    `part` is 1-based; `parts_total` is your declared part count and must be
    the SAME on every part — that declaration is what makes an incomplete
    transmission detectable rather than merely smaller than intended. Pass
    `item_count=len(items)` so a part that arrived short is caught here rather
    than assembling into a quietly shorter payload.

    Parts are applied in ascending index at assembly, so the same set of parts
    always assembles to the same bytes. Resending an index REPLACES it: a
    dropped connection costs one part, not the transmission.
    """
    with _conn() as c:
        return transport_mod.append_payload_part(
            c, upload_id, part, parts_total, path=path, items=items,
            fields=fields, item_count=item_count)


@mcp.tool()
@_traced
def submit_page_payload(run_id: str, page: str, payload: dict = None,
                        provenance: str = "producer",
                        producer_version: str = "", upload_id: str = "",
                        expect: dict = None) -> dict:
    """Validate (both passes), supersede the live row, stage, return the
    verdict. Reasons name the gate, the JSON path and the arithmetic;
    SG results disclose in warnings and never block.

    Two transports, one validation. Send `payload` inline for a page that fits
    in one call, or `upload_id` from open_payload for one that does not — the
    connector assembles the parts server-side and both passes then run over the
    assembled whole, exactly as they do for an inline payload. Never both.

    `expect={"<section>.<field>": N}` declares the assembled length of a path.
    With it, CG-17 catches a list truncated at a valid element boundary (which
    parses as JSON and so is otherwise invisible); a missing part is refused by
    CG-16 naming the indexes, and in neither case is a submission row written.
    """
    with _conn() as c:
        return submit_mod.submit_page_payload(
            c, run_id, page, payload, provenance=provenance,
            producer_version=producer_version, encoder=_encoder(),
            upload_id=upload_id, expect=expect)


@mcp.tool()
@_traced
def promote_run(run_id: str) -> dict:
    """All six pages, one transaction, all or nothing. incomplete_run
    names the missing and unpassed pages; re-promotion is idempotent."""
    with _conn() as c:
        return promote_mod.promote_run(c, run_id)


@mcp.tool()
@_traced
def withdraw_run(run_id: str, reason: str, actor: str) -> dict:
    """Take a promoted run off the client surface, with a recorded reason.

    Removes the run from `serving_directory`, which is the only window the
    API reads — so the entity stops being LISTED, not merely stops being
    openable. Setting is_active=false does not do this: the run stays in
    the view and the directory keeps publishing the client's name beside a
    set of pages that 404.

    Nothing is deleted. Promoted rows, annotations and alerts are retained;
    the alerts leave the queue with the run and return with it, still open.
    `reason` is required at 30 characters and is stored on the run.

    There is no restore tool. A withdrawn run returns by being re-promoted,
    which clears the withdrawal — the way back is passing the gates again.
    """
    with _conn() as c:
        return withdraw_mod.withdraw_run(c, run_id, reason, actor)


@mcp.tool()
@_traced
def list_withdrawn_runs() -> dict:
    """Every currently withdrawn run with its reason and who withdrew it."""
    with _conn() as c:
        return withdraw_mod.list_withdrawn(c)


# ── inspect ─────────────────────────────────────────────────────────────
@mcp.tool()
@_traced
def get_validation_verdict(submission_id: str) -> dict:
    """A prior submission's verdict, with superseded state."""
    with _conn() as c:
        return submit_mod.get_validation_verdict(c, submission_id)


@mcp.tool()
@_traced
def explain_gate(gate_id: str) -> dict:
    """A gate's definition and threshold history — direction of movement
    visible."""
    with _conn() as c:
        return gates_mod.explain_gate(c, gate_id)


# ── remember ────────────────────────────────────────────────────────────
# The findings memory (0034/0035). These tools are for AGENTS: a QA agent
# reporting what it measured, a rectifier agent asking whether this defect is
# already known, and a weekly refinement pass reading what came back.
#
# The one rule that runs through all of them: a finding that cannot say how it
# was measured is an opinion, and a resolution that cannot name the change that
# closed it cannot be checked for recurrence. Both are refused.
#
# Embedding happens HERE, at write time, inside the connector — the same place
# and the same model V4 uses at submit. Invariant 1 forbids a model call on the
# SERVING request path; this is not one. Do not read it as licence.
@mcp.tool()
@_traced
def record_enrichment(display_id: str, facet: str, source: str,
                      run_id: str = "", account: str = "",
                      rows_written: int = 0, note: str = "") -> dict:
    """Record that one FACET of a client was enriched. Call it every time.

    This is the MCP half of the enrichment-versioning contract. Without it,
    an enrichment that ran in this session and a surface that never got it
    are two facts nobody holds together — which is the whole of "the work was
    done but it is not showing", reported three rounds running across
    leadership, why-now, sentiment and the tech register.

    Call this AFTER the enrichment returns and BEFORE (or after) you submit
    the page — the order does not matter, because the version is what orders
    them. `promote_run` records the promotion side automatically from the
    sections it writes, so a facet enriched and never promoted shows up as
    `enriched_not_promoted` in `get_client_state` and in the app, and blocks
    the client being called done.

    facet         one of leadership · firmographics · techstack · sentiment ·
                  why_now · platform_readiness · peer_scores. Not a free
                  string: a typo would silently create an eighth facet that
                  nobody watches, so the database refuses it.
    source        REQUIRED. clay · explorium · exa · indeed · manual · … The
                  answer to "run it again how?", which is the only question a
                  stale facet raises.
    account       WHICH account ran it, and worth the keystrokes: the same
                  technographic scan returned empty twice under one account
                  and sixty technologies under another, and with no record of
                  which, the two runs were afterwards indistinguishable.
    rows_written  how many rows the enrichment produced. 0 is a real answer
                  and a useful one — it distinguishes "ran, found nothing"
                  from "never ran".

    Returns {enrichment_version, facet, entity_id, enrichment: {...}} where
    the last is the same drift summary `get_client_state` reports.
    """
    with _conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id FROM entities WHERE display_id = %s",
                    (display_id,))
        row = cur.fetchone()
        if row is None:
            return {"error": "unknown_entity", "display_id": display_id}
        entity_id = row[0]
        try:
            version = ledger_mod.record_enrichment(
                cur, entity_id, facet, source,
                run_id=run_id or None, account=account or None,
                rows_written=rows_written, note=note or None)
        except ledger_mod.LedgerError as e:
            c.rollback()
            return {"error": "bad_enrichment", "detail": str(e)}
        c.commit()
        return {"enrichment_version": version, "facet": facet,
                "entity_id": str(entity_id),
                "enrichment": ledger_mod.summary(
                    ledger_mod.drift(cur, entity_id))}


@mcp.tool()
@_traced
def record_finding(finding: dict) -> dict:
    """Record a defect in the findings memory. Idempotent by content — the same
    defect reported by three QA agents is ONE finding with three sightings.

    finding = {
      title           str  REQUIRED  one line: what is wrong
      observed        str  REQUIRED  what was actually seen
      measurement     str  REQUIRED  HOW it was measured — the command, query,
                                     HTTP status or count WITH its denominator.
                                     Minimum 30 chars. "it broke" is refused.
      component       str  REQUIRED  api | mcp | web | worker | migrations |
                                     infra | skill:<name> | agent:<name>
      defect_class    str  REQUIRED  a class id from list_defect_classes
      severity        str  REQUIRED  BLOCKER | MAJOR | MINOR | INFO
      raised_by_kind  str  REQUIRED  QA_AGENT | REVIEWER | GATE | USER |
                                     BUILD_AGENT | TEST | MONITOR
      raised_by       str  REQUIRED  the agent, gate or person BY NAME

      measured_value  str  the number/status itself ("403", "0 of 8")
      expected        str  what it should have been
      file_path       str  surface str (Surface Spec id)  gate_id str
      run_id / entity_id / annotation_id   where applicable
      fix_hint        str  what to do about it
      note            str  free text for THIS sighting
      session_ref     str  the chat, Cowork session or CI job that saw it
      source_ref      str  an idempotency token for this sighting
      dedup_key       str  override the dedup identity (see below)
      new_class  {title, description, tell, probe}
                      required ONLY when defect_class is not yet known — a
                      class may be invented, never invented silently
    }

    Dedup identity, when you do not pass dedup_key:
        component | defect_class | (file_path or surface or gate_id) | title

    Returns {finding_id: "MEM-0007", deduped, sighting_id, sightings,
             recurrences, status, content_hash, errors[]}.
    Reporting a defect that is already RESOLVED returns a warning telling you
    to use report_recurrence instead — that is how a failed fix gets recorded
    against the fix that failed.
    """
    with _conn() as c:
        return memory_mod.record_finding(c, finding, encoder=_encoder())


@mcp.tool()
@_traced
def search_findings(query: str, mode: str = "auto", limit: int = 10,
                    component: str = "", defect_class: str = "",
                    severity: str = "", status: str = "") -> dict:
    """"Have we seen this before?" — asked both ways, because it is asked both
    ways. Run this BEFORE recording a finding and before designing a fix.

    mode:
      auto      (default) lexical first; semantic as well; trigram only if
                neither matched
      lexical   websearch_to_tsquery + ts_rank_cd over the finding's text
      semantic  pgvector KNN over the embedding written at record time
      fuzzy     pg_trgm similarity on the title — for a typo or an
                abbreviation that shares no lexeme with the corpus

    Filters (all optional): component, defect_class, severity, status.

    Returns {paths_run[], paths_skipped{path: reason}, results[]}. Read
    paths_skipped: an empty result from a path that never ran is not evidence
    of absence — "no encoder in this image" and "nothing matched" are
    different answers. Each result carries matched_by[] and per-path scores,
    so you can see WHY it matched.
    """
    with _conn() as c:
        return memory_mod.search_findings(
            c, query, mode=mode, limit=limit, component=component or None,
            defect_class=defect_class or None, severity=severity or None,
            status=status or None, encoder=_encoder())


@mcp.tool()
@_traced
def list_open_findings(component: str = "", severity: str = "",
                       defect_class: str = "", status: str = "",
                       min_age_days: int = 0, max_age_days: int = 0,
                       limit: int = 50) -> dict:
    """Everything not closed — OPEN, INVESTIGATING and RECURRED — worst first.

    RECURRED counts as open because a fix that did not hold is open again.
    Ordered by severity, then recurrences, then sightings: the top of this
    list is what has hurt most often, not what arrived most recently.

    min_age_days / max_age_days filter by age in days since first sighting
    (0 means no bound). Each row carries sightings, recurrences and age_days,
    all computed at read time — nothing in this store keeps a count.
    """
    with _conn() as c:
        return memory_mod.list_open_findings(
            c, component=component or None, severity=severity or None,
            defect_class=defect_class or None, status=status or None,
            min_age_days=min_age_days or None,
            max_age_days=max_age_days or None, limit=limit)


@mcp.tool()
@_traced
def list_enrichment_gaps(run_id: str, page: str = "") -> dict:
    """Every empty field on this run's live submissions — your worklist.

    Build owner, 2026-08-14: "Never place an em dash. There should always be a
    way to send a signal to the MCP to give us an enrichment of the empty
    field." This is that signal, and it is COMPUTED rather than queued: the set
    of empty fields is derivable from the staged payloads against the contract
    at any moment, so a stored request could only go stale — it would keep
    asking for a field a later re-promote had already filled. Nothing is
    clicked, nothing is written, and the list cannot drift from what the
    surfaces actually show.

    Every gap here is a spot where a reader currently sees "Not stated". Close
    one and the surface fills; there is no separate step to mark it done.

    THE THREE KINDS, worst first:

      must_present_member  a member the contract names on EVERY sub-vertical is
                           neither stated nor held. Its absence is never a
                           property of this client, so this is the class to
                           work first.
      empty_required       a required field is empty and the section declares
                           no empty state.
      empty_optional       an optional field is empty.

    WHAT IS NOT HERE, deliberately. A field QUARANTINED with a reason is not a
    gap — the producer ran the ladder, the figure failed the identity gate, and
    the reason is the finding. Neither is a section that declared its
    `empty_state` with a ladder: the search happened and is recorded. Nor a
    boolean, whose absence IS its value. If you want a field to leave this list
    without finding the value, that is the route — state the ladder, do not
    invent the figure.

    Reads the STAGED submissions, never the served projection: the serve layer
    strips `internal_only` paths and redacts cohort `entity_ids` for every
    audience, and a list built from what the API returns would report redaction
    working correctly as content you failed to write.

    Pass `page` to narrow to one page. Returns {gaps[], count, by_kind,
    pages_read}, each gap carrying its contract `doc` text and `closes_with`.
    """
    with _conn() as c:
        return gaps_mod.list_enrichment_gaps(c, run_id, page or None)


@mcp.tool()
@_traced
def get_finding(finding_id: str) -> dict:
    """One finding in full: every sighting in order, and every refinement made
    against it with its relation (ADDRESSES or CLOSES). This is where you look
    before changing anything — if a refinement already exists and the finding
    recurred, the change that failed is named here."""
    with _conn() as c:
        return memory_mod.get_finding(c, finding_id)


@mcp.tool()
@_traced
def list_defect_classes() -> dict:
    """The shared vocabulary, with each class's TELL (how it presents) and
    PROBE (the command or query that detects it), and how many findings are
    open under each.

    Read this before recording a finding. A memory rots when one defect is
    filed under three synonyms, which is why defect_class is a foreign key.
    """
    with _conn() as c:
        return memory_mod.list_defect_classes(c)


@mcp.tool()
@_traced
def record_refinement(refinement: dict) -> dict:
    """What you CHANGED, in response to which findings. The server allocates
    REF-####.

    refinement = {
      target_kind  str REQUIRED  SKILL | AGENT | COMPONENT | GATE | TEST |
                                 SCHEMA | DOC | PROCESS
      target       str REQUIRED  named the way its owner names it:
                                 skill:dma-surface-production, agent:rectifier,
                                 CG-13, apps/mcp/dma_mcp/promote.py
      change       str REQUIRED  what was changed, in prose
      applied_by   str REQUIRED
      finding_ids  [str] REQUIRED  the findings this answers — they must exist
      commit_sha   str \\ ONE of these two is REQUIRED: a refinement nobody
      change_ref   str /  can locate is a claim, not a change
      gate_added   str  the gate added in response, so the memory holds the
                        fix beside the defect
      rationale / verification / relation (ADDRESSES | CLOSES)
    }

    Recording a refinement does NOT close anything. Call resolve_finding for
    that — deliberately two steps, because "changed" and "fixed" are two
    claims and only the second one can be wrong later.
    """
    with _conn() as c:
        return memory_mod.record_refinement(c, refinement)


@mcp.tool()
@_traced
def resolve_finding(finding_id: str, refinement_id: str,
                    verification: str = "") -> dict:
    """Close a finding by naming the refinement that closed it. The refinement
    is REQUIRED and there is no way around it: the column is under a CHECK.

    Without it, "did the fix hold?" has no subject — and that question is the
    only thing this store exists to answer. Pass `verification` (a test name, a
    gate id, a probe) when you have one.
    """
    with _conn() as c:
        return memory_mod.resolve_finding(c, finding_id, refinement_id,
                                          verification=verification or None)


@mcp.tool()
@_traced
def report_recurrence(finding_id: str, measurement: str, reported_by: str,
                      reported_by_kind: str = "QA_AGENT",
                      after_refinement: str = "", measured_value: str = "",
                      note: str = "", session_ref: str = "",
                      source_ref: str = "") -> dict:
    """A finding that was resolved and came back. THIS IS THE SIGNAL THAT
    MATTERS — a fix that did not hold is more informative than one that did.

    The recurrence is recorded against the refinement BY NAME (defaults to the
    one that closed the finding), the finding returns to RECURRED, and that
    refinement's `held` flips to false in the digest. `measurement` is required
    with the same 30-char floor: a recurrence claim is only as good as the
    measurement that saw it come back.

    If the finding was never resolved by a refinement, this refuses and tells
    you to use record_finding instead — nothing can have failed to hold.
    """
    with _conn() as c:
        return memory_mod.report_recurrence(
            c, finding_id, measurement=measurement, reported_by=reported_by,
            reported_by_kind=reported_by_kind,
            after_refinement=after_refinement or None,
            measured_value=measured_value or None, note=note or None,
            session_ref=session_ref or None, source_ref=source_ref or None)


@mcp.tool()
@_traced
def get_memory_digest(days: int = 7) -> dict:
    """Everything a weekly refinement pass needs, in one call: what came back,
    what is new, which refinements held, which defect CLASSES are still
    producing, and what nobody has changed anything about.

    Read it in that order. `recurrences_in_window` names the refinements that
    did not hold — their targets are where the next change belongs.
    `open_by_class` says which SHAPE of defect this build is still producing; a
    class with several open findings is a process problem, not several bugs.
    """
    with _conn() as c:
        return memory_mod.memory_digest(c, days)


# ── reviewer feedback (the web app's Accept/Reject pair) ─────────────────
@mcp.tool()
@_traced
def list_reviewer_feedback(display_id: str = "", ic_id: str = "",
                           run_id: str = "", limit: int = 50) -> dict:
    """Read reviewer verdicts on insight cards straight from `annotations`,
    with the actor and whether each has been ingested into the memory yet.

    This is a READ. Invariant 2 constrains the API's writes, not anyone's
    reads: no content enters a serving table here and no component gains a
    write it did not have.
    """
    with _conn() as c:
        return feedback_mod.list_reviewer_feedback(
            c, display_id=display_id or None, ic_id=ic_id or None,
            run_id=run_id or None, limit=limit)


@mcp.tool()
@_traced
def ingest_reviewer_feedback(limit: int = 200) -> dict:
    """Turn every un-ingested Accept/Reject into memory. Idempotent — run it on
    a schedule and again by hand five minutes later; a verdict becomes a
    finding exactly once.

    A REJECT becomes a finding against the SYNTHESIS SKILL, carrying the card's
    own text and its `r_layer`: a verdict with no claim attached teaches
    nothing, and it is the recorded reasoning the reviewer refused, not the
    headline. An ACCEPT lands as a verdict row (which is what makes the reject
    RATE measurable) and, on a card that was previously rejected, as a sighting
    saying so.

    Returns {ingested, skipped, findings_raised[], problems[], verdict_tally,
    reject_rate}. `problems` is never empty for the wrong reason: an
    unreadable verdict is left un-ingested and named, not counted as nothing.
    """
    with _conn() as c:
        return feedback_mod.ingest_reviewer_feedback(c, limit=limit,
                                                     encoder=_encoder())


def build_app():
    """Streamable-HTTP app on the capability path (stateless: Cloud Run
    may serve consecutive requests from different instances)."""
    return mcp.streamable_http_app(
        streamable_http_path=f"/mcp/{token}", stateless_http=True,
        json_response=True, host="0.0.0.0")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
