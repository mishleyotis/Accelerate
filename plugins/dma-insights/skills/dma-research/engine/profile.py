#!/usr/bin/env python3
"""The client's own facts — firmographics, priorities, issues, open gaps —
written into the workbook tabs the Client Profile and the app read.

    python3 -m engine.profile firmographic --run R --field website --value golden1.com \\
            --unit n/a --as-of 2026-08-31 --evidence E-002 --confidence High
    python3 -m engine.profile firmographic --run R --field cagr --state ABSENT \\
            --reason "a credit union returns surplus to members; no CAGR is published" \\
            --route "NCUA 5300 call reports FY2021-FY2025, searched 2026-08-31"
    python3 -m engine.profile focus --run R --id FA-01 --title "No single member view" \\
            --quote "<verbatim 50-400 chars>" --document "Illuminate Readout Jul 2024" \\
            --page 12 --cells P2C4,P4C1 --evidence E-005 [--currency AGING --note …]
    python3 -m engine.profile issue --run R --id I-001 --type "Data integration" \\
            --severity MATERIAL --status Active --description … --cells P4C1,P4C2 \\
            --evidence E-041 --as-of 2026-07-01
    python3 -m engine.profile enrichment-needed --run R --area Firmographics \\
            --field "3-year asset CAGR" --status PARTIAL --closes "FY2022-23 assets …"
    python3 -m engine.profile state --run R

WHY THIS EXISTS. Owner, 2026-09-03: "The workbook always defaults to the wrong
structure each time; missing fields etc." The gold-standard workbook (Golden 1)
carries Firmographics, Focus_Areas, Issue_Register and Enrichment_Needed, the
app reads all four (`workbook_parser._TAB_TARGET`: overview, H1 focus areas,
the stair-step's blocking findings, the enrichment facets), and the Client
Profile's §1, §6 and §7 are written FROM them. This engine had no tab and no
writer for any of them, so every run's profile was authored from prose and the
app's O2 strip and H1 focus areas rendered empty under the client's name —
measured across the corpus: "57 of 138 clients shipped with no focus areas at
all, and 53 shipped machine scoring text where a client quote belonged".

Every write goes through a refusal that is the Doc's own FAIL IF:

  firmographic  a must-present field is STATED (value + unit + as-of + evidence
                that resolves) or ABSENT / QUARANTINED with a real reason and
                the route searched — never blank, never a status word;
                `website` is bare and lowercased, `branches` is an integer
  focus         a verbatim quote of 50-400 characters that a PERSON wrote —
                no capability code, no maturity level, no diagnostic-question
                phrasing — with document, PAGE and the cells it bears on, all
                of them in this run
  issue         type, severity, status, capability impact and the cap the
                severity implies (read from Cap_Triggers, never typed)
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import re
import sys
from pathlib import Path

from . import contract as C
from . import rubric
from . import runstate
from .workbook import RunWorkbook, _split_ids


class ProfileRefusal(ValueError):
    """A client fact refused before it landed, with the reason."""


def _clean(v) -> str:
    return " ".join(str(v or "").split())


_STATUS_WORDS = re.compile(
    r"^(pending|queued|held|tbd|todo|n/?a|none|unknown|to be established.*|"
    r"not established.*|queued for enrichment)$", re.I)
_MACHINE_TEXT = re.compile(
    r"\bP[1-4]C\d\b|\bM[1-5]\b|\b(score|maturity)\s+(of\s+)?[1-5](\.\d)?\b|"
    r"\bcategory\s+P\d|\[[A-Z]{2,}-?\d*\]|\bto what extent\b|\bhow well\b",
    re.I)


def _resolve(wb: RunWorkbook, eids: str | list, *, where: str) -> list[str]:
    ids = [e.split(":")[0] for e in (eids if isinstance(eids, list)
                                     else _split_ids(eids)) if e]
    register = wb.evidence_index()
    dead = [e for e in ids if e not in register]
    if dead:
        raise ProfileRefusal(
            f"{where}: evidence {dead} does not resolve in this run's "
            f"register. Fail-closed (invariant 4): register the source first.")
    return ids


def _cells_in_run(wb: RunWorkbook, cells: str | list, *, where: str) -> list[str]:
    ids = [c for c in (cells if isinstance(cells, list) else _split_ids(cells)) if c]
    if not ids:
        raise ProfileRefusal(f"{where}: name the capability cell(s) it bears on")
    tax = C.taxonomy()
    selected = set(wb.selected_subcaps())
    cats = {s.split(".")[0] for s in selected}
    caps = {s.rsplit(".", 1)[0] for s in selected}
    bad = [c for c in ids if not (c in selected or c in cats or c in caps
                                   or c in tax.categories)]
    if bad:
        raise ProfileRefusal(
            f"{where}: {bad} name no cell, capability or category this run "
            f"serves — a priority mapped to a cell the run does not serve "
            f"renders nowhere.")
    return ids


# ── firmographics ────────────────────────────────────────────────────────

def firmographic(wb: RunWorkbook, *, field: str, value=None, unit: str = "",
                 as_of: str = "", evidence: str = "", confidence: str = "",
                 state: str = "STATED", reason: str = "", route: str = "") -> dict:
    field = _clean(field).lower().replace(" ", "_")
    if not field:
        raise ProfileRefusal("a firmographic needs a field name")
    state = _clean(state).upper() or "STATED"
    if state not in C.FIRMOGRAPHIC_STATES:
        raise ProfileRefusal(f"state {state!r} not in {C.FIRMOGRAPHIC_STATES}")
    row = {c: None for c in C.FIRMOGRAPHICS_COLUMNS}
    row["Field"] = field
    row["State"] = state
    if state == "STATED":
        val = _clean(value)
        if not val or _STATUS_WORDS.match(val):
            raise ProfileRefusal(
                f"{field}: {val!r} is not a value. A field the entity does not "
                f"disclose is --state ABSENT with a --reason a reader can act "
                f"on and the --route searched; a status word never renders.")
        if field == "website":
            if re.match(r"^(https?://|www\.)", val, re.I) or val != val.lower():
                raise ProfileRefusal(
                    f"website must be bare and lowercased ({val!r} carries a "
                    f"scheme, a www prefix or capitals) — it is the one "
                    f"firmographic that is load-bearing elsewhere in the app.")
        if field == "branches" and not re.fullmatch(r"\d+", val):
            raise ProfileRefusal(f"branches must serialise as an integer, not {val!r}")
        if not _clean(as_of):
            raise ProfileRefusal(f"{field}: a stated figure carries its as-at date")
        ids = _resolve(wb, evidence, where=field)
        if not ids:
            raise ProfileRefusal(f"{field}: a stated figure cites the evidence that states it")
        row.update({"Value": val, "Unit": _clean(unit) or "n/a", "As at": _clean(as_of),
                    "Evidence": ", ".join(ids),
                    "Conf.": _clean(confidence) or "Medium", "Reason": "", "Route": ""})
    else:
        if len(_clean(reason)) < 30 or _STATUS_WORDS.match(_clean(reason)):
            raise ProfileRefusal(
                f"{field}: an {state} field carries a REAL reason (>=30 chars) — "
                f"'a credit union returns its surplus to members' explains an "
                f"absent revenue field; 'queued for enrichment' is a status "
                f"word and must never appear.")
        if len(_clean(route)) < 20:
            raise ProfileRefusal(
                f"{field}: name the route attempted — the registry or source "
                f"searched, and when. An absence with no route is a statement "
                f"about the search, not the client.")
        row.update({"Value": f"{state} (see 1.2)", "Unit": _clean(unit) or "n/a",
                    "As at": _clean(as_of) or "", "Evidence": "see 1.2",
                    "Conf.": "n/a", "Reason": _clean(reason), "Route": _clean(route)})
    have = [r for r in wb.rows("Firmographics") if _clean(r.get("Field")).lower() == field]
    if have:
        wb.update_row("Firmographics", "Field", field, row)
    else:
        wb.append("Firmographics", row)
    return {"field": field, "state": state,
            "must_present_remaining": missing_firmographics(wb)}


def missing_firmographics(wb: RunWorkbook) -> list[str]:
    have = {_clean(r.get("Field")).lower() for r in wb.rows("Firmographics")}
    return [f for f in C.FIRMOGRAPHIC_MUST_PRESENT if f not in have]


# ── focus areas (client priorities, verbatim) ────────────────────────────

def focus(wb: RunWorkbook, *, fa_id: str, title: str, quote: str, document: str,
          page: str, cells, evidence: str, currency: str = "UNCONFIRMED",
          note: str = "") -> dict:
    fa_id = _clean(fa_id).upper()
    if not re.fullmatch(r"FA-\d{2}", fa_id):
        raise ProfileRefusal(f"focus id {fa_id!r} must be FA-NN")
    q = str(quote or "").strip()
    if not (50 <= len(q) <= 400):
        raise ProfileRefusal(
            f"{fa_id}: the quote is {len(q)} characters; the Doc requires a "
            f"verbatim 50-400 character span, trimmed at a clause boundary.")
    if _MACHINE_TEXT.search(q):
        raise ProfileRefusal(
            f"{fa_id}: the quote reads as machine text (a capability code, a "
            f"maturity level, a section tag or a diagnostic question's "
            f"phrasing). A priority is the CLIENT speaking, in a document a "
            f"person wrote about their own institution.")
    if not _clean(title) or len(_clean(title)) < 8:
        raise ProfileRefusal(f"{fa_id}: a priority carries a title in the client's words")
    if not _clean(document):
        raise ProfileRefusal(f"{fa_id}: name the source document")
    if not _clean(page):
        raise ProfileRefusal(
            f"{fa_id}: the page number is the provenance an account executive "
            f"points at in the room; without it the quote cannot be shown.")
    cur = _clean(currency).upper() or "UNCONFIRMED"
    if cur not in C.CURRENCY_STATUSES:
        raise ProfileRefusal(f"currency {cur!r} not in {C.CURRENCY_STATUSES}")
    ids = _resolve(wb, evidence, where=fa_id)
    cell_ids = _cells_in_run(wb, cells, where=fa_id)
    for r in wb.rows("Focus_Areas"):
        if (_clean(r.get("Priority in the client's words")).lower()
                == _clean(title).lower() and _clean(r.get("ID")).upper() != fa_id):
            raise ProfileRefusal(
                f"{fa_id}: a priority titled {title!r} already exists as "
                f"{r.get('ID')}. Two priorities that reduce to the same phrase "
                f"are one priority recorded twice.")
    row = {"ID": fa_id, "Priority in the client's words": _clean(title),
           "Verbatim quote": q, "Document": _clean(document), "Page": _clean(page),
           "Cells": ", ".join(cell_ids), "Evidence_IDs": ", ".join(ids),
           "Currency_Status": cur, "Currency_Note": _clean(note)}
    if any(_clean(r.get("ID")).upper() == fa_id for r in wb.rows("Focus_Areas")):
        wb.update_row("Focus_Areas", "ID", fa_id, row)
    else:
        wb.append("Focus_Areas", row)
    return {"id": fa_id, "cells": cell_ids, "rows": len(wb.rows("Focus_Areas"))}


# ── issue register ───────────────────────────────────────────────────────

def cap_for_severity(wb: RunWorkbook, severity: str) -> str:
    """The cap the severity implies, READ from Cap_Triggers when the scoring
    stage has written it, else from the contract's defaults — never typed."""
    sev = _clean(severity).upper()
    rows = wb.rows("Cap_Triggers") or [
        dict(zip(C.CAP_TRIGGERS_COLUMNS, r)) for r in C.CAP_TRIGGERS]
    for r in rows:
        if _clean(r.get("severity")).upper().startswith(sev):
            ms = r.get("max_score")
            return f"{float(ms):.1f} ({rubric.maturity_level(ms)})" if ms not in (None, "") else ""
    return ""


def issue(wb: RunWorkbook, *, issue_id: str, kind: str, severity: str, status: str,
          description: str, cells, evidence: str = "", as_of: str = "") -> dict:
    issue_id = _clean(issue_id).upper()
    if not re.fullmatch(r"I-\d{3}", issue_id):
        raise ProfileRefusal(f"issue id {issue_id!r} must be I-NNN")
    sev = _clean(severity).upper()
    if sev not in C.ISSUE_SEVERITIES:
        raise ProfileRefusal(f"severity {sev!r} not in {C.ISSUE_SEVERITIES}")
    st = _clean(status).title()
    if st not in C.ISSUE_STATUSES:
        raise ProfileRefusal(f"status {st!r} not in {C.ISSUE_STATUSES} — C2 wants a "
                             f"status that is never null")
    if len(_clean(description)) < 40:
        raise ProfileRefusal(f"{issue_id}: describe the matter (>=40 chars) — what, "
                             f"when, and its current state")
    cell_ids = _cells_in_run(wb, cells, where=issue_id)
    ids = _resolve(wb, evidence, where=issue_id) if _clean(evidence) else []
    if not ids:
        raise ProfileRefusal(f"{issue_id}: an issue is traced to a dated matter — "
                             f"cite the registered evidence that records it")
    row = {"ID": issue_id, "Type": _clean(kind), "Severity": sev, "Status": st,
           "Description": _clean(description), "Capability impact": ", ".join(cell_ids),
           "Cap": cap_for_severity(wb, sev), "Evidence_IDs": ", ".join(ids),
           "As_Of": _clean(as_of)}
    if any(_clean(r.get("ID")).upper() == issue_id for r in wb.rows("Issue_Register")):
        wb.update_row("Issue_Register", "ID", issue_id, row)
    else:
        wb.append("Issue_Register", row)
    return {"id": issue_id, "cap": row["Cap"], "rows": len(wb.rows("Issue_Register"))}


# ── enrichment needed ────────────────────────────────────────────────────

ENRICHMENT_STATUSES = ("OPEN", "PARTIAL", "AGING", "ESTIMATE", "RESOLVED")


def enrichment_needed(wb: RunWorkbook, *, area: str, field: str, status: str,
                      closes: str) -> dict:
    st = _clean(status).upper()
    if st not in ENRICHMENT_STATUSES:
        raise ProfileRefusal(f"status {st!r} not in {ENRICHMENT_STATUSES}")
    if len(_clean(closes)) < 20:
        raise ProfileRefusal("say WHAT would close the gap — the artefact, the "
                             "source or the question (>=20 chars)")
    row = {"Area": _clean(area), "Field / cell": _clean(field), "Status": st,
           "What would close it": _clean(closes)}
    wb.append("Enrichment_Needed", row)
    return {"rows": len(wb.rows("Enrichment_Needed"))}


# ── state ────────────────────────────────────────────────────────────────

def state(wb: RunWorkbook) -> dict:
    return {
        "firmographics": {
            "rows": len(wb.rows("Firmographics")),
            "must_present_missing": missing_firmographics(wb),
            "absent": [r["Field"] for r in wb.rows("Firmographics")
                       if _clean(r.get("State")) != "STATED"],
        },
        "focus_areas": {"rows": len(wb.rows("Focus_Areas")),
                        "floor": 3, "ceiling": 5},
        "issue_register": {"rows": len(wb.rows("Issue_Register"))},
        "enrichment_needed": {"rows": len(wb.rows("Enrichment_Needed"))},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.profile",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    f = common(sub.add_parser("firmographic"))
    f.add_argument("--field", required=True); f.add_argument("--value")
    f.add_argument("--unit", default=""); f.add_argument("--as-of", default="")
    f.add_argument("--evidence", default=""); f.add_argument("--confidence", default="")
    f.add_argument("--state", default="STATED", choices=C.FIRMOGRAPHIC_STATES)
    f.add_argument("--reason", default=""); f.add_argument("--route", default="")

    fo = common(sub.add_parser("focus"))
    fo.add_argument("--id", required=True); fo.add_argument("--title", required=True)
    fo.add_argument("--quote", required=True); fo.add_argument("--document", required=True)
    fo.add_argument("--page", required=True); fo.add_argument("--cells", required=True)
    fo.add_argument("--evidence", required=True)
    fo.add_argument("--currency", default="UNCONFIRMED", choices=C.CURRENCY_STATUSES)
    fo.add_argument("--note", default="")

    i = common(sub.add_parser("issue"))
    i.add_argument("--id", required=True); i.add_argument("--type", required=True)
    i.add_argument("--severity", required=True, choices=C.ISSUE_SEVERITIES)
    i.add_argument("--status", required=True); i.add_argument("--description", required=True)
    i.add_argument("--cells", required=True); i.add_argument("--evidence", required=True)
    i.add_argument("--as-of", default="")

    e = common(sub.add_parser("enrichment-needed"))
    e.add_argument("--area", required=True); e.add_argument("--field", required=True)
    e.add_argument("--status", required=True, choices=ENRICHMENT_STATUSES)
    e.add_argument("--closes", required=True)

    common(sub.add_parser("state"))
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "firmographic":
            out = firmographic(wb, field=a.field, value=a.value, unit=a.unit,
                               as_of=a.as_of, evidence=a.evidence,
                               confidence=a.confidence, state=a.state,
                               reason=a.reason, route=a.route)
        elif a.cmd == "focus":
            out = focus(wb, fa_id=a.id, title=a.title, quote=a.quote,
                        document=a.document, page=a.page, cells=a.cells,
                        evidence=a.evidence, currency=a.currency, note=a.note)
        elif a.cmd == "issue":
            out = issue(wb, issue_id=a.id, kind=a.type, severity=a.severity,
                        status=a.status, description=a.description, cells=a.cells,
                        evidence=a.evidence, as_of=a.as_of)
        elif a.cmd == "enrichment-needed":
            out = enrichment_needed(wb, area=a.area, field=a.field,
                                    status=a.status, closes=a.closes)
        else:
            out = state(wb)
        print(json.dumps(out, indent=2, default=str))
        return 0
    except ProfileRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
