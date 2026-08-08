"""The findings memory — what went wrong, how it was measured, what was
changed about it, and whether the change held (tables in migration 0034).

## Why this lives in the connector

Three facts already true before any of this was written:

  * the connector bundles the 384-dim encoder in-image for V4 grounding, so a
    finding can be embedded where it is recorded with no new dependency;
  * the database already has `vector`, `pg_trgm` and HNSW indexes created once
    at migration, so "have we seen this before" can be asked semantically and
    lexically over the same rows;
  * the connector is already the only component permitted to write.

## Invariant 1, stated once so nobody has to guess later

Invariant 1 forbids a model call ON THE SERVING REQUEST PATH. `record_finding`
embeds inside the connector at WRITE time, exactly as V4 embeds at submit. The
serving path never touches the encoder and nothing here changes that: the API
holds SELECT on these tables and no more, and every search below can answer
with lexical Postgres alone when no encoder is present. If this module is ever
cited as precedent for embedding something while a client waits, it has been
misread.

## Identifiers come from the server (invariant 10)

`MEM-0001` and `REF-0001` are minted here under an advisory lock, the same
discipline as `register_evidence`'s `E-CC-###`. A caller-supplied id is ignored.

## Dedup, and what counts as "the same defect"

One row per DEFECT, not per report: the same defect reported by three QA agents
is one finding with three sightings. The dedup key is a SHA-256 over the
defect's IDENTITY, not its wording —

    component | defect_class | locus | normalised(title)[:200]

where `locus` is the first of `file_path`, `surface`, `gate_id` that is present.
A caller who knows better may pass `dedup_key` and take the consequences. The
hash is computed in Python rather than by `digest()` in SQL (which is what
`evidence_index` does) for one reason: it can then be asserted in a unit test
with no database, and a dedup rule nobody can test is a dedup rule nobody
trusts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

_FINDING_LOCK = 815004      # advisory lock: the MEM-#### counter
_REFINEMENT_LOCK = 815005   # advisory lock: the REF-#### counter

# Mirrors of the CHECK constraints in migration 0034. A test asserts these
# lists and the migration's are identical — a vocabulary that drifts between
# the writer and the column rejects at INSERT time with a constraint name and
# no advice, which is the least useful refusal available.
SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "INFO")
STATUSES = ("OPEN", "INVESTIGATING", "RESOLVED", "RECURRED", "WONTFIX",
            "DUPLICATE")
RAISERS = ("QA_AGENT", "REVIEWER", "GATE", "USER", "BUILD_AGENT", "TEST",
           "MONITOR")
TARGET_KINDS = ("SKILL", "AGENT", "COMPONENT", "GATE", "TEST", "SCHEMA", "DOC",
                "PROCESS")
RELATIONS = ("ADDRESSES", "CLOSES")

#: A finding that cannot say how it was measured is an opinion. Same floor as
#: the CHECK constraint; enforced here too so the refusal names the rule
#: instead of naming a constraint.
MEASUREMENT_FLOOR = 30

OPEN_STATUSES = ("OPEN", "INVESTIGATING", "RECURRED")


# ── helpers ─────────────────────────────────────────────────────────────
def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _vec_literal(vec) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


def _embed(encoder, text: str):
    """Best-effort embedding. A missing or broken encoder is not an error:
    the row stores NULL and the lexical paths still answer, which is the same
    degradation `serving_passages` documents."""
    if encoder is None:
        return None, None
    try:
        return _vec_literal(encoder.encode([text])[0]), encoder.name
    except Exception:                                          # noqa: BLE001
        return None, None


def content_hash(component, defect_class, locus, title, dedup_key=None) -> str:
    """The dedup key, computed exactly as documented in this module's header.
    Public because a caller that wants to predict whether its report will
    dedup should be able to, without guessing."""
    if dedup_key:
        return hashlib.sha256(_norm(dedup_key).encode()).hexdigest()
    basis = "|".join((_norm(component), _norm(defect_class), _norm(locus),
                      _norm(title)[:200]))
    return hashlib.sha256(basis.encode()).hexdigest()


def _locus(item: dict) -> str:
    for key in ("file_path", "surface", "gate_id"):
        if item.get(key):
            return str(item[key])
    return ""


def _mint(cur, lock, table, column, prefix) -> str:
    """Minted under an advisory lock so concurrent sessions never race the
    counter — `svc_mcp` runs on session-mode pooling and a promote can hold
    locks for a while.

    No `LIKE '<prefix>-%'` filter, deliberately: `substring` returns NULL for
    anything that does not match and `MAX` ignores NULLs, which is the same
    filter without a literal `%` in a statement that carries no parameters.
    """
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
    cur.execute(
        f"""SELECT COALESCE(MAX(substring({column} FROM '{prefix}-(\\d+)')::int), 0) + 1
              FROM {table}""")
    return f"{prefix}-{cur.fetchone()[0]:04d}"


def _known_classes(cur) -> list:
    cur.execute("SELECT class_id FROM memory_defect_classes ORDER BY class_id")
    return [r[0] for r in cur.fetchall()]


def _row(cur):
    """Rows as dicts, using the cursor's own description — pg8000 returns
    tuples and a positional unpack five columns later is how a column gets
    silently swapped for its neighbour."""
    cols = [d[0] if isinstance(d[0], str) else d[0].decode()
            for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _clean(rows):
    return [{k: _iso(v) for k, v in r.items()} for r in rows]


# ── record ──────────────────────────────────────────────────────────────
def record_finding(conn, finding: dict, encoder=None) -> dict:
    """Idempotent by content hash. Returns the finding id, whether it deduped,
    and the sighting that this call added."""
    cur = conn.cursor()
    errors = []

    title = str(finding.get("title") or "").strip()
    observed = str(finding.get("observed") or "").strip()
    measurement = str(finding.get("measurement") or "").strip()
    component = str(finding.get("component") or "").strip()
    defect_class = str(finding.get("defect_class") or "").strip().upper()
    severity = str(finding.get("severity") or "").strip().upper()
    raised_by_kind = str(finding.get("raised_by_kind") or "").strip().upper()
    raised_by = str(finding.get("raised_by") or "").strip()

    if not title:
        errors.append("title: required — one line naming what is wrong")
    if not observed:
        errors.append("observed: required — what was actually seen")
    if len(measurement) < MEASUREMENT_FLOOR:
        errors.append(
            f"measurement: {len(measurement)} chars — at least "
            f"{MEASUREMENT_FLOOR} are required. State the command, query, "
            "HTTP status or count that produced this, with its denominator. "
            "A finding that cannot say how it was measured is an opinion.")
    if not component:
        errors.append("component: required — api · mcp · web · worker · "
                      "migrations · infra · skill:<name> · agent:<name>")
    if severity not in SEVERITIES:
        errors.append(f"severity: {severity!r} not in {SEVERITIES}")
    if raised_by_kind not in RAISERS:
        errors.append(f"raised_by_kind: {raised_by_kind!r} not in {RAISERS}")
    if not raised_by:
        errors.append("raised_by: required — the agent, gate or person by name")

    known = _known_classes(cur)
    new_class = finding.get("new_class")
    if defect_class and defect_class not in known:
        if isinstance(new_class, dict):
            missing = [k for k in ("title", "description", "tell", "probe")
                       if not str(new_class.get(k) or "").strip()]
            if missing:
                errors.append(
                    f"new_class: {defect_class} is not a known class and the "
                    f"definition is missing {missing}. A class may be invented "
                    "only by defining it: title, description, tell (how it "
                    "presents) and probe (how to check for it).")
        else:
            errors.append(
                f"defect_class: {defect_class!r} is not a known class. Use one "
                f"of {known}, or pass new_class={{title, description, tell, "
                "probe}} to define it — a class may be invented, never "
                "invented silently.")
    elif not defect_class:
        errors.append(f"defect_class: required — one of {known}")

    if errors:
        return {"finding_id": None, "deduped": False, "sighting_id": None,
                "errors": errors}

    if defect_class not in known:
        cur.execute(
            """INSERT INTO memory_defect_classes
                 (class_id, title, description, tell, probe, created_by)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (class_id) DO NOTHING""",
            (defect_class, new_class["title"], new_class["description"],
             new_class["tell"], new_class["probe"], raised_by))

    chash = content_hash(component, defect_class, _locus(finding), title,
                         finding.get("dedup_key"))
    cur.execute("SELECT finding_id, status FROM memory_findings "
                "WHERE content_hash = %s", (chash,))
    existing = cur.fetchone()

    if existing is None:
        finding_id = _mint(cur, _FINDING_LOCK, "memory_findings",
                           "finding_id", "MEM")
        emb, model = _embed(encoder,
                            f"{title}\n{observed}\n{measurement}")
        cur.execute(
            """INSERT INTO memory_findings
                 (finding_id, content_hash, title, observed, measurement,
                  measured_value, expected, component, file_path, surface,
                  gate_id, defect_class, severity, status, raised_by_kind,
                  raised_by, run_id, entity_id, annotation_id, fix_hint,
                  embedding, embedding_model, first_seen_at, last_seen_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN',%s,%s,
                       %s,%s,%s,%s,%s::vector,%s,now(),now())""",
            (finding_id, chash, title, observed, measurement,
             finding.get("measured_value"), finding.get("expected"),
             component, finding.get("file_path"), finding.get("surface"),
             finding.get("gate_id"), defect_class, severity, raised_by_kind,
             raised_by, finding.get("run_id"), finding.get("entity_id"),
             finding.get("annotation_id"), finding.get("fix_hint"),
             emb, model))
        deduped, status_now = False, "OPEN"
    else:
        finding_id, status_now = existing
        deduped = True
        # A defect reported again while it is closed is a RECURRENCE, and the
        # store says so rather than quietly reopening: `report_recurrence` is
        # the tool that names the refinement that failed to hold.
        cur.execute("UPDATE memory_findings SET last_seen_at = now() "
                    "WHERE finding_id = %s", (finding_id,))

    sighting_id = _add_sighting(
        cur, finding_id,
        reported_by_kind=raised_by_kind, reported_by=raised_by,
        measurement=measurement, measured_value=finding.get("measured_value"),
        note=finding.get("note"), session_ref=finding.get("session_ref"),
        source_ref=finding.get("source_ref"), run_id=finding.get("run_id"),
        entity_id=finding.get("entity_id"),
        annotation_id=finding.get("annotation_id"))

    cur.execute("""SELECT sightings, recurrences, status
                     FROM memory_finding_state WHERE finding_id = %s""",
                (finding_id,))
    sightings, recurrences, status_now = cur.fetchone()
    conn.commit()
    out = {"finding_id": finding_id, "deduped": deduped,
           "sighting_id": sighting_id, "status": status_now,
           "sightings": sightings, "recurrences": recurrences,
           "content_hash": chash, "errors": []}
    if deduped and status_now in ("RESOLVED", "WONTFIX"):
        out["warning"] = (
            f"{finding_id} is {status_now} and was just reported again. If a "
            "refinement was supposed to have closed it, call report_recurrence "
            "so the refinement that did not hold is named.")
    return out


def _add_sighting(cur, finding_id, *, reported_by_kind, reported_by,
                  measurement=None, measured_value=None, note=None,
                  session_ref=None, source_ref=None, run_id=None,
                  entity_id=None, annotation_id=None, after_refinement=None):
    """One row per report. `source_ref` is the caller's idempotency token: a
    replayed ingest returns the sighting it already made instead of a second
    one (partial unique index, 0034)."""
    if source_ref:
        cur.execute("""SELECT id FROM memory_finding_sightings
                        WHERE finding_id = %s AND source_ref = %s""",
                    (finding_id, source_ref))
        prior = cur.fetchone()
        if prior:
            return prior[0]
    cur.execute(
        """INSERT INTO memory_finding_sightings
             (finding_id, reported_by_kind, reported_by, observed_at,
              session_ref, source_ref, measurement, measured_value, note,
              run_id, entity_id, annotation_id, after_refinement)
           VALUES (%s,%s,%s,now(),%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (finding_id, reported_by_kind, reported_by, session_ref, source_ref,
         measurement, measured_value, note, run_id, entity_id, annotation_id,
         after_refinement))
    return cur.fetchone()[0]


# ── search ──────────────────────────────────────────────────────────────
_SEARCH_COLS = """f.finding_id, f.title, f.component, f.file_path, f.surface,
                  f.gate_id, f.defect_class, f.severity, f.status,
                  f.measurement, f.measured_value, f.fix_hint, f.resolved_by,
                  f.last_seen_at"""


def _shape(row, matched_by, score):
    return {"finding_id": row[0], "title": row[1], "component": row[2],
            "file_path": row[3], "surface": row[4], "gate_id": row[5],
            "defect_class": row[6], "severity": row[7], "status": row[8],
            "measurement": row[9], "measured_value": row[10],
            "fix_hint": row[11], "resolved_by": row[12],
            "last_seen_at": _iso(row[13]),
            "matched_by": [matched_by], "scores": {matched_by: score}}


def _filters(component, defect_class, severity, status):
    """(sql, params) — every filter optional, none of them defaulted to a value
    that looks like data."""
    sql, params = "", []
    if component:
        sql += " AND f.component = %s"
        params.append(component)
    if defect_class:
        sql += " AND f.defect_class = %s"
        params.append(str(defect_class).upper())
    if severity:
        sql += " AND f.severity = %s"
        params.append(str(severity).upper())
    if status:
        sql += " AND f.status = ANY(%s)"
        params.append([s.upper() for s in
                       ([status] if isinstance(status, str) else status)])
    return sql, params


def search_findings(conn, query: str, *, mode: str = "auto", limit: int = 10,
                    component=None, defect_class=None, severity=None,
                    status=None, encoder=None) -> dict:
    """"Have we seen this before" is asked two ways, so it is answered two
    ways. Every path that ran is named, and every path that did not is named
    with its reason — an empty result from a path that never ran is not
    evidence of absence."""
    cur = conn.cursor()
    query = str(query or "").strip()
    if not query:
        return {"query": query, "results": [], "paths_run": [],
                "paths_skipped": {"all": "empty query"},
                "errors": ["query: required"]}
    limit = max(1, min(int(limit or 10), 100))
    mode = (mode or "auto").lower()
    if mode not in ("auto", "semantic", "lexical", "fuzzy"):
        return {"query": query, "results": [], "errors": [
            f"mode: {mode!r} not in ('auto','semantic','lexical','fuzzy')"]}

    fsql, fparams = _filters(component, defect_class, severity, status)
    merged, paths_run, skipped = {}, [], {}

    def absorb(rows, matched_by):
        for row, score in rows:
            hit = merged.get(row[0])
            if hit is None:
                merged[row[0]] = _shape(row, matched_by, score)
            else:
                hit["matched_by"].append(matched_by)
                hit["scores"][matched_by] = score

    want_lexical = mode in ("auto", "lexical")
    want_semantic = mode in ("auto", "semantic")
    want_fuzzy = mode in ("auto", "fuzzy")

    # 1. lexical — deterministic core Postgres, and the only path that needs
    #    nothing bundled in the image.
    if want_lexical:
        cur.execute("SELECT websearch_to_tsquery('english', %s)::text", (query,))
        tsq = cur.fetchone()[0]
        if not tsq:
            skipped["lexical"] = ("websearch_to_tsquery produced no lexemes "
                                  "for this query (all stop words?)")
        else:
            cur.execute(
                f"""SELECT {_SEARCH_COLS},
                           ts_rank_cd(f.search_tsv,
                                      websearch_to_tsquery('english', %s)) AS r
                      FROM memory_findings f
                     WHERE f.search_tsv @@ websearch_to_tsquery('english', %s)
                       {fsql}
                     ORDER BY r DESC, f.last_seen_at DESC
                     LIMIT %s""",
                [query, query, *fparams, limit])
            rows = cur.fetchall()
            absorb([(r[:-1], round(float(r[-1]), 5)) for r in rows], "lexical")
            paths_run.append("lexical")

    # 2. semantic — pgvector KNN over text embedded at RECORD time. Skipped,
    #    never faked, when no encoder is in the image.
    if want_semantic:
        lit, _model = _embed(encoder, query)
        if lit is None:
            skipped["semantic"] = ("no encoder available in this image; the "
                                   "lexical paths answered instead")
        else:
            cur.execute(
                f"""SELECT {_SEARCH_COLS},
                           1 - (f.embedding <=> %s::vector) AS sim
                      FROM memory_findings f
                     WHERE f.embedding IS NOT NULL {fsql}
                     ORDER BY f.embedding <=> %s::vector
                     LIMIT %s""",
                [lit, *fparams, lit, limit])
            rows = cur.fetchall()
            absorb([(r[:-1], round(float(r[-1]), 4)) for r in rows], "semantic")
            paths_run.append("semantic")

    # 3. trigram — for the query that shares no lexeme with the corpus (a
    #    typo, an abbreviation). In auto mode only when the others found
    #    nothing, because it is the least precise of the three.
    if want_fuzzy and (mode == "fuzzy" or not merged):
        cur.execute(
            f"""SELECT {_SEARCH_COLS}, similarity(f.title, %s) AS sim
                  FROM memory_findings f
                 WHERE similarity(f.title, %s) > 0.20 {fsql}
                 ORDER BY sim DESC
                 LIMIT %s""",
            [query, query, *fparams, limit])
        rows = cur.fetchall()
        absorb([(r[:-1], round(float(r[-1]), 4)) for r in rows], "trigram")
        paths_run.append("trigram")
    elif want_fuzzy:
        skipped["trigram"] = ("not needed: an earlier path matched. Ask with "
                              "mode='fuzzy' to force it.")

    results = sorted(merged.values(),
                     key=lambda h: (-len(h["matched_by"]),
                                    -max(h["scores"].values())))[:limit]
    return {"query": query, "mode": mode, "paths_run": paths_run,
            "paths_skipped": skipped, "count": len(results),
            "results": results, "errors": []}


# ── list ────────────────────────────────────────────────────────────────
def list_open_findings(conn, *, component=None, severity=None,
                       defect_class=None, status=None, min_age_days=None,
                       max_age_days=None, limit: int = 50) -> dict:
    """Everything not closed, newest sighting first. `status` defaults to the
    three that mean open (OPEN, INVESTIGATING, RECURRED) — RECURRED belongs in
    that list because a fix that did not hold is open again."""
    cur = conn.cursor()
    limit = max(1, min(int(limit or 50), 500))
    where, params = ["1=1"], []
    statuses = ([status.upper()] if isinstance(status, str)
                else [s.upper() for s in status] if status
                else list(OPEN_STATUSES))
    where.append("status = ANY(%s)")
    params.append(statuses)
    if component:
        where.append("component = %s")
        params.append(component)
    if severity:
        where.append("severity = %s")
        params.append(str(severity).upper())
    if defect_class:
        where.append("defect_class = %s")
        params.append(str(defect_class).upper())
    if min_age_days is not None:
        where.append("age_days >= %s")
        params.append(int(min_age_days))
    if max_age_days is not None:
        where.append("age_days <= %s")
        params.append(int(max_age_days))
    cur.execute(
        f"""SELECT finding_id, title, component, file_path, surface, gate_id,
                   defect_class, severity, status, raised_by_kind, raised_by,
                   measurement, measured_value, fix_hint, sightings,
                   recurrences, age_days, last_seen_at, annotation_id
              FROM memory_finding_state
             WHERE {' AND '.join(where)}
             ORDER BY
               CASE severity WHEN 'BLOCKER' THEN 0 WHEN 'MAJOR' THEN 1
                             WHEN 'MINOR' THEN 2 ELSE 3 END,
               recurrences DESC, sightings DESC, last_seen_at DESC
             LIMIT %s""", [*params, limit])
    rows = _clean(_row(cur))
    return {"count": len(rows), "statuses": statuses, "findings": rows,
            "errors": []}


def list_defect_classes(conn) -> dict:
    """The shared vocabulary, with each class's tell and probe. Read this
    before inventing a class: a memory rots when one defect is filed under
    three synonyms."""
    cur = conn.cursor()
    cur.execute(
        """SELECT c.class_id, c.title, c.description, c.tell, c.probe,
                  count(f.finding_id) AS findings,
                  count(f.finding_id) FILTER (WHERE f.status IN
                        ('OPEN','INVESTIGATING','RECURRED')) AS open_findings
             FROM memory_defect_classes c
             LEFT JOIN memory_findings f ON f.defect_class = c.class_id
            GROUP BY c.class_id, c.title, c.description, c.tell, c.probe
            ORDER BY open_findings DESC, findings DESC, c.class_id""")
    return {"classes": _clean(_row(cur)), "errors": []}


# ── refine ──────────────────────────────────────────────────────────────
def record_refinement(conn, refinement: dict) -> dict:
    """What was changed, where, in response to which findings. The server
    allocates REF-####."""
    cur = conn.cursor()
    errors = []
    target_kind = str(refinement.get("target_kind") or "").strip().upper()
    target = str(refinement.get("target") or "").strip()
    change = str(refinement.get("change") or "").strip()
    applied_by = str(refinement.get("applied_by") or "").strip()
    commit_sha = refinement.get("commit_sha") or None
    change_ref = refinement.get("change_ref") or None
    addressed = refinement.get("finding_ids") or []
    if isinstance(addressed, str):
        addressed = [addressed]

    if target_kind not in TARGET_KINDS:
        errors.append(f"target_kind: {target_kind!r} not in {TARGET_KINDS}")
    if not target:
        errors.append("target: required — the thing that changed, named the "
                      "way its owner names it (skill:x, agent:x, CG-13, a path)")
    if not change:
        errors.append("change: required — what was changed, in prose")
    if not applied_by:
        errors.append("applied_by: required")
    if not (commit_sha or change_ref):
        errors.append("commit_sha or change_ref: one is required — a "
                      "refinement nobody can locate is a claim, not a change")
    if not addressed:
        errors.append("finding_ids: required — a refinement exists because of "
                      "a finding; record the finding first")
    if errors:
        return {"refinement_id": None, "errors": errors}

    cur.execute("SELECT finding_id FROM memory_findings "
                "WHERE finding_id = ANY(%s)", (list(addressed),))
    found = {r[0] for r in cur.fetchall()}
    missing = [f for f in addressed if f not in found]
    if missing:
        return {"refinement_id": None, "errors": [
            f"finding_ids: {missing} do not exist. Record the finding first — "
            "a refinement against nothing cannot be checked for recurrence."]}

    refinement_id = _mint(cur, _REFINEMENT_LOCK, "memory_refinements",
                          "refinement_id", "REF")
    cur.execute(
        """INSERT INTO memory_refinements
             (refinement_id, target_kind, target, change, rationale,
              commit_sha, change_ref, gate_added, verification, applied_by,
              applied_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""",
        (refinement_id, target_kind, target, change,
         refinement.get("rationale"), commit_sha, change_ref,
         refinement.get("gate_added"), refinement.get("verification"),
         applied_by))
    relation = str(refinement.get("relation") or "ADDRESSES").upper()
    if relation not in RELATIONS:
        relation = "ADDRESSES"
    for fid in addressed:
        cur.execute(
            """INSERT INTO memory_refinement_findings
                 (refinement_id, finding_id, relation)
               VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (refinement_id, fid, relation))
    conn.commit()
    return {"refinement_id": refinement_id, "addresses": list(addressed),
            "relation": relation, "errors": []}


def resolve_finding(conn, finding_id: str, refinement_id: str, *,
                    verification=None, resolved_by_actor=None) -> dict:
    """Close a finding by naming the refinement that closed it. There is no
    way to close one without — the column is NOT NULL under a CHECK, and that
    is deliberate: without it, "did the fix hold?" has no subject."""
    cur = conn.cursor()
    if not refinement_id:
        return {"finding_id": finding_id, "status": None, "errors": [
            "refinement_id: required — a finding is closed BY something. "
            "Call record_refinement first and pass its id here."]}
    cur.execute("SELECT status FROM memory_findings WHERE finding_id = %s",
                (finding_id,))
    row = cur.fetchone()
    if row is None:
        return {"finding_id": finding_id, "status": None,
                "errors": [f"unknown_finding: {finding_id}"]}
    cur.execute("SELECT applied_at FROM memory_refinements "
                "WHERE refinement_id = %s", (refinement_id,))
    ref = cur.fetchone()
    if ref is None:
        return {"finding_id": finding_id, "status": row[0], "errors": [
            f"unknown_refinement: {refinement_id} — record_refinement first"]}

    cur.execute(
        """UPDATE memory_findings
              SET status = 'RESOLVED', resolved_at = now(), resolved_by = %s
            WHERE finding_id = %s""", (refinement_id, finding_id))
    cur.execute(
        """INSERT INTO memory_refinement_findings
             (refinement_id, finding_id, relation)
           VALUES (%s,%s,'CLOSES')
           ON CONFLICT (refinement_id, finding_id)
           DO UPDATE SET relation = 'CLOSES'""",
        (refinement_id, finding_id))
    if verification:
        cur.execute(
            """UPDATE memory_refinements
                  SET verification = COALESCE(verification, %s)
                WHERE refinement_id = %s""", (verification, refinement_id))
    conn.commit()
    return {"finding_id": finding_id, "status": "RESOLVED",
            "resolved_by": refinement_id,
            "verification": verification,
            "resolved_by_actor": resolved_by_actor,
            "note": ("Resolution is a claim until it survives. Any later "
                     "sighting of this finding is a recurrence against "
                     f"{refinement_id}; report it with report_recurrence."),
            "errors": []}


def report_recurrence(conn, finding_id: str, *, measurement: str,
                      reported_by: str, reported_by_kind: str = "QA_AGENT",
                      after_refinement=None, measured_value=None, note=None,
                      session_ref=None, source_ref=None) -> dict:
    """A finding that was resolved and came back. Recurrence is the signal
    that matters: a fix that did not hold is more informative than one that
    did, and it is recorded AGAINST THE FIX BY NAME."""
    cur = conn.cursor()
    measurement = str(measurement or "").strip()
    if len(measurement) < MEASUREMENT_FLOOR:
        return {"finding_id": finding_id, "errors": [
            f"measurement: {len(measurement)} chars — at least "
            f"{MEASUREMENT_FLOOR}. A recurrence claim is only as good as the "
            "measurement that saw it come back."]}
    cur.execute("""SELECT status, resolved_by FROM memory_findings
                    WHERE finding_id = %s""", (finding_id,))
    row = cur.fetchone()
    if row is None:
        return {"finding_id": finding_id,
                "errors": [f"unknown_finding: {finding_id}"]}
    status, resolved_by = row
    refinement = after_refinement or resolved_by
    if refinement is None:
        return {"finding_id": finding_id, "status": status, "errors": [
            f"{finding_id} was never resolved by a refinement, so nothing can "
            "have failed to hold. This is another sighting, not a recurrence "
            "— use record_finding (it dedups to the same finding)."]}
    cur.execute("SELECT 1 FROM memory_refinements WHERE refinement_id = %s",
                (refinement,))
    if cur.fetchone() is None:
        return {"finding_id": finding_id, "status": status,
                "errors": [f"unknown_refinement: {refinement}"]}

    sighting_id = _add_sighting(
        cur, finding_id, reported_by_kind=str(reported_by_kind).upper(),
        reported_by=reported_by, measurement=measurement,
        measured_value=measured_value, note=note, session_ref=session_ref,
        source_ref=source_ref, after_refinement=refinement)
    cur.execute(
        """UPDATE memory_findings
              SET status = 'RECURRED', last_seen_at = now()
            WHERE finding_id = %s""", (finding_id,))
    cur.execute("""SELECT sightings, recurrences FROM memory_finding_state
                    WHERE finding_id = %s""", (finding_id,))
    sightings, recurrences = cur.fetchone()
    cur.execute("""SELECT held, findings_recurred FROM memory_refinement_outcome
                    WHERE refinement_id = %s""", (refinement,))
    outcome = cur.fetchone()
    conn.commit()
    return {"finding_id": finding_id, "status": "RECURRED",
            "sighting_id": sighting_id, "sightings": sightings,
            "recurrences": recurrences,
            "refinement_that_did_not_hold": refinement,
            "refinement_still_holds": (bool(outcome[0]) if outcome else None),
            "errors": []}


# ── the loop's own read ─────────────────────────────────────────────────
def memory_digest(conn, days: int = 7) -> dict:
    """What a weekly refinement pass needs in one call: what came back, what
    is new, which refinements held, and which classes are still producing.
    Every number here is computed from the two source tables at read time
    (invariant 8) — nothing in this store keeps a count."""
    cur = conn.cursor()
    days = max(1, min(int(days or 7), 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    cur.execute(
        """SELECT s.finding_id, f.title, f.component, f.defect_class,
                  f.severity, s.after_refinement, s.observed_at, s.reported_by,
                  s.measurement
             FROM memory_finding_sightings s
             JOIN memory_findings f ON f.finding_id = s.finding_id
            WHERE s.after_refinement IS NOT NULL AND s.observed_at >= %s
            ORDER BY s.observed_at DESC""", (since,))
    recurrences = _clean(_row(cur))

    cur.execute(
        """SELECT finding_id, title, component, defect_class, severity,
                  status, raised_by, sightings, first_seen_at, measurement
             FROM memory_finding_state
            WHERE first_seen_at >= %s
            ORDER BY first_seen_at DESC""", (since,))
    new_findings = _clean(_row(cur))

    cur.execute(
        """SELECT refinement_id, target_kind, target, change, gate_added,
                  commit_sha, applied_at, findings_addressed, findings_recurred,
                  held
             FROM memory_refinement_outcome
            WHERE applied_at >= %s
            ORDER BY applied_at DESC""", (since,))
    refinements = _clean(_row(cur))

    cur.execute(
        """SELECT f.defect_class, c.title,
                  count(*) FILTER (WHERE f.status IN
                        ('OPEN','INVESTIGATING','RECURRED')) AS open_findings,
                  count(*) AS total,
                  max(f.last_seen_at) AS last_seen
             FROM memory_findings f
             JOIN memory_defect_classes c ON c.class_id = f.defect_class
            GROUP BY f.defect_class, c.title
            HAVING count(*) FILTER (WHERE f.status IN
                   ('OPEN','INVESTIGATING','RECURRED')) > 0
            ORDER BY open_findings DESC, total DESC""")
    classes = _clean(_row(cur))

    cur.execute(
        """SELECT finding_id, title, component, defect_class, severity,
                  age_days, sightings
             FROM memory_finding_state
            WHERE status IN ('OPEN','INVESTIGATING','RECURRED')
              AND resolved_by IS NULL AND age_days >= 14
            ORDER BY age_days DESC LIMIT 50""")
    ageing = _clean(_row(cur))

    cur.execute(
        """SELECT count(*) FILTER (WHERE status IN
                  ('OPEN','INVESTIGATING','RECURRED')),
                  count(*) FILTER (WHERE status = 'RESOLVED'),
                  count(*)
             FROM memory_findings""")
    open_n, resolved_n, total_n = cur.fetchone()

    return {
        "window_days": days, "since": since.isoformat(),
        "totals": {"open": open_n, "resolved": resolved_n, "all": total_n},
        "recurrences_in_window": recurrences,
        "new_findings_in_window": new_findings,
        "refinements_in_window": refinements,
        "open_by_class": classes,
        "ageing_unrefined": ageing,
        "reading": (
            "Recurrences first: each names the refinement that did not hold, "
            "so that refinement's target is where the next change belongs. "
            "`open_by_class` says which SHAPE of defect this build is still "
            "producing; a class with several open findings is a process "
            "problem, not several bugs. `ageing_unrefined` is what nobody "
            "has changed anything about."),
        "errors": [],
    }


def get_finding(conn, finding_id: str) -> dict:
    """One finding, with every sighting and every refinement against it."""
    cur = conn.cursor()
    cur.execute(
        """SELECT f.finding_id, f.title, f.observed, f.measurement,
                  f.measured_value, f.expected, f.component, f.file_path,
                  f.surface, f.gate_id, f.defect_class, f.severity, f.status,
                  f.raised_by_kind, f.raised_by, f.fix_hint, f.duplicate_of,
                  f.resolved_by, f.resolved_at, f.first_seen_at,
                  f.last_seen_at, f.annotation_id, f.run_id, f.entity_id,
                  f.embedding IS NOT NULL AS embedded
             FROM memory_findings f WHERE f.finding_id = %s""", (finding_id,))
    rows = _clean(_row(cur))
    if not rows:
        return {"finding": None, "errors": [f"unknown_finding: {finding_id}"]}
    finding = rows[0]
    finding["run_id"] = str(finding["run_id"]) if finding["run_id"] else None
    finding["entity_id"] = (str(finding["entity_id"])
                            if finding["entity_id"] else None)
    cur.execute(
        """SELECT id, reported_by_kind, reported_by, observed_at, session_ref,
                  source_ref, measurement, measured_value, note,
                  after_refinement, annotation_id
             FROM memory_finding_sightings
            WHERE finding_id = %s ORDER BY observed_at""", (finding_id,))
    sightings = _clean(_row(cur))
    cur.execute(
        """SELECT r.refinement_id, r.target_kind, r.target, r.change,
                  r.gate_added, r.commit_sha, r.change_ref, r.verification,
                  r.applied_by, r.applied_at, l.relation
             FROM memory_refinement_findings l
             JOIN memory_refinements r ON r.refinement_id = l.refinement_id
            WHERE l.finding_id = %s ORDER BY r.applied_at""", (finding_id,))
    refinements = _clean(_row(cur))
    return {"finding": finding, "sightings": sightings,
            "refinements": refinements,
            "sighting_count": len(sightings),
            "recurrence_count": sum(1 for s in sightings
                                    if s.get("after_refinement")),
            "errors": []}


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, sort_keys=True)
