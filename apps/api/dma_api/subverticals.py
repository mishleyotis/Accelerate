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
SCOPE_TAG = "sv-scope@1"

# Surface-Spec / manifest spellings -> the catalogue's VC subvertical_code.
# Two vocabularies exist: the serving tier stores the Surface Specification
# codes (SV1-SV9) or, in older manifests, a spelled-out label; the catalogue
# keys on the workbook codes. The pairs are unambiguous — SV1 "Regional
# Banks" is the workbook's "Retail Banking" (RB), SV7 "Insurance Brokers"
# is "Insurance Brokerages" (IB) — and this crosswalk is that pairing,
# nothing more. Keys are _norm()-alised.
_SUBVERTICAL_ALIASES = {
    "RB": ("RB", "SV1", "REGIONAL BANKS", "RETAIL BANKING"),
    "CU": ("CU", "SV2", "CREDIT UNIONS", "CREDIT UNION"),
    "CL": ("CL", "SV3", "COMMERCIAL LENDING"),
    "CIB": ("CIB", "SV4", "CIB CAPITAL MARKETS", "CORP INVESTMENT BANKING",
            "CORPORATE INVESTMENT BANKING", "CIB BANKING"),
    "RIA": ("RIA", "SV5", "RIAS BROKER DEALERS", "RIA BROKER DEALER",
            "RIA BROKER DEALERS", "WEALTH RIAS"),
    "AM": ("AM", "SV6", "ASSET MANAGEMENT", "ASSET WEALTH MANAGEMENT",
           "WEALTH ASSET MANAGEMENT"),
    "IB": ("IB", "SV7", "INSURANCE BROKERS", "INSURANCE BROKERAGES"),
    "IC": ("IC", "SV8", "INSURANCE CARRIERS"),
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


def resolve_subvertical(raw) -> str | None:
    """The catalogue's VC code for an entity's sub_vertical, or None.
    None means neither vocabulary knows the value — the caller says so
    rather than guessing (a wrong arrangement is worse than none)."""
    if not raw or not str(raw).strip():
        return None
    return _ALIAS_INDEX.get(_norm(raw))


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
