"""The gate registry (stage 2.4/2.6) — every gate the validator can name.

Gate id prefixes are the four families of invariant 12 — AG analysis ·
SG safeguard · ET entity/identity · CG contract/grain — mapping onto
gate_family_t as the TRD's own explain_gate example shows (CG-07 →
family "corpus"): AG→analytical, SG→safeguard, ET→enrichment, CG→corpus.

A failing SG DISCLOSES and still promotes (on_failure=disclose, client-
visible, plain label 8-18 words); a failing evidence or contract reason
never does. A gate id absent from this registry cannot appear in a
verdict — the registry is seeded idempotently by the connector itself,
so definitions live next to the checks that emit them.
"""
from __future__ import annotations

_FAMILY = {"AG": "analytical", "SG": "safeguard", "ET": "enrichment", "CG": "corpus"}

# gate_id -> (name, plain_label|None, what_it_checks, why_it_exists, on_failure)
GATES = {
    "CG-01": ("Required section present", None,
              "Every required section of the page carries a payload object.",
              "A page missing a section renders a hole a client can see.",
              "block"),
    "CG-02": ("Required field present", None,
              "Every required field of a section is present and non-null; an "
              "explicit empty state passes where the contract allows one.",
              "A missing required field fails silently at render time.",
              "block"),
    "CG-03": ("Field type agreement", None,
              "Every field matches its contract type (list/object/scalar), "
              "list items included.",
              "A shape that type-checks wrongly promotes silently wrong content.",
              "block"),
    "CG-04": ("No invented fields", None,
              "No field outside the section contract, envelope included.",
              "Payload shapes are law; an invented field is a contract fork.",
              "block"),
    "CG-05": ("Envelope complete", None,
              "produced_at, producer_version, e_ids[], internal_only[] on "
              "every section.",
              "Unmarked internal paths reach the client; unstamped rows "
              "cannot be audited.",
              "block"),
    "CG-06": ("Absence carries its ladder", None,
              "empty_state names its reason and sources_searched.",
              "An absence with no recorded search is not a finding.",
              "block"),
    "CG-07": ("Quoted figure resolves to its cell", None,
              "Every quoted score resolves to the named served cell within "
              "0.05, label and figure read from one row, rounded once.",
              "A verdict naming both figures is repairable; a silent "
              "mismatch ships a wrong number.",
              "block"),
    "CG-08": ("Band word from the raw score", None,
              "Band words resolve from the RAW score at the four strict "
              "boundaries (<2, <3, <4, >=4); no fifth band exists.",
              "2.97 displays as 3.0 and still bands as Building.",
              "block"),
    "CG-09": ("Enum-column value", None,
              "A field promoted into an enum column carries one of that "
              "enum's values; a value the enum rejects type-checks as a "
              "string and then aborts the promote transaction.",
              "posture_basis is the EVIDENCE|HYBRID|INFERRED chip, not prose.",
              "block"),
    "ET-01": ("Cited ids resolve to this entity and run", None,
              "Every cited e_id resolves in the run's scope; a foreign id "
              "(another institution's row) halts production.",
              "A foreign id means the reasoning drifted onto another entity.",
              "block"),
    "ET-02": ("No minted-namespace fabrication", None,
              "Ids in the mint namespace must exist server-side; the agent "
              "never chooses the number.",
              "An invented evidence id is fabrication by construction.",
              "block"),
    "ET-03": ("Agent-created ids in their five classes", None,
              "ic/f/fa/ts/wn (+ authored rec) ids match their patterns; "
              "everything else is read or requested, never created.",
              "The mint namespace stayed invisible to five regexes once; "
              "one authority prevents the sixth.",
              "block"),
    "AG-01": ("Ranked or causal claims carry r_layer", None,
              "Any ranked/causal claim records hypothesis, counter, domain "
              "test, probes run and a verdict.",
              "A verdict not written down is a step that can be skipped.",
              "block"),
    "AG-02": ("Counts are computed", None,
              "Where a surface declares its grounding, the number equals "
              "the length of the citation list.",
              "A stored count drifts from its source of truth.",
              "block"),
    "SG-V4": ("Grounding against the run corpus",
              "Every claim is checked against this assessment's own "
              "evidence before it reaches you",
              "Prose similarity against the narrowest applicable centroid "
              "(cell .62 / category .58 / pillar .55 / run .50); abstains "
              "to a recorded NOT_RUN below five members or without an "
              "embedding tier.",
              "Text can pass every identifier check and still not be about "
              "the bundle.",
              "disclose"),
    "AG-03": ("Every claim-bearing item cites evidence", None,
              "Per ITEM, not per section: a why-now card, finding, "
              "recommendation, insight, timeline event, issue, tech row, "
              "alert, cap, gate result, phase or starter that asserts "
              "something carries a non-empty evidence list of its own, read "
              "from the keys its field's contract doc declares. A null-valued "
              "row and a recorded absence carrying its ladder assert nothing "
              "and are exempt; a state claiming a find with an empty id list "
              "is a contradiction, not an empty state.",
              "The envelope's citations are not enough — a reader drills into "
              "the item, and an inference cites the source it came from.",
              "block"),
    "AG-04": ("A named peer's technographics carry their source", None,
              "Where peer_coverage is stated, a per-peer breakdown exists "
              "with one row per peer including the peers that could not be "
              "established (deployed: null); every deployed row carries a "
              "source_url and an as_of; and the share agrees with its own "
              "breakdown to within one peer.",
              "A verdict beside a NAMED institution was derived from a hash "
              "of the row id. The claim cannot be manufactured, and a share "
              "with unknowns behind it is not that share.",
              "block"),
    "SG-S8": ("Sentiment rests on more than one line",
              "Sentiment rests on a single source, so treat it as "
              "indicative only",
              "The count of rating rows across all audiences, computed at "
              "submit and never read from a declared displayed_lines, is "
              "greater than one; a self-published NPS (T4/T5) standing alone "
              "is thin whatever the count.",
              "A single rating is not a sentiment picture, and thinness read "
              "as a finding is the most common misreading of this surface.",
              "disclose"),
}


def ensure_gate_registry(conn) -> int:
    cur = conn.cursor()
    for gate_id, (name, plain_label, what, why, on_failure) in GATES.items():
        family = _FAMILY[gate_id.split("-")[0]]
        cur.execute(
            """INSERT INTO gate_registry
                 (gate_id, family, name, plain_label, what_it_checks,
                  why_it_exists, threshold_kind, on_failure, is_client_visible)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (gate_id) DO UPDATE
                 SET name = EXCLUDED.name,
                     plain_label = EXCLUDED.plain_label,
                     what_it_checks = EXCLUDED.what_it_checks,
                     why_it_exists = EXCLUDED.why_it_exists,
                     on_failure = EXCLUDED.on_failure,
                     is_client_visible = EXCLUDED.is_client_visible""",
            (gate_id, family, name, plain_label, what, why,
             "boolean" if gate_id != "SG-V4" else "absolute",
             on_failure, gate_id.startswith("SG")))
    conn.commit()
    return len(GATES)


def explain_gate(conn, gate_id: str) -> dict:
    cur = conn.cursor()
    cur.execute("""SELECT gate_id, enum_label(family), name, plain_label,
                          what_it_checks, why_it_exists, on_failure,
                          is_client_visible
                     FROM gate_registry WHERE gate_id = %s""", (gate_id,))
    row = cur.fetchone()
    if row is None:
        return {"error": "unknown_gate", "gate_id": gate_id}
    out = dict(zip(("gate_id", "family", "name", "plain_label",
                    "what_it_checks", "why_it_exists", "on_failure",
                    "is_client_visible"), row))
    cur.execute("""SELECT changed_from, changed_to, reason, changed_at
                     FROM gate_threshold_history WHERE gate_id = %s
                    ORDER BY changed_at""", (gate_id,))
    out["threshold_history"] = [
        {"from": float(f) if f is not None else None,
         "to": float(t) if t is not None else None,
         "reason": r, "changed_at": at.isoformat() if at else None}
        for f, t, r, at in cur.fetchall()]
    return out
