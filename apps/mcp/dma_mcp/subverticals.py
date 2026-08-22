"""Which catalogue cells a run may cite — the connector's copy.

**Source of truth: `apps/api/dma_api/subverticals.py`.** That module's
docstring carries the full derivation and the reasoning behind its
one-sided rule; read it there, not here. This file is a deliberate
MIRROR, not a second answer:

- the two services are separate deployables. `apps/mcp/Dockerfile` copies
  `dma_mcp/` and nothing else, so an import across the boundary resolves
  in the test run and fails in the image — the worst possible split.
- the fact being stated is one fact ("which sub-vertical does this cell
  id belong to"), so a copy is only safe if drift is impossible. It is
  made impossible by `tests/test_subvertical_scope.py`, which reads the
  API module when it is on disk and asserts both sides agree on the code
  vocabulary, the alias table and the derivation for a spread of ids.

The serving tier applies this on READ (a promoted run keeps every row the
workbook measured). The connector applies it at SUBMIT for the opposite
reason: a payload that CITES another sub-vertical's cell has reasoned
about a capability that does not apply to this institution, and no read
filter can repair that — the sentence beside the cell is already wrong.
Baxter Credit Union (SV2) reached a client surface citing 59 insurance
carrier / RIA / insurance broker variant cells.
"""
from __future__ import annotations

import re

# Mirrors SUBVERTICAL_CODES in apps/api/dma_api/subverticals.py.
SUBVERTICAL_CODES = ("RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB")

# Mirrors _SUBVERTICAL_ALIASES. Keys are _norm()-alised.

# ── THE SHARED CORE ───────────────────────────────────────────────────
# Byte-identical to `apps/api/dma_api/subverticals.py` from
# `_SUBVERTICAL_ALIASES` through `serves()`, and
# `test_subvertical_core_is_one_rule` asserts that on every run.
#
# The two services cannot import one module — each image copies only its
# own package — so the rule lives in two files. It had already drifted
# once: measured 2026-08-15, this copy and the API's had different
# `resolve_subvertical` bodies, which means a cell the connector admitted
# at submit could be one the API hid at serve, or the reverse. A gate and
# a filter disagreeing about who the client is is the worst possible place
# for this class of drift.
#
# Anything BELOW `serves()` is this service's own and does not sync.

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


SUBVERTICAL_NAMES = {
    "RB": "retail banking", "CU": "credit unions",
    "CL": "commercial lending", "CIB": "CIB / capital markets",
    "FC": "farm credit", "AM": "asset and wealth management",
    "RIA": "RIAs and broker-dealers", "IC": "insurance carriers",
    "IB": "insurance brokers",
}
