"""Validation pass 2 (stage 2.4) — evidence, grain, bands, grounding.

Database work of a different shape from pass 1's format sweeps: every
cited id must resolve and belong to this entity and run (foreign HALTS);
every quoted figure must resolve to its named served cell within 0.05,
label and figure read from one row; band words resolve from the RAW
score at the four strict boundaries; ranked claims carry their r_layer;
declared grounding counts equal citation-list lengths; and V4 asks
whether the prose is about the bundle at all — abstaining to a RECORDED
NOT_RUN below five members or without an encoder, never failing closed
on a missing model. A failing SG discloses and still promotes; every
other reason here blocks.
"""
from __future__ import annotations

import json
import re

from .contracts import sections
from .evidence_tools import get_evidence
from .identifiers import MINT_RE

GRAIN_TOLERANCE = 0.05
V4_MIN_MEMBERS = 5
V4_MIN_PROSE = 40

# Every key under which a payload cites an evidence id. `e_ids` is the
# envelope's own key; the rest are item-level keys the section contracts
# declare. All of them are citations, so all of them resolve (invariant 4
# is fail-closed) and all of them satisfy AG-03 — before this list existed
# an id under `supporting_e_ids` was never checked against the store.
_EV_KEYS = ("e_ids", "supporting_e_ids", "evidence_ids", "new_evidence_ids",
            "source_e_id", "e_id")
# The item schema appears in the doc under several lead-ins ("Per item:",
# "Per card:", "Per recommendation:", or the inline "bars[] {…}" form).
# The negative lookbehind keeps a NESTED array's schema — "gaps[] per row:
# {…}" inside platform_story.platforms — from being read as the outer
# item's, which would demand a citation the outer item never carries.
_PER_ITEM_RE = re.compile(
    r"(?<!\[\] )\bPer [a-z ]*?(?:item|card|recommendation|starter|event|row|"
    r"point|signal|entry|person|gate|cap|tile|alert|pattern|phase|step)"
    r"[^:{]*:\s*\{([^}]*)\}", re.I)

# An item that asserts nothing needs no citation, and there are exactly
# two honest shapes for that: a null-valued row (the derived-or-null rule)
# and a recorded absence carrying the ladder that established it (the
# absence protocol). A state that asserts a FIND with no id is neither —
# it is a contradiction, and AG-03 blocks it.
_ABSENT_STATES = {"UNWORKED", "WORKED_ABSENT", "NOT_RUN", "verified_absent",
                  "verified_sparse", "cannot_estimate", "insufficient_cohort",
                  "empty_state", "quarantined"}

_BANDS = ("Activating", "Building", "Competing", "Differentiating")
_FORBIDDEN_BANDS = ("Transformational", "M5")

# Sections whose items are ranked or causal claims (the skill's page
# packs put an R-Layer CHALLENGE step on each of these).
_RANKED_SECTIONS = {
    ("overview", "findings"),
    ("insights", "insights"),
    ("heatmap", "focus_areas"),
    ("heatmap", "cohort_patterns"),
    ("platform", "recommendations"),
}

_SCORE_KEYS = ("score", "entity_score")
_ID_KEYS = ("subcap_id", "category_id", "pillar_id")
_SUBCAP_RE = re.compile(r"^P\d+C\d+\.")
_CATEGORY_RE = re.compile(r"^P\d+C\d+$")
_PILLAR_RE = re.compile(r"^P\d+$")


def _reason(gate, section, path, message):
    return {"gate_id": gate, "section": section, "path": path,
            "message": message, "severity": "block"}


def _declared_ev_keys(spec, field: str = None) -> tuple:
    """The evidence keys a field's own item schema declares. The doc text
    is the only place item keys are stated, so the requirement is read
    from the contract rather than hand-listed here: a field that gains an
    evidence key gains its enforcement in the same edit."""
    doc = spec.get("doc") or ""
    m = _PER_ITEM_RE.search(doc)
    if not m and field:
        # inline form, keyed by the field's own name: "bars[] {…, e_id}"
        m = re.search(re.escape(field) + r"\[\]\s*\{([^}]*)\}", doc)
    if not m:
        return ()
    keys = {k.strip().rstrip("[]") for k in m.group(1).split(",")}
    return tuple(k for k in _EV_KEYS if k in keys)


def _asserts_nothing(item: dict) -> bool:
    """True when the item makes no claim, so no citation is owed."""
    if item.get("quarantined"):
        return True
    for key in ("state", "status", "basis", "peer_basis"):
        state = item.get(key)
        if isinstance(state, str) and state in _ABSENT_STATES:
            # an absence is a finding only with the search that established it
            return bool(item.get("sources_searched") or item.get("queries_run"))
    return "value" in item and item.get("value") in (None, "")


def _check_item_evidence(page: str, payload: dict) -> list:
    """AG-03 — every claim carries an evidence id, inferences included.

    A card, signal, finding, ceiling or register row that asserts
    something about the institution and cites nothing is unfalsifiable:
    it renders to a client with no way back to a source. The section
    envelope's e_ids are not enough — a reader drills into the ITEM."""
    out = []
    for name, sec in sections(page).items():
        body = payload.get(name)
        if not isinstance(body, dict):
            continue
        for fname, spec in sec["fields"].items():
            ev_keys = _declared_ev_keys(spec, fname)
            if not ev_keys:
                continue
            items = body.get(fname)
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                if not isinstance(item, dict) or _asserts_nothing(item):
                    continue
                if any(item.get(k) for k in ev_keys):
                    continue
                shown = " or ".join(repr(k) for k in ev_keys)
                out.append(_reason(
                    "AG-03", name, f"{name}.{fname}[{i}].{ev_keys[0]}",
                    f"this item asserts a claim and cites no evidence — the "
                    f"{page}.{name}.{fname} item schema declares {shown}, and "
                    "every claim resolves to at least one registered evidence "
                    "id, inferences included. Register the source with "
                    "register_evidence and cite the id it returns, or state "
                    "the absence explicitly with its sources_searched ladder. "
                    "A state that asserts a find with an empty id list is a "
                    "contradiction, not an empty state"))
    return out


def _check_peer_research(page: str, payload: dict) -> list:
    """AG-04 — a technographic claim about a NAMED peer carries its source.

    `peer_coverage` renders as an adoption bar and a per-peer verdict beside a
    named institution. The version this replaces decided that verdict from
    `hashCode(ts_id + peerName) % 100`, so "✓ deployed" against a real credit
    union was a function of the characters in a row id. The figure cannot be
    manufactured and it cannot be asserted bare either: a share with no
    breakdown is unfalsifiable, and a breakdown whose rows carry no source is
    the same claim with more words.

    Three things are refused here:
      · a share with no per-peer breakdown
      · a `deployed: true` row with no source_url or no as_of
      · a share that disagrees with its own breakdown by more than one peer

    A peer the producer could NOT establish belongs in the list with
    `deployed: null`. That is what lets the card say "2 of 5, 3 not
    established" instead of implying it checked all five.
    """
    out = []
    for name, sec in sections(page).items():
        body = payload.get(name)
        if not isinstance(body, dict):
            continue
        for fname in sec["fields"]:
            items = body.get(fname)
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                cov = item.get("peer_coverage")
                rows = item.get("peer_deployments")
                base = f"{name}.{fname}[{i}]"
                if cov is None and not rows:
                    continue
                if cov is not None and not isinstance(rows, list):
                    out.append(_reason(
                        "AG-04", name, f"{base}.peer_deployments",
                        f"peer_coverage is {cov!r} with no per-peer breakdown. The "
                        "card renders a verdict beside a NAMED institution, so the "
                        "share needs one row per peer — including the peers you "
                        "could not establish, with deployed: null. A coverage "
                        "figure with unknowns behind it is not that figure"))
                    continue
                for j, r in enumerate(rows or []):
                    if not isinstance(r, dict):
                        continue
                    if r.get("deployed") is not True:
                        continue
                    missing = [k for k in ("source_url", "as_of") if not r.get(k)]
                    if missing:
                        out.append(_reason(
                            "AG-04", name, f"{base}.peer_deployments[{j}]",
                            f"claims {r.get('peer')!r} runs this product and states "
                            f"no {' and no '.join(missing)}. A technographic claim "
                            "about a named institution is a research finding; "
                            "without a source and a date it is an assertion about "
                            "someone else's estate on a client's dashboard"))
                if cov is not None and isinstance(rows, list) and rows:
                    yes = sum(1 for r in rows
                              if isinstance(r, dict) and r.get("deployed") is True)
                    implied = yes / len(rows)
                    # One peer of tolerance: the producer may legitimately scope
                    # the share to the established subset. More than that is an
                    # arithmetic disagreement between a figure and its own basis.
                    if abs(float(cov) - implied) > (1.0 / len(rows)) + 1e-9:
                        out.append(_reason(
                            "AG-04", name, f"{base}.peer_coverage",
                            f"peer_coverage {cov} disagrees with its own breakdown: "
                            f"{yes} of {len(rows)} rows say deployed, which is "
                            f"{implied:.3f}. State the share the breakdown supports, "
                            "or add the rows the share is counting"))
    return out


def band_for(raw) -> str | None:
    if raw is None:
        return None
    s = float(raw)
    if s < 2:
        return "Activating"
    if s < 3:
        return "Building"
    if s < 4:
        return "Competing"
    return "Differentiating"


def _served_figures(conn, run_id) -> dict:
    """Every figure the run serves, by grain id: subcaps from
    subcap_scores, pillar/category from the workbook's STATED grains."""
    cur = conn.cursor()
    served = {}
    cur.execute("SELECT subcap_id, score FROM subcap_scores WHERE run_id = %s",
                (run_id,))
    for sid, score in cur.fetchall():
        if score is not None:
            served[sid] = float(score)
    cur.execute("SELECT payload FROM run_manifest WHERE run_id = %s", (run_id,))
    payload = (cur.fetchone() or [None])[0] or {}
    grains = payload.get("workbook_grains") or {}
    for p in grains.get("pillars") or []:
        if p.get("score") is not None:
            served[p["pillar_id"]] = float(p["score"])
    for c in grains.get("categories") or []:
        if c.get("score") is not None:
            served[c["category_id"]] = float(c["score"])
    return served


def _walk(node, path):
    """Yield (path, dict) for every object in the payload tree."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")


# Producer metadata: fields ABOUT the production (method notes, search
# records, gate labels, provenance), not claims about the entity. Checking
# them against bundle centroids fails forever and drowns the client-visible
# gate card in noise — the first prod submission flagged filenames and
# R-layer notes as ungrounded claims.
_V4_SKIP_KEYS = frozenset((
    "produced_at", "producer_version", "source_cell", "r_layer",
    "grain_note", "currency_note", "reach_note", "provenance",
    "source_filename", "source_document", "closure_condition",
    "quarantine_reason", "not_run_reason", "queries_run",
    "sources_searched", "plain_label", "justification", "empty_state",
    "note", "rationale",
))


def _iter_prose(node, path):
    """Yield (path, text) for prose-bearing string fields — entity claims,
    not producer metadata, and never URLs."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _V4_SKIP_KEYS:
                continue
            yield from _iter_prose(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_prose(item, f"{path}[{i}]")
    elif isinstance(node, str):
        if node.startswith(("http://", "https://")):
            return
        text = re.sub(r"\s+", " ", re.sub(r"[#*_`\[\]]", "", node)).strip()
        if len(text) >= V4_MIN_PROSE:
            yield path, text


def _scope_for(obj: dict):
    """The narrowest scope an object's grain ids license."""
    sid = obj.get("subcap_id")
    if isinstance(sid, str) and _SUBCAP_RE.match(sid):
        return ("cell", sid)
    cid = obj.get("category_id")
    if isinstance(cid, str) and _CATEGORY_RE.match(cid):
        return ("category", cid)
    pid = obj.get("pillar_id")
    if isinstance(pid, str) and _PILLAR_RE.match(pid):
        return ("pillar", pid)
    return ("run", None)


def validate_pass2(conn, run_id, page: str, payload: dict,
                   encoder=None) -> tuple:
    """→ (blocking_reasons, sg_disclosures). SG results are also recorded
    in gate_results — a gate that reports pass because it did not run is
    worse than one that reports fail."""
    reasons = []
    if not isinstance(payload, dict):
        return reasons, []

    # ── ET: every cited id resolves to this entity and run — collected
    # from EVERY object in the tree, not just the section envelope (a
    # fabricated id inside an item is still a fabricated id) ────────────
    cited = {}
    for name, body in payload.items():
        if isinstance(body, dict):
            for _path, obj in _walk(body, name):
                for key in _EV_KEYS:
                    val = obj.get(key)
                    # every citation key, not just the envelope's e_ids:
                    # a fabricated id under supporting_e_ids is still one
                    for e in ([val] if isinstance(val, str) else (val or [])):
                        if isinstance(e, str):
                            cited.setdefault(e, name)
    if cited:
        split = get_evidence(conn, run_id, sorted(cited))
        for e in split.get("not_found", []):
            gate = "ET-02" if MINT_RE.match(e.split(":")[0]) else "ET-01"
            reasons.append(_reason(
                gate, cited[e], f"{cited[e]}.e_ids",
                f"{e} does not resolve — "
                + ("the mint namespace is server-allocated; an invented "
                   "mint id is fabrication by construction"
                   if gate == "ET-02" else
                   "fabricated or not yet registered; call get_evidence to "
                   "confirm, or register the source first")))
        for f in split.get("foreign", []):
            reasons.append(_reason(
                "ET-01", cited[f["e_id"]], f"{cited[f['e_id']]}.e_ids",
                f"{f['e_id']} is a real row belonging to another "
                f"institution ({f['belongs_to']}) — STOP: this is "
                "contamination; quarantine and escalate, do not filter it "
                "out quietly"))

    served = _served_figures(conn, run_id)

    for name, body in payload.items():
        if not isinstance(body, dict):
            continue

        # ── CG-07 grain lock + CG-08 band words ────────────────────────
        for path, obj in _walk(body, name):
            grain_id = next((obj[k] for k in _ID_KEYS
                             if isinstance(obj.get(k), str)), None)
            if grain_id:
                quoted_any = None
                for sk in _SCORE_KEYS:
                    quoted = obj.get(sk)
                    if isinstance(quoted, (int, float)) and not isinstance(quoted, bool):
                        quoted_any = quoted
                        if grain_id in served and \
                                abs(float(quoted) - served[grain_id]) > GRAIN_TOLERANCE:
                            reasons.append(_reason(
                                "CG-07", name, f"{path}.{sk}",
                                f"quoted {quoted} resolves to {grain_id} = "
                                f"{served[grain_id]} "
                                f"(Δ {abs(float(quoted) - served[grain_id]):.2f} "
                                f"> {GRAIN_TOLERANCE}) — the label and the "
                                "figure came from different rows; fix the "
                                "pairing, not the prose"))
                if quoted_any is not None and grain_id not in served:
                    # a figure whose named grain this run does not serve
                    # cannot be checked against anything — that IS the failure
                    reasons.append(_reason(
                        "CG-07", name, f"{path}",
                        f"quoted {quoted_any} names {grain_id}, which this "
                        "run serves no figure for — a figure that resolves "
                        "to no served cell cannot be checked and is rejected"))
            for bk, bv in obj.items():
                if not isinstance(bv, str):
                    continue
                if bv in _FORBIDDEN_BANDS or re.search(r"\bM5\b|\bTransformational\b", bv):
                    # the fifth band must not exist in prose either
                    # (invariant 6) — not as a field value, not mid-sentence
                    reasons.append(_reason(
                        "CG-08", name, f"{path}.{bk}",
                        f"{bv[:80]!r} carries the fifth band — it does not "
                        "render; the resolver has four branches and "
                        "anything at or above 4.0 is Differentiating"))
                elif bv in _BANDS and "band" in bk.lower():
                    raw = next((obj[k] for k in _SCORE_KEYS
                                if isinstance(obj.get(k), (int, float))
                                and not isinstance(obj.get(k), bool)), None)
                    if raw is None and grain_id and grain_id in served:
                        raw = served[grain_id]   # the served figure IS the raw score
                    if raw is not None and band_for(raw) != bv:
                        reasons.append(_reason(
                            "CG-08", name, f"{path}.{bk}",
                            f"band {bv!r} does not resolve from the raw "
                            f"score {raw} (strict less-than boundaries give "
                            f"{band_for(raw)!r}); resolve from the raw "
                            "value, not the rounded one"))

            # ── AG-02: declared grounding is computed ──────────────────
            if "grounded_on" in obj and isinstance(obj.get("e_ids"), list):
                if obj["grounded_on"] != len(obj["e_ids"]):
                    reasons.append(_reason(
                        "AG-02", name, f"{path}.grounded_on",
                        f"grounded_on={obj['grounded_on']} but the citation "
                        f"list has {len(obj['e_ids'])} ids — the number IS "
                        "the length of the citation array, never asserted"))

        # ── AG-01: ranked claims carry r_layer with a verdict — EVERY
        # list-of-object field of a ranked section, not just the first ──
        if (page, name) in _RANKED_SECTIONS:
            for fname, val in body.items():
                if isinstance(val, list) and val and all(isinstance(x, dict) for x in val):
                    for i, item in enumerate(val):
                        rl = item.get("r_layer")
                        if not isinstance(rl, dict) or not rl.get("verdict"):
                            reasons.append(_reason(
                                "AG-01", name, f"{name}.{fname}[{i}].r_layer",
                                "ranked or causal claim without a recorded "
                                "r_layer verdict — a verdict you did not "
                                "write down is a step you can convince "
                                "yourself you took"))

    # ── AG-03: every claim-bearing item cites evidence ─────────────────
    reasons.extend(_check_item_evidence(page, payload))
    reasons.extend(_check_peer_research(page, payload))

    sg = _run_s8(conn, run_id, page, payload)
    sg.extend(_run_v4(conn, run_id, page, payload, encoder))
    return reasons, sg


def _run_s8(conn, run_id, page, payload) -> list:
    """SG-S8 — sentiment resting on one line discloses and still promotes.

    A single rating is not a sentiment picture, and the common misreading is the
    other way round: a thin surface read as a finding about the institution. So
    this is a safeguard, not a block — it renders to the client with its
    `plain_label`, saying the reading is indicative.

    The count is computed here from the rating rows, never read from a declared
    `displayed_lines`: a producer that states its own line count is the one
    thing this gate cannot trust. O9's `bars` and C4's `context_tiles[].rows`
    are the same dataset at two depths, so whichever page is being submitted,
    the rows are counted the same way.
    """
    sec = {"overview": "sentiment", "context": "context_sentiment"}.get(page)
    if not sec:
        return []
    body = payload.get(sec)
    if not isinstance(body, dict):
        return []
    rows = []
    for bar in body.get("bars") or []:
        if isinstance(bar, dict):
            rows.append(bar)
    for tile in body.get("context_tiles") or []:
        if isinstance(tile, dict):
            rows.extend(r for r in (tile.get("rows") or []) if isinstance(r, dict))
    # A row with no rating is not a line of sentiment; it is a source that was
    # searched. Those belong in the ladder, not in the count.
    rated = [r for r in rows if r.get("rating") is not None]
    audiences = sorted({str(r.get("audience") or "").lower() for r in rated} - {""})
    # A self-published figure standing alone is thin whatever the count: it is
    # one voice about itself.
    self_published = all(
        str(r.get("source") or "").lower().find("nps") >= 0 for r in rated) if rated else False

    if not rated:
        result, detail = "NOT_RUN", {"page": page, "reason": "no rated rows"}
    elif len(rated) > 1 and not self_published:
        result, detail = "PASS", {"page": page, "rated_rows": len(rated),
                                  "audiences": audiences}
    else:
        result, detail = "FAIL", {
            "page": page, "rated_rows": len(rated), "audiences": audiences,
            "self_published_only": self_published,
            "note": ("sentiment rests on a single line"
                     if len(rated) <= 1
                     else "every rated row is a self-published figure")}

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO gate_results
             (run_id, gate_id, result, not_run_reason, detail, evaluated_at)
           VALUES (%s,'SG-S8',%s,%s,%s, now())""",
        (run_id, result, detail.get("reason"), json.dumps(detail)))
    conn.commit()
    out = {"gate_id": "SG-S8", "result": result, "page": page, "detail": detail}
    if result == "NOT_RUN":
        out["not_run_reason"] = detail.get("reason")
    return [out]


def _run_v4(conn, run_id, page, payload, encoder) -> list:
    """The grounding check. Each prose field is embedded and compared to
    the narrowest applicable centroid; failure DISCLOSES with attribution
    (the three nearest chunks), abstention is recorded, and nothing here
    blocks a promotion."""
    cur = conn.cursor()
    disclosures = []

    def record(result, detail, reason=None):
        cur.execute(
            """INSERT INTO gate_results
                 (run_id, gate_id, result, not_run_reason, detail, evaluated_at)
               VALUES (%s,'SG-V4',%s,%s,%s, now())""",
            (run_id, result, reason, json.dumps(detail)))

    if encoder is None:
        record("NOT_RUN", {"page": page},
               "embedding tier unavailable — V4 is an extra guard, never a "
               "fail-closed on a missing model")
        conn.commit()
        return [{"gate_id": "SG-V4", "result": "NOT_RUN", "page": page,
                 "not_run_reason": "embedding tier unavailable"}]

    cur.execute("""SELECT scope_kind, COALESCE(scope_id,''), centroid::text,
                          member_n, threshold
                     FROM bundle_centroids WHERE run_id = %s""", (run_id,))
    centroids = {(r[0], r[1]): {"centroid": r[2], "member_n": r[3],
                                "threshold": r[4]} for r in cur.fetchall()}
    if not centroids:
        record("NOT_RUN", {"page": page},
               "no centroids for this run — bundle not embedded")
        conn.commit()
        return [{"gate_id": "SG-V4", "result": "NOT_RUN", "page": page,
                 "not_run_reason": "no centroids for this run"}]

    fields = []          # (path, text, scope_kind, scope_id)
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in _walk(body, name):
            kind, sid = _scope_for(obj)
            for k, v in obj.items():
                if isinstance(v, str):
                    for p, text in _iter_prose(v, f"{path}.{k}"):
                        fields.append((p, text, kind, sid))

    checked = failed = abstained = 0
    for path, text, kind, sid in fields:
        key, scope_id = (kind, sid or ""), sid
        c = centroids.get(key)
        while c is None and kind != "run":
            kind = {"cell": "category", "category": "pillar",
                    "pillar": "run"}[kind]
            scope_id = (scope_id.split(".")[0] if kind == "category" else
                        scope_id.split("C")[0] if kind == "pillar" else "")
            c = centroids.get((kind, scope_id or ""))
        if c is None or c["member_n"] < V4_MIN_MEMBERS:
            abstained += 1
            continue
        vec = encoder.encode([text])[0]
        lit = "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
        cur.execute("SELECT 1 - (%s::vector <=> %s::vector)", (lit, c["centroid"]))
        sim = float(cur.fetchone()[0])
        checked += 1
        if sim < c["threshold"]:
            cur.execute(
                """SELECT source_kind, source_ref, left(content, 240),
                          1 - (embedding <=> %s::vector)
                     FROM bundle_embeddings
                    WHERE run_id = %s AND scope_kind = %s
                      AND (scope_id = %s OR %s::text IS NULL)
                    ORDER BY embedding <=> %s::vector LIMIT 3""",
                (lit, run_id, kind, scope_id or None, scope_id or None, lit))
            nearest = [{"source_kind": a, "source_ref": b, "snippet": c2,
                        "similarity": round(float(d), 3)}
                       for a, b, c2, d in cur.fetchall()]
            failed += 1
            disclosures.append({
                "gate_id": "SG-V4", "result": "FAIL", "path": path,
                "similarity": round(sim, 3), "threshold": c["threshold"],
                "scope": {"kind": kind, "id": scope_id or None},
                "nearest": nearest,
                "message": f"V4 similarity {sim:.2f} against a threshold of "
                           f"{c['threshold']} — the nearest chunks say what "
                           "the claim drifted toward; find grounding or "
                           "drop the claim"})

    detail = {"page": page, "fields_checked": checked, "failed": failed,
              "abstained_fields": abstained}
    if abstained and not checked:
        record("NOT_RUN", detail, "every applicable centroid was below "
                                  f"{V4_MIN_MEMBERS} members")
        disclosures.append({"gate_id": "SG-V4", "result": "NOT_RUN",
                            "page": page,
                            "not_run_reason": "centroids below the member "
                                              "floor"})
    else:
        record("FAIL" if failed else "PASS", detail)
    conn.commit()
    return disclosures
