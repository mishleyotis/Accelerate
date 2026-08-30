"""get_evidence (stage 2.3) — the three-way split.

Package Evidence_Master ids are workbook-LOCAL: every General-DMA template
starts at E-001, so two clients both ship an `E-007`. The ingest records what
each of a client's local ids resolves to in `evidence_package_ids`, whose
primary key is (entity_id, package_local_id) — so the lookup below is
entity-scoped by construction. A bare id cited for Northern Trust resolves to
a Northern Trust row or to nothing; there is no query shape here that can
return another institution's.

That property used to rest on a token folded out of the institution's NAME
(`E-{ENT}-nnn`), and a name is not an identity. Measured in production on
2026-08-08: 166 entities, 113 tokens, 13 tokens owned by more than one
entity, `UNK` — the fallback when a package ships no manifest — owned by 14.
Northern Trust's twelve cited ids all resolved onto one other institution's
rows and returned `foreign`; Kitsap's 62 resolved onto several. Both
producers halted, correctly, and could not be produced at all.

`foreign` is the dangerous bucket and it keeps its meaning: a real row
belonging to another institution, reached by a GLOBALLY scoped id — the
server's own `E-CC-nnn` mint, or another entity's stored id. That is the
reasoning having drifted onto the wrong entity, and it must stop synthesis
rather than be filtered out quietly. A workbook-local number is not that: it
names an item in THIS client's own ledger and cannot denote another's, so
when it does not resolve the honest answer is `not_found`.

The legacy `E-{ENT}-nnn` candidates are still tried, ENTITY-SCOPED, for rows
ingested before the mapping existed and not yet re-landed.
"""
from __future__ import annotations

import re

# Mirrors persist.py's _entity_token — kept for the legacy candidate path.
_DMA_ASM = re.compile(r"^DMA-ASM-(?P<entity>[A-Z0-9]+)-(?P<date>\d{8})-(?P<seq>\d{2,4})$")
# Workbook-local, optionally cited at fact grain (E-047:F1 cites fact 1 OF
# item E-047; the item is the row). Mirrors dma_worker.evidence_ids.
_BARE_PACKAGE = re.compile(r"^E-\d+$")

_ROW_FIELDS = """{a}e_id, {a}entity_id, {a}source_name, {a}source_url,
                 {a}excerpt, enum_label({a}claim_type), enum_label({a}tier),
                 {a}published_date, enum_label({a}recency_band), {a}ers,
                 enum_label({a}origin)"""
_FIELDS = _ROW_FIELDS.format(a="")            # single-table selects
_FIELDS_E = _ROW_FIELDS.format(a="e.")        # joined against the mapping


def _run_scope(conn, run_id):
    cur = conn.cursor()
    cur.execute(
        """SELECT r.entity_id, r.request_id, r.run_seq, e.legal_name
             FROM runs r JOIN entities e ON e.id = r.entity_id
            WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    if row is None:
        return None
    entity_id, request_id, run_seq, legal_name = row
    m = _DMA_ASM.match(str(request_id or "").strip().upper())
    if m:
        token = m.group("entity")
    else:
        token = re.sub(r"[^A-Z0-9]", "", (legal_name or "").upper())[:8] or "UNK"
    return {"entity_id": entity_id, "token": token, "run_seq": run_seq}


def _local_id(cited: str) -> str | None:
    item = str(cited or "").split(":")[0].strip().upper()
    return item if _BARE_PACKAGE.match(item) else None


def _resolve(cur, cited: str, scope):
    """(row, scoped) for one cited id.

    `scoped` says the lookup was confined to this run's entity — which is
    true for every workbook-local id, and is what makes `foreign`
    unreachable for one. A globally scoped id is looked up globally and can
    therefore be found to belong to someone else.
    """
    local = _local_id(cited)
    if local is not None:
        cur.execute(
            f"""SELECT {_FIELDS_E} FROM evidence_index e
                  JOIN evidence_package_ids m ON m.e_id = e.e_id
                 WHERE m.entity_id = %s AND m.package_local_id = %s""",
            (scope["entity_id"], local))
        row = cur.fetchone()
        if row:
            return row, True
        # Rows ingested before the mapping existed: the historic qualified
        # shapes, tried against THIS entity only. An id that matches another
        # institution's row simply does not match here.
        qualified = f"E-{scope['token']}-{local[2:]}"
        for candidate in (f"{qualified}-R{scope['run_seq']}", qualified):
            cur.execute(
                f"""SELECT {_FIELDS} FROM evidence_index
                     WHERE e_id = %s AND entity_id = %s""",
                (candidate, scope["entity_id"]))
            row = cur.fetchone()
            if row:
                return row, True
        return None, True
    cur.execute(f"SELECT {_FIELDS} FROM evidence_index WHERE e_id = %s",
                (str(cited).split(":")[0],))
    return cur.fetchone(), False


def get_evidence(conn, run_id, e_ids) -> dict:
    """→ {found: [rows], not_found: [ids], foreign: [{e_id, belongs_to}]}"""
    scope = _run_scope(conn, run_id)
    if scope is None:
        return {"error": "unknown_run", "run_id": str(run_id)}
    cur = conn.cursor()
    found, not_found, foreign = [], [], []
    for cited in e_ids:
        row, _scoped = _resolve(cur, cited, scope)
        if row is None:
            not_found.append(cited)
            continue
        (stored_id, entity_id, source_name, source_url, excerpt, claim_type,
         tier, published_date, recency_band, ers, origin) = row
        if entity_id != scope["entity_id"]:
            foreign.append({"e_id": cited, "belongs_to": str(entity_id)})
            continue
        cur.execute(
            """SELECT array_agg(DISTINCT subcap_id), array_agg(DISTINCT run_id)
                 FROM evidence_subcap_links WHERE e_id = %s""", (stored_id,))
        subcaps, runs_seen = cur.fetchone()
        found.append({
            "e_id": cited,
            "stored_id": stored_id,
            "entity_id": str(entity_id),
            "source_name": source_name,
            "source_url": source_url,
            "excerpt": excerpt,
            "claim_type": claim_type,
            "tier": tier,
            "published_date": (published_date.isoformat()
                               if published_date else None),
            "recency_band": recency_band,
            "ers": float(ers) if ers is not None else None,
            "origin": origin,
            "linked_subcap_ids": sorted(subcaps or []),
            "seen_in_runs": sorted(str(r) for r in (runs_seen or [])),
        })
    return {"found": found, "not_found": not_found, "foreign": foreign}
