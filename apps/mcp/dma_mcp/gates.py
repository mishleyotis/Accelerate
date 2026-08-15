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
    "CG-21": ("A leaf is a value, not a serialisation of one", None,
              "No payload leaf is a string that parses as a JSON object or "
              "array. Send the value; the encoding is never the value.",
              "A run promoted with `blocking_findings` holding "
              "'{\"f_id\": \"F-1\", ...}' as STRINGS where the contract asks "
              "for ids, and the ladder rendered literal JSON to the AE. CG-03 "
              "is structurally unable to catch it — it asks whether the items "
              "are strings, and a serialised object is a perfectly valid "
              "string.",
              "block"),
    "CG-20": ("A vendor is a company, not a category", None,
              "Every technology-register row names the COMPANY that supplies "
              "it: not a category ('Integration platform'), not a "
              "placeholder ('unnamed'), and not the same string as its own "
              "product.",
              "The contract always said vendor and product are separate and a "
              "category is neither, and nothing checked it — so placeholder "
              "rows promoted onto a client's register with the same weight as "
              "a confirmed deployment.",
              "block"),
    "CG-19": ("A required list is not silently empty", None,
              "A required list field carries items, or the section declares "
              "an empty state, or the contract marks the field "
              "`may_be_empty`. An empty list is a claim and is made "
              "deliberately.",
              "`required: true` was satisfied by []: not None, type-checks as "
              "a list, writes zero rows at promotion, and the surface then "
              "vanishes from the served page with nothing saying why. Every "
              "gate green.",
              "block"),
    "CG-18": ("Must-present members are stated or held", None,
              "A list field declaring `must_present` carries every named "
              "member — each either stated with provenance, or explicitly "
              "quarantined with a reason. Absent, or blank with no reason, "
              "is refused.",
              "`required: true` covers the CONTAINER; until 2026-08-14 every "
              "must-present set lived only as prose in a contract doc string, "
              "so a list with one member passed every gate and which members "
              "it carried was documentation rather than contract.",
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
    "CG-10": ("A date that could not be established says so", None,
              "An item's own dating field (the timeline's event_date, the "
              "register's opened_on, a signal's dated_on, a firmographic "
              "as_of) is either a date or an explicit absence rung — "
              "UNVERIFIED / WORKED_ABSENT / undated on a recency or basis "
              "key, a quarantine with its reason, or the sources_searched "
              "ladder. A cited evidence row with no published_date carries "
              "recency_band UNVERIFIED, never a computed freshness.",
              "A bare null renders as an empty slot beside a populated one, "
              "and the surface cannot tell 'nobody looked' from 'looked and "
              "found nothing'. Undated is UNVERIFIED, never current.",
              "block"),
    "CG-11": ("Prose begins as a sentence", None,
              "A prose field on a client surface — a prose-keyed field, or "
              "any string that ends in terminal punctuation — begins with a "
              "capital. A first word carrying an uppercase letter after its "
              "first character (nCino, iOS, eBay) is the vendor's own "
              "spelling and is exempt; identifiers, hostnames, URLs, enums "
              "and verbatim excerpts are never touched.",
              "A lowercase sentence opening on a client dashboard reads as "
              "unfinished text, and it is: the capital was lost between the "
              "draft and the payload.",
              "block"),
    "CG-12": ("A face field is a label, not a paragraph", None,
              "A field that renders in a chip, badge or single-line slot "
              "stays inside its contract's stated budget (window 20-40 "
              "words, trigger 25-45, detection_basis one clause of 160 "
              "characters, a landscape tile detail 90, a client-visible "
              "plain_label 6-24 words); the long form lives in the field "
              "the surface renders as prose.",
              "A 20-40-word window clause put in a chip destroyed the "
              "why-now strip, and a 150-character detection_basis rendered "
              "as a badge overflowed every register row.",
              "block"),
    "CG-13": ("Every required field has somewhere to live", None,
              "Build-time census: each required contract field is bound by "
              "its section's writer, or is named in the computed-at-read "
              "register with the source it is recomputed from.",
              "A required field with no column is validated at submit and "
              "then discarded at promotion — the card renders empty under a "
              "real client's name and nothing failed.",
              "block"),
    "CG-14": ("A linked cell exists on this run", None,
              "Every `*subcap_ids` link and every `subcap_id` scalar "
              "resolves against the run's own scored cell set — existence, "
              "not score.",
              "A linked cell the run does not carry renders as a chip that "
              "opens the cell drawer onto nothing, and stays invisible until "
              "somebody clicks it.",
              "block"),
    "CG-15": ("A payload that says nothing", None,
              "Prose that a client would read as content actually carries "
              "some: no placeholder scalar ('N/A', 'TBD', '-', 'none', "
              "'pending', blank) where the contract requires prose; no prose "
              "field under half the word floor its own contract doc states; "
              "no section whose every present content field is vacuous; no "
              "template repeated across three or more items of one field, "
              "which needs BOTH an 8-gram overlap of 0.40 or more AND a "
              "content-word overlap of 0.40 or more once the score and "
              "evidence-inventory registers are stripped — the registers "
              "being the scaffolding the contract itself mandates, so prose "
              "that shares only the frame is not a template; and no sentence "
              "left with two or fewer content words once those same "
              "registers are removed. A recorded absence carrying its "
              "ladder, and a section with a valid empty_state, are exempt "
              "from all of it except the placeholder rule — an ITEM's "
              "absence only on the keys its own contract shape declares, "
              "since a key the shape does not name is one CG-04 never "
              "sweeps and promote has no column for.",
              "Every other gate here checks structure, identity or "
              "arithmetic. A six-page payload with all 34 sections present "
              "and every required field set to 'N/A' or [] produced zero "
              "blocking reasons and was eligible to promote: the pipeline "
              "could not tell a real assessment from an empty shell.",
              "block"),
    # CG-16/CG-17 are TRANSPORT gates, and the distinction matters: they judge
    # whether the payload ARRIVED, never what it says. They can only fire on
    # the chunked path, they fire before any submission row exists, and no gate
    # that judges content changed when they were added (MEM-0030).
    "CG-16": ("The assembled payload is the whole payload", None,
              "A chunked upload assembles only when the received part set is "
              "exactly {1..parts_total}: parts_total agrees across every "
              "part, the upload is bound to the run and page it was opened "
              "for, and every part places at its stated path. A gap names the "
              "missing indexes and NO submission row is written.",
              "A contract-complete heatmap does not fit in one tool call "
              "(measured: 1,128,742 bytes for Frost Bank, 1,598,147 for "
              "Fisher Investments), so payloads now arrive in parts. A "
              "partially transmitted payload that could be staged would "
              "validate perfectly and serve a fraction of the assessment — "
              "which is exactly how the reference client came to serve 69 "
              "cell_evidence rows out of 765 cells with a clean verdict.",
              "block"),
    "CG-17": ("A declared length is the assembled length", None,
              "Where the producer declares the assembled length of a path "
              "(`expect={'heatmap.cell_evidence.cells': 706}`), the assembled "
              "payload carries exactly that many.",
              "A list truncated at a valid element boundary still parses as "
              "JSON, so nothing structural sees it. The producer's own "
              "declared count is the only thing that does.",
              "block"),
    "ET-01": ("Cited ids resolve to this entity and run", None,
              "Every cited e_id resolves in the run's scope; a foreign id "
              "(another institution's row) halts production.",
              "A foreign id means the reasoning drifted onto another entity.",
              "block"),
    "ET-09": ("No other client named in this client's prose", None,
              "No payload string names another client in the corpus, unless "
              "that name is a peer recorded server-side for this run.",
              "ET-01 halts a foreign CITATION. Contamination that never "
              "cites — a sentence written while reading the wrong client's "
              "bundle — is invisible to it, and that is the route that "
              "actually occurred (MEM-0023).",
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
    "ET-04": ("Cited evidence carries its excerpt", None,
              "Every cited id resolves to a row carrying a verbatim excerpt "
              "of 50-500 characters; an empty excerpt is a refusal, and so "
              "is a payload-carried excerpt outside the band.",
              "Invariant 4 was fail-closed on resolution and open on "
              "content: a chip a reader can open onto nothing claims a "
              "source it does not have.",
              "block"),
    "ET-05": ("A run cites only its own sub-vertical's cells", None,
              "No section cites a variant cell whose terminal segment names "
              "a sub-vertical other than the entity's. Base cells and "
              "family or product-line variants serve every entity; the "
              "derivation is the catalogue's own id convention.",
              "A credit union's served register carried 59 insurance "
              "carrier, RIA and insurance broker cells — the workbook "
              "measuring them is a fact, serving them to this institution "
              "is not.",
              "block"),
    "ET-07": ("A cited source resolves to the cells it supports", None,
              "Every id a cell-grain section cites resolves to a row "
              "carrying at least one evidence_subcap_links entry, OR the "
              "citation is stated as supporting no cell — either because "
              "the citing section reasons at IDENTITY grain (firmographics, "
              "the financial series, regulatory standing, the leadership "
              "roster, thought leadership, evidence coverage and evidence "
              "age), or because the section's own r_layer.probes_run / "
              "empty_state.sources_searched carries a rung naming that id. "
              "Registration without linkage is an incomplete registration; "
              "an entity-identity document that genuinely supports no "
              "capability passes by saying so, never by being forced into a "
              "false link. Where a package source has TWO registrations one "
              "re-scan apart and only one of them holds the cells, the "
              "citation is named as what it is — pointing at the twin that "
              "does not carry the linkage, repaired by citing the one that "
              "does — rather than being asked to declare that it supports "
              "nothing. Which twin holds them is looked up, not inferred "
              "from the id shape: migration 0043 moved the links from the "
              "originals onto the re-mints, and remediation text that "
              "assumed the old direction would name the orphan.",
              "Measured on a promoted run: 178 served evidence rows, 72 of "
              "them carrying no cell link, 28 of those cited by a section. A "
              "reader opened the Great Place To Work chip and the drawer "
              "read 'no cell links served for this item'. An unlinked "
              "citation is worse than no citation — the reader is invited to "
              "drill in and lands on an orphan.",
              "block"),
    "ET-08": ("A cell-link field carries a cell id",
              "Cells named on this page resolve to real capabilities",
              "Every field this connector treats as a cell link — anything "
              "ending subcap_id / subcap_ids, plus capability_ids and "
              "subcaps — holds a catalogue cell id or nothing. A non-empty "
              "value that is not an id is refused.",
              "Every other cell gate SKIPS a value it cannot parse as an "
              "id: that is right for gates asking about a cited cell, and "
              "it means a cell-link field holding a capability NAME is "
              "invisible to all of them at once. Measured on the reference "
              "client, all five platform starters named their gap with "
              "'Technology Architecture & Integration.1.2' where the id "
              "belongs. Nothing refused it, and downstream the same five "
              "are cells cited on a page with no drawer behind them — a "
              "chip that renders and opens onto something that cannot "
              "exist. Refusing a name is also the only way a grain error "
              "gets caught: a category id in a cell field (P1C4 in "
              "mapped_subcap_ids) is the same defect one level up.",
              "block"),
    "ET-06": ("The candidate set is bounded by the entity's vertical", None,
              "No discard list carries a platform ruled out by the entity's "
              "own vertical — neither one whose stated reason argues from "
              "vertical or entity type, nor one whose anchor cells are "
              "another sub-vertical's variant cells.",
              "A credit union's platform page spent one of its six "
              "'considered and set aside' cards on an insurance carrier "
              "product, explaining to the client why policy administration "
              "does not apply to them. The vertical bounds the candidate set "
              "BEFORE relevance is scored: a platform outside it was never "
              "weighed, so it has no discard to show.",
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
    "AG-05": ("One event, one direction, across both pages", None,
              "An event the timeline classifies as constraining "
              "(signal NEGATIVE / maturity_effect CONSTRAINED) must not be "
              "the same event a why-now signal names as the reason to act — "
              "matched on a shared evidence id, or on the same date and "
              "subject. The pair is read across the page under validation "
              "and the sibling page's live submission, so whichever of the "
              "two is submitted second sees the other. Within one page, "
              "signal and maturity_effect are one claim: POSITIVE↔ADVANCED, "
              "NEGATIVE↔CONSTRAINED, NEUTRAL↔NEUTRAL.",
              "A merger read NEGATIVE on the context timeline while the "
              "overview's why-now used the same announcement, citing the "
              "same id and the same date, as its LEADING opportunity "
              "trigger. Both surfaces promoted; no per-page gate could see "
              "the contradiction because neither page held both halves.",
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
    "AG-09": ("A rank that contradicts its own score says why", None,
              "For every platform P: if some platform Q ranks above P and "
              "scores below it, P carries a non-empty fit_basis or story_md. "
              "Rows missing either number are skipped, not failed.",
              "A run served rank 2 at fit 70.0 and rank 3 at fit 73.0. "
              "Ranking on dependency rather than on the composite is often "
              "the honest answer, but an inversion with nothing beside it "
              "reads as a broken sort and takes the surrounding argument "
              "down with it.",
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
