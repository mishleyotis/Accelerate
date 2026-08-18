"""Sub-vertical vocabulary, and which catalogue cells a run may serve.

Two things live here because they are one fact stated twice: what
sub-vertical an ENTITY is, and what sub-vertical a catalogue CELL belongs
to. Keeping them in one module is what stops the crosswalk drifting from
the filter that depends on it.

## The defect this module exists to close

Baxter Credit Union (`SV2` — a credit union) served 765 cells, and 59 of
them were sub-vertical VARIANT cells belonging to somebody else:

    IC  25   insurance carriers  (P1C1.3.IC1 "Insurance Line Strategy")
    RIA 19   RIAs/broker-dealers (P2C4.6.RIA1 "AUM-Based Segmentation")
    IB  15   insurance brokers   (P1C1.4.IB1  "Producer/Advisor Channel…")

They came in from the assessment workbook itself — its four
`P*_Subcap_Scoring` tabs carry 766 rows including those variants — and
the ingested tier is read-only once scanned, so they cannot be deleted
at the source. Nor should they be: the workbook is the measurement, and
what it measured is a fact even when it measured a cell that does not
apply. The exclusion is therefore a SERVING decision, applied on read,
so that the same ingested rows serve correctly to whoever asks.

## How a cell's sub-vertical is derived, and the limits of that

The catalogue has no per-cell applicability column: `ccg_subcaps` is
(subcap_id, version, capability_id, category_id, pillar_id, name, weight,
l3_platform_areas, l4_features) and nothing else. The workbooks' own
"Sub-Vertical Matrix" tab is at CAPABILITY grain (P1C1.1), marking which
sub-verticals a capability applies to and whether it has T2 variants —
it never names the variant CELL. What does name it is the cell id: the
V7/V5 schema mints a T2 variant as `<capability>.<CODE><ordinal>`, and
the CODE is the sub-vertical. That is the derivation, and it is the
catalogue's own convention, not an inference over names:

    P1C1.3.CU1   Member Segment Strategy        credit unions
    P1C1.3.IC1   Insurance Line Strategy        insurance carriers
    P1C1.3.CL1   Commercial Segment Strategy    commercial lending

Its limit is that not every suffix code names ONE sub-vertical. v5.0 also
mints family and product-line codes over the same grammar:

    BK   "NCUA/FFIEC Governance", "Fair Lending Governance" — the
         DEPOSITORY family; NCUA is the credit-union regulator, so a BK
         cell applies to a credit union as much as to a bank
    WM   "Wealth Segment Strategy", "Fiduciary Governance" — the wealth
         family, spanning AM and RIA
    PEN  "Retirement Plan Administration Automation" — a product line,
         not a sub-vertical at all

So the rule is deliberately one-sided: a variant cell is FOREIGN only
when its code names exactly one sub-vertical AND that sub-vertical is
not the entity's. A family code, a product code, an unrecognised code
and a base (non-variant) cell all serve, for every entity. Absent beats
wrong (invariant 9): failing to exclude shows a cell that may not apply,
while over-excluding hides a score the assessment actually made — and
only the first is visible enough to be reported and fixed.

Nothing here is a list of ids. Adding a sub-vertical means adding its
code to `SUBVERTICAL_CODES` below (the loader's own vocabulary); adding
a variant cell means nothing at all.
"""
from __future__ import annotations

import re

# The codes that name exactly ONE sub-vertical — the values of the
# ccg_loader's SUBVERTICAL_CODES, which is the vocabulary the catalogue's
# own VC tables key on (`ccg_vc_mapping.subvertical_code`). A suffix code
# outside this set is NOT evidence that a cell belongs to somebody else.
SUBVERTICAL_CODES = ("RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB")

# Folded into the /subcaps ETag. The document a run serves now depends on
# this rule as well as on the run's promoted_at, and a client holding the
# pre-fix 765-row body would otherwise revalidate to a 304 and keep it —
# `promoted_at` does not move when the SERVING rule does. Bump on any
# change to what `serves()` admits.
SCOPE_TAG = "sv-scope@2"

# Surface-Spec / manifest spellings -> the catalogue's VC subvertical_code.
# Two vocabularies exist: the serving tier stores the Surface Specification
# codes (SV1-SV9) or, in older manifests, a spelled-out label; the catalogue
# keys on the workbook codes. The pairs are unambiguous — SV1 "Regional
# Banks" is the workbook's "Retail Banking" (RB), SV7 "Insurance Brokers"
# is "Insurance Brokerages" (IB) — and this crosswalk is that pairing,
# nothing more. Keys are _norm()-alised.
_SUBVERTICAL_ALIASES = {
    "RB": ("RB", "SV1", "REGIONAL BANKS", "REGIONAL BANK",
           "RETAIL BANKING", "COMMUNITY BANKS", "COMMUNITY BANK"),
    "CU": ("CU", "SV2", "CREDIT UNIONS", "CREDIT UNION"),
    "CL": ("CL", "SV3", "COMMERCIAL LENDING"),
    # Singular/plural are one spelling; the corpus writes both.
    "CIB": ("CIB", "SV4", "CIB CAPITAL MARKETS", "CORP INVESTMENT BANKING",
            "CORPORATE INVESTMENT BANKING", "CIB BANKING"),
    "RIA": ("RIA", "SV5", "RIAS BROKER DEALERS", "RIA BROKER DEALER",
            "RIA BROKER DEALERS", "WEALTH RIAS"),
    "AM": ("AM", "SV6", "ASSET MANAGEMENT", "ASSET WEALTH MANAGEMENT",
           "WEALTH ASSET MANAGEMENT"),
    "IB": ("IB", "SV7", "INSURANCE BROKERS", "INSURANCE BROKER",
           "INSURANCE BROKERAGES", "INSURANCE BROKERAGE"),
    "IC": ("IC", "SV8", "INSURANCE CARRIERS", "INSURANCE CARRIER"),
    "FC": ("FC", "SV9", "FARM CREDIT", "FARM CREDIT AG LENDING"),
}
_ALIAS_INDEX = {alias: code
                for code, aliases in _SUBVERTICAL_ALIASES.items()
                for alias in aliases}

# A T2 variant cell's terminal segment: an uppercase code and an ordinal
# ("CU1", "RIA3", "IC12"). A base cell's terminal segment is numeric, so
# this never matches one.
_VARIANT_SEGMENT = re.compile(r"^([A-Z]+)([0-9]+)$")


def _norm(value: str) -> str:
    """'RIA / Broker-Dealer', 'ria broker dealer' and 'RIA_Broker Dealer'
    are one spelling: uppercase, non-alphanumerics collapse to a space."""
    return re.sub(r"[^A-Z0-9]+", " ", str(value).upper()).strip()


# An SV token anywhere in the string: SV1, SV 1, SV-04, SV_9. Bounded on
# both sides so "SV12" never reads as SV1 and a bare "5" never reads at all.
_SV_TOKEN = re.compile(r"(?<![A-Z0-9])SV\s*0?([1-9])(?![0-9])")
_SV_TO_CODE = {"1": "RB", "2": "CU", "3": "CL", "4": "CIB", "5": "RIA",
               "6": "AM", "7": "IB", "8": "IC", "9": "FC"}


def _codes_in(text: str) -> set:
    """Every sub-vertical code this string names, by either vocabulary."""
    found = {_SV_TO_CODE[m] for m in _SV_TOKEN.findall(text)}
    # Longest alias first, so "CREDIT UNIONS" is read before "CU" and a
    # phrase never loses to a fragment of itself.
    for alias in sorted(_ALIAS_INDEX, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])", text):
            found.add(_ALIAS_INDEX[alias])
    return found


def resolve_subvertical(raw) -> str | None:
    """The catalogue's VC code for an entity's sub_vertical, or None.

    None means neither vocabulary knows the value, or the two disagree —
    the caller says so rather than guessing (a wrong arrangement is worse
    than none).

    ## Why this reads TOKENS and no longer the whole string

    It used to be `_ALIAS_INDEX.get(_norm(raw))` — an exact lookup of the
    entire normalised value. That resolves `"SV2"` and `"Credit Unions"`
    and nothing else, and the form every assessment manifest actually
    writes is the COMPOUND one:

        "SV5 — RIAs & Broker-Dealers (Canada)"   -> None
        "SV1 — Regional Banks"                   -> None
        "SV9 Farm Credit / Ag Lending"           -> None

    Measured 2026-08-15 across the 120 manifests in the corpus: 61
    distinct spellings, and most of them missed. The consequence is worse
    than a missing label, because `serves()` treats None as "keep
    everything" — deliberately, since not knowing who you are is not
    grounds for hiding scores. So the T2 variant exclusion did not fail
    loudly on those entities; it silently did NOTHING, and an unscoped run
    is indistinguishable from a correctly scoped one at every layer above.
    `CHECK_NEVER_RAN_READS_AS_UNKNOWN`, in the module whose entire job is
    the check.

    The second client is the live case: its stated sub-vertical is
    `"SV5 — RIAs & Broker-Dealers (Canada)"`, so nothing was ever scoped
    for it. The reference client only worked because its DIRECTORY row
    happens to carry the bare `"SV2"`.

    ## Agreement, not first-match

    Both vocabularies are read and they must AGREE. A string naming two
    different sub-verticals — `"Insurance & Wealth — mutual/fraternal
    (IC/AM)"` is a real corpus value — resolves to None rather than to
    whichever the code happened to check first. That is the same rule as
    everywhere else here: a contradiction is stated, never resolved by
    ordering. Ambiguity keeps every cell, which is the safe direction.
    """
    # No empty-guard: `_codes_in` already answers "" and None with the empty
    # set, so a guard here only restates the result. Mutating its `or` to an
    # `and` changed nothing, which is how the mutation check reported it —
    # a branch whose two sides agree is not a decision, it is noise pretending
    # to be care.
    codes = _codes_in(_norm(raw)) if raw is not None else set()
    return codes.pop() if len(codes) == 1 else None


def scope_status(raw) -> dict:
    """Whether scoping is actually in force for this entity, and why not.

    The permissive fallback above is correct and it is also invisible: a
    run serving every variant because its sub-vertical did not resolve
    looks exactly like a run serving every variant because they all
    belong to it. This is what lets a caller — the audit script, a test,
    an operator — tell those apart. Nothing branches on it; it reports.
    """
    if not raw or not str(raw).strip():
        return {"scoped": False, "code": None, "reason": "no sub-vertical stated"}
    codes = _codes_in(_norm(raw))
    if len(codes) == 1:
        return {"scoped": True, "code": next(iter(codes)), "reason": None}
    if not codes:
        return {"scoped": False, "code": None,
                "reason": f"unrecognised sub-vertical {str(raw)!r}: neither an "
                          "SV token nor a known label. Every T2 variant "
                          "serves, including any belonging to another "
                          "sub-vertical."}
    return {"scoped": False, "code": None,
            "reason": f"ambiguous sub-vertical {str(raw)!r}: names "
                      f"{sorted(codes)}. Two readings disagree, so none is "
                      "applied — every T2 variant serves."}


def variant_subvertical(subcap_id) -> str | None:
    """The sub-vertical a VARIANT cell belongs to, or None.

    None for a base cell (`P1C1.3.2`), and also for a variant whose code
    is a family or product line rather than a sub-vertical (`P1C2.7.BK1`,
    `P3C4.2.PEN1`) — see the module docstring. None always means "this
    cell is not evidence of belonging to one sub-vertical", never "this
    cell belongs to no one".
    """
    if not subcap_id:
        return None
    match = _VARIANT_SEGMENT.match(str(subcap_id).rsplit(".", 1)[-1])
    if not match:
        return None
    code = match.group(1)
    return code if code in SUBVERTICAL_CODES else None


def serves(subcap_id, entity_code: str | None) -> bool:
    """May a run for an entity of `entity_code` serve this cell?

    True for every base cell, every family/product variant and every
    variant of the entity's own sub-vertical. False only for a variant
    that names a DIFFERENT sub-vertical. An entity whose sub-vertical
    resolves to None (unknown vocabulary) keeps everything: not knowing
    who you are is not grounds for hiding scores.
    """
    if not entity_code:
        return True
    owner = variant_subvertical(subcap_id)
    return owner is None or owner == entity_code


# ── END SHARED CORE — everything below is this service's own ──


def scope_to_entity(rows, entity_sub_vertical, key=None) -> list:
    """`rows` less the cells belonging to another sub-vertical.

    `rows` may be bare cell ids (`key=None`), DB tuples (`key` an integer
    column index) or dicts (`key` a column name). Order is preserved — the
    caller's ORDER BY is the served order — and the result is a list so
    callers can count it without re-querying (invariant 8: counts are
    computed from the rows actually served, never from a stored total).
    """
    code = resolve_subvertical(entity_sub_vertical)
    if code is None:
        return list(rows)
    # One subscript serves both shapes: an integer indexes a DB tuple, a
    # string keys a dict.
    read = (lambda row: row) if key is None else (lambda row: row[key])
    return [r for r in rows if serves(read(r), code)]


# ── serving a whole section, not just a row list ──────────────────────
# The keys a payload uses to name a cell. Taken from the connector's own
# `_CELL_KEYS` / `_is_cell_key` (validation2.py) so the gate that refuses a
# foreign cell at submit and the filter that drops one at serve are looking
# at the same fields — the two halves disagreeing about WHERE a cell id can
# live is the same drift as disagreeing about what one means.
_CELL_KEYS = ("capability_ids", "subcaps", "anchor_cells", "addressable_cells")


def _is_cell_key(key: str) -> bool:
    return (str(key).endswith(("subcap_id", "subcap_ids"))
            or str(key) in _CELL_KEYS)


def scope_sections(entity_sub_vertical, data) -> int:
    """Drop foreign-variant cells from a section payload, in place.

    Returns how many were dropped, so a caller can log or assert it rather
    than trust it (invariant 8: counted, never assumed).

    Two shapes, because payloads use both: a LIST of objects each naming a
    cell (`cells[].subcap_id`) has its foreign members removed; a list of
    bare cell ids (`linked_subcap_ids`) has its foreign entries removed. A
    scalar `subcap_id` on an object is handled by the first case — the
    object is dropped whole, because a synthesis card about a cell that does
    not apply is not improved by deleting its id.

    An unresolved sub-vertical drops nothing, as everywhere else here.
    """
    code = resolve_subvertical(entity_sub_vertical)
    if code is None or not isinstance(data, (dict, list)):
        return 0
    dropped = 0

    def walk(node):
        nonlocal dropped
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if _is_cell_key(key) and isinstance(value, list):
                    kept = [v for v in value
                            if not isinstance(v, str) or serves(v, code)]
                    dropped += len(value) - len(kept)
                    node[key] = kept
                    continue
                if isinstance(value, list):
                    kept = []
                    for item in value:
                        cell = (item.get("subcap_id") or item.get("cell_id")
                                if isinstance(item, dict) else None)
                        if cell and not serves(cell, code):
                            dropped += 1
                            continue
                        kept.append(item)
                    node[key] = kept
                    for item in kept:
                        walk(item)
                    continue
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return dropped
