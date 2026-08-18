"""Validation pass 1 (stage 2.4) — structural and editorial.

Format sweeps against the contract registry: required sections and
fields, types, invented fields, the universal envelope, empty-state
ladders, and id-pattern discipline. Every reason names the gate, the
JSON path and the concrete conflict — a verdict an agent cannot act on
produces another failed submission.

Pass 2 (evidence resolution, grain locks, band words, V4) runs
separately: checking extractions against database rows is different
work from format sweeps, and the split keeps both legible.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .contracts import ENVELOPE, PAGES, sections
from .dates import ACCEPTED as DATE_SHAPES, resolve as resolve_date
from .identifiers import EID_TOKEN_RE, agent_id_class
from .vacuity import check_vacuity

_AGENT_ID_KEYS = ("ic_id", "f_id", "fa_id", "ts_id", "wn_id", "rec_id")

_TYPE_CHECK = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _norm_member(s) -> str:
    """One normaliser for both sides of the membership test, so `founded_year`,
    `Founded Year` and `founded-year` are one member and not three."""
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def _check_must_present(section, fname, spec, val, empty_declared) -> list:
    """CG-18 — the members a list field must contain, not just that it exists.

    THE ROOT CAUSE THIS CLOSES, measured 2026-08-14.

    Every "must-present set" in this product lived only as prose inside a
    contract's `doc` string. `required: true` applies to the CONTAINER — that
    `firmographics.fields` is a list — and CG-02 fires on
    `body.get(fname) is None`. So a payload carrying a list with ONE member
    satisfied every gate the connector has, and which members it carried was
    documentation.

    The consequence was reported by the build owner as "changes do not get
    promoted": `website` was added to the firmographics contract, no gate
    asked for it, and the next run would have omitted it exactly as the last
    one did. Measured on the live reference: 12 firmographics fields served,
    no website among them, while the producer's own absence ladder on that
    same section named the firm's domain twice. Nothing was broken. Nothing
    had been asked.

    WHAT COUNTS AS PRESENT — and this is the whole design:

      * a member carrying a value                                 -> passes
      * a member explicitly quarantined WITH a reason             -> passes
      * a member absent from the list entirely                    -> BLOCKS
      * a member present but null with no quarantine reason       -> BLOCKS

    The second line is what keeps the absence protocol legal: a field the
    ladder could not close is a finding, and it renders as a documented em
    dash. The third and fourth are the ones that were invisible — silence,
    and silence dressed as a value.

    The set is read from the contract, so a section that gains a member gains
    its enforcement in the same edit and this function never changes.
    """
    members = spec.get("must_present") or []
    any_of = spec.get("must_present_any") or []
    if not members and not any_of:
        return []
    # A section that declares an empty state and sends nothing has said so
    # honestly; CG-02 already governs whether that is allowed.
    if not val and empty_declared:
        return []
    key = spec.get("must_present_key", "field")

    stated, held, empty = set(), set(), set()
    for item in val or []:
        if not isinstance(item, dict):
            continue
        member = _norm_member(item.get(key))
        if not member:
            continue
        value = item.get("value")
        if value not in (None, "", []):
            stated.add(member)
        elif item.get("quarantined") and str(item.get("quarantine_reason") or "").strip():
            held.add(member)
        else:
            empty.add(member)

    out, accounted = [], stated | held
    for want in members:
        # A member may be a STRING or a LIST OF ALIASES for one fact. The
        # spec writes "founded year"; the corpus writes `founded`; the
        # normaliser folds case and punctuation but not synonyms, so the gate
        # refused the gold-standard payload for a field it plainly stated.
        # A gate that refuses correct content teaches producers to route
        # around it, which is worse than the gap it was guarding.
        aliases = want if isinstance(want, (list, tuple)) else [want]
        norms = [_norm_member(a) for a in aliases]
        want = aliases[0]                      # the canonical name, for prose
        norm = norms[0]
        if any(n in accounted for n in norms):
            continue
        if any(n in empty for n in norms):
            out.append(_reason(
                "CG-18", section, f"{section}.{fname}[{want}]",
                f"must-present member {want!r} is present with no value and "
                "no quarantine reason — an unexplained blank is the one state "
                "this set exists to refuse. Either state the value with its "
                "provenance, or run the ladder and mark the field "
                "`quarantined` with `quarantine_reason`; a documented em dash "
                "is a finding, a silent one is an omission"))
        else:
            out.append(_reason(
                "CG-18", section, f"{section}.{fname}",
                f"must-present member {want!r} is absent from "
                f"{section}.{fname} entirely. The contract's must-present set "
                "is not a suggestion: every member is stated with its "
                "provenance, or held with `quarantined` and a "
                "`quarantine_reason` naming the ladder that failed. Absent "
                "beats wrong, but absent-and-unmentioned is neither"))
    for group in any_of:
        if any(_norm_member(g) in accounted for g in group):
            continue
        out.append(_reason(
            "CG-18", section, f"{section}.{fname}",
            f"none of {', '.join(map(repr, group))} is stated or held — the "
            "set requires one of them, and a sub-vertical that genuinely "
            "reports none of them still has to say which ladder established "
            "that"))
    return out


# ── CG-20 · a vendor is a company, not a category ─────────────────────
#
# The contract has always said it: "A PRODUCT, not a service and not a
# category — 'Salesforce Financial Services Cloud' is a product; 'CRM',
# 'Analytics/BI', 'Django' are not; vendor and product are separate fields."
# Nothing checked it, so rows reading `vendor: "Integration platform"` and
# `vendor: "e-signature vendor (unnamed)"` promoted onto a client's technology
# register beside Salesforce and Fortinet. The build owner called them noise
# entries, which is exactly what they are: a placeholder for research that did
# not finish, rendered with the same weight as a confirmed deployment.
#
# Measured over both promoted registers, 2026-08-14: 39 distinct vendors, of
# which exactly 3 are categories and 36 are real companies. Both rules below
# separate them with no false positives — "Early Warning Services" keeps its
# generic third word and passes, because it also carries two words that are
# not generic.
_CG20_PLACEHOLDER = ("unnamed", "unknown", "tbd", "n/a", "not named",
                     "to be confirmed", "unspecified")
_CG20_GENERIC = frozenset((
    "platform", "platforms", "vendor", "vendors", "tool", "tools", "tooling",
    "solution", "solutions", "software", "provider", "providers", "system",
    "systems", "suite", "service", "services", "integration", "portal",
    "application", "applications", "app", "apps", "product", "products",
    "the", "a", "an", "and", "or", "of", "unnamed", "unknown", "tbd",
))


def _check_page_thread(page, section, fields, body) -> list:
    """CG-23 — a section whose writer stores a thread carries one.

    The contract registry merges `narrative_thread` into a section's fields
    only where that section's WRITER binds the column (contracts.py,
    `_section_meta_for`), so the presence of the key in `fields` is exactly
    the question "does this section have somewhere to put a thread". Six of
    the thirty-four writers bind it at item grain instead and are silently
    exempt here, which is why the field itself stays `required: false` and
    this check reads the writer rather than the flag.

    Measured 2026-08-18: the third client promoted 16 of 34 sections with a
    null thread; the reference client had 32 of 33 written. Nothing refused
    either, because `required: false` is a statement about the FIELD and the
    obligation is about the PAGE.
    """
    if "narrative_thread" not in (fields or {}):
        return []
    if not isinstance(body, dict):
        return []
    thread = body.get("narrative_thread")
    if isinstance(thread, str) and thread.strip():
        return []
    return [_reason(
        "CG-23", section, f"{section}.narrative_thread",
        "this section's writer stores a page thread and none was sent. "
        "45-75 words tracing the line through this page's surfaces in "
        "render order, written last from what was actually produced. A "
        "page is not a container for surfaces; if the thread cannot be "
        "written, the surfaces are not yet a page.")]


#: Statuses that count toward a layer's `detected` figure. CONFIRMED and
#: INFERRED are the two the contract calls detected; CLAIMED is a supplier's
#: word for it and ABSENT is a searched absence, and neither is a detection.
_DETECTED_STATUSES = frozenset({"CONFIRMED", "INFERRED"})


def _check_rollup_agrees(section, body) -> list:
    """CG-24 — `layers[].detected` equals what items[] actually holds.

    Invariant 8: counts are computed, never stored where a source of truth
    exists, and `items` is the source of truth for `detected`. Measured
    2026-08-18: a register serving six named OPS products beside
    `detected: 0` on the OPS card, because four rows were appended after the
    rollup was written and nothing recomputed it. Both numbers passed every
    other gate; the page reads as an empty estate.

    The refusal states the arithmetic, per charter invariant 12: the layer,
    the figure sent, the figure computed, and which rows were counted.
    """
    if section != "techstack" or not isinstance(body, dict):
        return []
    layers, items = body.get("layers"), body.get("items")
    if not isinstance(layers, list) or not isinstance(items, list):
        return []
    counted = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        lay = str(it.get("layer") or "").strip().upper()
        if str(it.get("status") or "").strip().upper() in _DETECTED_STATUSES:
            counted[lay] = counted.get(lay, 0) + 1
    out = []
    for i, lay in enumerate(layers):
        if not isinstance(lay, dict):
            continue
        name = str(lay.get("layer") or "").strip().upper()
        sent = lay.get("detected")
        if not isinstance(sent, int) or isinstance(sent, bool):
            continue
        got = counted.get(name, 0)
        if sent != got:
            rows = sum(1 for it in items
                       if isinstance(it, dict)
                       and str(it.get("layer") or "").strip().upper() == name)
            out.append(_reason(
                "CG-24", section, f"{section}.layers[{i}].detected",
                f"layer {name} sends detected={sent} and its own items[] "
                f"hold {got}: of the {rows} rows on this layer, {got} carry "
                f"status CONFIRMED or INFERRED. Compute this figure from "
                f"items[] at build time rather than asserting it, or the two "
                f"numbers on the card drift apart the moment a row is added."))
    return out


def _check_vendor_is_a_company(section, fname, spec, val) -> list:
    if fname != "items" or section != "techstack":
        return []
    out = []
    for i, item in enumerate(val or []):
        if not isinstance(item, dict):
            continue
        vendor = str(item.get("vendor") or "").strip()
        product = str(item.get("product") or "").strip()
        if not vendor:
            continue
        low = vendor.lower()
        words = [w for w in re.split(r"[^a-z0-9]+", low) if w]
        if any(p in low for p in _CG20_PLACEHOLDER):
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].vendor",
                f"vendor {vendor!r} says it is a placeholder. A row whose "
                "vendor is not named is research that did not finish, and it "
                "renders on the client's register with the same weight as a "
                "confirmed deployment. Name the company, or drop the row and "
                "let the section's reach counters carry the gap"))
        elif words and all(w in _CG20_GENERIC for w in words):
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].vendor",
                f"vendor {vendor!r} is a CATEGORY, not a company. The "
                "contract is explicit — vendor and product are separate "
                "fields, and 'CRM' or 'Analytics/BI' is neither. Name the "
                "company that supplies it; if the run could not establish "
                "one, the row is not a register entry"))
        elif product and product.lower() == low:
            out.append(_reason(
                "CG-20", section, f"{section}.{fname}[{i}].product",
                f"product and vendor are both {vendor!r}. One of the two is "
                "unstated: a register row names a company AND the thing it "
                "supplies, and repeating the company in both fields renders "
                "as a product nobody sells"))
    return out


def _reason(gate, section, path, message):
    return {"gate_id": gate, "section": section, "path": path,
            "message": message, "severity": "block"}


# CG-21 — a serialisation that escaped into a payload leaf.
#
# Measured 2026-08-14: a promoted run carried
# `stairstep.ladder.steps[*].blocking_findings` as JSON-ENCODED STRINGS —
# `'{"f_id": "F-1", "e_ids": ["E-CC-139"]}'` where the contract says finding
# ids. The frontend printed each item straight into a chip, so the ladder
# showed literal JSON to the AE.
#
# CG-03 cannot see this and never will: it asks whether a list's items are
# the declared type, and a JSON-encoded object IS a valid string. The
# encoding is invisible to every type check in this module, which is exactly
# why it needs its own gate rather than a widening of an existing one.
#
# The predicate is deliberately narrow — a leaf that PARSES as a JSON object
# or array. Prose that merely mentions a brace does not parse; a stringified
# object always does. Anything that parses to a scalar (a bare number, a
# quoted word) is not a serialisation of a structure and is left alone.
def _looks_like_serialised_json(text: str) -> bool:
    s = text.strip()
    if len(s) < 2 or s[0] not in "{[":
        return False
    try:
        return isinstance(json.loads(s), (dict, list))
    except Exception:
        return False


def _check_serialised_leaves(section: str, node, path=None) -> list:
    """Walk every leaf of a section and refuse the ones that are JSON."""
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_serialised_leaves(section, v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_serialised_leaves(section, item, f"{path}[{i}]"))
    elif isinstance(node, str) and _looks_like_serialised_json(node):
        shape = "object" if node.strip()[0] == "{" else "array"
        out.append(_reason(
            "CG-21", section, path,
            f"this leaf is a JSON {shape} that has been SERIALISED into a "
            f"string: {node.strip()[:80]!r}. Send the value, not a "
            "serialisation of it — the serving path stores what it is given "
            "and the page renders it verbatim, so an encoded object reaches "
            "the client as literal JSON. If the contract asks for ids, send "
            "the ids; if it asks for objects, send objects and let CG-03 "
            "check their type"))
    return out


def _valid_empty_state(es) -> bool:
    return (isinstance(es, dict) and bool(es.get("reason"))
            and isinstance(es.get("sources_searched"), list)
            and len(es["sources_searched"]) > 0)


def validate_pass1(page: str, payload: dict) -> list:
    if page not in PAGES:
        return [_reason("CG-01", None, page, f"unknown page {page!r}; pages are {list(PAGES)}")]
    if not isinstance(payload, dict):
        return [_reason("CG-03", None, page, "payload must be an object of sections")]

    reasons = []
    contract = sections(page)

    for name in payload:
        if name not in contract:
            reasons.append(_reason(
                "CG-04", name, name,
                f"section {name!r} is not in the {page} contract — payload "
                "shapes are law; call get_page_contract and re-shape"))

    for name, sec in contract.items():
        body = payload.get(name)
        if body is None:
            if sec.get("required", True):
                reasons.append(_reason(
                    "CG-01", name, name,
                    f"required section {name!r} missing — promotion requires "
                    "a passing submission on every required section"))
            continue
        if not isinstance(body, dict):
            reasons.append(_reason("CG-03", name, name,
                                   f"section {name!r} must be an object"))
            continue

        fields = sec["fields"]
        empty = body.get("empty_state")
        empty_declared = empty is not None
        if empty_declared and not _valid_empty_state(empty):
            reasons.append(_reason(
                "CG-06", name, f"{name}.empty_state",
                "an explicit empty state must name its reason and the "
                "sources_searched — an absence with no ladder is rejected"))

        for fname in body:
            if fname not in fields:
                reasons.append(_reason(
                    "CG-04", name, f"{name}.{fname}",
                    f"field {fname!r} is not in the {page}.{name} contract"))

        for fname, spec in fields.items():
            val = body.get(fname)
            if val is None:
                if spec["required"] and fname in ENVELOPE:
                    reasons.append(_reason(
                        "CG-05", name, f"{name}.{fname}",
                        f"envelope field {fname!r} is required on every "
                        "section, empty states included"))
                elif spec["required"] and not empty_declared:
                    reasons.append(_reason(
                        "CG-02", name, f"{name}.{fname}",
                        f"required field {fname!r} missing and no explicit "
                        "empty state declared"))
                continue
            # CG-19 — `required: true` was satisfied by an EMPTY list.
            #
            # `val = []` is not None, so the branch above never ran, and a
            # list type-checks fine. The empty list then wrote zero rows at
            # promotion, and the read path omits a key with no rows — so the
            # surface DISAPPEARED from the served page with no empty_state to
            # explain it, and every gate was green. Measured 2026-08-14 across
            # both promoted clients: exactly one content field each is empty
            # or absent without an empty state, and on the second client it is
            # `platform.starters.starters` — the conversation starters the
            # build owner reported as "disappeared".
            #
            # An empty list is a claim ("there are none") and it has to be
            # made deliberately: declare the section's empty_state with the
            # ladder, or mark the field `may_be_empty` in the contract where
            # emptiness is the ordinary case rather than a finding
            # (`techstack.dropped` — nothing was dropped — is the one such
            # field in the registry today).
            if (spec["type"] == "list" and spec["required"] and not val
                    and fname not in ENVELOPE and not empty_declared
                    and not spec.get("may_be_empty")):
                reasons.append(_reason(
                    "CG-19", name, f"{name}.{fname}",
                    f"required list {fname!r} is EMPTY and the section "
                    "declares no empty state. An empty list is not a quiet "
                    "pass: promotion writes no rows for it and the surface "
                    "vanishes from the page with nothing saying why. Either "
                    "send the items, or declare the section's empty_state "
                    "with the ladder that established the absence"))
                continue
            check = _TYPE_CHECK.get(spec["type"])
            if check and not check(val):
                reasons.append(_reason(
                    "CG-03", name, f"{name}.{fname}",
                    f"{fname!r} must be {spec['type']}, got "
                    f"{type(val).__name__}"))
                continue
            if spec["type"] == "list" and spec.get("item_type") in ("object", "string"):
                want = dict if spec["item_type"] == "object" else str
                for i, item in enumerate(val):
                    if not isinstance(item, want):
                        reasons.append(_reason(
                            "CG-03", name, f"{name}.{fname}[{i}]",
                            f"items of {fname!r} must be "
                            f"{spec['item_type']}s (the item schema is in "
                            "the field's doc text)"))
                        break
            reasons.extend(_check_must_present(name, fname, spec, val,
                                               empty_declared))
            reasons.extend(_check_vendor_is_a_company(name, fname, spec, val))

        reasons.extend(_check_page_thread(page, name, fields, body))
        reasons.extend(_check_rollup_agrees(name, body))

        # id-pattern discipline
        for i, e in enumerate(body.get("e_ids") or []):
            if isinstance(e, str) and not EID_TOKEN_RE.fullmatch(e.split(":")[0]):
                reasons.append(_reason(
                    "ET-03", name, f"{name}.e_ids[{i}]",
                    f"{e!r} is not an evidence id the recogniser accepts"))
        reasons.extend(_check_agent_ids(name, body))
        reasons.extend(_check_enum_fields(page, name, body))
        reasons.extend(_check_contract_vocabularies(page, name, body))
        reasons.extend(_check_date_fields(page, name, body))
        reasons.extend(_check_date_absence(page, name, body))
        reasons.extend(_check_sentence_case(name, body))
        reasons.extend(_check_face_budgets(page, name, body))
        reasons.extend(_check_payload_excerpts(name, body))
        reasons.extend(_check_serialised_leaves(name, body))

    # CG-15 runs once over the whole page: template repetition is a
    # relation BETWEEN a field's items, not a property of one value, so it
    # cannot be answered inside the per-section loop above.
    reasons.extend(check_vacuity(page, payload))

    return reasons


# Payload fields whose promoted column is a Postgres enum. Generated from
# the live schema and the writer spec (scripts/gen_enum_fields.py), because
# a value the enum rejects is not a JSON-type error — it type-checks as a
# string and then aborts the promote transaction, which is the one place a
# failure must never surface. The first production promote of this
# connector died exactly there: prose written into an EVIDENCE│HYBRID│
# INFERRED chip.
_ENUM_FIELDS = None


def _enum_fields() -> dict:
    global _ENUM_FIELDS
    if _ENUM_FIELDS is None:
        try:
            _ENUM_FIELDS = json.loads(
                Path(__file__).with_name("enum_fields.json").read_text())["enum_fields"]
        except Exception:
            _ENUM_FIELDS = {}
    return _ENUM_FIELDS


def _at_path(body, path):
    """Yield (json_path, value) for a spec path, following `[*]` lists.

    Handles repeated `[*].` levels and dotted leaves, so a nested face
    field (`tiles[*].addressable_cells[*].feature_that_addresses_it`) and
    a nested object leaf (`validation_gate.grain_note`) are both
    addressable — a registry that could only reach one level deep would
    silently police nothing on the surfaces that nest.
    """
    head, sep, rest = path.partition("[*].")
    if not sep:
        node = body
        for part in head.split("."):
            if not isinstance(node, dict) or part not in node:
                return
            node = node[part]
        yield head, node
        return
    node = body
    for part in head.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, list):
        for i, item in enumerate(node):
            for sub, value in _at_path(item, rest):
                yield f"{head}[{i}].{sub}", value


def _check_date_fields(page: str, section: str, body) -> list:
    """A field promoted into a DATE column must resolve to one. Month and
    quarter precision are legitimate (the prompts ask for them) and resolve;
    anything else is rejected here rather than aborting the promote."""
    out = []
    spec = None
    try:
        spec = json.loads(
            Path(__file__).with_name("enum_fields.json").read_text()).get("date_fields", {})
    except Exception:
        return out
    for path in spec.get(f"{page}.{section}", ()):
        for jpath, value in _at_path(body, path):
            if resolve_date(value) is False:
                out.append(_reason(
                    "CG-09", section, f"{section}.{jpath}",
                    f"{str(value)[:40]!r} does not resolve to a date — this field is "
                    f"promoted into a DATE column and accepts {DATE_SHAPES}"))
    return out


# Fields whose promoted column is plain TEXT but whose CONTRACT states a closed
# vocabulary. The generated `enum_fields` registry only knows Postgres enums, so
# these were policed by nothing: a producer wrote a consequence SENTENCE into
# `context.timeline.events[*].signal`, the TEXT column accepted it, promotion
# succeeded, and the Positive/Neutral/Negative filters on D5 then matched zero
# events on a page with ten of them. A filter that silently matches nothing is
# worse than a failed submission, so the vocabulary is enforced here.
#
# Add a field only where the contract names the values. This is not a place to
# invent vocabulary — the contract's `doc` text is the source.
_CONTRACT_VOCABULARIES = {
    "context.timeline": {
        "events[*].signal": {
            "name": "signal",
            "values": ("POSITIVE", "NEUTRAL", "NEGATIVE"),
            "note": ("the event's direction for maturity, which the D5 timeline "
                     "clusters on. The consequence sentence belongs in "
                     "`maturity_effect`, not here"),
        },
        # Measured on a served run: 4 of 11 events carried a kind outside the
        # eight — TECHNOLOGY (x3) and CAPABILITY (x1). The column is plain TEXT
        # and nothing else looked, so those four events matched no D5 filter
        # and were invisible on a page that rendered them.
        "events[*].kind": {
            "name": "kind",
            "values": ("PLATFORM", "LEADERSHIP", "M&A", "REGULATORY",
                       "CHANNEL", "DATA", "SECURITY", "STRATEGY"),
            "note": ("the event's class, which D5 filters on. A near-miss "
                     "('TECHNOLOGY' for PLATFORM, 'CAPABILITY' for DATA) is "
                     "not a synonym — it is an event no filter can reach"),
        },
        # LEADING: the contract asks for the word "with one clause of
        # reasoning", so the served value is 'ADVANCED — the core is no longer
        # the constraint…'. An exact match here would have refused all eleven
        # events of a run that is doing exactly what it was asked.
        "events[*].maturity_effect": {
            "name": "maturity_effect",
            "values": ("ADVANCED", "CONSTRAINED", "NEUTRAL"),
            "leading": True,
            "note": ("the effect on today's assessed position, leading the "
                     "field; the clause of reasoning follows it"),
        },
        # Served value: 'strategy-first, substrate-later' — prose against a
        # five-word vocabulary, on a TEXT column with no enum behind it.
        "arc_shape": {
            "name": "arc_shape",
            "values": ("STEADY_INVESTMENT", "STOP_START", "POST_EVENT_CATCHUP",
                       "LEGACY_ANCHORED", "RECENT_ACCELERATION"),
            # leading, because the contract states the five "with one sentence
            # of evidence" — the badge must be one of them, what follows it is
            # the producer's own prose
            "leading": True,
            "note": ("the shape of the sequence, one of five, leading the "
                     "field. A coined phrase renders as an unrecognised badge; "
                     "the sentence of evidence follows the word"),
        },
    },
    # Per-item provenance, now that it HAS a column (0027). The vocabularies
    # differ per surface because the contract states different ones, which is
    # why the column is TEXT — so CG-09 is the only thing standing between a
    # coined value and a badge nobody can read.
    "platform.recommendations": {
        "recommendations[*].provenance": {
            "name": "provenance",
            "values": ("ANALYST", "DERIVED"),
            "note": ("how THIS recommendation was arrived at — required, never "
                     "blank. Distinct from the section envelope's provenance, "
                     "which says who produced the section"),
        },
    },
    "platform.starters": {
        "starters[*].provenance": {
            "name": "provenance",
            "values": ("TEMPLATE_FILL", "ANALYST"),
            "note": ("and RENDER it — a rule-composed starter labelled as "
                     "analyst work misrepresents how it was written"),
        },
    },
    "platform.roadmap": {
        "phases[*].provenance": {
            "name": "provenance",
            "values": ("analyst", "derived"),
            "note": ("if the package states the phasing use it and label it "
                     "analyst; derive only where it does not"),
        },
    },
    "techstack.techstack": {
        "items[*].status": {
            "name": "status",
            "values": ("CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"),
            "note": "required per row; the register renders each state distinctly",
        },
    },
}


_LEADING_TOKEN = re.compile(r"^[A-Z][A-Z_]*")


# Vocabularies the CONTRACT declares in its own `doc` text, derived rather
# than copied. `_CONTRACT_VOCABULARIES` above is hand-written, and hand-
# written is how `context.timeline.arc_shape` — whose doc opens
# "STEADY_INVESTMENT|STOP_START|POST_EVENT_CATCHUP|LEGACY_ANCHORED|
# RECENT_ACCELERATION" — was never added to it. A promoted run served
# `'strategy-first, substrate-later'` there: a coined phrase in a
# five-value field, which is MEM-0010's exact class on the exact page
# CG-09 was built for, one field along.
#
# So the hand-written entries stay (they carry near-miss guidance and the
# `leading` rule, which no derivation can infer) and anything the contract
# declares and they do not is derived and policed automatically. A
# vocabulary added to the contract tomorrow is enforced tomorrow.
# Case-INSENSITIVE, because a vocabulary is not always shouted: the
# contract states `platform.roadmap.sequencing_basis` as
# "prerequisites|undetermined", and an uppercase-only expression let a
# 90-word paragraph sit in it on a promoted run. Found by the producer
# repairing that run, not by this gate.
_DOC_VOCAB = re.compile(
    r"^([A-Za-z][A-Za-z0-9_&/-]{1,30}(?:\|[A-Za-z][A-Za-z0-9_&/-]{1,30}){1,12})")
# …and a TYPE description is not a vocabulary. `context.regulatory_standing
# .charter_date` opens "date|null", which reads as a two-value enum to the
# expression above and would refuse every real date. Measured before
# landing the widening: it was the only false positive in the corpus, and
# it is the reason this list exists rather than a case fold alone.
_TYPE_WORDS = frozenset((
    "date", "datetime", "time", "null", "none", "string", "str", "text",
    "number", "numeric", "int", "integer", "float", "decimal", "bool",
    "boolean", "true", "false", "object", "dict", "list", "array", "any",
))
_DERIVED_VOCABULARIES = None


def _derived_vocabularies() -> dict:
    """{"page.section": {field: spec}} from the contract's own doc text."""
    global _DERIVED_VOCABULARIES
    if _DERIVED_VOCABULARIES is not None:
        return _DERIVED_VOCABULARIES
    out: dict = {}
    try:
        for page in PAGES:
            for sname, sec in sections(page).items():
                key = f"{page}.{sname}"
                hand = _CONTRACT_VOCABULARIES.get(key, {})
                for fname, spec in (sec.get("fields") or {}).items():
                    if fname in hand:
                        continue          # the hand-written entry wins
                    m = _DOC_VOCAB.match((spec.get("doc") or "").strip())
                    if not m:
                        continue
                    values = tuple(m.group(1).split("|"))
                    if any(v.lower() in _TYPE_WORDS for v in values):
                        continue          # a type description, not a vocabulary
                    out.setdefault(key, {})[fname] = {
                        "name": fname,
                        "values": values,
                        "note": ("the vocabulary is stated in this field's "
                                 "own contract doc, first line. A coined "
                                 "phrase in a fixed-vocabulary field renders, "
                                 "matches no filter, and is invisible to "
                                 "every surface that groups on it"),
                        # A vocabulary the contract states as a bare pipe list
                        # is exact: where a field legitimately takes the WORD
                        # then a clause, its hand-written entry says so.
                        "leading": False,
                    }
    except Exception:                     # noqa: BLE001 — derived, never fatal
        out = {}
    _DERIVED_VOCABULARIES = out
    return out


def _vocabularies(page: str, section: str) -> dict:
    key = f"{page}.{section}"
    return {**_derived_vocabularies().get(key, {}),
            **_CONTRACT_VOCABULARIES.get(key, {})}


def _check_contract_vocabularies(page: str, section: str, body) -> list:
    out = []
    for path, spec in _vocabularies(page, section).items():
        for jpath, value in _at_path(body, path):
            if value is None or value in spec["values"]:
                continue
            if spec.get("leading") and isinstance(value, str):
                # The contract asks for the WORD and then a clause. The badge
                # is the leading run of capitals; everything after it is the
                # producer's prose and none of this gate's business.
                m = _LEADING_TOKEN.match(value)
                if m and m.group(0) in spec["values"]:
                    continue
            shown = (value if isinstance(value, str) and len(value) <= 60
                     else f"{str(value)[:57]}…")
            out.append(_reason(
                "CG-09", section, f"{section}.{jpath}",
                f"{shown!r} is not a value of {spec['name']} — the contract "
                f"states {' │ '.join(spec['values'])}. {spec['note']}"))
    return out


def _check_enum_fields(page: str, section: str, body) -> list:
    out = []
    for path, spec in _enum_fields().get(f"{page}.{section}", {}).items():
        for jpath, value in _at_path(body, path):
            if value is None or value in spec["values"]:
                continue
            shown = value if isinstance(value, str) and len(value) <= 60 else f"{str(value)[:57]}…"
            out.append(_reason(
                "CG-09", section, f"{section}.{jpath}",
                f"{shown!r} is not a value of {spec['enum']} — this field is promoted "
                f"into an enum column and takes one of {' │ '.join(spec['values'])}"))
    return out


def _check_agent_ids(section, node, path=None) -> list:
    """Agent-created ids (five classes + authored rec_id) must match
    their patterns wherever they appear in the section tree."""
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if k in _AGENT_ID_KEYS and isinstance(v, str):
                if agent_id_class(v) != k:
                    out.append(_reason(
                        "ET-03", section, p,
                        f"{v!r} does not match the {k} pattern — the agent "
                        "creates exactly five id classes plus authored rec_id"))
            else:
                out.extend(_check_agent_ids(section, v, p))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_agent_ids(section, item, f"{path}[{i}]"))
    return out


# ── CG-10 · a date that could not be established says so ──────────────
#
# The date that DATES an item on a surface: the timeline's x-position, the
# issue register's Gantt start, the signal's event date, the firmographic
# row's recency dot. A bare null in one of these does not render as "no
# date" — it renders as an EMPTY SLOT beside a populated row, which reads
# as undated when nobody looked and as undated when somebody looked and
# found nothing. Those are different facts and the surface cannot tell
# them apart, so the payload has to (invariant 9: undated evidence is
# UNVERIFIED, never current; a derived value is computed or null, never a
# default that looks like data).
#
# Registered here are the item-dating fields only. A SECOND date on the
# same item — `resolved_on` on an ACTIVE matter, `closed_on` on an
# ANNOUNCED merger, `appointed_on` where the source gives no start date —
# is legitimately null: the event has not happened, which is a fact about
# the world rather than a gap in the research. Refusing those would be
# refusing the truth.
_ITEM_DATING = {
    "context.timeline": ("events[*].event_date", "the timeline places the "
                         "event on an axis; an undated event has no position"),
    "context.issue_register": ("issues[*].opened_on", "the register orders on "
                               "opened_on and the Gantt draws from it"),
    "overview.why_now": ("signals[*].dated_on", "a why-now is an EVENT; the "
                         "contract drops an undated signal rather than "
                         "rendering one"),
    "overview.thought_leadership": ("entries[*].published_on", "the card "
                                    "prints the publication date beside the "
                                    "quote"),
    "overview.firmographics": ("fields[*].as_of", "the recency dot is computed "
                               "from as_of"),
    "overview.leadership": ("roster[*].as_of", "a name with no verification "
                            "date does not render — a stale executive is "
                            "worse than a gap"),
    "heatmap.evidence_age": ("rows[*].published_or_asof", "age_months and band "
                             "are computed from this date"),
}

# Values that RECORD non-establishment rather than assert a date. The
# ladder's own words, plus the evidence tier's UNVERIFIED and the
# evidence-age contract's own `undated` band.
_ABSENCE_RUNGS = frozenset((
    "UNVERIFIED", "UNWORKED", "WORKED_ABSENT", "NOT_RUN", "undated",
    "verified_absent", "verified_sparse", "cannot_estimate", "empty_state",
))
# Keys whose value may carry one of those rungs (an enum) or, for the
# `_reason`/`_note`/`_basis` forms, any non-empty sentence.
_RUNG_KEYS = ("recency_band", "recency_tag", "band", "date_basis",
              "dating_basis", "undated_reason", "date_absence")


def _records_absence(item: dict, field: str) -> bool:
    """True when the item states that the date was searched for and not
    established, rather than leaving a hole."""
    if not isinstance(item, dict):
        return False
    if item.get("quarantined") and item.get("quarantine_reason"):
        return True
    for key in (f"{field}_basis", f"{field}_absence", f"{field}_note",
                f"{field}_reason"):
        if str(item.get(key) or "").strip():
            return True
    for key in _RUNG_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip() in _ABSENCE_RUNGS:
            return True
    # the absence protocol's own record: what was searched, and with what
    for key in ("sources_searched", "queries_run"):
        if isinstance(item.get(key), list) and item[key]:
            return True
    return False


def _check_date_absence(page: str, section: str, body) -> list:
    out = []
    entry = _ITEM_DATING.get(f"{page}.{section}")
    if not entry or not isinstance(body, dict):
        return out
    path, why = entry
    container, _, field = path.partition("[*].")
    items = body.get(container)
    for i, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        if item.get(field) is not None:
            continue
        if _records_absence(item, field):
            continue
        out.append(_reason(
            "CG-10", section, f"{section}.{container}[{i}].{field}",
            f"{field} is a bare null — {why}. A date nobody could establish "
            "is a finding and is recorded as one: carry the rung that says "
            f"so ({' │ '.join(sorted(_ABSENCE_RUNGS))} on {', '.join(_RUNG_KEYS)}, "
            "or the sources_searched ladder that established the absence), "
            "or state the date, or drop the row. What must not happen is an "
            "empty slot beside a populated one — the surface cannot tell "
            "'not looked for' from 'looked for and not found', so the "
            "payload has to"))
    return out


# ── CG-11 · prose begins as a sentence ────────────────────────────────
#
# Mechanical, and asked for by name: a field that renders as a line of
# prose on a client surface starts with a capital. The exception is a
# first word that carries an uppercase letter after its first character —
# nCino, iOS, eBay, iPhone — which is the vendor's own orthography and
# must survive untouched. Everything else that starts lowercase is a
# sentence that lost its opening capital somewhere between the draft and
# the payload.
#
# Scope is deliberately narrow enough to be right every time: a value is
# policed when its KEY is a prose key, or when the value ENDS in terminal
# punctuation (the producer wrote a sentence, so it is one). A noun-phrase
# fragment that renders inline after a label — a unit, a system reference,
# an id, a hostname, an enum — is none of those and is left alone, because
# capitalising a fragment mid-sentence is the same defect pointing the
# other way.
_PROSE_KEYS = frozenset((
    "body", "rationale", "story", "story_md", "text", "framing", "synthesis",
    "summary", "narrative", "narrative_thread", "consequence",
    "consequence_of_waiting", "cost_of_acting_now", "why_this_sequence",
    "trigger", "window", "detection_basis", "dma_impact", "so_what", "what",
    "why", "reason", "not_run_reason", "note", "grain_note", "currency_note",
    "reach_note", "detail", "statement", "pattern_statement", "headline",
    "relevance_note", "effect_note", "mix_implication", "strategic_alignment",
    "plain_label", "rejected_alternative", "implication", "clause",
    "limiting_absence", "description", "justification", "closure_condition",
    "quarantine_reason", "sequencing_basis", "sequencing_reason",
    "denominator_definition", "target_basis", "enrichment_basis",
    "proxy_disclosure", "maturity_effect", "empty_reason",
))
# Never touched: a verbatim span is a copy of what a document says, and
# editing its first letter to look tidier is the one thing evidence may
# never have done to it. Identifiers, hostnames and URLs are not prose.
_NEVER_SENTENCE = frozenset((
    "excerpt", "quote", "verbatim", "snippet", "url", "source_url",
    "linkedin_url", "producer_version", "source_domain", "domain", "email",
    "phone", "e_id", "source_name", "vendor", "product", "name", "field",
    "unit", "value", "kind", "layer", "status", "tier", "id",
))
_MIN_SENTENCE = 25
# nCino, iOS, eBay: an uppercase letter anywhere after the first character
# of the FIRST word. Their lowercase opener is the spelling, not a slip.
_CAMEL_FIRST_WORD = re.compile(r"^[a-z]+[A-Z]")


def _sentence_case_reason(path_key: str, value: str):
    """→ the offending first word, or None when the value is fine."""
    if not isinstance(value, str) or len(value) < _MIN_SENTENCE:
        return None
    if path_key in _NEVER_SENTENCE:
        return None
    if not re.search(r"\s", value):
        return None                      # a token, not a sentence
    text = value.strip().lstrip("\"'“‘([{")
    if not text or not text[0].isalpha() or not text[0].islower():
        return None
    ends_as_sentence = value.strip()[-1] in ".?!"
    if path_key not in _PROSE_KEYS and not ends_as_sentence:
        return None
    word = text.split()[0].strip(".,;:")
    if _CAMEL_FIRST_WORD.match(word):
        return None                      # nCino, iOS, eBay — the vendor's own
    return word


def _check_sentence_case(section: str, node, path=None, key=None) -> list:
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_sentence_case(section, v, f"{path}.{k}", k))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_sentence_case(section, item, f"{path}[{i}]", key))
    elif isinstance(node, str) and key:
        word = _sentence_case_reason(key, node)
        if word:
            out.append(_reason(
                "CG-11", section, path,
                f"begins {word!r} — a prose field on a client surface begins "
                f"with a capital. Write {word.capitalize()!r}. (A first word "
                "carrying an uppercase letter after its first character — "
                "nCino, iOS, eBay — is the vendor's own spelling and is "
                "exempt; this one is not.)"))
    return out


# ── CG-12 · a face field is a label, not a paragraph ──────────────────
#
# Two measured failures, one class. A 20-40-word `window` clause was
# rendered as a chip on the why-now card FACE and destroyed the strip's
# layout; a 150-character `detection_basis` was rendered as a badge in the
# tech register's right rail and overflowed every row. The renderer has
# since moved both to where prose belongs, and this is the other half of
# that repair: the payload keeps the face field inside the budget its own
# contract states, so the next surface that puts it on a face has a
# bounded string to put there.
#
# Each entry names the slot and where the long form lives, because the
# repair is never "cut words" — it is "move the argument to the field
# that renders it".
_FACE_BUDGETS = {
    "overview.why_now": (
        ("signals[*].window", {"max_words": 40, "min_words": 20},
         "the drilldown's Window row",
         "the closing EVENT and its date; the argument for acting belongs "
         "in consequence_of_waiting"),
        ("signals[*].trigger", {"max_words": 45, "min_words": 25},
         "the card face, cut at its first clause",
         "what changed, dated and cited; the reasoning belongs in "
         "why_this_sequence"),
    ),
    "techstack.techstack": (
        ("items[*].detection_basis", {"max_chars": 160, "max_sentences": 1},
         "the register row and the T3 detail header",
         "ONE CLAUSE saying how the product was placed in this estate; the "
         "explanation of what it bears on belongs in dma_impact (40-90 words)"),
    ),
    "insights.landscape": (
        ("tiles[*].detail", {"max_chars": 90},
         "the landscape tile's one-line detail",
         "the count's meaning in one line"),
    ),
    "heatmap.safeguard_gates": (
        ("gates[*].plain_label", {"min_words": 6, "max_words": 24},
         "the client-visible gate card",
         "a human sentence of 8-18 words; the mechanism belongs in "
         "what_it_checks"),
    ),
    "overview.opportunity": (
        ("tiles[*].addressable_cells[*].feature_that_addresses_it",
         {"max_chars": 80}, "the addressable-cell chip",
         "the feature's name, not its case"),
    ),
}


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _check_face_budgets(page: str, section: str, body) -> list:
    out = []
    for path, budget, slot, belongs in _FACE_BUDGETS.get(f"{page}.{section}", ()):
        for jpath, value in _at_path(body, path):
            if not isinstance(value, str) or not value.strip():
                continue
            words, chars = len(value.split()), len(value)
            over = None
            if "max_chars" in budget and chars > budget["max_chars"]:
                over = (f"{chars} characters against a budget of "
                        f"{budget['max_chars']}")
            elif "max_words" in budget and words > budget["max_words"]:
                over = f"{words} words against a budget of {budget['max_words']}"
            elif "max_sentences" in budget and \
                    _sentences(value) > budget["max_sentences"]:
                over = (f"{_sentences(value)} sentences where the contract "
                        f"states {budget['max_sentences']}")
            elif "min_words" in budget and words < budget["min_words"]:
                over = f"{words} words, under the stated floor of {budget['min_words']}"
            if over is None:
                continue
            out.append(_reason(
                "CG-12", section, f"{section}.{jpath}",
                f"renders in {slot} and carries {over}. This field holds "
                f"{belongs}. The repair is to MOVE the prose, not to trim it: "
                "a paragraph in a face slot overflows its container, and a "
                "20-40-word window clause put in a chip is what broke the "
                "why-now strip"))
    return out


# ── ET-04 (payload half) · an excerpt is a 50-500 char verbatim span ───
#
# The store enforces this at registration, but a payload may carry the
# excerpt itself (the run's evidence index renders it under every chip),
# and an empty or clipped one reaches the client as a citation with
# nothing behind it. Same floor either side of the boundary: 50 characters
# is the fail-closed minimum for a grounded excerpt, 500 the ceiling.
def _check_payload_excerpts(section: str, node, path=None, key=None) -> list:
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_check_payload_excerpts(section, v, f"{path}.{k}", k))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_payload_excerpts(section, item, f"{path}[{i}]", key))
    elif key == "excerpt":
        text = node if isinstance(node, str) else ""
        n = len(text.strip())
        if n == 0:
            out.append(_reason(
                "ET-04", section, path,
                "empty excerpt — a citation with no verbatim span is a "
                "reference, not evidence. Re-extract the 50-500 character "
                "span from the source; never compose one"))
        elif not (50 <= n <= 500):
            out.append(_reason(
                "ET-04", section, path,
                f"excerpt is {n} characters — a verbatim span is 50-500 "
                "(50 is the fail-closed floor for a grounded excerpt, above "
                "the 40-character linkable minimum). Widen the span in the "
                "source or cite a different passage; never pad it"))
    return out
