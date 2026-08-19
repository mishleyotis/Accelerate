"""The enrichment routine — the loop that closes gaps without a human in it.

Owner, 2026-08-15: "There should be a working enrichment routine; not you doing
it as Claude Code."

He is right, and the distinction is the whole point of this module. Every gap
closed on this build so far was closed by a person driving Clay and a browser by
hand. That is not a pipeline; it is a person, and it does not survive the person
leaving, the tenth client, or a Tuesday.

WHAT THIS IS. A Cloud Run Job, on a schedule, that:

  1. reads every ACTIVE run's live submissions,
  2. computes that run's gap set from the contract — the SAME computation the
     connector's `list_enrichment_gaps` performs, from the same shared module,
     so the routine and the producer can never disagree about what is missing,
  3. runs each gap past an ordered RESOLVER LADDER,
  4. writes one attempt row per (gap, resolver) — RESOLVED with its provenance,
     or NOT_RUN / NO_SOURCE with a REASON the database will not let it omit,
  5. closes the job row, which is what the app reads to answer "is the loop
     alive".

WHAT THIS IS NOT, and the boundary matters more than the feature. It does not
write serving content. A RESOLVED attempt is a candidate with a source, sitting
in a workflow table; the value still has to travel the only path content may
take — registered as evidence and submitted through the connector (invariant 2).
This job shortens the producer's search; it does not replace the producer's
judgement, and it is not a side door into the serving tier.

THE RESOLVER LADDER, and why it is honest about being short. A resolver is a
deterministic function from (entity, run, field) to a value with a source. Two
exist today:

  `self_domain`   the entity's own web domain, derived from the registrable
                  domain that dominates its T1 evidence. This is genuinely
                  computable from data already in the database and it closes
                  the field the owner reported first.
  `run_manifest`  fields the ingest package already stated and the producer did
                  not carry through.

Everything else records NO_SOURCE with the reason, because the two obvious
sources are both unavailable and saying so is the job: Clay is session-bound
(this org's trigger API refuses connector grants, so a scheduled job cannot hold
it) and Explorium has no key in Secret Manager. A routine that silently resolved
nothing would look identical to one that had nothing to do. This one makes the
difference legible in a table.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

# The gap computation is SHARED with the connector rather than reimplemented.
# Two copies of "what counts as missing" is the drift class this build has paid
# for repeatedly — the enrichment register rendered on one surface of five, the
# pinned-row/pinned-key pair that duplicated CAGR, `founded` versus
# `founded_year`. deploy.sh stages the module into both images; Gate D fails CI
# if either one is missing it.
# Candidate roots, built LAZILY. In the image this module is
# /app/<pkg>/<name>.py — THREE parents — so `parents[3]` raises IndexError, and
# a tuple literal evaluates BOTH entries before the loop body runs, so it raises
# before the image path it would have found is ever tried. Exactly this killed
# the api once (computed.py) and the mcp container twice (deploy 8 and 9). The
# repo layout is optional; the image layout is not.
def _shared_roots():
    here = Path(__file__).resolve()
    roots = [here.parent / "shared", here.parent.parent / "shared"]
    if len(here.parents) > 3:
        roots.append(here.parents[3] / "packages" / "shared")
    return roots


for _cand in _shared_roots():
    if _cand.exists() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))

try:
    import enrichment_gaps as gapmod
except ImportError as exc:                                       # pragma: no cover
    raise ImportError(
        "enrichment_gaps is not in this image — deploy.sh stages "
        "packages/shared into the worker's build context, the same way it does "
        "for the api. A job that cannot compute gaps must not report that "
        "there are none."
    ) from exc


# ── resolvers ─────────────────────────────────────────────────────────
#
# Each returns (value, provenance dict) or (None, reason string). The signature
# is deliberately total: a resolver may not return nothing without saying why.

_PUBLIC_SUFFIX_2 = {"co.uk", "com.au", "co.nz", "co.jp", "com.br", "co.za"}


def _registrable(url: str) -> str | None:
    m = re.match(r"^\s*(?:https?://)?(?:www\.)?([^/\s:?#]+)", str(url or ""),
                 re.I)
    if not m:
        return None
    host = m.group(1).lower().strip(".")
    parts = host.split(".")
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and ".".join(parts[-2:]) in _PUBLIC_SUFFIX_2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# Domains that host many entities' material and are therefore never the
# entity's OWN domain, however often they appear in its evidence.
_AGGREGATORS = frozenset((
    "linkedin.com", "glassdoor.com", "indeed.com", "crunchbase.com",
    "bloomberg.com", "reuters.com", "wsj.com", "forbes.com", "prnewswire.com",
    "businesswire.com", "globenewswire.com", "sec.gov", "ncua.gov", "fdic.gov",
    "occ.gov", "federalreserve.gov", "youtube.com", "twitter.com", "x.com",
    "facebook.com", "medium.com", "wikipedia.org", "google.com", "apple.com",
    "prweb.com", "yahoo.com", "msn.com", "cuinsight.com", "creditunions.com",
    "americanbanker.com", "bankrate.com", "nerdwallet.com", "zoominfo.com",
))

MIN_SELF_DOMAIN_HITS = 3


def resolve_self_domain(cur, entity_id, run_id):
    """The entity's own web domain, from the domain that dominates its evidence.

    Not a guess and not a search: an institution's own site is, by a wide
    margin, the most-cited non-aggregator host in its own evidence register.
    The floor and the aggregator list are what keep that true — without them a
    client with four LinkedIn citations and one own-site page would be assigned
    linkedin.com, which is worse than the gap.
    """
    cur.execute(
        """SELECT source_url FROM evidence_index
            WHERE entity_id = %s AND source_url IS NOT NULL""", (entity_id,))
    counts = Counter()
    for (url,) in cur.fetchall():
        d = _registrable(url)
        if d and d not in _AGGREGATORS:
            counts[d] += 1
    if not counts:
        return None, ("no evidence row for this entity carries a source_url on "
                      "a non-aggregator host, so no self-domain can be derived")
    domain, hits = counts.most_common(1)[0]
    if hits < MIN_SELF_DOMAIN_HITS:
        return None, (
            f"the leading non-aggregator domain {domain!r} appears on only "
            f"{hits} evidence row(s), below the floor of {MIN_SELF_DOMAIN_HITS}; "
            "one or two citations do not establish an institution's own site")
    # A tie is not a majority. Two domains level at the top means the entity's
    # own site has not been established — a merged brand, a holding company, or
    # contamination — and each of those wants a person, not a default.
    top = [d for d, n in counts.items() if n == hits]
    if len(top) > 1:
        return None, (f"{len(top)} domains tie at {hits} citations "
                      f"({', '.join(sorted(top)[:4])}); no single self-domain "
                      "is established")
    cur.execute("""SELECT source_url FROM evidence_index
                    WHERE entity_id = %s AND source_url ILIKE %s LIMIT 1""",
                (entity_id, f"%{domain}%"))
    row = cur.fetchone()
    return domain, {
        "source_url": row[0] if row else f"https://{domain}",
        "confidence": "FACT",
        "basis": (f"the registrable domain on {hits} of this entity's evidence "
                  f"rows, excluding aggregator hosts"),
    }


RESOLVERS = {
    # field name (normalised) -> ordered resolvers to try
    "website": [("self_domain", resolve_self_domain)],
}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


# ── the job ───────────────────────────────────────────────────────────

# The run states that can still have their gaps closed. Taken from
# `run_status_t` — the first draft guessed 'ACTIVE' and 'IN_PROGRESS', neither
# of which exists, and postgres rejected the enum outright. That is the good
# failure: a guessed vocabulary that HAPPENED to be valid would have scanned
# nothing and reported a clean run.
#
# SUPERSEDED and WITHDRAWN are excluded because closing a gap on either changes
# nothing a reader sees. INGESTED through PROMOTED are all in scope: a gap found
# before synthesis is the most useful kind, since it reaches the producer while
# the page is still being written.
ENRICHABLE_STATES = ("INGESTED", "CLAIMED", "SYNTHESISING", "STAGED", "PROMOTED")


def active_runs(cur) -> list:
    cur.execute(
        """SELECT r.id, r.entity_id FROM runs r
            WHERE enum_label(r.status) = ANY(%s)
              AND r.withdrawn_at IS NULL
            ORDER BY r.run_seq""", (list(ENRICHABLE_STATES),))
    return cur.fetchall()


def submissions_for(cur, run_id) -> dict:
    cur.execute("""SELECT enum_label(page), payload FROM submissions
                    WHERE run_id = %s AND superseded_at IS NULL""", (run_id,))
    return {p: (pl or {}) for p, pl in cur.fetchall()}


# ── The six-month refresh sweep ─────────────────────────────────────────
#
# 0031 computes refresh_due_date in the serving directory and 0032 gives
# refresh_requests an origin of 'cadence' — and then nothing raised one:
# the queue endpoint listed due entities and no writer existed, so a client
# past its date sat silent until a human noticed. This is that writer. It
# runs inside the hourly loop because the loop is the one scheduled thing
# that already owns "what should have happened and has not".
#
# Idempotent by the schema: refresh_requests_open_uq allows ONE open row
# per entity, so a due entity is requested once and re-requested only after
# the previous request closes. requested_by is NULL — the origin says who.
_DUE_SWEEP_SQL = """
    INSERT INTO refresh_requests (entity_id, observed_run_id, origin, reason,
                                  status)
    SELECT DISTINCT ON (r.entity_id)
           r.entity_id, r.id, 'cadence',
           'assessment dated ' || ad.assessment_date::date || ' passed its '
           || 'six-month refresh date '
           || (ad.assessment_date + INTERVAL '6 months')::date
           || ' (basis ' || ad.basis || ')',
           'REQUESTED'
      FROM runs r
      LEFT JOIN run_manifest rm ON rm.run_id = r.id
     CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                            r.request_id) ad
     WHERE r.promoted_at IS NOT NULL
       AND ad.assessment_date IS NOT NULL
       AND (ad.assessment_date + INTERVAL '6 months')::date <= CURRENT_DATE
       AND NOT EXISTS (SELECT 1 FROM refresh_requests q
                        WHERE q.entity_id = r.entity_id
                          AND q.status IN ('REQUESTED', 'ACKNOWLEDGED'))
     ORDER BY r.entity_id, r.promoted_at DESC
    ON CONFLICT DO NOTHING
    RETURNING entity_id
"""


def sweep_refresh_due(cur) -> int:
    """Raise a cadence refresh request for every promoted entity past its
    six-month date with nothing already open. Returns rows raised."""
    cur.execute(_DUE_SWEEP_SQL)
    return len(cur.fetchall())


def run_once(conn, trigger: str = "schedule") -> dict:
    """One execution. Idempotent by construction: it writes only attempt rows,
    reads only staged payloads, and changes nothing a later run depends on."""
    cur = conn.cursor()
    cur.execute("""INSERT INTO enrichment_jobs (trigger) VALUES (%s)
                   RETURNING id""", (trigger,))
    job_id = cur.fetchone()[0]
    conn.commit()

    tally = Counter()
    runs = active_runs(cur)
    try:
        for run_id, entity_id in runs:
            for page, payload in submissions_for(cur, run_id).items():
                for gap in gapmod.gaps_for_payload(page, payload):
                    tally["gaps"] += 1
                    field = _norm(gap.get("field"))
                    ladder = RESOLVERS.get(field) or []
                    if not ladder:
                        _attempt(cur, job_id, run_id, entity_id, gap, "none",
                                 "NO_SOURCE", None,
                                 reason=("no resolver is configured for this "
                                         "field. Clay is session-bound (this "
                                         "org's trigger API refuses connector "
                                         "grants) and Explorium has no key in "
                                         "Secret Manager, so a scheduled job "
                                         "cannot reach either; the gap stays "
                                         "on the producer's worklist"))
                        tally["no_source"] += 1
                        continue
                    for name, fn in ladder:
                        try:
                            value, extra = fn(cur, entity_id, run_id)
                        except Exception as exc:                # noqa: BLE001
                            _attempt(cur, job_id, run_id, entity_id, gap, name,
                                     "FAILED", None,
                                     reason=f"{type(exc).__name__}: {exc}"[:400])
                            tally["failed"] += 1
                            continue
                        if value:
                            _attempt(cur, job_id, run_id, entity_id, gap, name,
                                     "RESOLVED", value, prov=extra)
                            tally["resolved"] += 1
                            break
                        _attempt(cur, job_id, run_id, entity_id, gap, name,
                                 "NOT_RUN", None, reason=str(extra)[:400])
                        tally["not_run"] += 1
        conn.commit()
        err = None
    except Exception as exc:                                    # noqa: BLE001
        conn.rollback()
        err = f"{type(exc).__name__}: {exc}"[:400]

    # The refresh sweep commits separately from the gap loop: a resolver
    # failure must not cost the due-date safeguard, and vice versa.
    try:
        tally["refresh_raised"] = sweep_refresh_due(cur)
        conn.commit()
    except Exception as exc:                                    # noqa: BLE001
        conn.rollback()
        err = err or f"refresh_sweep {type(exc).__name__}: {exc}"[:400]

    cur.execute("""UPDATE enrichment_jobs
                      SET finished_at = now(), runs_scanned = %s,
                          gaps_found = %s, resolved = %s, not_run = %s,
                          failed = %s, error = %s
                    WHERE id = %s""",
                (len(runs), tally["gaps"], tally["resolved"],
                 tally["not_run"] + tally["no_source"], tally["failed"],
                 err, job_id))
    conn.commit()
    return {"job_id": job_id, "runs_scanned": len(runs),
            "gaps_found": tally["gaps"], "resolved": tally["resolved"],
            "not_run": tally["not_run"] + tally["no_source"],
            "failed": tally["failed"],
            "refresh_requests_raised": tally["refresh_raised"],
            "error": err}


def _attempt(cur, job_id, run_id, entity_id, gap, resolver, status, value,
             prov=None, reason=None) -> None:
    prov = prov if isinstance(prov, dict) else {}
    cur.execute(
        """INSERT INTO enrichment_attempts
             (job_id, run_id, entity_id, page, section, field, field_path,
              resolver, status, value, source_url, excerpt, confidence, reason)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (job_id, run_id, entity_id, gap.get("page"), gap.get("section"),
         gap.get("field"), gap.get("path"), resolver, status, value,
         prov.get("source_url"), prov.get("basis"), prov.get("confidence"),
         reason))


def _connect():
    """The worker's canonical connect, matching job_main.py exactly.

    The first version imported a `connect` from .persist that does not exist —
    guessed, not read — and the job died on ImportError before touching the
    database. The endpoint reported "no enrichment job has ever run", which was
    true and is why it says that rather than assuming health.

    Local dev goes through pg8000 with a password; production goes through the
    Cloud SQL connector with IAM auth on the private IP. No DB password exists
    in production (charter: IAM DB auth), so these cannot be one path.
    """
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        host = os.environ["LOCAL_DATABASE_URL"].split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(
            user="dmai-worker@digital-maturity-assessor.iam",
            password="local", host=host, port=5432, database="dma_insights")
    from google.cloud.sql.connector import Connector
    return Connector().connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


def main() -> int:
    conn = _connect()
    try:
        out = run_once(conn, os.environ.get("ENRICH_TRIGGER", "schedule"))
    finally:
        conn.close()
    print(f"enrichment job {out['job_id']}: {out['runs_scanned']} run(s), "
          f"{out['gaps_found']} gap(s) — {out['resolved']} resolved, "
          f"{out['not_run']} unresolved, {out['failed']} failed")
    if out["error"]:
        print(f"ERROR: {out['error']}", file=sys.stderr)
        return 1
    # A job that scanned no runs is not a success. Two promoted clients exist;
    # zero means the query, the status vocabulary or the database is wrong, and
    # a green exit would report that as "nothing to do".
    if out["runs_scanned"] == 0:
        print("no active runs found — the loop had nothing to scan, which is "
              "a failure to look, not a clean result", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
