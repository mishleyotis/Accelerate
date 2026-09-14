"""WHICH ACTOR MAY WRITE WHICH CELL — one table, read by the engine and by
the hook.

THE GAP THIS CLOSES, measured 2026-09-14 across every write path: nothing in
the engine checked that an actor wrote only its own work. `append_evidence`
and `append_search` took no actor at all; `append_synthesis`,
`declare_absence` and `record_challenge` took one and used it only for
attribution and independence. The only cell-scope refusal anywhere was
run-membership (`evidence names cells outside this run's engagement set`),
which is a different question with a different answer. So
`research-p1c1-producer` could write every P3 cell in the run and no gate,
test or verdict would say so.

Containment was carried by three sentences of prose — the SessionStart
brief's "Work only your own category", the agent manifest's description, and
the conductor's "what you never do". Sixteen lanes run in parallel against
one workbook; prose is not a boundary.

WHAT IS DELIBERATELY NOT CONSTRAINED. An actor whose name matches none of
the patterns below is unconstrained, and that is the design rather than a
gap: the closed vocabulary is the set of agents this repository DISPATCHES,
and a name it does not recognise (a person, a one-off repair, a future
tier) must not be refused by a table that has never heard of it. The
refusals here are for the actors whose scope the run actually depends on.

THE CORRELATION POINT IS AN EXCEPTION, ON PURPOSE. A servicing actor — the
conductor draining a relay batch, or an enrichment specialist it dispatches
— logs searches and registers evidence against ANY cell in the run. That is
the whole mechanism by which one lane's find reaches another lane's cell.
What it may never do is form a judgement: no synthesis, no absence, no
challenge, no score. Retrieval crosses categories; judgement does not.
"""
from __future__ import annotations

import os
import re

#: `research-p1c1-producer` -> the one category it may write.
_CATEGORY_RESEARCHER = re.compile(r"^research-(p\d+c\d+)-producer$", re.I)
#: `scoring-p1-producer` -> the one pillar it may score.
_PILLAR_SCORER = re.compile(r"^scoring-(p\d+)-producer$", re.I)

#: Actors that exist to DISBELIEVE a synthesis. They challenge any cell and
#: write nothing else; `challenge_independence` still decides whether this
#: particular challenger may judge this particular cell.
_CHALLENGERS = frozenset({"research-challenger", "finding-challenger"})

#: Actors that RETRIEVE on behalf of the run. They may search and register
#: evidence anywhere — that is the correlation point — and judge nothing.
_SERVICING = frozenset({"research-conductor", "enrichment-web-specialist",
                        "enrichment-connector-specialist"})

_CRITICS = frozenset({"scoring-critic"})

#: Every op a write path can name. `note` is the memory notebook's entry.
OPS = ("search", "evidence", "attach", "synthesis", "absence", "challenge",
       "note", "score", "critique")

#: op -> the classes allowed to perform it. A class absent from a row may
#: not perform that op at all, whatever cell it names.
_ALLOWED = {
    "search":    {"category-researcher", "servicing", "technographic-scanner"},
    "evidence":  {"category-researcher", "servicing", "technographic-scanner"},
    "attach":    {"category-researcher", "servicing"},
    "note":      {"category-researcher", "servicing"},
    "synthesis": {"category-researcher"},
    "absence":   {"category-researcher"},
    "challenge": {"challenger"},
    "score":     {"pillar-scorer"},
    "critique":  {"critic"},
}

#: Classes whose cells are restricted to a prefix of their own name.
_SCOPED = {"category-researcher", "pillar-scorer"}


def actor_from_env() -> str:
    """The agent name the harness dispatched, for a CLI that was not told.

    A headless lane's hook cannot see which agent is running (the harness
    carries `agent_type` only inside a subagent), so `agent_run.py` puts the
    name in the child's environment and every write CLI defaults to it.
    """
    return str(os.environ.get("DMA_ACTOR") or "").strip()


def classify(actor: str | None) -> dict:
    """`{"class", "scope", "actor"}`. `class` is "" for an actor this table
    does not recognise, and `scope` is the cell prefix it is confined to."""
    name = str(actor or "").strip().lower()
    out = {"actor": name, "class": "", "scope": ""}
    if not name:
        return out
    m = _CATEGORY_RESEARCHER.match(name)
    if m:
        return {"actor": name, "class": "category-researcher",
                "scope": m.group(1).upper()}
    m = _PILLAR_SCORER.match(name)
    if m:
        return {"actor": name, "class": "pillar-scorer",
                "scope": m.group(1).upper()}
    if name in _CHALLENGERS:
        out["class"] = "challenger"
    elif name in _SERVICING:
        out["class"] = "servicing"
    elif name in _CRITICS:
        out["class"] = "critic"
    elif name == "technographic-scanner":
        out["class"] = "technographic-scanner"
    return out


def violation(actor: str | None, op: str, cells=None) -> str:
    """The reason this write is out of scope, or "" when it is in scope.

    Returns a sentence rather than raising, so the hook can print it and the
    ledger can raise it — one rule, two enforcers, one wording.
    """
    op = str(op or "").strip().lower()
    if op not in OPS:
        return ""                      # an op this table does not govern
    who = classify(actor)
    if not who["class"]:
        return ""                      # an actor this table does not govern
    allowed = _ALLOWED.get(op) or set()
    if who["class"] not in allowed:
        return (f"{who['actor']} may not {op}: that is the "
                f"{'/'.join(sorted(allowed)) or 'nobody'} tier's write. "
                f"A {who['class']} "
                + ("retrieves for the run and forms no judgement"
                   if who["class"] == "servicing" else
                   "writes only what its own tier is dispatched to write")
                + " — see engine/scope.py.")
    if who["class"] not in _SCOPED:
        return ""
    prefix = who["scope"]
    stray = sorted({str(c).strip().upper() for c in (cells or [])
                    if str(c).strip()
                    and not str(c).strip().upper().startswith(prefix)})
    if stray:
        return (f"{who['actor']} may write only {prefix} cells; this {op} "
                f"names {', '.join(stray[:6])}"
                + (f" and {len(stray) - 6} more" if len(stray) > 6 else "")
                + ". Sixteen lanes write one workbook in parallel: a lane "
                f"that writes another category's row overwrites work it "
                f"cannot see. If the source genuinely bears on that cell, "
                f"hand it up — the run's handback carries it to the lane "
                f"that owns it.")
    return ""
