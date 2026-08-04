"""Identifier authority (stage 2.2) — one recogniser, four namespaces.

Recognition lives HERE and only here. Every module that needs to see an
evidence id imports these compiled objects; a test asserts object
identity (`is`, not equality) at every call site. The failure mode this
prevents is silent under-detection: the retired system carried five
different regexes with three digit bounds, none of which matched the
mint namespace — so genuine mints passed unchecked and fabricated mints
were equally invisible (TRD "One recogniser, four namespaces").

The four namespaces:
  package     E-nnn as it arrives; stored entity-qualified E-{ENT}-nnn
              (and run-qualified E-{ENT}-nnn-R{n} after a content change)
  mint        E-CC-nnn — the server's enrichment allocations
  connector   EV-{scope}-nnn
  internal    INT-{label}

Load-bearing properties, not stylistic ones: case-sensitive (lowercasing
makes every "e-" in prose a candidate), no partial match (the trailing
lookahead stops a match ending mid-token), order preserved (the
truncated-cell recovery path takes the FIRST token).
"""
from __future__ import annotations

import re

# The one compiled evidence-id recogniser (TRD §"One recogniser").
EID_TOKEN_RE = re.compile(
    r"\b(?:E|EV|INT)-[A-Z0-9]+(?:-[A-Z0-9]+){0,3}(?![A-Za-z0-9-])")

# The mint namespace within it. The agent never chooses these numbers; a
# payload attempting to mint one is fabrication by construction.
MINT_RE = re.compile(r"^E-CC-\d+$")

# The five id classes the agent may create (TRD "Five, and only five"),
# plus the authored recommendation id it shares with the package.
AGENT_ID_RES = {
    "ic_id": re.compile(r"^IC-\d{1,4}$"),
    "f_id": re.compile(r"^F-\d{1,3}$"),
    "fa_id": re.compile(r"^FA-\d{1,3}$"),
    "ts_id": re.compile(r"^TS-\d{1,3}$"),
    "wn_id": re.compile(r"^WN-\d{1,2}$"),
    "rec_id": re.compile(r"^REC-(?:[A-Z0-9]+-)?\d{1,3}$"),
}


def find_ids(text: str) -> list:
    """Every evidence-shaped token in the text, in order, duplicates
    retained — order is what the truncated-cell recovery path relies on."""
    return EID_TOKEN_RE.findall(text or "")


def is_mint(e_id: str) -> bool:
    return bool(MINT_RE.match(e_id))


def find_fabricated(claimed, allowed) -> list:
    """Claimed ids that are not in the allowed set, in claim order —
    including ids in the mint namespace, which the agent may use but
    never invent. Deduplicated, first occurrence kept."""
    allowed_set = set(allowed)
    seen = set()
    out = []
    for c in claimed:
        if c not in allowed_set and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def agent_id_class(identifier: str) -> str | None:
    """The class of an agent-creatable id, or None. Exactly six patterns
    match; everything else the agent sends as its own creation is
    rejected upstream."""
    for cls, rx in AGENT_ID_RES.items():
        if rx.match(identifier):
            return cls
    return None
