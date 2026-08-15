"""register_evidence (stage 2.3b/2.5) — mint before you cite.

The server allocates the id and computes the rank score; sending either
is ignored. Idempotent by content: the dedup key is the hash of URL,
claim type and the normalised leading excerpt, scoped to the entity —
registering the same source from six surfaces returns the same id six
times, each call accumulating that surface's cell links.

Fail-closed rules enforced here:
- excerpt is a verbatim 50-500 char span, verified against the FETCHED
  artefact at registration (rejected here, not at promotion);
- an item with no traceable source URL is accepted as INFERENCE, never
  FACT (the coercion is reported, never silent);
- ERS = 0.35·Tier + 0.25·Recency + 0.20·Specificity + 0.20·Corroboration,
  every factor 1.0-5.0 (PRD "The evidence rank score"), bounded by CHECK;
- identity_ok is asserted only when a domain check actually ran —
  computed or null, never a default that looks like a pass.
"""
from __future__ import annotations

import re
from datetime import date

from . import source_rules

_MINT_LOCK = 815001          # advisory lock key for the E-CC mint counter

_HASH_SQL = r"""encode(digest(coalesce(%s,'') || '|' || coalesce(%s,'') || '|' ||
                lower(left(regexp_replace(%s,'\s+',' ','g'),500)),
         'sha256'),'hex')"""

_TIER_FACTOR = {"T1": 5.0, "T2": 4.0, "T3": 3.0, "T4": 2.0, "T5": 1.0}
_RECENCY_FACTOR = {"CURRENT": 5.0, "RECENT": 4.0, "DATED": 3.0,
                   "STALE": 2.0, "ARCHIVAL": 1.0, "UNVERIFIED": 1.0}
_CLAIMS = ("FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE")
_TIERS = ("T1", "T2", "T3", "T4", "T5")


def _recency_band(published: date | None, reference: date | None) -> str:
    if not published or not reference:
        return "UNVERIFIED"
    months = (reference.year - published.year) * 12 + (reference.month - published.month)
    if months <= 12:
        return "CURRENT"
    if months <= 24:
        return "RECENT"
    if months <= 36:
        return "DATED"
    if months <= 48:
        return "STALE"
    return "ARCHIVAL"


def _specificity(excerpt: str, facts: list) -> int:
    """Deterministic reading of the PRD ladder (quantified with method /
    quantified / specific-qualitative / general / vague). Digits mark a
    quantified claim; structured facts stand in for a stated method."""
    has_number = bool(re.search(r"\d", excerpt))
    if has_number and facts:
        return 5
    if has_number:
        return 4
    return 3 if len(excerpt) >= 80 else 2


def _corroboration(cur, entity_id, subcap_ids, source_domain, tier) -> int:
    """Distinct ORIGINS supporting the same cells. Two documents from one
    domain are one source. Single-source falls back to the tier rungs."""
    independents = 1
    if subcap_ids:
        cur.execute(
            """SELECT count(DISTINCT e.source_domain)
                 FROM evidence_index e
                 JOIN evidence_subcap_links l ON l.e_id = e.e_id
                WHERE e.entity_id = %s AND l.subcap_id = ANY(%s)
                  AND e.source_domain IS NOT NULL
                  AND e.source_domain IS DISTINCT FROM %s""",
            (entity_id, list(subcap_ids), source_domain))
        independents += cur.fetchone()[0]
    if independents >= 3:
        return 5
    if independents == 2:
        return 4
    return {"T1": 3, "T2": 3, "T3": 2}.get(tier, 1)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def date_merge(stored: date | None, incoming: date | None) -> str:
    """What a later registration may do to an already-stored date.

    Three cases and they are not the same, which is the whole point:

      fill          stored is unknown, incoming states one. Strictly
                    additive — unknown becoming known — so take it.
      keep          they agree, or the incoming one says nothing.
      contradiction they disagree. The stored date STANDS and the conflict
                    is reported. Two sources disagreeing about when a
                    document was published is a finding; letting the later
                    write win resolves it silently in favour of whichever
                    call happened to be second, which is not a resolution.

    A separate function because every test of this behaviour otherwise needs
    a live database, and `apps/mcp/tests` skips 53 tests for want of one —
    a test that always skips is a test that never runs.
    """
    if incoming is None:
        return "keep"
    if stored is None:
        return "fill"
    return "keep" if stored == incoming else "contradiction"


def register_evidence(conn, run_id, item: dict, fetch=None,
                      known_entity_domains=None) -> dict:
    """fetch(url) -> str|None is injectable (tests; and the worker image
    may route through a proxy). known_entity_domains enables the domain
    identity check; absent, identity_ok stays NULL — unknown, not ok."""
    cur = conn.cursor()
    cur.execute("""SELECT r.entity_id, r.completed_at
                     FROM runs r WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    if row is None:
        return {"e_id": None, "deduped": False, "ers": None,
                "errors": ["unknown_run"]}
    entity_id, completed_at = row
    reference_date = completed_at if isinstance(completed_at, date) else None

    errors, adjustments = [], []
    excerpt = str(item.get("excerpt") or "")
    source_url = item.get("source_url") or None
    claim = str(item.get("claim_type") or "").upper() or None
    tier = str(item.get("tier") or "").upper() or None

    if not (50 <= len(excerpt) <= 500):
        errors.append(f"excerpt_length: {len(excerpt)} chars — a verbatim "
                      "span of 50-500 is required")
    if claim not in _CLAIMS:
        errors.append(f"claim_type: {claim!r} not in {_CLAIMS}")
    if tier not in _TIERS:
        errors.append(f"tier: {tier!r} not in {_TIERS}")
    # W6 — what a source may be used to ESTABLISH, checked where the source
    # is named rather than left to the producer's typing. Both refusals are
    # about the source's own nature, so they belong beside the tier and
    # claim vocabulary checks and before anything is fetched or minted.
    tier_bad = source_rules.tier_violation(source_url, tier)
    if tier_bad:
        errors.append(tier_bad)
    absence_bad = source_rules.absence_as_capability(excerpt, claim)
    if absence_bad:
        errors.append(absence_bad)
    if errors:
        return {"e_id": None, "deduped": False, "ers": None, "errors": errors}

    if not source_url and claim == "FACT":
        claim = "INFERENCE"
        adjustments.append("no traceable source URL: claim_type FACT "
                           "downgraded to INFERENCE")

    # Verbatim verification against the fetched artefact — fail closed.
    if source_url:
        if fetch is None:
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": ["excerpt_unverifiable: no fetcher available; "
                               "an unverified excerpt is not evidence"]}
        fetched = fetch(source_url)
        if fetched is None:
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": [f"url_unreachable: {source_url}"]}
        if _normalise(excerpt) not in _normalise(fetched):
            return {"e_id": None, "deduped": False, "ers": None,
                    "errors": ["excerpt_not_verbatim: the span is not in the "
                               "fetched artefact — re-extract from the "
                               "source; never repair by hand"]}

    # Domain identity — asserted only when a check actually ran.
    domain = None
    if source_url:
        m = re.match(r"^[A-Za-z]+://(?:www\.)?([^/:?#]+)", source_url)
        domain = m.group(1).lower() if m else None
    # identity_ok=True only for the entity's OWN domains; a third-party
    # domain stays NULL here (not yet resolved against the registry the
    # identity gate holds — validation pass 2). Never asserted by default.
    identity_ok, identity_note = None, None
    if domain and known_entity_domains and domain in {d.lower() for d in known_entity_domains}:
        identity_ok = True
        identity_note = "entity's own domain"
    # A document about a RELATED entity is noted, never refused: a filing
    # saying A is wholly owned by B is the right evidence for ownership and
    # the wrong evidence for B's operational capability. The note is what
    # lets a reader see which one this is (W6).
    relation = source_rules.relation_note(excerpt)
    if relation:
        identity_note = f"{identity_note}; {relation}" if identity_note else relation
        adjustments.append(relation)
    subcaps = [s for s in (item.get("linked_subcap_ids") or []) if s]

    published = item.get("published_date")
    if isinstance(published, str):
        try:
            published = date.fromisoformat(published[:10])
        except ValueError:
            published = None
            adjustments.append("published_date unparseable: stored as "
                               "undated (UNVERIFIED, never current)")

    band = _recency_band(published, reference_date)
    spec = _specificity(excerpt, item.get("facts") or [])
    corr = _corroboration(cur, entity_id, subcaps, domain, tier)
    ers = round(0.35 * _TIER_FACTOR[tier] + 0.25 * _RECENCY_FACTOR[band]
                + 0.20 * spec + 0.20 * corr, 2)

    # Mint under an advisory lock so concurrent sessions never race the
    # counter (svc_mcp runs on session-mode pooling).
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (_MINT_LOCK,))
    cur.execute("""SELECT COALESCE(MAX(substring(e_id FROM 'E-CC-(\\d+)')::int), 0) + 1
                     FROM evidence_index WHERE e_id LIKE 'E-CC-%%'""")
    e_id = f"E-CC-{cur.fetchone()[0]:03d}"

    cur.execute(
        f"""INSERT INTO evidence_index
              (e_id, entity_id, origin, source_name, source_url, excerpt,
               claim_type, tier, published_date, reference_date,
               specificity, corroboration, identity_ok, identity_note, ers)
            VALUES (%s,%s,'producer',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING RETURNING e_id""",
        (e_id, entity_id, item.get("source_name"), source_url, excerpt,
         claim, tier, published, reference_date, spec, corr,
         identity_ok, identity_note, ers))
    minted = cur.fetchone()
    if minted:
        kept_id, deduped, ers_out = e_id, False, ers
    else:
        # the entity-scoped content hash fired: same URL+claim+span
        cur.execute(
            f"""SELECT e_id FROM evidence_index
                 WHERE entity_id = %s AND content_hash = {_HASH_SQL}""",
            (entity_id, source_url, claim, excerpt))
        kept_id = cur.fetchone()[0]
        deduped, ers_out = True, None
        cur.execute(
            f"""INSERT INTO evidence_dedup_audit
                  (e_id, content_hash, branch, matched_e_id, occurred_at)
                VALUES (NULL, {_HASH_SQL}, 'dedup_same_entity', %s, now())""",
            (source_url, claim, excerpt, kept_id))

        # A DATE THE FIRST REGISTRATION LACKED, arriving on a later one.
        #
        # Measured 2026-08-15 on the second client. A producer registered
        # three spans from a Client Agreement before it had established the
        # document's date, then re-registered them with published_date set.
        # Dedup fired, `linked_subcap_ids` MERGED — a new cell was genuinely
        # added to E-CC-178 — and `published_date` stayed null. The merge was
        # partial, on one field and not the other, which is the defect: an
        # item first registered undated could never afterwards be dated, so
        # it sat at UNVERIFIED forever and its ERS stayed suppressed (3.40
        # undated against 4.15 dated, on comparable spans from one document).
        #
        # Filling it is strictly additive — unknown becoming known. What is
        # NOT done here is overwriting a date the row already carries with a
        # different one: two sources disagreeing about when a document was
        # published is a contradiction, and the rule for a contradiction is
        # to state it, never to resolve it silently by taking the newer
        # write. So the three cases are separated and the third is reported.
        if published:
            cur.execute("SELECT published_date FROM evidence_index "
                        "WHERE e_id = %s", (kept_id,))
            stored = cur.fetchone()[0]
            verdict = date_merge(stored, published)
            if verdict == "fill":
                # Recompute ERS: recency is 25% of it, and a row left at
                # UNVERIFIED scores as though nobody had ever dated it.
                new_band = _recency_band(published, reference_date)
                cur.execute(
                    """UPDATE evidence_index
                          SET published_date = %s,
                              ers = round((0.35 * %s + 0.25 * %s
                                         + 0.20 * specificity
                                         + 0.20 * corroboration)::numeric, 2)
                        WHERE e_id = %s
                    RETURNING ers""",
                    (published, _TIER_FACTOR[tier], _RECENCY_FACTOR[new_band],
                     kept_id))
                ers_out = float(cur.fetchone()[0])
                adjustments.append(
                    f"{kept_id} was registered undated and is now dated "
                    f"{published.isoformat()}: recency {new_band}, ERS "
                    f"recomputed to {ers_out}")
            elif verdict == "contradiction":
                adjustments.append(
                    f"CONTRADICTION not resolved: {kept_id} is stored as "
                    f"published {stored.isoformat()} and this registration "
                    f"says {published.isoformat()}. The stored date stands. "
                    "One of the two readings is wrong and which one is a "
                    "finding — establish it from the document rather than "
                    "letting the later write win.")

    # The per-DOCUMENT sole-evidence cap (W6). Checked here, after the mint,
    # because the refusal is about the LINKS and not the registration: the
    # id is minted and its excerpt stored either way, so a producer never
    # loses a verified span to this rule — it loses the further cells the
    # document would have become the only voice for. A per-evidence-id cap
    # was refuted in the adversarial pass by splitting one filing into eight
    # ids sharing one URL, so the key is the canonicalised document.
    reach_bad = source_rules.sole_evidence_reach(cur, run_id, kept_id,
                                                source_url, subcaps)
    if reach_bad:
        conn.commit()                     # keep the mint; refuse the links
        return {"e_id": kept_id, "deduped": deduped, "ers": ers_out,
                "errors": [reach_bad],
                "links_written": 0,
                "adjustments": adjustments or []}
    for sid in subcaps:
        cur.execute(
            """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
               VALUES (%s,%s,%s,'registered') ON CONFLICT DO NOTHING""",
            (kept_id, sid, run_id))
    conn.commit()
    out = {"e_id": kept_id, "deduped": deduped, "ers": ers_out, "errors": []}
    if adjustments:
        out["adjustments"] = adjustments
    return out
