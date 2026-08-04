"""get_evidence (stage 2.3) — the three-way split.

Package Evidence_Master ids are workbook-local; the ingest step stores
them entity-qualified (E-047 → E-{ENT}-047, run-suffixed -R{n} after a
content change — see apps/worker/dma_worker/persist.py). The agent cites
the bare package form; resolution here (and in the validator, which uses
THIS function) qualifies within the run's entity scope, so two clients'
E-047 can never collide and a citation can never silently resolve onto
another institution.

foreign is the dangerous bucket: a real row belonging to another entity.
It must stop synthesis, never be filtered out quietly — its presence
means the reasoning has drifted onto the wrong entity.
"""
from __future__ import annotations

import re

# Mirrors persist.py's _entity_token — the qualification must agree on
# both sides of the boundary or no citation would ever resolve.
_DMA_ASM = re.compile(r"^DMA-ASM-(?P<entity>[A-Z0-9]+)-(?P<date>\d{8})-(?P<seq>\d{2,4})$")
_BARE_PACKAGE = re.compile(r"^E-\d+(?::F\d+)?$")   # workbook-local, optionally fact-level

_ROW_FIELDS = """e_id, entity_id, source_name, source_url, excerpt,
                 enum_label(claim_type), enum_label(tier), published_date,
                 enum_label(recency_band), ers, enum_label(origin)"""


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


def _candidates(e_id: str, scope) -> list:
    """Stored-id candidates for a cited id, most specific first."""
    cited = e_id.split(":")[0]        # E-047:F1 cites the item, fact-level suffix aside
    if _BARE_PACKAGE.match(cited):
        qualified = f"E-{scope['token']}-{cited[2:]}"
        return [f"{qualified}-R{scope['run_seq']}", qualified]
    return [cited]


def get_evidence(conn, run_id, e_ids) -> dict:
    """→ {found: [rows], not_found: [ids], foreign: [{e_id, belongs_to}]}"""
    scope = _run_scope(conn, run_id)
    if scope is None:
        return {"error": "unknown_run", "run_id": str(run_id)}
    cur = conn.cursor()
    found, not_found, foreign = [], [], []
    for cited in e_ids:
        row = None
        for candidate in _candidates(cited, scope):
            cur.execute(
                f"SELECT {_ROW_FIELDS} FROM evidence_index WHERE e_id = %s",
                (candidate,))
            row = cur.fetchone()
            if row:
                break
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
