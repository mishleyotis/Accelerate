"""What may not appear in a sentence a client reads.

ONE PATTERN, TWO IMAGES. The connector refuses it at submit (CG-49) and the
api withholds it at serve (MEM-0137). Those are different jobs on the same
rule, and a rule held in two places drifts — MEM-0193's whole defect class,
and this build has paid for it more than once.

WHY BOTH ENDS ARE NEEDED, since either alone looks sufficient:

CG-49 refuses a MEM id inside a client-visible `empty_state.reason` at
submit. It protects everything submitted after it existed. It does nothing
for the three clients promoted before it, whose bodies carry the ids today.

MEM-0137's serve-side fix protects those. It cannot replace CG-49, because
the right repair for a bad sentence is a better sentence from the producer,
not a hole punched in a live page.

WHAT THIS IS NOT FOR. Ordinary English is not machinery: "no regulatory gate
applies", "the connector between the two systems", "staged for the next
cycle" are sentences a client may legitimately read, and a rule that refuses
them teaches producers to fight the gate rather than read it. So this matches
IDENTIFIERS and CALL SYNTAX — `MEM-0081`, `SG-V4`, `get_evidence(` — never
the words gate, connector or staged on their own.
"""
from __future__ import annotations

import re

#: An id or call that names this system's own machinery.
#:
#: Measured in production 2026-08-24 across three promoted clients: ten
#: customer-visible fields matched, including
#: `platform.starters.empty_state.sources_searched` carrying
#: `get_page_contract('platform')`, `r_layer` and the literal
#: `CUSTOMER_WITHHELD`, and `heatmap.safeguard_gates.empty_state
#: .sources_searched` carrying SG-01 and SG-V4.
INTERNAL_ID = re.compile(
    r"\b(?:MEM|REF)-\d{3,4}\b"                   # findings-memory ids
    r"|\b(?:CG|AG|ET)-\d{2,3}\b"                 # gate ids (SG below)
    r"|\bSG-[A-Z0-9]{1,3}\d?\b"                  # SG-01, SG-V4, SG-AC1
    r"|\bCUSTOMER_WITHHELD\b"                    # the redaction constant
    r"|\bno_staged_submission\b"
    r"|\b(?:get|list|submit|promote|register|record|resolve|report)_[a-z_]+\("
    , re.I)


def names_machinery(text) -> str | None:
    """The first internal identifier in `text`, or None.

    Returns the MATCH rather than a boolean so a caller can say what it
    found: a verdict that names the string is one a producer can act on, and
    a verdict that says "something in here" is one they have to hunt for.
    """
    if not isinstance(text, str):
        return None
    m = INTERNAL_ID.search(text)
    return m.group(0) if m else None


def scan(node, path: str = "") -> list:
    """[(path, matched_string)] over every string in a nested structure.

    A key filter cannot see this. `reason` is an allowed key and its VALUE is
    where the id sits, which is why the serve allowlist — correct as far as it
    goes — let ten fields through.
    """
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += scan(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += scan(v, f"{path}[{i}]")
    else:
        hit = names_machinery(node)
        if hit:
            out.append((path, hit))
    return out
