"""The empty fields on a promoted run, computed — never stored, never clicked.

Build owner, 2026-08-14: "Never place an em dash. There should always be a way
to send a signal to the MCP to give us an enrichment of the empty field with the
em dash."

An em dash is a dead end in two directions. It reads the same whether the
producer searched and found nothing, held a figure that failed the identity
gate, or was never asked — and a reader who meets one has no route to getting it
filled. This module is the second half: the route.

WHY IT IS COMPUTED RATHER THAN QUEUED. The obvious design is a table a reader
writes to. It was rejected, by the build owner, for the reason invariant 8
already gives about counts: where a source of truth exists, the value is
recomputed and never stored. The set of empty fields IS derivable at any moment
from the promoted payload against the contract, so a stored queue could only
disagree with reality — it would go stale the instant a page was re-promoted,
and a request nobody dequeued would keep asking for a field that had since been
filled. Computed, the worklist cannot drift, cannot be forgotten, and needs no
new write path anywhere (invariant 2 stands untouched: the API still writes only
annotations and alert actions).

So the signal is not a click. It is that this list exists and the producer reads
it. Every gap a reader sees on a surface is already in it.

WHAT COUNTS AS A GAP, and the distinction the whole module turns on:

    stated            a value is present                    -> not a gap
    held              null, quarantined, WITH a reason       -> not a gap; it is
                                                                a finding, and
                                                                the reason is
                                                                the content
    silent            null, or absent from the payload       -> A GAP
    empty-declared    the section declares an empty_state
                      with a ladder                          -> not a gap; the
                                                                search happened
                                                                and is recorded

A held field and a silent one look identical on a page rendering em dashes.
That is precisely the damage: one is the assessment's most defensible output and
the other is a hole, and the reader could not tell them apart.
"""

# ── ONE definition, imported ─────────────────────────────────────────
#
# The gap computation moved to packages/shared/enrichment_gaps.py so the
# CONNECTOR and the WORKER's enrichment routine cannot disagree about what is
# missing. Two copies of "what counts as missing" is the drift class this build
# has paid for four times now — the enrichment register that rendered on one
# surface of five, the pinned-row/pinned-key pair that duplicated CAGR,
# `founded` versus `founded_year`, and the api image that shipped without the
# register at all. This module is now a re-export so the connector's callers
# and its tests keep their import path.
import sys as _sys
from pathlib import Path as _Path

# Candidate roots, built LAZILY. In the image this module is
# /app/<pkg>/<name>.py — THREE parents — so `parents[3]` raises IndexError, and
# a tuple literal evaluates BOTH entries before the loop body runs, so it raises
# before the image path it would have found is ever tried. Exactly this killed
# the api once (computed.py) and the mcp container twice (deploy 8 and 9). The
# repo layout is optional; the image layout is not.
def _shared_roots():
    here = _Path(__file__).resolve()
    roots = [here.parent / "shared", here.parent.parent / "shared"]
    if len(here.parents) > 3:
        roots.append(here.parents[3] / "packages" / "shared")
    return roots


for _cand in _shared_roots():
    if _cand.exists() and str(_cand) not in _sys.path:
        _sys.path.insert(0, str(_cand))

from enrichment_gaps import (  # noqa: E402,F401  enrichment_gaps.py
    ENVELOPE_KEYS, NON_GAP_TYPES, gaps_for_payload, gaps_for_section,
    list_enrichment_gaps, _is_empty, _held, _empty_declared, _member_gaps,
    _norm,
)
