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
from .subverticals import (SUBVERTICAL_NAMES, resolve_subvertical, serves,
                           variant_subvertical)

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
#
# A NOUN MISSING FROM THIS LIST IS A GATE SWITCHED OFF, SILENTLY. `issue` and
# `action` were: C2's shape is stated as "Per issue: {…}" and C3's as "Per
# action: {…}", so the register's item schema was invisible — AG-03 never asked
# an issue row for its citations, and the item-level field census could not see
# that `capped_subcap_ids` had nowhere to be stored. The census test now
# resolves every item_field's shape through this expression, so a section whose
# lead-in noun is not here fails a test instead of quietly opting out.
_PER_ITEM_RE = re.compile(
    r"(?<!\[\] )\bPer [a-z ]*?(?:item|card|recommendation|starter|event|row|"
    r"point|signal|entry|person|gate|cap|tile|alert|pattern|phase|step|"
    r"issue|action)"
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


def _asserts_nothing(item: dict, declared=None) -> bool:
    """True when the item makes no claim, so no citation is owed.

    BOUND TO THE ITEM'S OWN SHAPE. `declared` is the key set the field's
    contract declares; a key outside it buys nothing, however well-formed it
    looks. That is not pedantry about spelling — it is the hole this gate had.
    CG-04 sweeps SECTION keys only, so an undeclared ITEM key validates
    cleanly; no writer binds it, so promotion drops it. An exemption bought
    with such a key trades a real refusal for a field the client never sees.
    Measured on one Frost Bank payload: 394 of 697 `cell_evidence.cells`
    carried `state` and `sources_searched`, neither of them in H2's item
    shape. Strip the invented keys and AG-03 refuses all 394 — the gate was
    honouring fields promotion drops. `vacuity.records_absence` has been
    shape-bound for exactly this reason; AG-03 now reads the same way.

    Pass None only where the caller genuinely has no shape to bind to.
    """
    if not isinstance(item, dict):
        return False

    def named(key):
        return declared is None or key in declared

    # A quarantine is a finding only WITH its reason — `quarantined: true`
    # alone was a one-boolean exemption here while vacuity.records_absence
    # required the reason, and the daylight between the two copies is a
    # route (found by the pass-4 adversarial review, reproduced live).
    if (named("quarantined") and item.get("quarantined")
            and named("quarantine_reason")
            and str(item.get("quarantine_reason") or "").strip()):
        return True
    # The rung predicate is vacuity's, imported rather than restated: the
    # exemption lives in two gates, and a rule held in two places drifts —
    # REF-0012 hardened both copies against invented keys and then 517
    # cells bought both with DECLARED keys holding a pointer and a
    # template. A ladder that cannot exempt there cannot exempt here.
    # Presence is judged on the FILTERED rungs (vacuity._rungs), never on
    # raw truthiness: `[""]` and `true` were both "present" here and
    # rungless in the flaw check, and that gap was itself an exemption.
    from .vacuity import _rungs, ladder_flaw  # local: vacuity imports this module
    ladder = (bool(_rungs(item, declared))
              and ladder_flaw(item, declared) is None)
    # The CELL-GRAIN protocol, which the TRD states at `Representing absence`
    # and the Surface Spec's H2 item shape omitted: thin + sources_searched +
    # closure_condition. All three. `thin` alone marks a cell short of evidence
    # that still owes its argument, so a producer who could buy the exemption
    # by setting it would have a switch rather than a gate; the ladder and the
    # closure condition are what turn it into a finding.
    if (named("thin") and item.get("thin") is True and ladder
            and named("closure_condition")
            and str(item.get("closure_condition") or "").strip()):
        return True
    for key in ("state", "status", "basis", "peer_basis"):
        if not named(key):
            continue
        state = item.get(key)
        if isinstance(state, str) and state in _ABSENT_STATES:
            # an absence is a finding only with the search that established it
            return ladder
    return named("value") and "value" in item and item.get("value") in (None, "")


def _check_item_evidence(page: str, payload: dict) -> list:
    """AG-03 — every claim carries an evidence id, inferences included.

    A card, signal, finding, ceiling or register row that asserts
    something about the institution and cites nothing is unfalsifiable:
    it renders to a client with no way back to a source. The section
    envelope's e_ids are not enough — a reader drills into the ITEM."""
    # local: avoids an import cycle (vacuity reads _PER_ITEM_RE from here)
    from .vacuity import _absence_route, item_keys

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
            declared = item_keys(page, name, fname) or None
            for i, item in enumerate(items):
                if not isinstance(item, dict) or _asserts_nothing(item, declared):
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
                    "register_evidence and cite the id it returns. A state "
                    "that asserts a find with an empty id list is a "
                    "contradiction, not an empty state."
                    # …and the absence route named from the shape's OWN keys.
                    # The old tail said "state the absence explicitly with its
                    # sources_searched ladder" to all nineteen shapes, one of
                    # which declared it. Naming a door that is not in the wall
                    # is what pushes a producer into inventing one — the
                    # invented key then buys the exemption and is dropped at
                    # promotion, which is the 394-cell defect this gate was
                    # party to.
                    + _absence_route(declared)))
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


# ── ET-04 · a cited id resolves to a row that carries its excerpt ─────
#
# Invariant 4 is fail-closed in three parts: the id resolves, it belongs
# to this entity and run, and it CARRIES A VERBATIM EXCERPT of 50-500
# characters. The first two were enforced and the third was not, so a
# citation could resolve to a row with an empty excerpt and render as a
# chip a reader can open onto nothing. register_evidence refuses a short
# span at the door; an ingested row can still arrive without one, and it
# is the citation — not the registration — that puts it in front of a
# client.
EXCERPT_MIN, EXCERPT_MAX = 50, 500


def _check_excerpt_completeness(found, cited_by) -> list:
    out = []
    for row in found:
        e_id = row.get("e_id")
        section = cited_by.get(e_id) or cited_by.get(row.get("stored_id"))
        excerpt = (row.get("excerpt") or "").strip()
        if not excerpt:
            out.append(_reason(
                "ET-04", section, f"{section}.e_ids",
                f"{e_id} resolves to a row with an EMPTY excerpt — the id is "
                "real and the quotation behind it is not there. A chip a "
                "reader can open onto nothing is worse than an uncited "
                "sentence, because it claims a source. Re-register the item "
                "with its verbatim span, or cite an item that has one"))
        elif not (EXCERPT_MIN <= len(excerpt) <= EXCERPT_MAX):
            out.append(_reason(
                "ET-04", section, f"{section}.e_ids",
                f"{e_id} carries a {len(excerpt)}-character excerpt — a "
                f"verbatim span is {EXCERPT_MIN}-{EXCERPT_MAX} characters "
                f"({EXCERPT_MIN} is the fail-closed floor for a grounded "
                "excerpt). Re-extract the span from the source; never pad "
                "or trim it by hand"))
    return out


# ── ET-07 · a cited source resolves to the cells it supports ──────────
#
# ET-04 asks whether the chip opens onto a quotation. This asks the next
# question a reader asks after reading it: WHICH capability does this
# support? Measured on a promoted run — 178 served evidence rows, 72 with
# no cell link, 28 of those cited by a section — the answer for the row a
# user actually clicked (a Great Place To Work profile) was "no cell links
# served for this item". Registration without linkage is an incomplete
# registration, and an unlinked citation is worse than no citation at all:
# an uncited sentence asks nothing of the reader, while a citation invites
# them to drill in and then hands them an orphan.
#
# The honest exception is real and must pass STATED rather than be forced
# into a false link. Some sections do not reason at cell grain at all: a
# charter registry entry, an NCUA call-report period file, a licence record
# or a board roster is evidence about the INSTITUTION, not about a
# capability, and inventing a cell for it would be the misattribution
# failure this gate is supposed to reduce. Those sections are named here,
# each with the class of source it legitimately carries — a registry in
# code, not a boolean a producer can set.
_IDENTITY_GRAIN = {
    ("overview", "firmographics"): "firmographic — entity shape, not capability",
    ("overview", "financial_series"): "regulator period filing — a financial point, not a capability",
    ("overview", "leadership"): "roster / appointment record — who, not what they can do",
    ("overview", "thought_leadership"): "authored signal — attributed to a person, not a cell",
    ("overview", "evidence_coverage"): "inventory of the corpus, not a claim inside it",
    ("context", "regulatory_standing"): "regulator registry — charter, licence and perimeter",
    ("heatmap", "evidence_age"): "inventory of the corpus, not a claim inside it",
}


def _stated_unlinked(body: dict) -> str:
    """The prose a section serves whole, where a producer states why a
    cited source supports no cell. Both carriers reach the reader —
    r_layer.probes_run renders as the recorded reasoning, and
    empty_state.sources_searched as the ladder — so a reason written here
    is a reason the reader gets, not a flag in a payload."""
    parts = []
    r_layer = body.get("r_layer")
    if isinstance(r_layer, dict):
        for key in ("probes_run", "domain_test", "counter", "verdict"):
            val = r_layer.get(key)
            parts.extend(val if isinstance(val, list) else [val])
    empty = body.get("empty_state")
    if isinstance(empty, dict):
        val = empty.get("sources_searched")
        parts.extend(val if isinstance(val, list) else [val])
    return " ".join(p for p in parts if isinstance(p, str))


# A package row re-landed under a run-qualified id after a re-scan changed
# its content has a TWIN, and one of the two carries the cell links. Which
# one is not a property of the id shape, and this code used to assume it
# was.
#
# When it was written, `persist.py` minted the new id and nothing carried
# the linkage across, so the links stayed on the ORIGINAL and the re-scan
# copy was the orphan. The remediation said "cite the package id in its
# BARE form", which was right then.
#
# Migration 0043 and `persist.carry_links_across_remint` MOVE the links
# onto the re-mint. Measured on production 2026-08-09, over every cited id
# on the promoted heatmap: 3 orphans have a linked twin, and **all three
# are bare ids whose links now sit on the `-R2` copy** — E-XXX-012 (192
# cells), E-XXX-071 (43), E-XXX-026 (39). The direction inverted, and the
# advice inverted with it: telling a producer to cite the bare form now
# names the orphan.
#
# So the lookup goes BOTH ways and the reason names the id that actually
# holds the links rather than the id shape it happens to have. The class
# is `RULE_HELD_IN_TWO_PLACES_DRIFTS` again — remediation text is a second
# copy of a rule the data moved out from under.
_RUN_SUFFIX = re.compile(r"^(?P<base>.+)-R\d+$")


def _sibling_with_links(conn, stored_id: str):
    """(successor_id, cells) when this row was superseded by one that carries
    the links, or None.

    0046 records the supersession the re-scan performs, and
    `resolve_evidence_id()` is the ONE implementation of the rule — in the
    database, because `apps/api`'s evidence drawer resolves the same
    citations and this file having its own copy is what produced the
    inverted advice above. The id-shape lookup this replaced could only
    ever guess the direction from a string suffix.
    """
    stored_id = str(stored_id or "")
    if not stored_id:
        return None
    try:
        cur = conn.cursor()
        cur.execute("""SELECT r.e_id, count(DISTINCT l.subcap_id)
                         FROM resolve_evidence_id(%s) AS r(e_id)
                         JOIN evidence_subcap_links l ON l.e_id = r.e_id
                        WHERE r.e_id <> %s
                        GROUP BY r.e_id""", (stored_id, stored_id))
        row = cur.fetchone()
    except Exception:
        return None
    return (row[0], row[1]) if row and row[1] else None


def _check_cited_linkage(page, payload, found, cited_by, conn=None) -> list:
    out = []
    for row in found:
        if row.get("linked_subcap_ids"):
            continue
        e_id = row.get("e_id")
        section = cited_by.get(e_id) or cited_by.get(row.get("stored_id"))
        if (page, section) in _IDENTITY_GRAIN:
            continue                        # stated exception, named in code
        body = payload.get(section)
        if isinstance(body, dict) and e_id in _stated_unlinked(body):
            continue                        # stated exception, named on the surface
        sibling = (_sibling_with_links(conn, row.get("stored_id"))
                   if conn is not None else None)
        if sibling:
            twin, n = sibling
            # DISCLOSES, does not refuse. The reader is not stranded: the
            # serving path resolves through the same 0046 pointer, so this
            # chip opens on `twin` with its links and its fuller excerpt.
            # Blocking here would refuse a citation that renders correctly,
            # and would refuse it on 4,366 ids at once — every bare row whose
            # links 0043 moved. The producer is told to cite the current id
            # because it is better practice, not because the page is broken.
            r = _reason(
                "ET-07", section, f"{section}.e_ids",
                f"{e_id} was superseded by {twin} — the same source, re-scanned "
                f"— and the {n} cells it supports are linked to {twin}. The "
                "chip still opens: the serve path resolves the citation through "
                "the same pointer this check used. Cite the current id so the "
                "payload says what the reader is shown")
            r["severity"] = "warn"
            out.append(r)
            continue
        out.append(_reason(
            "ET-07", section, f"{section}.e_ids",
            f"{e_id} resolves to a row linked to NO capability cell, and "
            f"{section} reasons at cell grain — a reader who opens this chip "
            "is told 'no cell links served for this item', which is the "
            "orphan an unlinked citation always produces. Two honest "
            "repairs: re-register the source with the linked_subcap_ids it "
            "genuinely supports (the catalogue's own cell names decide "
            "which), or, if it supports none because it is a firmographic, "
            "registry or entity-identity document, say so in this section's "
            f"r_layer.probes_run naming {e_id} — a reason that renders beats "
            "a link that is not true"))
    return out


# ── CG-10 (evidence half) · an undated row says it is undated ─────────
#
# Invariant 9's own sentence: undated evidence is UNVERIFIED, never
# current. A row with no published_date whose band says CURRENT is a
# freshness claim computed from nothing, and the freshness dot on the
# cell drawer is drawn from that band.
_DATED_BANDS = ("CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL")


def _check_evidence_dating(found, cited_by) -> list:
    out = []
    for row in found:
        if row.get("published_date"):
            continue
        band = row.get("recency_band")
        if band in (None, "UNVERIFIED"):
            continue                       # the absence rung, correctly stated
        e_id = row.get("e_id")
        section = cited_by.get(e_id) or cited_by.get(row.get("stored_id"))
        out.append(_reason(
            "CG-10", section, f"{section}.e_ids",
            f"{e_id} has no published_date and a recency band of {band!r} — "
            "a freshness reading computed from no date. Undated evidence is "
            "UNVERIFIED, never current: re-register the row with the date "
            "the source states, or leave the band at UNVERIFIED so the "
            "surface can say the date was not established"))
    return out


# ── ET-05 · a run cites only its own sub-vertical's variant cells ─────
#
# The derivation lives in apps/api/dma_api/subverticals.py and is mirrored
# into dma_mcp/subverticals.py (the two services are separate images).
# The serving tier applies it on READ; this applies it at SUBMIT, because
# a payload that CITES another sub-vertical's cell has reasoned about a
# capability that does not apply to this institution — no read filter can
# repair the sentence written beside it. the reference client (SV2) reached
# a client surface citing 59 insurance carrier / RIA / insurance broker
# cells.
_CELL_ID_RE = re.compile(r"^P\d+C\d+\.")


# The contract does not spell every cell link `subcap_id(s)`. Three
# surfaces name the same thing differently — the timeline's
# `capability_ids`, the value chain's `subcaps`, an insight card's
# singular `linked_subcap_id` — and a predicate written from the two
# commonest spellings could not see any of them. On the run this comment
# was written against, two of the eight cards pointing at a MISATTRIBUTED
# cell sat in fields ET-05 and CG-14 were structurally blind to, so the
# chips a reader clicks were the ones no gate had read.
#
# Membership, not shape: a key is a cell link or it is not, and the value
# may be one id or a list of them. The id regex still decides what counts,
# so a key that happens to carry prose contributes nothing.
_CELL_KEYS = ("capability_ids", "subcaps")


def _is_cell_key(key: str) -> bool:
    return key.endswith(("subcap_id", "subcap_ids")) or key in _CELL_KEYS


def _iter_cell_citations(payload):
    """Yield (path, key, cell_id) for every catalogue cell id a payload
    cites — every cell-link key, scalar or list, wherever it sits in the
    tree."""
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in _walk(body, name):
            for key, value in obj.items():
                if not _is_cell_key(key):
                    continue
                if isinstance(value, str):
                    if _CELL_ID_RE.match(value):
                        yield f"{path}.{key}", key, value
                elif isinstance(value, list):
                    for i, cell in enumerate(value):
                        if isinstance(cell, str) and _CELL_ID_RE.match(cell):
                            yield f"{path}.{key}[{i}]", key, cell


def _iter_malformed_cell_ids(payload):
    """Yield (path, key, value) for a cell-link key holding something that
    is NOT a cell id.

    The citation walker above skips them — "the id regex still decides what
    counts, so a key that happens to carry prose contributes nothing" — and
    skipping is right for the gates that ask about a CITED cell. But it
    means a cell-link field carrying a capability NAME is invisible to
    every gate in this connector: ET-05, CG-14 and the rest never see the
    value, so nothing refuses it and nothing renders it either.

    Measured on the reference client: all five
    `platform.starters.starters[].named_gap_subcap_id` values carry a name
    ("Technology Architecture & Integration.1.2") where the contract wants
    a cell id. Three independent local checks reported it and no gate did;
    downstream, the same five are what `check_consistency` sees as cells
    cited on the platform page with no cell_evidence row — a reader sent to
    a drawer that cannot exist, because the id it was sent with is not one.
    """
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in _walk(body, name):
            for key, value in obj.items():
                if not _is_cell_key(key):
                    continue
                items = ([(f"{path}.{key}", value)] if isinstance(value, str)
                         else [(f"{path}.{key}[{i}]", v)
                               for i, v in enumerate(value)]
                         if isinstance(value, list) else [])
                for where, v in items:
                    if isinstance(v, str) and v.strip() \
                            and not _CELL_ID_RE.match(v):
                        yield where, key, v


def check_cell_id_shape(page: str, payload: dict) -> list:
    """ET-08 — a cell-link field carries a cell id, or names nothing.

    Deliberately narrow: it fires only on a key this connector already
    treats as a cell link, and only on a non-empty string that is not an
    id. An empty value is CG-02's business and a missing key is the
    contract's; this gate exists for the one shape both of those miss and
    every other gate skips.
    """
    out = []
    for where, key, value in _iter_malformed_cell_ids(payload):
        out.append({
            "gate_id": "ET-08", "section": where.split(".")[0],
            "path": where, "severity": "block",
            "message": (
                f"{value[:60]!r} is not a catalogue cell id, and {key!r} is a "
                "cell-link field. Every gate that reads cell links — the "
                "sub-vertical scope check, the serves check, the drawer "
                "reconciliation — skips a value it cannot parse as an id, so "
                "a name here is refused by nothing and resolves to nothing: "
                "the chip renders and opens a drawer that cannot exist. Use "
                "the id from get_capability_catalogue; the NAME belongs in "
                "the field beside it that renders the label.")})
    return out


def _entity_subvertical(conn, run_id):
    cur = conn.cursor()
    cur.execute("""SELECT e.sub_vertical FROM runs r
                     JOIN entities e ON e.id = r.entity_id
                    WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    return resolve_subvertical(row[0]) if row else None


def _check_subvertical_scope(page, payload, entity_code) -> list:
    """ET-05. Silent when the entity's sub-vertical is not in the
    vocabulary — not knowing who you are is not grounds for refusing a
    citation (the API's `serves` makes the same one-sided choice)."""
    if not entity_code or not isinstance(payload, dict):
        return []
    out, seen = [], set()
    mine = SUBVERTICAL_NAMES.get(entity_code, entity_code)
    for path, _key, cell in _iter_cell_citations(payload):
        if serves(cell, entity_code):
            continue
        owner = variant_subvertical(cell)
        section = path.split(".")[0]
        if (section, cell) in seen:
            continue                        # one verdict per cell per section
        seen.add((section, cell))
        out.append(_reason(
            "ET-05", section, path,
            f"{cell} is a {SUBVERTICAL_NAMES.get(owner, owner)} variant cell "
            f"and this run is {mine} — its terminal segment names the "
            "sub-vertical that owns it. The workbook measuring it is a fact; "
            "SERVING it to this institution is not. Drop the cell from this "
            "citation list (a base cell and a family or product variant both "
            "stay), and take the sentence that rests on it with it"))
    return out


# ── ET-06 · the candidate set is bounded by the entity's vertical ─────
#
# ET-05 is about a CITATION: a cell from somebody else's sub-vertical
# reached a sentence. This is about a CANDIDATE: a platform from somebody
# else's vertical reached the shortlist, was weighed there, and then spent
# a client-facing card explaining itself.
#
# A discard list is evidence of judgement — "why not X" is the question an
# AE gets asked, and a page that cannot answer it is a sort rather than a
# ranking. But a platform ruled out by the entity's OWN VERTICAL was never
# a candidate. It is not a close call the producer resolved; it is a thing
# that could not have applied, and putting it on the page tells the client
# their assessment considered a product for a different industry and
# congratulated itself for noticing.
#
# the reference client's platform page shipped exactly that: "Insurance
# policy administration and claims", relevance 0.15, reason "Out of
# vertical: its anchor cells belong to a carrier entity type…". One of six
# cards on a credit union's surface, spent on an insurance carrier
# product. The producer knew — it said so in the reason it wrote — and
# listed it anyway, because the contract named out-of-vertical as a DROP
# rule and a drop rule produces a card.
#
# So the boundary moves earlier: the vertical bounds the candidate set
# BEFORE relevance is scored. Discards are for platforms genuinely in
# contention — already deployed at that layer, too few cells, a relevance
# the numbers put below the line.
#
# The gate reads two things and guesses at neither: what the discard SAYS
# (a reason arguing from vertical or entity type is a reason that the
# platform was never in the set) and what it POINTS AT (anchor cells
# `serves()` says belong to another sub-vertical). A discard that argues
# from adoption, coverage or cost says none of this and passes.
_DISCARD_KEYS = ("discarded", "considered_and_set_aside", "set_aside")

# Sections in whose items an anchor-cell key means "the cells this
# candidate would address".
_ANCHOR_KEYS = ("anchor_subcap_id", "anchor_cells", "anchor_subcap_ids",
                "subcap_id", "subcap_ids", "addressable_cells")

# A reason that argues from the vertical or the entity type. Deliberately
# narrow: it matches the VOCABULARY OF BELONGING, not the mention of
# another industry. "Their insurance brokerage subsidiary already runs it"
# is an adoption reason and stays; "out of vertical", "a carrier entity
# type", "wrong sub-vertical" are declarations that the candidate was
# never in the set.
_OUT_OF_VERTICAL_RE = re.compile(
    r"out[\s-]of[\s-]vertical"
    r"|(?:wrong|different|another|other|foreign|separate)\s+"
    r"(?:sub[\s-]?)?vertical"
    r"|outside\s+(?:the|this|our|their|a)\s+(?:[\w-]+\s+){0,2}"
    r"(?:sub[\s-]?)?vertical"
    r"|(?:entity|institution|firm|business|charter)\s+type"
    r"|(?:not|never)\s+(?:a|an)\s+(?:credit\s+union|bank|carrier|insurer|"
    r"broker|RIA|broker[\s-]dealer)\b",
    re.I)


def _iter_discards(payload):
    """Yield (section, path, item) for every entry of every discard list."""
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in _walk(body, name):
            for key, value in obj.items():
                if key not in _DISCARD_KEYS or not isinstance(value, list):
                    continue
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        yield name, f"{path}.{key}[{i}]", item


def _discard_anchor_cells(item):
    for key in _ANCHOR_KEYS:
        value = item.get(key)
        if isinstance(value, str) and _CELL_ID_RE.match(value):
            yield key, value
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and _CELL_ID_RE.match(entry):
                    yield key, entry
                elif isinstance(entry, dict):
                    cell = entry.get("subcap_id")
                    if isinstance(cell, str) and _CELL_ID_RE.match(cell):
                        yield key, cell


def _check_candidate_vertical(page, payload, entity_code) -> list:
    """ET-06. Silent when the entity's sub-vertical is not in the
    vocabulary — the same one-sided choice ET-05 and the API's `serves`
    make: not knowing who you are is not grounds for refusing anything."""
    if not entity_code or not isinstance(payload, dict):
        return []
    out = []
    mine = SUBVERTICAL_NAMES.get(entity_code, entity_code)
    for section, path, item in _iter_discards(payload):
        name = str(item.get("platform") or item.get("name") or "this candidate")
        prose = " ".join(str(v) for k, v in item.items()
                         if isinstance(v, str) and k != "platform")
        foreign = [(key, cell) for key, cell in _discard_anchor_cells(item)
                   if not serves(cell, entity_code)]
        if foreign:
            key, cell = foreign[0]
            owner = SUBVERTICAL_NAMES.get(variant_subvertical(cell),
                                          variant_subvertical(cell))
            out.append(_reason(
                "ET-06", section, path,
                f"{name} is carried as a discard, and its anchor cell {cell} "
                f"(at {key}) is a {owner} variant cell while this run is "
                f"{mine}. The candidate set is drawn from the entity's own "
                "vertical, and it is bounded BEFORE any relevance is scored: "
                "a platform outside that vertical is not a candidate that was "
                "weighed and set aside, so it has no discard to render. "
                "Remove the entry — do not lower its relevance — and let a "
                "platform that is genuinely in contention have the card"))
            continue
        if _OUT_OF_VERTICAL_RE.search(prose):
            out.append(_reason(
                "ET-06", section, path,
                f"{name} is carried as a discard whose own reason rules it out "
                f"by vertical or entity type, and this run is {mine}. The "
                "candidate set is drawn from the entity's vertical, and it is "
                "bounded BEFORE any relevance is scored — a platform outside "
                "that vertical is not a candidate, so it was never weighed and "
                "has no discard to render. A card explaining to a client why a "
                "product for another industry does not apply to them spends a "
                "client-facing slot on a question they did not ask. Remove the "
                "entry; keep the discards that were genuinely in contention — "
                "already deployed at that layer, too few cells addressed, a "
                "relevance the arithmetic put below the line"))
    return out


# ── CG-14 · a linked cell exists on this run ──────────────────────────
#
# A tech row's `linked_subcap_ids` and a why-now's `linked_subcap_ids` are
# navigation: the card renders them as chips that open the cell drawer. An
# id the run does not carry opens onto nothing, and it is invisible until
# somebody clicks. Same posture as evidence — fail-closed — because a
# link to a cell that is not there is a claim about a capability this
# assessment never scored.
def _run_cells(conn, run_id) -> set:
    cur = conn.cursor()
    cur.execute("SELECT subcap_id FROM subcap_scores WHERE run_id = %s",
                (run_id,))
    return {r[0] for r in cur.fetchall() if r[0]}


def _check_cell_linkage(page, payload, run_cells) -> list:
    """CG-14. Existence, not score: a cell the run carries with a null
    score is still a cell. Silent on a run with no cells at all — an
    unscored run cannot distinguish a bad link from an unloaded workbook,
    and the empty-run case is caught by the ingest gates instead."""
    if not run_cells or not isinstance(payload, dict):
        return []
    out, seen = [], set()
    for path, key, cell in _iter_cell_citations(payload):
        if cell in run_cells:
            continue
        section = path.split(".")[0]
        if (section, key, cell) in seen:
            continue
        seen.add((section, key, cell))
        out.append(_reason(
            "CG-14", section, path,
            f"{key} names {cell}, which this run does not carry — the chip "
            "renders and opens the cell drawer onto nothing. Every linked "
            "cell resolves against the run's own scored set, the same "
            "fail-closed posture as an evidence id: link a cell the run "
            "carries, or drop the link and say what the row bears on in "
            "prose"))
    return out


# ── AG-05 · one event, one direction, across both pages ───────────────
#
# The measured defect: the context timeline classified a merger
# announcement NEGATIVE / CONSTRAINED, and the overview's why-now used the
# SAME announcement — same evidence id, same date — as its leading reason
# to act now. Both pages passed every gate they had, because neither page
# held both halves of the contradiction. A reader holds both.
#
# `signal` on the timeline is not a mood. It is the direction this event
# moved the ASSESSED POSITION of the cells it names: POSITIVE where the
# cells score higher because it happened, NEGATIVE where the assessment
# holds them to a maximum because of it and that constraint is live,
# NEUTRAL where the event explains the position without setting it — a
# retired cap, an announcement not yet completed, an obligation that adds
# demand and takes no capability away. A why-now signal says the opposite
# thing about an event: this opens a window worth acting in. One event
# cannot be both, so if the two surfaces name the same one, one of them
# is wrong and a client sees both.
_CONSTRAINING = ("NEGATIVE", "CONSTRAINED")
_EFFECT_FOR_SIGNAL = {"POSITIVE": "ADVANCED", "NEGATIVE": "CONSTRAINED",
                      "NEUTRAL": "NEUTRAL"}
_STOPWORDS = frozenset((
    "about", "after", "against", "announced", "another", "banking", "before",
    "credit", "during", "first", "their", "there", "these", "those", "union",
    "which", "while", "with", "would"))


def _content_words(*texts) -> set:
    """Words long enough to name a subject, minus the ones every event on a
    financial-services timeline shares."""
    out = set()
    for text in texts:
        if isinstance(text, str):
            out |= {w for w in re.findall(r"[a-z]{5,}", text.lower())
                    if w not in _STOPWORDS}
    return out


def _timeline_events(payload) -> list:
    body = (payload or {}).get("timeline")
    if not isinstance(body, dict):
        return []
    return [e for e in (body.get("events") or []) if isinstance(e, dict)]


def _why_now_signals(payload) -> list:
    body = (payload or {}).get("why_now")
    if not isinstance(body, dict):
        return []
    return [s for s in (body.get("signals") or []) if isinstance(s, dict)]


def _same_event(event: dict, signal: dict) -> str | None:
    """Why these two rows are the same event, or None. The event's own id
    first — a shared evidence row is the strongest possible match — then
    its date plus its subject, because a producer can cite two different
    sources for one announcement."""
    shared = ({e for e in (event.get("e_ids") or []) if isinstance(e, str)}
              & {e for e in (signal.get("e_ids") or []) if isinstance(e, str)})
    if shared:
        return f"both cite {sorted(shared)[0]}"
    date = str(event.get("event_date") or "")[:10]
    if not date or date != str(signal.get("dated_on") or "")[:10]:
        return None
    kinds = {str(event.get("kind") or "").upper(),
             str(signal.get("kind") or "").upper()}
    if len(kinds) == 1 and kinds != {""}:
        return f"same date {date} and kind {kinds.pop()}"
    overlap = (_content_words(event.get("title"), event.get("body"))
               & _content_words(signal.get("trigger")))
    if len(overlap) >= 2:
        return f"same date {date} and subject ({', '.join(sorted(overlap)[:3])})"
    return None


def _check_event_direction(page, payload, sibling) -> list:
    """AG-05. Symmetric: whichever of the two pages is submitted second
    reads the other's live submission, so the pair is always compared once
    both exist. Within one page the badge and the sentence are one claim,
    and that half needs no sibling at all."""
    out = []
    if page == "context":
        events, signals = _timeline_events(payload), _why_now_signals(sibling)
        e_section, e_path = "timeline", "timeline.events"
    elif page == "overview":
        events, signals = _timeline_events(sibling), _why_now_signals(payload)
        e_section, e_path = "why_now", "why_now.signals"
    else:
        return out

    if page == "context":
        # signal and maturity_effect are one claim about one event
        for i, event in enumerate(events):
            sig = str(event.get("signal") or "").upper()
            effect = str(event.get("maturity_effect") or "").upper()
            wanted = _EFFECT_FOR_SIGNAL.get(sig)
            if not wanted or not effect:
                continue
            if not effect.startswith(wanted):
                out.append(_reason(
                    "AG-05", "timeline", f"timeline.events[{i}].signal",
                    f"signal {sig} with a maturity_effect of "
                    f"{effect.split()[0]} — the badge and the sentence are "
                    "one claim about one event, and they disagree. signal is "
                    "the direction this event moved the assessed position of "
                    "the cells it names, so POSITIVE pairs with ADVANCED, "
                    "NEGATIVE with CONSTRAINED, NEUTRAL with NEUTRAL. Decide "
                    "which reading is right and write both halves of it"))

    for i, event in enumerate(events):
        constraining = (str(event.get("signal") or "").upper() in _CONSTRAINING
                        or str(event.get("maturity_effect") or "").upper()
                        .startswith("CONSTRAINED"))
        if not constraining:
            continue
        for j, signal in enumerate(signals):
            why = _same_event(event, signal)
            if not why:
                continue
            here = i if page == "context" else j
            out.append(_reason(
                "AG-05", e_section, f"{e_path}[{here}]",
                f"the timeline classifies {str(event.get('title'))[:60]!r} as "
                f"CONSTRAINING while why-now signal "
                f"{signal.get('wn_id') or j} names the same event as a reason "
                f"to act now ({why}). One event cannot both cap the "
                "assessment and open the window a client is asked to move "
                "in, and the same reader sees both pages. Re-read it against "
                "the cells it names: if the assessment holds them to a "
                "maximum because of this event and the cap is live today, "
                "the why-now is wrong; if it adds demand, exposure or scale "
                "without taking capability away, the timeline is wrong and "
                "the event is NEUTRAL with its pressure argued in `body`"))
    return out


def _live_submission(conn, run_id, page: str) -> dict:
    """The sibling page as it currently stands in staging. A page not yet
    submitted is not a pass — it is nothing to compare, and the symmetric
    check means the other page will make the comparison when it lands."""
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT payload FROM submissions
                WHERE run_id = %s AND page = %s AND superseded_at IS NULL
                ORDER BY submitted_at DESC LIMIT 1""", (run_id, page))
        row = cur.fetchone()
    except Exception:
        return {}
    payload = row[0] if row else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return {}
    return payload if isinstance(payload, dict) else {}


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
        reasons.extend(_check_excerpt_completeness(split.get("found", []), cited))
        reasons.extend(_check_evidence_dating(split.get("found", []), cited))
        reasons.extend(_check_cited_linkage(page, payload,
                                            split.get("found", []), cited,
                                            conn))
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
    # ET-08 runs BEFORE the cell gates below, because those all skip a
    # value they cannot parse as an id: a cell-link field holding a name
    # is invisible to every one of them, and this is where it is seen.
    reasons.extend(check_cell_id_shape(page, payload))
    # One read of the entity's sub-vertical, two gates: ET-05 scopes the
    # cells a sentence may cite, ET-06 scopes the candidates a shortlist
    # may contain.
    entity_code = _entity_subvertical(conn, run_id)
    reasons.extend(_check_subvertical_scope(page, payload, entity_code))
    reasons.extend(_check_candidate_vertical(page, payload, entity_code))
    reasons.extend(_check_cell_linkage(page, payload, _run_cells(conn, run_id)))
    # AG-05 needs the OTHER half of the pair: the timeline lives on context
    # and the why-now on overview, so each page reads the sibling's live
    # submission. Whichever lands second makes the comparison.
    if page in ("context", "overview"):
        sibling = _live_submission(
            conn, run_id, "overview" if page == "context" else "context")
        reasons.extend(_check_event_direction(page, payload, sibling))

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
        result, detail = "NOT_RUN", {"page": page, "reason": "No rated rows"}
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
               "Embedding tier unavailable — V4 is an extra guard, never a "
               "fail-closed on a missing model")
        conn.commit()
        return [{"gate_id": "SG-V4", "result": "NOT_RUN", "page": page,
                 "not_run_reason": "Embedding tier unavailable"}]

    cur.execute("""SELECT scope_kind, COALESCE(scope_id,''), centroid::text,
                          member_n, threshold
                     FROM bundle_centroids WHERE run_id = %s""", (run_id,))
    centroids = {(r[0], r[1]): {"centroid": r[2], "member_n": r[3],
                                "threshold": r[4]} for r in cur.fetchall()}
    if not centroids:
        record("NOT_RUN", {"page": page},
               "No centroids for this run — bundle not embedded")
        conn.commit()
        return [{"gate_id": "SG-V4", "result": "NOT_RUN", "page": page,
                 "not_run_reason": "No centroids for this run"}]

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
        record("NOT_RUN", detail, "Every applicable centroid was below "
                                  f"{V4_MIN_MEMBERS} members")
        disclosures.append({"gate_id": "SG-V4", "result": "NOT_RUN",
                            "page": page,
                            "not_run_reason": "Centroids below the member "
                                              "floor"})
    else:
        record("FAIL" if failed else "PASS", detail)
    conn.commit()
    return disclosures
