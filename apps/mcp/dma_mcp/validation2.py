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


def _check_rank_against_score(page: str, payload: dict) -> list:
    """AG-09 — a rank that contradicts its own score says why, on the row.

    Measured on a promoted run, 2026-08-15: the platform set served rank 2 at
    fit 70.0 and rank 3 at fit 73.0. The doc's BAX-24 and BAX-10 both name this
    ("fit-70 ranked above fit-73") and both call it a defect.

    It is not an arithmetic error, and refusing every inversion would be wrong.
    This producer ranks on DEPENDENCY — "ranked third because its value
    multiplies after the data layer lands" — and a dependency order that
    disagrees with a weighted composite is the honest answer, not a broken sort.
    The R-Layer says as much: a ranking that cannot discard is a sort.

    What cannot ship is the inversion with nothing beside it. A reader who sees
    73.0 sitting under 70.0 and no reason concludes the arithmetic is broken,
    and the surrounding argument loses with it. So the gate is narrow:

        for every platform P, if some platform Q ranks ABOVE P (Q.rank <
        P.rank) and scores BELOW it (Q.fit_score < P.fit_score), then P must
        carry a non-empty ordering basis.

    `fit_basis` is that basis — the contract already requires it to say where
    the figure came from — and `story_md` is accepted as the longer form of the
    same statement. Both empty is the refusal.

    Rows missing either number are skipped rather than failed: a null rank or a
    null fit is a different finding, and inventing an inversion out of two
    nulls would be a derived value that is neither computed nor null.
    """
    if page != "platform":
        return []
    body = ((payload.get("sections") or {}).get("platform_story") or {})
    body = body.get("data") if isinstance(body.get("data"), dict) else body
    rows = (body or {}).get("platforms")
    if not isinstance(rows, list):
        return []

    def num(v):
        try:
            return float(v) if v is not None and v != "" else None
        except (TypeError, ValueError):
            return None

    scored = [(i, r, num(r.get("rank")), num(r.get("fit_score")))
              for i, r in enumerate(rows) if isinstance(r, dict)]
    scored = [t for t in scored if t[2] is not None and t[3] is not None]

    out = []
    for i, row, rank, fit in scored:
        above = [(o_rank, o_fit, o_row.get("platform"))
                 for _, o_row, o_rank, o_fit in scored
                 if o_rank < rank and o_fit < fit]
        if not above:
            continue
        basis = (row.get("fit_basis") or "") or (row.get("story_md") or "")
        if str(basis).strip():
            continue
        o_rank, o_fit, o_name = sorted(above)[0]
        out.append(_reason(
            "AG-09", "platform_story",
            f"platform_story.platforms[{i}].fit_basis",
            f"{row.get('platform')!r} is ranked {rank:g} with fit_score "
            f"{fit:g}, below {o_name!r} at rank {o_rank:g} with fit_score "
            f"{o_fit:g} — a lower rank on a higher score. That can be right "
            "when the order is a dependency sequence rather than a sort, but "
            "the row has to say so: fit_basis and story_md are both empty, so "
            "the page can only show two numbers that contradict each other."))
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


#: Sections whose numbers are FINANCIAL DISCLOSURES rather than assessment
#: outputs. A maturity score is produced by the assessment and belongs to us;
#: an assets-under-management figure belongs to the filer, and the only
#: honest way to carry it is to quote the sentence that states it.
_QUOTED_FIGURE_PATHS = {
    "financial_series": ("series", "value"),
}

_DIGITS = re.compile(r"\d")


def _mantissa(x) -> str:
    """The significant digits of a number, scale and separators removed.

    1687.8 · "1,687.8" · "$1,687.8 billion"  ->  "16878"
    1890   · "1.89 trillion"                 ->  "189"

    WHY SCALE IS ALLOWED AND ARITHMETIC IS NOT. Writing a stated $1.89
    trillion as 1890 USD billions changes the representation of a number the
    source states; the digits are the filer's. Computing $1,444.5 billion by
    subtracting $162.1 billion from $1,606.6 billion produces a number that
    appears in no sentence anywhere, and its digits are ours. This function
    is what separates the two, and it is why the gate compares mantissas
    rather than strings or floats.
    """
    s = str(x if x is not None else "")
    digits = "".join(_DIGITS.findall(s))
    return digits.strip("0") or ("0" if digits else "")


def _check_financial_figures_are_quoted(found, cited_by, payload) -> list:
    """CG-38 — a financial figure is quoted from a filing, never computed.

    Owner, 2026-08-22: "Have a clear prohibition against derived figures,
    figures should verbatim come from 10-K filings or company financials."

    The rule this makes enforceable had, until now, only ever been a habit.
    Building the T. Rowe Price five-year trajectory, the FY2023 figure was
    available two ways: the FY2023 Form 10-K states "$1,444.5 billion", and
    the FY2024 filing states "$1,606.6 billion, an increase of $162.1 billion
    from the end of 2023", from which the same number falls out by
    subtraction. Both routes give 1444.5. Only one of them is a disclosure.

    A derived figure is undetectable downstream: it is the right number, it
    carries a real evidence id, the id resolves, belongs to the entity, and
    its excerpt is a genuine verbatim span from a genuine filing. Every
    existing check passes. What is false is only the relationship between the
    number and the sentence — and nothing looked at that.

    So this looks at exactly that: the figure's significant digits must occur
    in the excerpt of the row it cites. Scale is not the test (see
    `_mantissa`); arithmetic is.
    """
    if not isinstance(payload, dict):
        return []
    by_id = {}
    for row in found:
        for key in ("e_id", "stored_id"):
            if row.get(key):
                by_id[row[key]] = row
    out = []
    for section, (list_key, value_key) in _QUOTED_FIGURE_PATHS.items():
        body = payload.get(section)
        if not isinstance(body, dict):
            continue
        for i, item in enumerate(body.get(list_key) or []):
            if not isinstance(item, dict):
                continue
            value = item.get(value_key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            e_id = item.get("source_e_id")
            row = by_id.get(e_id)
            if row is None:
                continue          # ET-01/ET-02 own an unresolvable id
            want = _mantissa(value)
            excerpt = row.get("excerpt") or ""
            if not want or want in _mantissa(excerpt):
                continue
            # A cheaper, more forgiving second look: the digits may be split
            # across the excerpt by separators the mantissa of the WHOLE
            # excerpt already removes, so also try each number in it alone.
            if any(want == _mantissa(tok)
                   for tok in re.findall(r"[\d][\d,.]*", excerpt)):
                continue
            out.append(_reason(
                "CG-38", section, f"{section}.{list_key}[{i}].{value_key}",
                f"{value} does not appear in the span this point cites "
                f"({e_id}). A financial figure is a DISCLOSURE: it is carried "
                f"by quoting the sentence that states it, never by computing "
                f"it from one that states something else. The commonest route "
                f"in is a neighbouring year's comparative — a filing saying "
                f"'X, an increase of Y from last year' gives last year by "
                f"subtraction, and the result appears in no sentence anywhere. "
                f"Cite the filing that states {value} itself. Rescaling a "
                f"stated figure between units is fine and passes this check; "
                f"arithmetic on two figures is not."))
    return out


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


# ── ET-09 · another client's name in this client's prose ─────────────
#
# ET-01 halts a CITATION that resolves to another institution's row. It sees
# nothing when the contamination never cites: a sentence, a leadership name,
# a tech row or a why-now card that simply names a different client. That is
# the route that actually bit this build — MEM-0023, where two concurrent
# sessions shared a scratchpad path and a producer analysed another client's
# bundle for twenty-two minutes. Every id it cited would have been that other
# client's, so ET-01 would have caught THAT; but the prose written from the
# same read is invisible to every gate in this connector.
#
# The corpus knows who its clients are, so the check is a lookup rather than
# a heuristic. Measured over the 113 distinct entity names in the intake tree
# on 2026-08-14: 111 carry two or more words, ZERO are composed entirely of
# generic banking tokens (bank, first, national, credit, union, trust …), and
# exactly one is shorter than eight characters. So a floor of "two words and
# eight characters, or one word of ten" matches 112 of 113 by their own
# distinctiveness and cannot fire on a phrase like "the first national bank".
#
# Peers are excluded from server-side truth — `peer_scores.peer_name` for
# THIS run — never from the payload's own claims, because a payload that
# names its own exculpation is not evidence.
_ET09_MIN_MULTI, _ET09_MIN_SINGLE = 8, 10

# A name must carry at least one word that is not sector furniture. The
# length floor alone is not enough: "First National Bank" is three words and
# nineteen characters and matches the sentence "the first national bank in
# the state", which appears in ordinary prose on any run. Zero of the
# corpus's 113 names are composed ENTIRELY of these, so requiring one
# distinctive word costs no real coverage — it was measured before it was
# written, and the test that pins it fired on the first implementation,
# which had the measurement in its comment and not in its code.
# Kept deliberately SMALL. A first draft included capital, farm, global and
# partners, which reads sensible and dropped three real clients out of
# coverage — their names are built entirely from sector words and are still
# perfectly distinctive as phrases. The test is not "is this word generic"
# but "does this PHRASE occur in ordinary prose": "the first national bank
# in the state" does, "global federal credit union" does not. Re-measured
# after tightening: 112 of the corpus's 113 names covered, the one gap being
# a five-character acronym that the length floor excludes anyway.
_ET09_GENERIC = frozenset((
    "the", "of", "and", "a", "an", "for", "at", "in", "co", "inc", "llc",
    "ltd", "limited", "corp", "corporation", "company", "group", "holdings",
    "holding", "services", "service", "systems", "association",
    "bank", "banking", "banks", "credit", "union", "federal", "national",
    "state", "community", "savings", "mutual", "financial", "finance",
    "trust", "insurance", "first", "american", "america", "us", "usa"))


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _foreign_entity_names(conn, run_id) -> dict:
    """{compiled pattern: legal name} for every OTHER client in the corpus."""
    cur = conn.cursor()
    cur.execute(
        """SELECT e.legal_name, e.trading_name
             FROM entities e
            WHERE e.id <> (SELECT entity_id FROM runs WHERE id = %s)""",
        (run_id,))
    candidates = {n for row in cur.fetchall() for n in row if n}
    cur.execute("SELECT DISTINCT peer_name FROM peer_scores WHERE run_id = %s",
                (run_id,))
    peers = {_norm_name(r[0]) for r in cur.fetchall() if r[0]}
    out = {}
    for name in candidates:
        norm = _norm_name(name)
        if not norm or norm in peers:
            continue
        words = norm.split()
        long_enough = (len(words) >= 2 and len(norm) >= _ET09_MIN_MULTI) or \
                      (len(words) == 1 and len(norm) >= _ET09_MIN_SINGLE)
        if not long_enough:
            continue
        # At least one word that is not sector furniture, or the pattern
        # matches ordinary prose rather than an institution.
        if all(w in _ET09_GENERIC for w in words):
            continue
        out[re.compile(r"\b" + r"\W+".join(map(re.escape, words)) + r"\b",
                       re.I)] = name
    return out


def _check_foreign_entity_prose(conn, run_id, payload) -> list:
    try:
        patterns = _foreign_entity_names(conn, run_id)
    except Exception:                                          # noqa: BLE001
        # A gate that cannot read its corpus must not silently pass the
        # payload it was meant to check. It also must not block a run on a
        # transient read, so it says nothing here and the reason is that
        # ET-01 still covers the cited route.
        return []
    if not patterns:
        return []
    out, seen = [], set()
    for section, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in _walk(body, section):
            for key, value in obj.items():
                if not isinstance(value, str) or len(value) < 4:
                    continue
                for pat, name in patterns.items():
                    if (section, name) in seen or not pat.search(value):
                        continue
                    seen.add((section, name))
                    out.append(_reason(
                        "ET-09", section, f"{path}.{key}",
                        f"names {name!r} — another client in this corpus, and "
                        "not a peer recorded for this run. STOP: this is "
                        "contamination, the same class as a foreign citation "
                        "and invisible to ET-01 because the sentence cites "
                        "nothing. Confirm which client's material you are "
                        "reading (assert the bundle's run_id and display_id), "
                        "quarantine and escalate — do not delete the sentence "
                        "and carry on, because the reasoning that produced it "
                        "drifted onto the wrong entity and everything else it "
                        "produced is suspect"))
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
    # The index itself is the inventory: a row's presence in the listing
    # makes no capability claim — the claims live in the sections that cite
    # the row, and THOSE citations still owe links or a stated reason. The
    # omission was found live: five registry/telemetry rows blocked the
    # index while its own serving table (the ingested evidence_index) binds
    # neither r_layer nor empty_state, so the gate's prescribed repair was
    # a field CG-04 refuses — a gate demanding what the shape forbids.
    ("heatmap", "evidence"): "inventory of the corpus, not a claim inside it",
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
# `affects` is the fourth spelling and it was invisible here. Measured
# 2026-08-18 on a promoted run: an adversarial pass injected P1C1.3.BK1 (a
# retail-bank variant cell) and P1C9.9.9 (no such cell in any catalogue) into
# insights.cards[0].affects, and BOTH the connector's pass 2 and the local
# checker returned zero blocking; the same two ids in
# heatmap.focus_areas[*].involved_subcap_ids produced two CG-14 refusals in
# each. The field carries 32 cell ids on that run and every one of them was
# correct, which is the point: its green check could not have been red, so it
# was never evidence about anything. ET-05 was blind to it on the same route.
_CELL_KEYS = ("capability_ids", "subcaps", "affects")


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
    subcap_scores, pillar/category from the workbook's STATED grains, and —
    only where the workbook states none — the mean of the run's own scored
    cells at that grain.

    The computed fallback exists because CG-07's rejection branch refuses a
    quoted figure whose grain "cannot be checked". On a run whose ingestion
    carried no pillar or category rollup row, that was true of every pillar
    figure, so the four bars on the first card of the first page could carry
    no number at all — while the same run served all 705 cells the mean is
    taken over, and `bundle.rollups.capabilities` already publishes exactly
    this arithmetic one grain lower ("capabilities are computed and say so").
    Deriving the mean here removes the premise rather than the gate: the
    figure becomes checkable, and a producer quoting a DIFFERENT weighting
    (an assessment report's own pillar table, say) is now caught at 0.05
    instead of passing unexamined because nothing could be compared.

    A STATED grain always wins. A struck workbook figure is the source of
    truth wherever one exists, and is never overridden by a derived one.
    """
    cur = conn.cursor()
    served = {}
    cells: dict[str, list] = {}
    cur.execute("SELECT subcap_id, score FROM subcap_scores WHERE run_id = %s",
                (run_id,))
    for sid, score in cur.fetchall():
        if score is None:
            continue
        served[sid] = float(score)
        # P1C2.7.3 -> category P1C2 -> pillar P1. Grains are read off the id
        # rather than a join: the id IS the taxonomy path.
        head = sid.split(".", 1)[0]
        if _CATEGORY_RE.match(head):
            cells.setdefault(head, []).append(float(score))
            cells.setdefault(head[:head.index("C")], []).append(float(score))
    cur.execute("SELECT payload FROM run_manifest WHERE run_id = %s", (run_id,))
    payload = (cur.fetchone() or [None])[0] or {}
    grains = payload.get("workbook_grains") or {}
    for gid, scores in cells.items():
        served[gid] = sum(scores) / len(scores)
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


def _check_platform_fit_is_the_engine_s(conn, run_id, page, payload) -> list:
    """CG-30 — the fit on the card is the fit the engine computed.

    THE DEFECT, reported 2026-08-19: "Platform fit scores calculation is very
    different from Baxter's." There were four definitions of one number. The
    Surface Spec's, engine v2's (which the Spec names and mis-transcribes),
    Baxter's — 76.5, whose own basis says it was read from the OPPORTUNITY
    tile — and Logix's, which was null on all five.

    The engine exists now and the contract's rule applies: "read, never
    recomputed — the agent EXPLAINS it, never recomputes or re-ranks it."
    This is what makes that enforceable. The producer's own inputs
    (`l3_area`, `alignment`, `readiness`) are fed back through the engine and
    the answer must match what it shipped, within the charter's 0.05 grain
    tolerance.

    Two absences are refused as well as a disagreement:
      · a card with no `fit_score` where the engine CAN score it — five nulls
        is what the reported client shipped, and a page that cannot rank is
        not a ranking. A null is honest in exactly one case: the engine's own
        state for the candidate is unrankable (TOO_NARROW, OUT_OF_VERTICAL),
        and the card carries that state so the reader sees why. A 0.0 there
        would be a sentinel that looks like data (invariant 9);
      · a card whose `rank` disagrees with the engine's ordering, because a
        correct number in the wrong order is the same page.

    `depends_on` is fed back through with the other producer inputs. The
    engine refuses to rank a card above something it depends on; a gate that
    dropped the field would refuse a producer for shipping the engine's own
    ordering — the workload-above-foundation defect, reintroduced by the
    check meant to prevent it.
    """
    if page != "platform":
        return []
    body = (payload or {}).get("platform_story")
    if not isinstance(body, dict):
        return []
    rows = body.get("platforms")
    if not isinstance(rows, list) or not rows:
        return []

    candidates, out = [], []
    for r in rows:
        if not isinstance(r, dict):
            continue
        candidates.append({"platform": r.get("platform"),
                           "l3_area": r.get("l3_area"),
                           "alignment": r.get("alignment"),
                           "alignment_quote": r.get("alignment_quote"),
                           "readiness": r.get("readiness") or "green",
                           "depends_on": r.get("depends_on") or []})

    try:
        from . import fit as fit_mod
        computed = fit_mod.platform_fit(conn, run_id, candidates)
    except Exception as exc:                        # noqa: BLE001
        # A gate that cannot run says so rather than passing: this file's
        # whole subject is checks that report clean because they never ran.
        return [_reason("CG-30", "platform_story", "platform.platform_story",
                        f"the fit engine could not be run for this payload "
                        f"({str(exc)[:120]}), so the scores on these cards are "
                        f"unchecked. That is a refusal, not a pass.")]

    by_name = {str(p.get("platform")): p for p in computed.get("platforms", [])}
    unrankable = {"TOO_NARROW", "OUT_OF_VERTICAL"}
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        got = by_name.get(str(r.get("platform")))
        if r.get("fit_score") is None:
            if got is None or got.get("state") not in unrankable:
                out.append(_reason(
                    "CG-30", "platform_story",
                    f"platform.platform_story.platforms[{i}].fit_score",
                    "no fit score on this card, and the engine can score it"
                    + ("" if got is None else
                       f" ({got['fit_score']}, state {got.get('state')})")
                    + ". Call `get_platform_fit` and read the number it "
                    "returns; a platform page whose cards cannot be ranked "
                    "is not a ranking."))
            elif str(r.get("state") or "") != str(got.get("state")):
                out.append(_reason(
                    "CG-30", "platform_story",
                    f"platform.platform_story.platforms[{i}].state",
                    f"fit_score is null, which is honest only with the "
                    f"engine's own reason on the card: state "
                    f"{got.get('state')!r}, not {r.get('state')!r}. A null "
                    "with no stated reason reads as a rendering defect, and "
                    "a 0.0 would read as the worst score on the page."))
            continue
        if got is None:
            continue
        if abs(float(r["fit_score"]) - float(got["fit_score"])) > 0.05:
            out.append(_reason(
                "CG-30", "platform_story",
                f"platform.platform_story.platforms[{i}].fit_score",
                f"the card says {r['fit_score']} and the engine computes "
                f"{got['fit_score']} from the same inputs. Read the engine's "
                f"number; explaining it is your job, recomputing it is not. "
                f"{got['fit_basis']}"))
        elif r.get("rank") is not None and int(r["rank"]) != int(got["rank"]):
            out.append(_reason(
                "CG-30", "platform_story",
                f"platform.platform_story.platforms[{i}].rank",
                f"ranked {r['rank']} on the card, {got['rank']} by the engine. "
                "A correct score in the wrong order is the same defect: the "
                "reader takes the top card as the recommendation."))
    return out[:6]




# The engine's four factor names, and every name a pre-engine tile ever
# rendered. The blacklist is matched against factor NAMES only: "business
# impact analysis" is honest prose about the BIA capability, and a sweep of
# both promoted corpora confirmed every prose occurrence is exactly that.
_ENGINE_FACTORS = frozenset(("Addressable opportunity", "Catalogue interconnect",
                             "Greenfield family", "Strategic alignment"))
_LEGACY_FACTORS = frozenset((
    "business_impact", "risk_exposure", "competitive_gap", "effort_inverse",
    "quick_win", "trend_momentum", "business impact", "risk exposure",
    "competitive gap", "effort inverse", "quick win", "trend momentum",
    "Addressable gap depth", "Sub-vertical relevance",
    "Substrate already in place"))


def _check_opportunity_tiles_are_the_engine_s(conn, run_id, page,
                                              payload) -> list:
    """CG-31 — the tile is the same number as the card, from the same engine.

    THE DEFECT, reported twice on 2026-08-19: the round-6 report was
    "Platform fit scores calculation is very different from Baxter's", and
    after the cards were pinned to the shared engine (CG-30) the report came
    back as "Platform scores still reflect different composite factors" —
    because the OVERVIEW tiles carried their own per-client factor systems
    (Baxter a six-factor 76.5, Logix a three-factor 67.0) and no gate read
    them. The cards were fixed by hand and nothing stopped the next
    submission regressing.

    Two rules, both cheap and both refusals:
      · a tile's factor names are the engine's four — a legacy name is
        refused BY NAME, so the six-factor and three-factor vocabularies
        cannot re-enter through this section;
      · where the platform page is staged, a tile's composite and rank equal
        its card's fit_score and rank (0.05 grain). CG-30 pins the card to
        the engine, so the tile is transitively the engine's — one number,
        both pages, one code path. A tile whose platform has no card is a
        scored recommendation with no story and is refused too.
    A platform page not yet staged is nothing to compare; the promote-time
    re-gate makes the comparison when both exist.
    """
    if page != "overview":
        return []
    body = (payload or {}).get("opportunity")
    if not isinstance(body, dict):
        return []
    tiles = body.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        return []

    out = []
    for i, t in enumerate(tiles):
        if not isinstance(t, dict):
            continue
        names = [str(f.get("name")) for f in (t.get("factors") or [])
                 if isinstance(f, dict)]
        legacy = sorted(set(names) & _LEGACY_FACTORS)
        if legacy:
            out.append(_reason(
                "CG-31", "opportunity",
                f"overview.opportunity.tiles[{i}].factors",
                f"factor name(s) {', '.join(legacy)} are a pre-engine "
                "vocabulary. The tile reads composite, factors, rank and "
                "relevance from `get_platform_fit`; its factor names are "
                "exactly: " + ", ".join(sorted(_ENGINE_FACTORS)) + ". Two "
                "clients rendered two factor systems for one number — that "
                "is the defect this gate exists to refuse."))
            continue
        if set(names) != set(_ENGINE_FACTORS):
            out.append(_reason(
                "CG-31", "opportunity",
                f"overview.opportunity.tiles[{i}].factors",
                f"factor names {names!r} are not the engine's four "
                f"({', '.join(sorted(_ENGINE_FACTORS))}). Read the tile's "
                "breakdown from `get_platform_fit` — the breakdown a reader "
                "opens must be the arithmetic that produced the headline."))
    if len(out) >= 6:
        return out[:6]

    sibling = _live_submission(conn, run_id, "platform")
    cards = ((sibling.get("platform_story") or {}).get("platforms")
             if isinstance(sibling, dict) else None)
    if not isinstance(cards, list) or not cards:
        return out[:6]
    by_name = {str(c.get("platform")): c for c in cards if isinstance(c, dict)}
    for i, t in enumerate(tiles):
        if not isinstance(t, dict):
            continue
        card = by_name.get(str(t.get("platform")))
        if card is None:
            out.append(_reason(
                "CG-31", "opportunity",
                f"overview.opportunity.tiles[{i}].platform",
                f"tile {t.get('platform')!r} has no card on the staged "
                "platform page — a scored recommendation with no story. "
                "Card it, or drop the tile."))
            continue
        fit = card.get("fit_score")
        comp = t.get("composite")
        if fit is None or comp is None:
            if fit != comp:
                out.append(_reason(
                    "CG-31", "opportunity",
                    f"overview.opportunity.tiles[{i}].composite",
                    f"tile composite {comp!r} against card fit {fit!r} — "
                    "an unrankable platform is null on BOTH pages with the "
                    "engine's state, never null on one and scored on the "
                    "other."))
            continue
        if abs(float(comp) - float(fit)) > 0.05:
            out.append(_reason(
                "CG-31", "opportunity",
                f"overview.opportunity.tiles[{i}].composite",
                f"tile composite {comp} against card fit {fit} for "
                f"{t.get('platform')!r}. One platform, one number: the tile "
                "reads the same engine row the card reads (CG-30 pins the "
                "card, this pins the tile to it)."))
        elif (t.get("rank") is not None and card.get("rank") is not None
              and int(t["rank"]) != int(card["rank"])):
            out.append(_reason(
                "CG-31", "opportunity",
                f"overview.opportunity.tiles[{i}].rank",
                f"tile rank {t['rank']} against card rank {card['rank']} "
                f"for {t.get('platform')!r} — the reader takes tile order "
                "as the recommendation, so the two pages must agree."))
    return out[:6]



def _check_recommendations_reach_the_platform_page(conn, run_id, page, payload):
    """CG-39 — a run whose analyst wrote recommendations must serve some.

    Measured 2026-08-23 on a promoted run. get_report_bundle returned SEVEN
    recommendations — integrate FactorSoft with Salesforce, deliver as managed
    services, operationalise Pardot — each with a category, an evidence_basis
    of real e_ids and a named offering. The promoted platform page served four
    tiles reading "5 cells · 0 recs", one of them Marketing Cloud Account
    Engagement (Pardot), which is the subject of the third recommendation.

    Nothing was wrong with the analysis. The write path had no read path, and
    a client saw four cards recommending nothing.

    The check is deliberately weak — ONE recommendation served clears it. It
    is not trying to judge the mapping, only to catch the case where the whole
    set was dropped, which is the one that reached a client.
    """
    if page != "platform" or not isinstance(payload, dict):
        return []
    tiles = ((payload.get("platform_story") or {}).get("platforms")
             if isinstance(payload.get("platform_story"), dict) else None)
    if not isinstance(tiles, list) or not tiles:
        return []                       # no tiles: CG-30 owns that case
    served = ((payload.get("recommendations") or {}).get("recommendations")
              if isinstance(payload.get("recommendations"), dict) else None)
    if isinstance(served, list) and served:
        return []                       # something reached the page
    try:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM recommendations_raw
                        WHERE run_id = %s""", (run_id,))
        available = int((cur.fetchone() or [0])[0])
    except Exception:                                        # noqa: BLE001
        # Unreadable: this check did not run. It must not manufacture a
        # verdict either way — that is the defect class it belongs to.
        return []
    if not available:
        return []                       # nothing to drop; an honest absence
    return [_reason(
        "CG-39", "recommendations", "platform.recommendations.recommendations",
        f"the run carries {available} recommendation(s) in its bundle and "
        f"this payload serves none, while platform_story shows "
        f"{len(tiles)} tile(s) — every card will read '0 recs'. Read them "
        f"with get_report_bundle(run_id)['recommendations'] and serve the "
        f"ones this page supports; if a recommendation genuinely maps to no "
        f"tile, serve it anyway with its own l3_area, because the analyst "
        f"wrote it about this client. Exactly one served clears this gate.")]


#: Peer arithmetic is derived, so it is checked rather than trusted. The value
#: matches the contract's grain tolerance: two figures rounded for display
#: agree to within a twentieth, and anything wider is a different subtraction.
PEER_DELTA_TOLERANCE = 0.05


def _num(v):
    """A real number, or None. `True` is not a score."""
    return float(v) if isinstance(v, (int, float)) \
        and not isinstance(v, bool) else None


def _pillar_rows(body):
    """The overview score strip's pillar rows."""
    return [p for p in ((body or {}).get("pillars") or [])
            if isinstance(p, dict)] if isinstance(body, dict) else []


def _heatmap_peer_scores(body):
    """Every peer figure the heatmap's focus areas actually carry. A null
    peer_score is not a peer figure — it is the row saying it has none."""
    if not isinstance(body, dict):
        return []
    return [n for row in (body.get("focus_areas") or [])
            if isinstance(row, dict)
            for n in [_num(row.get("peer_score"))] if n is not None]


def _check_peer_scores_cascade(conn, run_id, page, payload) -> list:
    """CG-44 — a peer figure the assessment holds reaches the overview strip.

    Owner, 2026-08-23: "For Gulf and Axos, the overview has no peer scores
    which have not been cascaded from the heatmaps."

    The heatmap's focus areas carry `peer_score` per area. The overview's
    pillar strip is where a reader forms the comparison, and it was serving
    the entity's own bar alone. Nothing was wrong with either surface in
    isolation, which is why no gate saw it: the failure is that a figure the
    assessment already holds stopped one page short of the page that needed
    it. Same shape as CG-39 (recommendations written, never served) and CG-43
    (one dataset, two drifting projections).

    TWO HALVES, and the second is the one that keeps this honest:

    1. CASCADE. If the heatmap carries any peer figure at all, the strip may
       not be silent about peers. It may still carry none — the workbook's
       area-level peers need not roll up to a pillar — but then it says so,
       in the same disclosure discipline the rest of the payload keeps.

    2. ARITHMETIC. Where a row states both its own score and a peer median,
       the delta is DERIVED and must be the subtraction, and `direction` must
       agree with its sign. Invariant 9: derived values are computed, never a
       sentinel and never a default that looks like data. A restated delta
       that drifts from its own operands is the adjacent-column defect
       wearing a comparison's clothes.

    GULF PASSES ON THE FIRST HALF BY BEING HONEST. Its focus areas carry
    `peer_score: null` throughout, because the workbook states no area-level
    cohort; its strip still carries pillar medians read from the workbook's
    own Pillar_Summary sheet, with `peer_n: null` and a disclosure saying the
    cohort size was not stated rather than guessing one. That is the right
    answer in both directions and the gate must not punish it.
    """
    if page != "overview" or not isinstance(payload, dict):
        return []
    rows = _pillar_rows(payload.get("scores"))
    if not rows:
        return []                       # no strip: other gates own that

    out = []
    with_peer = [r for r in rows if _num(r.get("peer_median")) is not None]
    if not with_peer:
        sibling = _live_submission(conn, run_id, "heatmap")
        peers = _heatmap_peer_scores(
            (sibling or {}).get("focus_areas") if isinstance(sibling, dict)
            else None)
        # Silence is only a finding when the run demonstrably HAS peer data.
        # An unstaged sibling proves nothing; promotion re-gates every page.
        if peers and not _says_it_searched(payload.get("scores")):
            out.append(_reason(
                "CG-44", "scores", "overview.scores.pillars[].peer_median",
                f"the heatmap carries {len(peers)} focus area(s) with a peer "
                f"score (median {sorted(peers)[len(peers) // 2]:.2f}) and not "
                f"one pillar row on the overview strip carries a peer figure. "
                f"The comparison a reader forms is formed here, on the strip, "
                f"and this run already holds the numbers to form it. Cascade "
                f"them, or state on the section why area-level peers do not "
                f"roll up to a pillar for this assessment — an absence that "
                f"names its reason is fine, an absence that says nothing is "
                f"indistinguishable from a figure that was dropped."))

    for i, r in enumerate(rows):
        pid = r.get("pillar_id") or r.get("pillar") or f"[{i}]"
        score, peer = _num(r.get("score")), _num(r.get("peer_median"))
        if score is None or peer is None:
            continue
        want = round(score - peer, 4)
        delta = _num(r.get("delta"))
        if delta is None:
            out.append(_reason(
                "CG-44", "scores", f"overview.scores.pillars[{i}].delta",
                f"{pid} states its own score ({score}) and a peer median "
                f"({peer}) and leaves the delta empty. The subtraction is "
                f"available — it is {want:+.2f}. A derived value with both "
                f"operands in hand is computed, never left null; null here "
                f"reads to a client as 'not comparable' when the comparison "
                f"is one line of arithmetic."))
            continue
        if abs(delta - want) > PEER_DELTA_TOLERANCE:
            out.append(_reason(
                "CG-44", "scores", f"overview.scores.pillars[{i}].delta",
                f"{pid} states a delta of {delta} against {score} - {peer} = "
                f"{want:+.2f} (Δ {abs(delta - want):.2f} > "
                f"{PEER_DELTA_TOLERANCE}). The delta is derived from the two "
                f"figures beside it; when it disagrees with them, one of the "
                f"three came from a different row. Fix the pairing, not the "
                f"number."))
            continue
        got = str(r.get("direction") or "").strip().lower()
        if not got:
            continue                    # optional field; the delta carries it
        want_dir = ("at" if abs(want) <= PEER_DELTA_TOLERANCE
                    else "below" if want < 0 else "above")
        if got not in (want_dir, {"at": "level"}.get(want_dir, want_dir)):
            out.append(_reason(
                "CG-44", "scores", f"overview.scores.pillars[{i}].direction",
                f"{pid} reads '{got}' against a delta of {want:+.2f}, which "
                f"is '{want_dir}'. The word and the number are the same fact "
                f"stated twice, and a reader who takes the word away from "
                f"this card takes away the opposite of what the bar shows."))
    return out[:6]


#: The reach a card has to state, in the order the surfaces carry it. The
#: platform card names its estate structurally; the overview tile carries the
#: same account as prose, because a tile has no room for a table.
_REACH_KEYS = ("estate_reach", "their_stack_context", "current_estate")

#: What "we could not see how much of it is used" has to look like to count.
#: Naming the platform is not the same as sizing the client's hold on it.
_REACH_MIN_CHARS = 120


def _reach_statement(card) -> str:
    """Whatever the card says about the estate it is proposing into."""
    if not isinstance(card, dict):
        return ""
    for key in _REACH_KEYS:
        v = card.get(key)
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # a structured reach: the derivation is the part that is checkable
            return " ".join(str(v.get(k) or "") for k in
                            ("derivation", "why_this_is_established",
                             "products_holding_this_layer", "utilization"))
    return ""


def _check_cards_state_their_reach(conn, run_id, page, payload) -> list:
    """CG-45 — a card proposing a platform says how far the client already
    reaches into it.

    Owner, 2026-08-23: "The platform still ignores that Gulf has a lot of the
    platform proposed. No work has been done to infer utilization."

    Both halves of that sentence are one defect. Gulf licenses Salesforce and
    Pardot already — its own intake brief asks for help ON THE EXISTING
    INSTANCE — and four cards proposed the Salesforce family as though the
    estate were empty. A card that has not looked at what the client holds is
    not a recommendation, it is a catalogue page.

    WHAT THIS GATE WILL AND WILL NOT ACCEPT. It cannot check whether the
    reach is *right* — no gate can. It checks that the card ANSWERED, with
    enough text to carry a derivation. `_REACH_MIN_CHARS` is deliberately low
    and deliberately non-zero: naming the platform again is not an answer,
    and a sentence is.

    AND IT MUST NOT PUSH ANYONE INTO INVENTING UTILIZATION. Login counts,
    seat counts and query volumes are not visible from outside, and the right
    answer on both these runs says exactly that: "nothing this run can reach
    shows how much of the licence is actually used ... and no claim is made
    about them". That is a complete answer and it passes. What fails is a
    card that never raises the question — because a reader cannot tell that
    from a card whose author looked and found the estate empty.
    """
    if not isinstance(payload, dict):
        return []
    if page == "platform":
        cards = ((payload.get("platform_story") or {}).get("platforms")
                 if isinstance(payload.get("platform_story"), dict) else None)
        sect, base = "platform_story", "platform.platform_story.platforms"
        name_of = (lambda c: c.get("platform") or c.get("name"))
    elif page == "overview":
        cards = ((payload.get("opportunity") or {}).get("tiles")
                 if isinstance(payload.get("opportunity"), dict) else None)
        sect, base = "opportunity", "overview.opportunity.tiles"
        name_of = (lambda c: c.get("platform") or c.get("headline"))
    else:
        return []
    if not isinstance(cards, list):
        return []

    out = []
    for i, card in enumerate(cards):
        if not isinstance(card, dict):
            continue
        said = _reach_statement(card).strip()
        if len(said) >= _REACH_MIN_CHARS:
            continue
        label = str(name_of(card) or f"card {i}")[:70]
        out.append(_reason(
            "CG-45", sect, f"{base}[{i}].estate_reach",
            f"'{label}' proposes a platform without saying how far this "
            f"client's existing estate already reaches into it"
            + (f" (it carries {len(said)} characters where a derivation "
               f"needs {_REACH_MIN_CHARS})" if said else "")
            + ". The client's own register is in this run: say what it "
            "already holds in this area, how that was established, and — "
            "separately — what could not be seen about how much of it is "
            "actually used. 'Nothing available here shows utilization, and "
            "none is claimed' is a complete answer. Silence is not: a card "
            "that never raises the question reads identically to one whose "
            "author looked and found the estate empty, and this client "
            "already licenses part of what is being proposed."))
    return out[:6]


#: Subjects that belong to the ASSESSMENT, not to the institution. Each is a
#: phrase a producer actually filed on an issue register during this build.
_ASSESSMENT_SUBJECT = re.compile(
    r"\b(evidence (?:register|index|coverage|base|discipline)"
    r"|uncited|citation coverage|source concentration|single[- ]source"
    r"|scoring workbook|the workbook|this (?:run|assessment)'s own"
    r"|assessment'?s? own|register completeness|qa[_ ]verdict"
    r"|scoring methodolog|grain tolerance|coverage of the register)\b",
    re.I)

#: What an issue IS, in the owner's words: "enforcement actions; breaches;
#: news that may affect the entity's scores etc."
_ENTITY_MATTER = re.compile(
    r"\b(enforcement|consent order|cease and desist|civil money penalt"
    r"|breach|incident|data loss|ransomware|outage|lawsuit|litigation"
    r"|settlement|fine|penalt|investigation|subpoena|recall|sanction"
    r"|regulator|examination finding|matter requiring attention|MRA"
    r"|class action|complaint|indictment|violation|deficienc"
    # Added 2026-08-23 from the T. Rowe Price register, which carries the
    # arbitration and supervisory vocabulary the first list missed: a FINRA
    # customer-dispute award is an entity matter by any reading and matched
    # none of the words above.
    r"|arbitration|award|censure|disciplinar|FINRA|SEC|OCC|FDIC|NCUA|FTC"
    r"|BrokerCheck|dispute|claim|exposure|fiduciary|misconduct"
    r"|restitution|disgorgement|suspension|revocation|bar(?:red)?)\b", re.I)


#: WHAT the row is about. The subject test reads only these.
_ISSUE_SUBJECT_KEYS = ("title", "summary", "description", "matter", "name")

#: WHY it is here and how it was handled. Read for the entity-matter test —
#: a real matter is often only named in full in the reasoning — but never for
#: the subject test.
#:
#: MEASURED ON T. ROWE PRICE, 2026-08-23, and this split is the repair. CG-46
#: refused three of its eleven rows on the phrase "the workbook", which in
#: every case sat in `rationale` describing how the row was SCORED:
#:
#:   · "The registered rows and the workbook's Issue Time Map disagree on the
#:      award years … so this row keeps the workbook's dates" — on a row
#:      about three FINRA customer arbitration awards.
#:   · "both board-oversight cells were scored under the workbook's Step 6
#:      conservative-default rule" — on a disclosure conflict between a 10-K
#:      and a proxy.
#:   · "the workbook applied its Step 6 conservative-default rule rather than
#:      picking a reading" — on an unresolved data-organization structure.
#:
#: All three are the institution's own matters and all three were refused.
#: A row may explain its own provenance in assessment vocabulary without
#: BEING about the assessment, and a gate that cannot tell those apart is
#: the reject-rather-than-triage failure wearing a gate's clothes.
_ISSUE_REASONING_KEYS = ("rationale", "detail", "impact", "provenance",
                         "opened_on_basis")


def _issue_text(issue, keys=None) -> str:
    keys = keys or (_ISSUE_SUBJECT_KEYS + _ISSUE_REASONING_KEYS)
    return " ".join(str(issue.get(k) or "") for k in keys) \
        if isinstance(issue, dict) else ""


def _check_issue_register_is_the_entitys(page, payload) -> list:
    """CG-46 — the issue register holds the institution's own matters.

    Owner, 2026-08-23: "Issue register for Gulf are not issues. Issues entail
    enforcement actions; breaches; news that may affect the entity's scores
    etc."

    What Gulf's register actually held was two findings about THE ASSESSMENT:
    26 of 61 evidence items uncited, and source concentration across 58 of 70
    cells. Both true, both useful, both filed in the one place a client reads
    as "what is wrong at this company". Each row stated "Cap: none" in its own
    text, so the producer had already noticed the mismatch and filed it here
    anyway — which is why this needs a gate and not a note.

    The contract agrees with the owner: C2 scopes the register to "the
    client's OWN open matters", and "an issue is only interesting here
    because it CAPS something".

    THE EMPTY REGISTER IS THE OTHER HALF, and it is the half that matters
    more often. Most institutions have no open enforcement matter, so most
    registers are empty and empty is the correct answer. But an empty
    register that names no search is indistinguishable from one nobody ran —
    the defect class this build keeps paying for. Gulf's repaired register
    names five databases searched, the one civil matter it found against the
    PARENT, and why that matter reaches no scored capability. That is a
    finding. A bare `issues: []` is not.
    """
    if page != "context" or not isinstance(payload, dict):
        return []
    body = payload.get("issue_register")
    if not isinstance(body, dict):
        return []
    issues = [i for i in (body.get("issues") or []) if isinstance(i, dict)]

    out = []
    for i, issue in enumerate(issues):
        # The SUBJECT is read from the naming fields only; the entity-matter
        # test reads everything, because a real matter is often named in full
        # only in the reasoning. See _ISSUE_REASONING_KEYS for the three live
        # rows that made this split necessary.
        subject = _issue_text(issue, _ISSUE_SUBJECT_KEYS)
        text = _issue_text(issue)
        hit = _ASSESSMENT_SUBJECT.search(subject)
        if hit and not _ENTITY_MATTER.search(text):
            out.append(_reason(
                "CG-46", "issue_register", f"context.issue_register.issues[{i}]",
                f"this row's subject is the assessment, not the institution — "
                f"it turns on '{hit.group(0)}'. The register is scoped to the "
                f"client's OWN open matters: enforcement actions, breaches, "
                f"conduct matters, news that bears on the scores. A finding "
                f"about how this run was evidenced is real and worth keeping, "
                f"and its home is the findings memory (record_finding) or the "
                f"safeguard disclosure, not the card a client reads as 'what "
                f"is wrong at my company'. Telling a client their own file is "
                f"an open matter against them is the failure here."))
    if issues:
        return out[:6]

    # Empty — which is usually correct, and has to prove it looked.
    if not _says_it_searched(body):
        out.append(_reason(
            "CG-46", "issue_register", "context.issue_register.empty_state",
            "the register is empty and names no search. Most institutions "
            "have no open enforcement matter, so empty is usually the right "
            "answer — but an empty register that cannot say where it looked "
            "is indistinguishable from one nobody ran, and a client reading "
            "'no issues' is entitled to know it is a result. Name the "
            "databases queried (the federal enforcement registers, court "
            "records, trade press), any matter found and set aside with the "
            "reason it does not reach a scored capability, and what would "
            "change the answer."))
    return out[:6]


#: (page, section) -> (the list field that IS the count, the nouns the prose
#: uses for its members). Explicit rather than inferred: a gate that guessed
#: which nouns name a section's items would fire on prose about the world.
COUNTED_SECTIONS = {
    ("overview", "why_now"): ("signals", ("signals", "signal", "dates")),
}

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                 "eleven": 11, "twelve": 12}

#: Adjectives that describe every member rather than selecting some of them.
#: ONLY these may stand between the number and the noun. "Three DATED
#: signals" counts the whole set because every signal is dated; "three
#: AUTOMATION products" counts a slice, and an allowlist is the only way to
#: tell those apart without parsing. Anything not on this list makes the
#: phrase a subset claim, and the gate stays silent.
_WHOLE_SET_ADJECTIVES = frozenset((
    "dated", "distinct", "separate", "such", "these", "those", "same",
    "remaining", "published", "named", "listed", "supporting"))

#: The section's own summary voice. Per-item prose is NOT read: an item that
#: says "this is second" is describing the recommended SEQUENCE, not its
#: array position, and conflating the two fired on axos-bank's WN-01 ("It
#: comes first because the standard has to exist before the estate it
#: governs arrives") on the very first measurement.
_PROSE_KEYS = ("narrative_thread", "synthesis", "storyline")


def _stated_counts(text, nouns):
    """Every "<number> [whole-set adjective] <noun>" the prose asserts, as
    (phrase, number).

    Guarded against everything measured that looks like a count and is not:
    a year ("each 2026 signal"), a partition's numerator ("three of the
    five"), and - the guard that matters most - a narrowing adjective, which
    makes the phrase a slice of the set rather than the set itself.
    """
    if not isinstance(text, str) or not text:
        return []
    alt = "|".join(sorted((re.escape(n) for n in nouns), key=len, reverse=True))
    pat = re.compile(
        r"\b(?P<num>" + "|".join(_NUMBER_WORDS) + r"|\d{1,3})\b"
        r"(?P<mid>(?:\s+[A-Za-z][\w-]*)?)\s+"
        r"(?P<noun>" + alt + r")\b", re.I)
    out = []
    for m in pat.finditer(text):
        raw = m.group("num").lower()
        mid = (m.group("mid") or "").strip().lower()
        if mid and mid not in _WHOLE_SET_ADJECTIVES:
            continue                    # a slice of the set, not the set
        n = _NUMBER_WORDS.get(raw) or (int(raw) if raw.isdigit() else None)
        if n is None or n > 900:                       # a year, not a count
            continue
        out.append((m.group(0).strip(), n))
    return out


def _check_prose_counts_what_is_served(page, payload) -> list:
    """CG-47 - why_now's summary prose counts the signals it serves.

    Invariant 8: counts are computed, never stored where a source of truth
    exists. A count written into a sentence IS a stored count, and it stops
    agreeing with its own list the moment an item is added or dropped.

    MEASURED ON BOTH PROMOTED RUNS, 2026-08-23, in both directions:

      - gulf-coast-business-credit lost WN-1 when ET-04 refused its evidence
        id (an ingested row carrying an empty excerpt, so the chip would have
        opened onto nothing). Two signals remained. The synthesis still read
        "the three signals describe a business ..." and still described the
        dropped one - "a decade-old platform decision now sits with a
        different vendor".

      - axos-bank gained WN-04 in a later repair. Four signals served, and
        the synthesis still read "Taken together the three dates describe".

    Removal and addition, same defect, neither caught, both promoted.

    WHY THIS GATE IS ONE SECTION WIDE, WHICH IS THE IMPORTANT PART. The first
    version covered thirteen sections and was run against every promoted page
    of both runs before shipping. It produced three findings on why_now, all
    real, and four on techstack and issue_register, ALL FALSE - every one of
    them on prose that was better than the rule judging it:

      - "three automation products, four source-control systems" - category
        slices of a 30-row register, not a claim that it holds three.
      - "Twenty-four rows where the promoted register carried four" - the
        four is a PRIOR state of a different register.
      - "This register tested the two matters it found ... Neither survives
        that test" - two candidates found and excluded, over a register that
        correctly serves zero.

    A gate that refuses writing like that is worse than the defect it
    catches, because it teaches producers to strip informative numbers out of
    their prose. So: one section, the section's own nouns, and only an
    adjective from _WHOLE_SET_ADJECTIVES may stand between number and noun.

    What it therefore does NOT catch, said plainly so nobody assumes
    otherwise: a wrong subset count, a count in any other section, and any
    count phrased around a narrowing adjective. Those remain the
    consolidator's cross-surface reconciliation to hold.
    """
    if not isinstance(payload, dict):
        return []
    out = []
    for section, body in payload.items():
        spec = COUNTED_SECTIONS.get((page, section))
        if not spec or not isinstance(body, dict):
            continue
        field, nouns = spec
        served = body.get(field)
        if not isinstance(served, list):
            continue
        n = len(served)
        for key in _PROSE_KEYS:
            for phrase, said in _stated_counts(body.get(key), nouns):
                if said == n:
                    continue
                out.append(_reason(
                    "CG-47", section, f"{page}.{section}.{key}",
                    f"the prose says \'{phrase}\' and this section serves "
                    f"{n}. Counts are computed, never written into a "
                    f"sentence: a stated count stops agreeing with its own "
                    f"list the moment a signal is added or dropped, and the "
                    f"reader is looking at the list. Say \'{n}\', or say it "
                    f"without a number. If the missing signal should be "
                    f"there, the repair is the signal - not the sentence; "
                    f"and read the prose around it, because a sentence that "
                    f"miscounts usually still describes what it lost."))
    return out[:6]



def _load_json_beside(name):
    """A generated file next to this module, or {} if it is not there.

    Returning {} rather than raising is deliberate and narrow: this gate is
    additive, and a connector that refused to start because a generated index
    was missing would turn a stale artefact into an outage. The gate reports
    nothing when the index is empty; `gen_column_types.py --check` in CI is
    what keeps the file present and current.
    """
    try:
        import pathlib
        return json.loads((pathlib.Path(__file__).parent / name).read_text())
    except Exception:                                        # noqa: BLE001
        return {}


COLUMN_TYPES = _load_json_beside("column_types.json")
_WRITER_SPEC = _load_json_beside("writer_spec.json")

#: Column families this gate checks. TEXT, arrays and the custom enum types
#: are deliberately absent: almost anything is a valid TEXT, and an enum's
#: members already belong to CG-08 and the contract. Reading only what can
#: HARD-FAIL a write keeps every entry on the verdict list real.
_NUMERIC_SQL = ("SMALLINT", "INTEGER", "INT", "BIGINT", "NUMERIC", "DECIMAL",
                "REAL", "DOUBLE PRECISION")
_DATEISH_SQL = ("DATE", "TIMESTAMPTZ", "TIMESTAMP",
                "TIMESTAMP WITH TIME ZONE")
_ISO_DATE = re.compile(r"^\s*\d{4}-\d{2}(-\d{2})?")


def _sql_family(sqltype):
    t = (sqltype or "").upper().strip()
    if not t or t.endswith("[]"):
        return None                    # arrays: element checking is CG-03's
    base = t.split("(")[0].strip()
    if base in _NUMERIC_SQL:
        return "numeric"
    if base in ("BOOLEAN", "BOOL"):
        return "boolean"
    if base in _DATEISH_SQL:
        return "dateish"
    return None


def _fits(value, family):
    if value is None:
        return True
    if family == "numeric":
        # A NUMERIC STRING IS STILL REFUSED. MEM-0194 measured three of these
        # on platform.roadmap.phases[].phase - '1', '2', '3' into a SMALLINT
        # - which Postgres coerced from an unknown-typed literal and so did
        # NOT fail. A value that survives only by coercion is one type-
        # inference change away from the outage its neighbour already caused.
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if family == "boolean":
        return isinstance(value, bool)
    if family == "dateish":
        return isinstance(value, str) and bool(_ISO_DATE.match(value))
    return True


def _writers_for(page):
    for spec in (_WRITER_SPEC.get("specs") or []):
        if spec.get("page") == page:
            return spec.get("writers") or []
    return []


def _column_reason(section, path, value, table, column, sqltype, family):
    shown = repr(value)
    if len(shown) > 90:
        shown = shown[:87] + "...'"
    advice = {
        "numeric": "Send the number, or null.",
        "boolean": "Send true or false, or null - not the word.",
        "dateish": ("Send an ISO-8601 date or timestamp, or null. A phrase "
                    "about when something happened is not a date."),
    }[family]
    # The one column where the right repair is not obvious from the type
    # alone: a web source has no page, and the paragraph detail a producer
    # was reaching for has somewhere else to go.
    if column == "source_page" and family == "numeric":
        advice += (" A web source has no page number, so source_page is null "
                   "and the paragraph or section detail goes into "
                   "source_document as a parenthetical - which is where a "
                   "reader meets it anyway, on the one-line SOURCE row.")
    return _reason(
        "CG-48", section, path,
        f"{shown} cannot be written to {table}.{column}, which is {sqltype}. "
        f"{advice} This is refused HERE because of where it used to surface "
        f"instead: inside promote_run, as Postgres SQLSTATE 22P02 naming a "
        f"parameter index, with the run already part-way through an atomic "
        f"promotion of six pages.")


def _check_values_fit_their_columns(page, payload) -> list:
    """CG-48 - a value is refused at submit if its column cannot hold it.

    MEM-0136 and MEM-0194, both BLOCKER, both the same shape. A producer put
    a prose locator into heatmap_focus_areas.source_page, an INTEGER column:

        "P4 of the release (Sharps quote), immediately after P3's
         introduction of Andrew Reich"

    Every submit gate passed the page. It failed later, inside promote_run,
    as a raw Postgres error - SQLSTATE 22P02, invalid input syntax for type
    integer - naming a parameter index and nothing a producer can act on.
    And it failed there having already passed here, so the run was part-way
    through an atomic promotion when the database refused it.

    MEM-0194 then measured the whole surface rather than the one field: 135
    values type-checked across 33 tables, 6 mismatches, every one a numeric
    column receiving a string. Three were that source_page; three were
    platform_roadmap.phase (SMALLINT) carrying '1', '2', '3', which Postgres
    coerced and which therefore did not fail - the same defect surviving on
    an accident of type inference.

    Both inputs already ship in this package: writer_spec.json maps every
    section field to its column, and column_types.json is generated from the
    migrations that create it. This walks the pair.

    WHAT IT DOES NOT CHECK, so nobody reads more into a pass than is there:
    TEXT columns, arrays, and the custom enum types. Only the families that
    can hard-fail a write are read - numeric, boolean and date-like.
    """
    if not isinstance(payload, dict) or not COLUMN_TYPES or not _WRITER_SPEC:
        return []
    out = []
    for w in _writers_for(page):
        section = w.get("section")
        body = payload.get(section)
        if not isinstance(body, dict):
            continue
        table = w.get("table") or ""
        table_types = COLUMN_TYPES.get(table) or {}
        if not table_types:
            continue
        item_field = w.get("item_field")
        items = body.get(item_field) if item_field else None
        items = items if isinstance(items, list) else []

        for col in (w.get("columns") or []):
            src = str(col.get("source") or "")
            if src.startswith(("skip:", "sys:")) or col.get("jsonb"):
                continue
            name = col.get("column")
            family = _sql_family(table_types.get(name))
            if not family:
                continue
            kind, _sep, field = src.partition(":")
            if not field:
                continue
            if kind == "item":
                for i, it in enumerate(items):
                    if not isinstance(it, dict) or field not in it:
                        continue
                    if not _fits(it.get(field), family):
                        out.append(_column_reason(
                            section,
                            f"{page}.{section}.{item_field}[{i}].{field}",
                            it.get(field), table, name,
                            table_types[name], family))
            elif kind in ("section", "env"):
                if field in body and not _fits(body.get(field), family):
                    out.append(_column_reason(
                        section, f"{page}.{section}.{field}",
                        body.get(field), table, name,
                        table_types[name], family))
    return out[:8]


#: The empty_state keys the API serves to a CUSTOMER. Mirrors
#: apps/api/dma_api/customer_allowlist.json["empty_state_keys"]; a key added
#: there and not here is prose this gate stops reading, which the test beside
#: it pins.
CUSTOMER_EMPTY_STATE_KEYS = ("reason", "closure_condition", "closure", "kind")

#: Identifiers that are UNAMBIGUOUSLY this system talking about itself. Every
#: one names a thing a client has no way to look up and no business seeing.
#:
#: WHAT IS DELIBERATELY ABSENT, and it is most of the vocabulary: "gate",
#: "connector", "staged", "promoted". Those are ordinary English in a
#: sentence like "no regulatory gate applies to this division", and a gate
#: that refused them would be refusing good prose - the failure this build
#: has already paid for twice, on the vetter and on CG-47. Only the tokens
#: that cannot occur by accident are listed.
_INTERNAL_ID = re.compile(
    r"\b(?:MEM|REF)-\d{3,4}\b"                  # findings-memory ids
    r"|\b(?:CG|AG|ET)-\d{2,3}\b"                # gate ids (SG below)
    r"|\bSG-[A-Z0-9]{1,3}\d?\b"                 # SG-01, SG-V4, SG-AC1
    r"|\bCUSTOMER_WITHHELD\b"                    # the redaction constant
    r"|\bno_staged_submission\b"
    r"|\b(?:get|list|submit|promote|register|record|resolve|report)_[a-z_]+\("
    , re.I)


def _check_customer_empty_state_prose(page, payload) -> list:
    """CG-49 - a client-visible absence does not name this system's machinery.

    Invariant 5 is default-deny redaction, and the serve layer honours it at
    KEY grain: apps/api/dma_api/customer_allowlist.json keeps `reason`,
    `closure_condition`, `closure` and `kind` from an empty_state and drops
    the rest, so `sources_searched` and `r_layer` never reach a customer.

    What a key-grain allowlist structurally cannot see is what those four
    kept keys SAY. MEM-0137 measured the leak on a promoted run and this
    gate's own sweep found it still live on all five clients in the
    directory, 12 fields between them:

      · platform.starters.closure_condition naming CUSTOMER_WITHHELD and
        MEM-0081
      · heatmap.cohort_patterns.reason naming MEM-0099
      · heatmap.safeguard_gates.reason naming SG-01 and SG-06
      · context.issue_register.reason naming MEM-0209 and MEM-0210 - which
        this session wrote, hours before writing this gate

    Refused at SUBMIT rather than stripped at serve, and the distinction is
    the point: stripping prose leaves a client reading half a sentence, while
    refusing it makes the producer write the sentence a client can read. The
    substance never has to be lost - "recorded where assessment defects
    belong" says everything "recorded as MEM-0209 and MEM-0210" says, to a
    reader who can act on it.
    """
    if not isinstance(payload, dict):
        return []
    out = []
    for section, body in payload.items():
        if not isinstance(body, dict):
            continue
        es = body.get("empty_state")
        if not isinstance(es, dict):
            continue
        for key in CUSTOMER_EMPTY_STATE_KEYS:
            v = es.get(key)
            if not isinstance(v, str) or not v:
                continue
            hits = sorted({m.group(0) for m in _INTERNAL_ID.finditer(v)})
            if not hits:
                continue
            out.append(_reason(
                "CG-49", section, f"{page}.{section}.empty_state.{key}",
                f"this sentence reaches the CUSTOMER audience and names "
                f"{len(hits)} piece(s) of this system\'s own machinery: "
                f"{', '.join(hits[:5])}"
                f"{'' if len(hits) <= 5 else f' (+{len(hits) - 5} more)'}. "
                f"The serve allowlist keeps this key by design - an absence "
                f"owes a client a reason - but it can only drop KEYS, so what "
                f"the kept prose says is nobody\'s check but this one. Say the "
                f"same thing in the client\'s terms: \'recorded where "
                f"assessment defects belong\' carries everything \'recorded as "
                f"MEM-0209\' carries, to a reader who can act on it. The "
                f"internal id belongs in r_layer, which the walker already "
                f"strips."))
    return out[:6]


#: The depth floors, and what each is a floor ON. Every one is already in the
#: contract's own field docs; none had a reader until 2026-08-23.
DEPTH_FLOORS = {
    ("overview", "sentiment"): (
        2, "rating lines",
        "the contract's own field doc says it: 'A single displayed line is "
        "not a sentiment picture'"),
    ("overview", "why_now"): (
        2, "signals",
        "the field doc asks for three to six trigger cards; below two the "
        "contract already defines thin=true"),
    ("techstack", "techstack"): (
        15, "products",
        "owner, 2026-08-23: 'I expect at least 15 technology stack items "
        "through recursive searches'"),
}

#: Three years, in days, for the why_now span. The owner's words: "the
#: evolution timeline spans 1 year? At least 3 years should be covered."
WHY_NOW_SPAN_DAYS = 3 * 365


def _depth_count(page, section, body):
    """How many things this section actually serves, by its own shape."""
    if section == "sentiment":
        bars = body.get("bars")
        n = len(bars) if isinstance(bars, list) else 0
        # `displayed_lines` is the producer's own counter for the same thing;
        # take the larger so a section cannot be thin by miscounting itself.
        d = body.get("displayed_lines")
        return max(n, d if isinstance(d, int) else 0)
    if section == "why_now":
        sig = body.get("signals")
        return len(sig) if isinstance(sig, list) else 0
    if section == "techstack":
        items = body.get("items")
        return len(items) if isinstance(items, list) else 0
    return 0


def _says_it_searched(body) -> bool:
    """Does this section name the work behind a thin result?

    The empty-state discipline the rest of the payload already keeps: an
    absence names its search and its closure condition. `thin` alone counts
    only when something travels with it — a bare boolean is an assertion.
    """
    if body.get("thin") is True and (
            body.get("empty_state") or body.get("searches")
            or body.get("sources_searched") or body.get("r_layer")):
        return True
    es = body.get("empty_state")
    if isinstance(es, dict) and (es.get("sources_searched")
                                 or es.get("searches_run")
                                 or es.get("reason")):
        return True
    if isinstance(es, str) and len(es.strip()) >= 40:
        return True
    r = body.get("r_layer")
    if isinstance(r, dict) and (r.get("probes_run") or r.get("searches")):
        return True
    return False


#: Read in this order, first hit wins. `dated_on` leads because it is the
#: contract's own field — "dated_on required (an undated signal is dropped)"
#: — and every producer in the corpus writes it. The original list omitted
#: it and started at `date`, so on a real payload the loop found nothing,
#: returned None, and the span check reported "undatable" instead of a
#: number: measured on axos-bank 2026-08-23, three signals dated 2026-01-26,
#: 2026-07-07 and 2026-07-30 spanning six months, and the gate never fired.
#: A check that cannot see the field it is about is the defect class this
#: whole gate family exists for.
#:
#: `window` stays last and only as a fallback: its date is the event that
#: CLOSES the opening, which is in the future and inflates the span. It is
#: better than nothing on a payload that dates signals no other way.
_WHY_NOW_DATE_KEYS = ("dated_on", "date", "as_of", "observed_at",
                      "published_date", "window")


#: Eighteen months. Past this, a why-now signal is describing the world as it
#: was rather than as it is, and the card stops being an argument for acting.
WHY_NOW_STALE_DAYS = 548
#: The reach-back floor, moved to the surface the owner was actually reading.
TIMELINE_SPAN_DAYS = 1095


def _dates_of(rows, keys):
    """Every parseable date on these rows, first matching key per row."""
    import datetime as _dt
    seen = []
    for s in rows or []:
        if not isinstance(s, dict):
            continue
        for k in keys:
            v = s.get(k)
            if not isinstance(v, str):
                continue
            m = re.search(r"(\d{4})-(\d{2})(?:-(\d{2}))?", v)
            if m:
                try:
                    seen.append(_dt.date(int(m.group(1)), int(m.group(2)),
                                         int(m.group(3) or 1)))
                except ValueError:
                    pass
                break
    return seen


def _timeline_span_days(body):
    """How far back the evolution timeline reaches, or None when undatable.

    THIS is the surface the owner meant. The floor lived on why_now for a
    day and that was the wrong home: a why-now signal argues for acting NOW,
    so a reach-back floor there rewards quoting an old event as a trigger —
    which is the exact defect reported the next morning ("Why quote something
    from 2015… is it still relevant?"). A history reaching back three years
    and a trigger dated this month are both correct at once, and only a rule
    per surface can say so.
    """
    seen = _dates_of(body.get("events"), ("event_date", "date", "as_of",
                                          "occurred_on", "dated_on"))
    if len(seen) < 2:
        return None
    return (max(seen) - min(seen)).days


def _why_now_staleness_days(body):
    """Days between the NEWEST signal and this section's own produced_at.

    Measured against the payload's own timestamp rather than the wall clock,
    so the verdict is deterministic and a run re-validated next year does not
    fail for having aged. The producer's own honesty is what is being checked:
    on the day you wrote this, how old was your freshest reason to act?
    """
    seen = _dates_of(body.get("signals"), _WHY_NOW_DATE_KEYS)
    if not seen:
        return None
    made = _dates_of([body], ("produced_at",))
    if not made:
        return None
    return (max(made) - max(seen)).days


def _why_now_span_days(body):
    """The span the signals actually cover, or None when undatable."""
    import datetime as _dt
    seen = []
    for s in body.get("signals") or []:
        if not isinstance(s, dict):
            continue
        for k in _WHY_NOW_DATE_KEYS:
            v = s.get(k)
            if not isinstance(v, str):
                continue
            m = re.search(r"(\d{4})-(\d{2})(?:-(\d{2}))?", v)
            if m:
                try:
                    seen.append(_dt.date(int(m.group(1)), int(m.group(2)),
                                         int(m.group(3) or 1)))
                except ValueError:
                    pass
                break
    if len(seen) < 2:
        return None
    return (max(seen) - min(seen)).days


#: The contact routes a roster seat can carry. Mirrors
#: `CUSTOMER_STRIP_CONTACT_KEYS` in the overview rulebook — one vocabulary,
#: because a key this list forgets is a route CG-41 cannot see and redaction
#: still has to strip.
CONTACT_ROUTE_KEYS = ("email", "contact_email", "work_email", "linkedin_url",
                      "linkedin", "phone", "direct_line", "mobile")

#: Where a seat may record what the contact search did. `enrichment_basis` is
#: the contract's field; the rest are shapes promoted runs have actually used,
#: read rather than declared wrong after the fact.
CONTACT_BASIS_KEYS = ("enrichment_basis", "contact_basis", "contact_search",
                      "searched_on", "enrichment_note")

#: A basis has to be a sentence. Below this it is a token — "n/a", "none",
#: "Clay" — and a token cannot distinguish a search that ran from one that
#: did not, which is the only thing this gate is asking.
_BASIS_MIN = 25


def _seat_contact_state(seat) -> str:
    """`resolved` · `recorded_negative` · `unknown` for one roster seat."""
    if not isinstance(seat, dict):
        return "unknown"
    basis = ""
    for k in CONTACT_BASIS_KEYS:
        v = seat.get(k)
        if isinstance(v, str) and len(v.strip()) > len(basis):
            basis = v.strip()
        elif isinstance(v, (list, dict)) and v:
            basis = basis or "structured"
    has_route = any(isinstance(seat.get(k), str) and seat[k].strip()
                    for k in CONTACT_ROUTE_KEYS)
    if has_route:
        # A route with no basis is the Logix shape: a value on the page and
        # no answer to "from where". It is not resolved, it is unattributed.
        return "resolved" if (basis == "structured" or len(basis) >= _BASIS_MIN) \
            else "unknown"
    if basis == "structured" or len(basis) >= _BASIS_MIN:
        return "recorded_negative"
    return "unknown"


def _roster_of(body):
    """The seat list and the KEY it was found under.

    The key travels with it because the refusal quotes a JSON path (invariant
    12: a verdict names the gate, the path and the arithmetic). A path that
    says `roster` on a payload whose container is `people` sends the producer
    to a field that is not there.
    """
    for k in ("roster", "people", "leaders", "rows"):
        v = body.get(k)
        if isinstance(v, list):
            return v, k
    return None, None


#: The email routes specifically. Kept apart from CONTACT_ROUTE_KEYS because
#: a LinkedIn profile and a mailbox are not interchangeable, and treating them
#: as one is what let the reported run through — see the second half of the
#: docstring below.
EMAIL_ROUTE_KEYS = ("email", "contact_email", "work_email")

#: Words that mean the basis is talking about the ADDRESS search rather than
#: about a profile match. Deliberately broad: the gate wants evidence that the
#: question was asked, not a particular phrasing.
_EMAIL_WORDS = ("email", "e-mail", "mailbox", "address", "mail")

#: The wider set for "did this section speak to the CONTACT search at all",
#: which is the escape for the per-seat check. Wider than the address set
#: because a producer that says "no contact route could be established for
#: these seats" has answered honestly without naming a mailbox.
_CONTACT_WORDS = _EMAIL_WORDS + ("contact", "phone", "reach", "route",
                                 "direct line")


def _mentions_email_search(body, roster, words=_EMAIL_WORDS) -> bool:
    """Does anything in this section speak to the ADDRESS search?

    `words` widens it to the contact search generally — see `_CONTACT_WORDS`.
    Scans the section's own prose AND every seat's basis, because a producer
    may answer this once at the top or once per seat and both are honest.
    """
    blobs = []
    for k in ("empty_state", "thin_reason", "narrative_thread", "contact_note"):
        v = body.get(k)
        if isinstance(v, str):
            blobs.append(v)
        elif isinstance(v, dict):
            blobs += [str(x) for x in v.values() if isinstance(x, str)]
    r = body.get("r_layer")
    if isinstance(r, dict):
        for v in r.values():
            if isinstance(v, str):
                blobs.append(v)
            elif isinstance(v, list):
                blobs += [str(x) for x in v if isinstance(x, str)]
    for seat in roster:
        if isinstance(seat, dict):
            for k in CONTACT_BASIS_KEYS:
                if isinstance(seat.get(k), str):
                    blobs.append(seat[k])
    text = " ".join(blobs).lower()
    return any(w in text for w in words)


def _check_contact_enrichment_baseline(page, payload):
    """CG-41 — every roster seat says what the contact search found, and a
    roster with NO EMAIL AT ALL says why.

    The baseline is the SEARCH, not the email. A private company's CFO may
    have no reachable address anywhere and that run must still promote, so
    the gate is always satisfiable by recording the negative — deliberately
    the same escape CG-40 leaves, because a gate that can only be satisfied
    by data the world may not hold is a gate that teaches producers to refuse
    packages.

    THE SECOND CHECK EXISTS BECAUSE THE FIRST ONE MISSED THE REPORTED RUN.
    Measured 2026-08-23 against gulf-coast-business-credit's live promoted
    payload, which is the run the owner reported with "Clay enrichment for
    Gulf has no emails": all three seats carry a `linkedin_url` and a long,
    genuine `enrichment_basis`, so every one of them scored `resolved` and the
    per-seat check PASSED a roster with zero email addresses on it. The basis
    text describes the profile match and never mentions an address search at
    all — so "we looked for emails and found none" and "we never looked" were
    still the same payload, one level down from where the gate was looking.

    A LinkedIn profile and a mailbox are not interchangeable. So the roster is
    also asked, once, at section level: if NOT ONE seat carries an email and
    nothing anywhere in the section speaks to the address search, that is
    refused. One sentence closes it — in a seat's basis, the section's
    empty_state, or the r_layer's probe list — and a roster where addresses
    genuinely do not exist still promotes.
    """
    if page != "overview" or not isinstance(payload, dict):
        return []
    body = payload.get("leadership")
    if not isinstance(body, dict):
        return []
    body = body.get("data") if isinstance(body.get("data"), dict) else body
    roster, container = _roster_of(body or {})
    if not roster:
        return []

    states = [(i, _seat_contact_state(s)) for i, s in enumerate(roster)]
    unknown = [i for i, st in states if st == "unknown"]

    # ── the second check: a roster with NO EMAIL AT ALL says why ──────
    #
    # Runs BEFORE the early return, because the reported run had ZERO unknown
    # seats — every one carried a linkedin_url and a real basis — and still
    # served no addresses. Returning early on `not unknown` was exactly how it
    # got through.
    # AND ONLY WHERE A SEARCH ACTUALLY SUCCEEDED. A roster whose every seat
    # recorded a negative has already said the search found nothing, and
    # demanding a second, address-specific sentence from it would buy nothing
    # but boilerplate. The Gulf shape is the opposite and is the one worth
    # refusing: the search WORKED — three profiles came back — and produced no
    # address, with nothing said about why. So the question is only asked of a
    # roster that has at least one resolved seat.
    out = []
    seats = [s for s in roster if isinstance(s, dict)]
    resolved_any = any(st == "resolved" for _, st in states)
    with_email = [i for i, s in enumerate(roster)
                  if isinstance(s, dict)
                  and any(isinstance(s.get(k), str) and s[k].strip()
                          for k in EMAIL_ROUTE_KEYS)]
    # SUPPRESSED ONLY BY TEXT THAT SPEAKS TO ADDRESSES, never by
    # `_says_it_searched`. That helper answers the FIRST check's question —
    # "did this section disclose that its contact pass did not run" — and it
    # returns True for any section carrying an `r_layer.probes_run` at all.
    # Gulf carries five probes, every one about IDENTITY (management page,
    # title match, start year), and reusing the helper here let those probes
    # answer a question they never addressed: the gate went green on the exact
    # payload it was written for. `_mentions_email_search` reads the same
    # r_layer, and the seats' bases, for words that are actually about an
    # address.
    if seats and resolved_any and not with_email \
            and not _mentions_email_search(body, roster):
        out.append(_reason(
            "CG-41", "leadership", f"overview.leadership.{container}",
            f"not one of {len(seats)} roster seats carries an email address, "
            f"and nothing in this section speaks to the address search — not "
            f"a seat's enrichment_basis, not the empty_state, not the "
            f"r_layer's probes. A LinkedIn profile is not a mailbox, so a "
            f"roster full of resolved profiles with no address on it is still "
            f"the state where 'we searched for addresses and found none' and "
            f"'we never searched' read identically. Measured on the run that "
            f"prompted this gate: three seats, three profiles, three genuine "
            f"bases, zero emails, and no sentence anywhere about an address. "
            f"ONE sentence closes this — in a seat's basis, in the section's "
            f"empty_state, or as an r_layer probe — and a roster whose "
            f"addresses genuinely are not discoverable still promotes. What "
            f"is refused is the silence, never the absence."))

    if not unknown:
        return out

    # SECTION-LEVEL DISCLOSURE STILL COUNTS, AND IT HAS TO BE ABOUT CONTACTS.
    # A roster that states once, for the whole section, that the contact pass
    # did not run is honest — it is thin and it says so. Silence is the
    # refusal, not thinness.
    #
    # `_says_it_searched` is deliberately NOT used here. It is CG-40's escape,
    # where "this section documents its search" is exactly the right test, and
    # it returns True for any section carrying an `r_layer.probes_run` at all.
    # Gulf carries five probes, every one about IDENTITY — the management page,
    # the title match, the start year — and none about reaching anybody. Borrowed
    # here it let an identity ladder excuse a contact silence.
    if _mentions_email_search(body, roster, _CONTACT_WORDS):
        return out

    n = len(roster)
    resolved = sum(1 for _, st in states if st == "resolved")
    negative = sum(1 for _, st in states if st == "recorded_negative")
    where = ", ".join(f"{container}[{i}]" for i in unknown[:12])
    more = "" if len(unknown) <= 12 else f" (+{len(unknown) - 12} more)"
    out.append(_reason(
        "CG-41", "leadership", f"overview.leadership.{container}",
        f"{len(unknown)} of {n} roster seats record no contact-search "
        f"outcome — no route and no basis: {where}{more}. "
        f"({resolved} resolved with a basis, {negative} recorded a negative.) "
        f"The baseline is the SEARCH, not the email: a seat with no reachable "
        f"address is fine and promotes, but it has to say so. Give each seat "
        f"either a contact route WITH the profile or filing its "
        f"enrichment_basis came from, or a basis stating the search ran and "
        f"matched nothing — 'the enrichment search returned no profile whose "
        f"TITLE matched this person' is the contract's own wording. A seat "
        f"carrying neither is indistinguishable from a seat the enrichment "
        f"never reached, which is the state three of four promoted clients "
        f"were in. One section-level empty_state or thin flag naming the "
        f"queries run also satisfies this."))
    return out


def _check_date_reach(page, section, body):
    """CG-40's two DATE rules, one per surface.

    They pull in opposite directions on purpose. The evolution timeline
    must REACH BACK, because a history that starts this year is a
    snapshot. A why-now trigger must be RECENT, because it is an argument
    for acting now. Holding both as one rule on one surface is what put a
    2015 vendor acquisition on a why-now card and had the gate call it
    compliant.
    """
    out = []
    # The reach-back floor belongs to the EVOLUTION TIMELINE, which is
    # what the owner was reading when they asked for three years.
    if section == "timeline":
        span = _timeline_span_days(body)
        if span is not None and span < TIMELINE_SPAN_DAYS \
                and not _says_it_searched(body):
            out.append(_reason(
                "CG-40", section, f"{page}.{section}.events",
                f"the evolution timeline spans {span} days "
                f"({span // 365}y) against a floor of three years. Owner, "
                f"2026-08-23: 'the evolution timeline spans 1 year? At "
                f"least 3 years should be covered.' A history that starts "
                f"this year is a snapshot, not an evolution. Reach "
                f"further back — acquisitions, platform decisions, "
                f"leadership changes and filings are all dated and "
                f"citable — or say what was searched and why the trail "
                f"ends where it does."))
    # …and why_now gets the OPPOSITE test. A trigger is an argument for
    # acting NOW, so the defect there is staleness, never shortness.
    if section == "why_now":
        stale = _why_now_staleness_days(body)
        if stale is not None and stale > WHY_NOW_STALE_DAYS \
                and not _says_it_searched(body):
            out.append(_reason(
                "CG-40", section, f"{page}.{section}.signals",
                f"the newest signal predates this section's own "
                f"produced_at by {stale} days ({stale // 365}y), against "
                f"a staleness ceiling of {WHY_NOW_STALE_DAYS // 30} "
                f"months. Owner, 2026-08-23, on a signal dated 2015: "
                f"'Why Now signals seem stale. Why quote something from "
                f"2015 — is it still relevant?' An old event can be "
                f"DURATION inside a trigger; it cannot be the trigger. "
                f"Re-date to what changed recently, or say what was "
                f"searched and why nothing newer exists."))
    return out


def _sentiment_bar_rows(body):
    """The overview's rating bars, by evidence id."""
    if not isinstance(body, dict):
        return {}
    return {str(b["e_id"]): b for b in (body.get("bars") or [])
            if isinstance(b, dict) and b.get("e_id")}


def _sentiment_grid_rows(body):
    """The context grid's drilldown rows, by evidence id — the same readings
    the overview draws as bars, one card each."""
    out = {}
    if not isinstance(body, dict):
        return out
    for tile in body.get("context_tiles") or []:
        if not isinstance(tile, dict):
            continue
        for row in tile.get("rows") or []:
            if isinstance(row, dict) and row.get("e_id"):
                out[str(row["e_id"])] = row
    return out


def _check_sentiment_projections_agree(conn, run_id, page, payload) -> list:
    """CG-43 — the Context grid and the Overview bars are one dataset.

    The contract says it outright, in the context_tiles field doc: the grid is
    "a RE-PROJECTION of the same dataset O9 renders as bars, so the two cards
    cannot disagree". Nothing read that sentence, and the two surfaces drifted
    the moment either was edited alone.

    Measured 2026-08-23, and the drift was mine: I added a second customer bar
    to axos-bank's overview (UFB Direct, 4.83 over 19,831 ratings) without
    touching the context grid, so the Overview showed two readings and the
    Context page showed one. Nothing refused it. The owner had asked for this
    exact congruence the same evening.

    Keyed on `e_id`, because that is the one identifier both sides already
    carry and it survives a source string being reworded on one page. A
    reading present on one surface and absent from the other is the finding;
    where both carry it, the RATING has to match too, since a re-projection
    that renumbers is worse than one that omits.

    BOTH EMPTY IS CONGRUENT and passes: gulf-coast-business-credit serves no
    bar and no tile because a business-to-business lender accumulates no
    consumer review estate, and both cards say so in the same terms. The gate
    is about disagreement, never about depth — CG-40 owns depth.
    """
    if page not in ("overview", "context") or not isinstance(payload, dict):
        return []
    if page == "overview":
        bars = _sentiment_bar_rows(payload.get("sentiment"))
        sibling = _live_submission(conn, run_id, "context")
        grid = _sentiment_grid_rows(
            (sibling or {}).get("context_sentiment") if isinstance(sibling, dict) else None)
        here, there = "overview.sentiment.bars", "context.context_sentiment"
        staged = isinstance(sibling, dict) and bool(sibling)
    else:
        grid = _sentiment_grid_rows(payload.get("context_sentiment"))
        sibling = _live_submission(conn, run_id, "overview")
        bars = _sentiment_bar_rows(
            (sibling or {}).get("sentiment") if isinstance(sibling, dict) else None)
        here, there = "context.context_sentiment.context_tiles", "overview.sentiment"
        staged = isinstance(sibling, dict) and bool(sibling)
    if not staged:
        return []                    # nothing to compare yet; promote re-gates
    if not bars and not grid:
        return []                    # congruently empty, which is a real answer

    out = []
    only_bars = sorted(set(bars) - set(grid))
    only_grid = sorted(set(grid) - set(bars))
    if only_bars:
        out.append(_reason(
            "CG-43", "sentiment" if page == "overview" else "context_sentiment",
            here,
            f"{len(only_bars)} reading(s) render as a bar on the Overview and "
            f"appear nowhere in the Context grid: {', '.join(only_bars[:6])}"
            f"{'' if len(only_bars) <= 6 else f' (+{len(only_bars) - 6} more)'}. "
            "The contract calls the grid a re-projection of the same dataset, "
            f"so the two cards cannot disagree — add the row to {there}, or "
            "drop the bar. A reader who opens the Context page to see the "
            "detail behind a bar and finds it missing has been told the "
            "assessment looked twice and saw different things."))
    if only_grid:
        out.append(_reason(
            "CG-43", "sentiment" if page == "overview" else "context_sentiment",
            here,
            f"{len(only_grid)} reading(s) sit in the Context grid with no bar "
            f"on the Overview: {', '.join(only_grid[:6])}. Same rule, the "
            "other way round: the Overview is the summary of this dataset and "
            "a reading it omits is one the summary hides."))
    for eid in sorted(set(bars) & set(grid)):
        b, g = bars[eid].get("rating"), grid[eid].get("rating")
        if isinstance(b, (int, float)) and isinstance(g, (int, float)) \
                and abs(float(b) - float(g)) > 0.005:
            out.append(_reason(
                "CG-43", "sentiment" if page == "overview" else "context_sentiment",
                here,
                f"{eid} reads {b} on the Overview and {g} in the Context "
                "grid. One dataset, one number: a re-projection that "
                "renumbers is worse than one that omits, because both look "
                "authoritative."))
    return out[:6]


def _check_depth_floors(page, payload):
    """CG-40 — a section whose value is its depth reaches a floor or says why.

    The floor is a floor on EFFORT, never on the world. A client with eight
    detectable products has eight, and refusing that run would be the
    reject-rather-than-triage failure this system has already paid for. What
    this refuses is SILENCE: a thin section that never says it searched.
    """
    if not isinstance(payload, dict):
        return []
    out = []
    for section, body in payload.items():
        if not isinstance(body, dict):
            continue
        # The date rules below are NOT depth floors and must not sit behind
        # the depth-floor guard: `timeline` has no entry in DEPTH_FLOORS, so
        # a `continue` here skipped its reach-back check entirely and the
        # gate reported nothing on a one-year history — the same shape as the
        # `dated_on` blindness this file already carries a fixture for.
        out.extend(_check_date_reach(page, section, body))
        floor = DEPTH_FLOORS.get((page, section))
        if not floor:
            continue
        need, unit, why = floor
        got = _depth_count(page, section, body)
        if got < need and not _says_it_searched(body):
            out.append(_reason(
                "CG-40", section, f"{page}.{section}",
                f"serves {got} {unit} against a floor of {need}, and names no "
                f"search. {why}. Either serve the floor — the enrichment "
                f"connectors are what this depth comes from — or keep what "
                f"you have and set thin/empty_state naming the queries you "
                f"ran and what would change the answer. A thin section that "
                f"says so is fine; a thin section that is silent is "
                f"indistinguishable from one nobody worked."))
    return out

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
        reasons.extend(_check_financial_figures_are_quoted(
            split.get("found", []), cited, payload))
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

    # Runs whether or not anything was cited: the whole point of ET-09 is the
    # contamination that never cites, so it must not sit inside `if cited:`.
    reasons.extend(_check_foreign_entity_prose(conn, run_id, payload))
    reasons.extend(_check_platform_fit_is_the_engine_s(
        conn, run_id, page, payload))
    reasons.extend(_check_opportunity_tiles_are_the_engine_s(
        conn, run_id, page, payload))
    reasons.extend(_check_recommendations_reach_the_platform_page(
        conn, run_id, page, payload))
    reasons.extend(_check_depth_floors(page, payload))
    reasons.extend(_check_contact_enrichment_baseline(page, payload))
    reasons.extend(_check_sentiment_projections_agree(
        conn, run_id, page, payload))
    reasons.extend(_check_peer_scores_cascade(conn, run_id, page, payload))
    reasons.extend(_check_cards_state_their_reach(conn, run_id, page, payload))
    reasons.extend(_check_issue_register_is_the_entitys(page, payload))
    reasons.extend(_check_prose_counts_what_is_served(page, payload))
    reasons.extend(_check_values_fit_their_columns(page, payload))
    reasons.extend(_check_customer_empty_state_prose(page, payload))

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
        #
        # An item that ASSERTS NOTHING is not a ranked claim, and the same
        # predicate AG-03 uses decides it. `cohort_patterns.insufficient_
        # cohorts` is the case that forced this: it is the contract's own
        # field for RECORDING A WITHHELD COHORT, every item carries
        # `insufficient_cohort`, and demanding an R-Layer verdict on each
        # asks a producer to argue for a conclusion it explicitly declined
        # to draw. Measured 2026-08-16: a producer met that refusal, could
        # not satisfy it honestly, and deleted the field — so a gate meant
        # to raise the standard of ranked claims removed an honest
        # disclosure from a client surface instead.
        if (page, name) in _RANKED_SECTIONS:
            from .vacuity import item_keys
            for fname, val in body.items():
                if isinstance(val, list) and val and all(isinstance(x, dict) for x in val):
                    declared = item_keys(page, name, fname)
                    for i, item in enumerate(val):
                        if _asserts_nothing(item, declared):
                            continue
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
    reasons.extend(_check_rank_against_score(page, payload))
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
    reasons.extend(_check_safeguard_gate_ids(conn, page, payload))
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


def _check_safeguard_gate_ids(conn, page, payload) -> list:
    """CG-22 — a gate_id a producer writes into heatmap.safeguard_gates.gates
    must name a real gate.

    Measured 2026-08-17: a payload carried gates[] entries SG-E1, SG-E2,
    SG-Q1 and SG-D1, none of them ever registered anywhere in gates.py or
    gate_registry, three rendering FAIL with an official-looking plain_label.
    `computed.safeguard_gates` only ever serves rows it reads back from
    `gate_results` — a table only real, machine-evaluated gates write to — so
    the fabricated entries never reached a client. But that was accidental:
    they simply landed in a key nothing reads, not a rule the producer could
    see, and the effort spent authoring them was wasted. Caught here instead,
    at submit, with the reason a producer needs: this belongs in caps[].

    Retired counts as present — a gate that once ran and has since been
    retired still has a real history worth citing; only a gate_id with NO
    row at all, ever, is fabricated.
    """
    if page != "heatmap":
        return []
    sg = payload.get("safeguard_gates")
    if not isinstance(sg, dict):
        return []
    gates = sg.get("gates")
    if not isinstance(gates, list) or not gates:
        return []
    named = {g.get("gate_id") for g in gates
             if isinstance(g, dict) and g.get("gate_id")}
    if not named:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT gate_id FROM gate_registry WHERE gate_id = ANY(%s)",
                    (list(named),))
        known = {row[0] for row in cur.fetchall()}
    except Exception:                                          # noqa: BLE001
        # A gate that cannot read the registry must not block on a transient
        # read; it also must not silently wave through a fabricated id, so it
        # says nothing rather than either.
        return []
    out = []
    for i, g in enumerate(gates):
        if not isinstance(g, dict):
            continue
        gid = g.get("gate_id")
        if gid and gid not in known:
            out.append(_reason(
                "CG-22", "safeguard_gates", f"safeguard_gates.gates[{i}].gate_id",
                f"gate_id {gid!r} is not a real gate — it has no row in "
                "gate_registry, ever. A gate result must come from a "
                "connector-evaluated gate; a disclosure about what the "
                "assessment applied (a public-evidence ceiling, a withheld "
                "peer comparison, a rebuilt citation base) belongs in "
                "caps[], not in a fabricated gates[] entry"))
    return out


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
