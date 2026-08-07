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
# ("CU1", "RIA3", "IC12"). A base cell's terminal segment is numeric.
_VARIANT_SEGMENT = re.compile(r"^([A-Z]+)([0-9]+)$")

# Human names for the verdict text — a producer reading "IC" learns less
# than one reading "insurance carriers".
SUBVERTICAL_NAMES = {
    "RB": "retail banking", "CU": "credit unions",
    "CL": "commercial lending", "CIB": "CIB / capital markets",
    "FC": "farm credit", "AM": "asset and wealth management",
    "RIA": "RIAs and broker-dealers", "IC": "insurance carriers",
    "IB": "insurance brokers",
}


def _norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value).upper()).strip()


def resolve_subvertical(raw) -> str | None:
    """The catalogue's VC code for an entity's sub_vertical, or None.
    None means neither vocabulary knows the value — the caller says so
    rather than guessing."""
    if not raw or not str(raw).strip():
        return None
    return _ALIAS_INDEX.get(_norm(raw))


def variant_subvertical(subcap_id) -> str | None:
    """The sub-vertical a VARIANT cell belongs to, or None.

    None for a base cell (`P1C1.3.2`) and for a variant whose code is a
    family or product line rather than a sub-vertical (`P1C2.7.BK1`,
    `P3C4.2.PEN1`). None always means "this cell is not evidence of
    belonging to one sub-vertical", never "this cell belongs to no one".
    """
    if not subcap_id:
        return None
    match = _VARIANT_SEGMENT.match(str(subcap_id).rsplit(".", 1)[-1])
    if not match:
        return None
    code = match.group(1)
    return code if code in SUBVERTICAL_CODES else None


def serves(subcap_id, entity_code: str | None) -> bool:
    """May a run for an entity of `entity_code` cite this cell?

    True for every base cell, every family/product variant and every
    variant of the entity's own sub-vertical. False only for a variant
    that names a DIFFERENT sub-vertical. An entity whose sub-vertical
    resolves to None keeps everything: not knowing who you are is not
    grounds for refusing a citation.
    """
    if not entity_code:
        return True
    owner = variant_subvertical(subcap_id)
    return owner is None or owner == entity_code
