#!/usr/bin/env python3
"""The binding preflight — financial statements, LOB census, and the question
that was actually PUT TO A PERSON.

    python3 -m engine.preflight init  --entity "Golden 1 Credit Union" \
                                      --entity-id golden-1-cu --out pf.json
    python3 -m engine.preflight check --file pf.json [--json]
    python3 -m engine.preflight record --run R --file pf.json

WHY THIS EXISTS. The 2026-08-29 Golden 1 calibration bound a sub-vertical,
a scope and an evidence mode from three free-text strings an agent wrote to
itself. `--sv-basis` said "single LOB"; nothing had read a revenue line, and
nobody had been asked. `runstate.vet_basis` refused FILLER, which is a real
guard against `tbd`, and no guard at all against a fluent assertion — the
failure mode that actually costs a run, because a confident sentence passes
every length and vocabulary check ever written.

So the basis is no longer a sentence. It is a FILE, and the file has to
contain three things a sentence cannot fake:

  1. **The financial-statement review.** Named statements with URLs, and the
     revenue lines read out of them, each line naming the line of business it
     implies. A run may proceed without one — some entities publish nothing —
     but only by recording the negative ladder that establishes that, the
     same discipline every absence in this engine already carries.
  2. **The LOB census.** Every material line of business, and for every
     sub-vertical a candidate verdict with a reason. A material LOB with no
     verdict is the multi-LOB trap: the entity has a second business nobody
     examined, and 165 variant cells were selected on the strength of the
     first one.
  3. **The question, and the answer.** `AskUserQuestion` put to the
     engagement owner, with what was asked, what the options were, and what
     came back. The bound sub-vertical MUST be the one that came back. This
     is the only check in the engine that cannot be satisfied by reasoning
     harder, which is exactly why it is here: an agent can talk itself into a
     sub-vertical, and it cannot talk itself into a recorded human answer.

The refusals name the missing field and the call that fills it, because an
unattended session must be able to ACT on a refusal rather than only read it.
"""
from __future__ import annotations

# Runnable both ways: -m engine.preflight, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

from . import contract as C

CONTRACT = "preflight-v1"

#: A line of business at or above this share of revenue is MATERIAL: it
#: selects variant cells, and it may not go unexamined. Below it, a line can
#: be noted and passed over. 10% is the level at which a second business
#: changes which of the 165 sub-vertical variant cells belong in the run.
MATERIAL_SHARE_PCT = 10.0

#: Free text that reads as an answer without being one. Shared spirit with
#: runstate._BASIS_BANNED, kept separate because a preflight answer is a
#: transcript of a person, not a rationale an agent composed.
_BANNED = ("tbd", "todo", "placeholder", "lorem", "xxx", "n/a", "unknown",
           "not applicable", "same as above", "see above")
_MIN_REASON = 20
_MIN_LADDER = 40


class PreflightRefusal(ValueError):
    """The preflight is not a binding basis yet, and here is what is missing."""


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _is_filler(text: str, *, minimum: int = _MIN_REASON) -> bool:
    t = _clean(text)
    low = t.lower()
    return len(t) < minimum or any(b in low for b in _BANNED)


# ── the skeleton an agent fills ──────────────────────────────────────────

def skeleton(*, entity: str, entity_id: str, run_id: str | None = None,
             website: str | None = None) -> dict:
    """A preflight with every required field present and EMPTY.

    Empty on purpose. A skeleton pre-filled with plausible defaults is how a
    binding gets asserted rather than established; this one cannot pass
    `check` until a person and a financial statement have both been consulted.
    """
    return {
        "_contract": CONTRACT,
        "_how_to_fill": (
            "1) find the entity's financial statements (call report, annual "
            "report, 10-K, statutory filing) and read the REVENUE lines out "
            "of them into financials.revenue_lines, each naming the line of "
            "business it implies; if none are published, set "
            "financials.not_run to the ladder you searched. "
            "2) census the lines of business, and give EVERY sub-vertical "
            "that could plausibly fit an ACCEPT or REJECT with a reason. "
            "3) put the binding to the engagement owner with AskUserQuestion "
            "and record what came back, verbatim, in binding_question. "
            "Then: engine.preflight check --file <this file>."),
        "run_id": run_id or "",
        "entity": {"name": entity, "entity_id": entity_id,
                   "website": website or "", "as_of": ""},
        "financials": {
            "statements": [],       # {source_name,url,kind,period,tier,retrieved_at}
            "revenue_lines": [],    # {line,amount,currency,period,share_pct,
                                    #  implies_lob,source}
            "not_run": "",          # the ladder, if nothing is published
        },
        "lob_census": {
            "lines_of_business": [],   # {lob,basis,revenue_share_pct,material}
            "candidates": [],          # {sub_vertical,verdict,reason}
        },
        "binding_question": {
            "asked": False, "tool": "AskUserQuestion", "question": "",
            "options": [], "answer": "", "answer_sub_vertical": "",
            "answered_by": "", "answered_at": "",
        },
        "mode_question": {
            "asked": False, "tool": "AskUserQuestion", "question": "",
            "options": [], "answer": "", "answer_mode": "",
            "answered_by": "", "answered_at": "",
        },
        "binding": {"sub_vertical": "", "evidence_mode": "",
                    "scope_mode": "FULL"},
    }


# ── the checks ───────────────────────────────────────────────────────────

def _check_financials(doc: dict, problems: list[str]) -> dict:
    fin = doc.get("financials") or {}
    statements = list(fin.get("statements") or [])
    lines = list(fin.get("revenue_lines") or [])
    not_run = _clean(fin.get("not_run"))

    if not statements and not lines:
        if not not_run:
            problems.append(
                "financials: no statement was reviewed and no revenue line "
                "was read. Find the call report / annual report / 10-K and "
                "record the revenue lines, or — if the entity publishes "
                "none — record the search ladder in financials.not_run. A "
                "sub-vertical bound without either is bound on nothing.")
        elif _is_filler(not_run, minimum=_MIN_LADDER):
            problems.append(
                f"financials.not_run = {not_run!r} is not a ladder. Name the "
                f"registries and queries that came back empty (NCUA/FFIEC "
                f"call report, EDGAR, state regulator, the entity's own "
                f"investor page), >= {_MIN_LADDER} chars.")
    else:
        for i, s in enumerate(statements):
            if not _clean(s.get("source_name")):
                problems.append(f"financials.statements[{i}]: no source_name")
            if not _clean(s.get("url")):
                problems.append(
                    f"financials.statements[{i}] "
                    f"({_clean(s.get('source_name')) or '?'}): no url — a "
                    f"statement nobody can reopen is not a review")
        if not lines:
            problems.append(
                "financials.revenue_lines is empty though a statement was "
                "reviewed. The point of the review is the revenue split; "
                "read the lines out, or say in financials.not_run why the "
                "statement carries none.")
        for i, ln in enumerate(lines):
            if not _clean(ln.get("line")):
                problems.append(f"financials.revenue_lines[{i}]: no line name")
            if not _clean(ln.get("implies_lob")):
                problems.append(
                    f"financials.revenue_lines[{i}] "
                    f"({_clean(ln.get('line')) or '?'}): implies_lob is empty "
                    f"— a revenue line that names no line of business cannot "
                    f"inform the census, which is the only reason to read it")
    shares = [float(ln.get("share_pct") or 0) for ln in lines
              if ln.get("share_pct") not in (None, "")]
    if shares and sum(shares) > 100.5:
        problems.append(
            f"financials.revenue_lines: share_pct sums to {sum(shares):.1f}% "
            f"— shares of one revenue base cannot exceed 100")
    return {"statements": len(statements), "revenue_lines": len(lines),
            "not_run": not_run or None,
            "share_total_pct": round(sum(shares), 2) if shares else None}


def _check_census(doc: dict, problems: list[str]) -> dict:
    cen = doc.get("lob_census") or {}
    lobs = list(cen.get("lines_of_business") or [])
    cands = list(cen.get("candidates") or [])
    known = set(C.taxonomy().sub_vertical_codes())

    if not lobs:
        problems.append(
            "lob_census.lines_of_business is empty. Even a single-line "
            "entity has one line of business, and stating it is what makes "
            "'single LOB' a finding rather than an assumption.")
    material = []
    for i, lob in enumerate(lobs):
        name = _clean(lob.get("lob"))
        if not name:
            problems.append(f"lob_census.lines_of_business[{i}]: no lob name")
            continue
        if _is_filler(lob.get("basis")):
            problems.append(
                f"lob_census.lines_of_business[{i}] ({name}): basis is empty "
                f"or filler — name the revenue line, charter or product set "
                f"this LOB is read from")
        share = lob.get("revenue_share_pct")
        flagged = bool(lob.get("material"))
        if share not in (None, "") and float(share) >= MATERIAL_SHARE_PCT:
            flagged = True
        if flagged:
            material.append(name)

    if not cands:
        problems.append(
            "lob_census.candidates is empty. Every sub-vertical that could "
            "plausibly fit needs an ACCEPT or a REJECT with a reason — the "
            "REJECTs are the record that the alternatives were considered.")
    accepted, verdicts = [], {}
    for i, c in enumerate(cands):
        sv = _clean(c.get("sub_vertical")).upper()
        verdict = _clean(c.get("verdict")).upper()
        if sv not in known:
            problems.append(
                f"lob_census.candidates[{i}]: sub_vertical {sv!r} is not one "
                f"of {', '.join(sorted(known))}")
            continue
        if verdict not in ("ACCEPT", "REJECT"):
            problems.append(
                f"lob_census.candidates[{i}] ({sv}): verdict {verdict!r} is "
                f"neither ACCEPT nor REJECT")
        if _is_filler(c.get("reason")):
            problems.append(
                f"lob_census.candidates[{i}] ({sv}): reason is empty or "
                f"filler — a verdict without a reason is a coin toss with "
                f"165 variant cells riding on it")
        verdicts[sv] = verdict
        if verdict == "ACCEPT":
            accepted.append(sv)

    if len(accepted) > 1 and not (doc.get("binding_question") or {}).get("asked"):
        problems.append(
            f"lob_census: {len(accepted)} sub-verticals are ACCEPTed "
            f"({', '.join(sorted(accepted))}) and no question was put to the "
            f"engagement owner. A multi-LOB entity is the case AskUserQuestion "
            f"exists for; it is not a tie for the agent to break.")
    if len(material) > 1 and not (doc.get("binding_question") or {}).get("asked"):
        problems.append(
            f"lob_census: {len(material)} MATERIAL lines of business "
            f"({', '.join(material[:4])}) and no question was put to the "
            f"engagement owner. Scope is theirs to decide.")
    return {"lines_of_business": len(lobs), "material": material,
            "candidates": len(cands), "accepted": sorted(accepted),
            "verdicts": verdicts}


def _check_question(doc: dict, key: str, field: str, vocabulary: tuple,
                    what: str, problems: list[str]) -> str:
    q = doc.get(key) or {}
    if not q.get("asked"):
        problems.append(
            f"{key}.asked is false. Put {what} to the engagement owner with "
            f"AskUserQuestion, then record the question, the options and the "
            f"verbatim answer here. This is the one check reasoning cannot "
            f"satisfy, and that is the point.")
        return ""
    if _is_filler(q.get("question")):
        problems.append(f"{key}.question is empty or filler")
    if not list(q.get("options") or []):
        problems.append(
            f"{key}.options is empty — record what the owner was choosing "
            f"BETWEEN, or the answer cannot be read back")
    if _is_filler(q.get("answer")):
        problems.append(
            f"{key}.answer is empty or filler — an unanswered question is "
            f"not a confirmation")
    if not _clean(q.get("answered_by")):
        problems.append(f"{key}.answered_by is empty — name who answered")
    value = _clean(q.get(field)).upper()
    if not value:
        problems.append(
            f"{key}.{field} is empty — say which of {', '.join(vocabulary)} "
            f"the answer resolves to, so the binding can be checked against it")
    elif value not in vocabulary:
        problems.append(
            f"{key}.{field} = {value!r} is not one of "
            f"{', '.join(vocabulary)}")
    return value


def check(doc: dict) -> dict:
    """Every refusal at once, so a fix pass closes them all in one turn."""
    problems: list[str] = []
    if str(doc.get("_contract") or "") != CONTRACT:
        problems.append(
            f"_contract is {doc.get('_contract')!r}, expected {CONTRACT!r} — "
            f"rebuild with: engine.preflight init")
    ent = doc.get("entity") or {}
    for f in ("name", "entity_id"):
        if not _clean(ent.get(f)):
            problems.append(f"entity.{f} is empty")

    fin = _check_financials(doc, problems)
    cen = _check_census(doc, problems)
    known_sv = tuple(sorted(C.taxonomy().sub_vertical_codes()))
    answered_sv = _check_question(doc, "binding_question", "answer_sub_vertical",
                                  known_sv, "the sub-vertical binding", problems)
    answered_mode = _check_question(doc, "mode_question", "answer_mode",
                                    C.ASSESSMENT_MODES,
                                    "the evidence mode (PUBLIC / INTERNAL / "
                                    "HYBRID)", problems)

    binding = doc.get("binding") or {}
    sv = _clean(binding.get("sub_vertical")).upper()
    mode = _clean(binding.get("evidence_mode")).upper()
    scope = _clean(binding.get("scope_mode")).upper() or "FULL"
    if not sv:
        problems.append("binding.sub_vertical is empty")
    elif answered_sv and sv != answered_sv:
        problems.append(
            f"binding.sub_vertical is {sv} but the engagement owner answered "
            f"{answered_sv}. The run binds what was CONFIRMED; change the "
            f"binding, or ask again and record the new answer.")
    if sv and cen["verdicts"].get(sv) == "REJECT":
        problems.append(
            f"binding.sub_vertical is {sv}, which lob_census.candidates "
            f"itself REJECTs. Bind what the census accepts, or correct the "
            f"census — the run cannot hold both readings.")
    if not mode:
        problems.append("binding.evidence_mode is empty")
    elif mode not in C.ASSESSMENT_MODES:
        problems.append(
            f"binding.evidence_mode {mode!r} is not one of "
            f"{', '.join(C.ASSESSMENT_MODES)}")
    elif answered_mode and mode != answered_mode:
        problems.append(
            f"binding.evidence_mode is {mode} but the engagement owner "
            f"answered {answered_mode}")
    if scope not in C.SCOPE_MODES:
        problems.append(
            f"binding.scope_mode {scope!r} is not one of "
            f"{', '.join(C.SCOPE_MODES)}")

    return {"ok": not problems, "problems": problems,
            "financials": fin, "census": cen,
            "binding": {"sub_vertical": sv, "evidence_mode": mode,
                        "scope_mode": scope},
            "sha256": digest(doc)}


def digest(doc: dict) -> str:
    """A stable digest of the preflight, minus its advisory prose."""
    body = {k: v for k, v in doc.items() if not k.startswith("_")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def load(path) -> dict:
    p = Path(path)
    if not p.exists():
        raise PreflightRefusal(
            f"no preflight at {p}. A run binds a sub-vertical, a scope and an "
            f"evidence mode; build the basis first with: "
            f"python3 -m engine.preflight init --entity '<Entity>' "
            f"--entity-id <id> --out {p}")
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise PreflightRefusal(f"{p} is not readable JSON: {e}") from None


def require(path) -> dict:
    """Load, check, and REFUSE with everything that is missing."""
    doc = load(path)
    report = check(doc)
    if not report["ok"]:
        raise PreflightRefusal(
            f"the preflight at {path} is not a binding basis yet — "
            f"{len(report['problems'])} problem(s):\n  - "
            + "\n  - ".join(report["problems"]))
    return {"doc": doc, "report": report}


# ── the bases the run is bound with, DERIVED not asserted ────────────────

def bases(doc: dict, report: dict | None = None) -> dict:
    """`sv_basis`, `mode_basis` and `lob_census` composed FROM the preflight.

    Composed, never typed: `runstate.vet_basis` refuses filler, and this
    refuses fiction, by making the sentence a rendering of the file rather
    than a claim beside it."""
    report = report or check(doc)
    cen = report["census"]
    fin = report["financials"]
    q = doc.get("binding_question") or {}
    mq = doc.get("mode_question") or {}
    sv = report["binding"]["sub_vertical"]

    if fin["revenue_lines"]:
        fin_txt = (f"{fin['revenue_lines']} revenue line(s) read from "
                   f"{fin['statements']} statement(s)")
    else:
        fin_txt = "no published statement (ladder recorded)"
    lobs = [_clean(l.get("lob")) for l in
            (doc.get("lob_census") or {}).get("lines_of_business") or []]
    rejected = [k for k, v in cen["verdicts"].items() if v == "REJECT"]

    who = _clean(q.get("answered_by")) or "the engagement owner"
    when = _clean(q.get("answered_at")) or "the recorded date"
    sv_basis = (
        f"{sv} confirmed by {who} on {when}; {fin_txt}; "
        f"LOB census: {', '.join(lobs) or 'none stated'}"
        + (f"; rejected {', '.join(sorted(rejected))}" if rejected else ""))
    mode_who = _clean(mq.get("answered_by")) or "the engagement owner"
    mode_basis = (
        f"{report['binding']['evidence_mode']} confirmed by {mode_who}: "
        f"{_clean(mq.get('answer'))}")
    census = "; ".join(
        f"{_clean(l.get('lob'))}"
        + (f" {float(l.get('revenue_share_pct')):.1f}%"
           if l.get("revenue_share_pct") not in (None, "") else "")
        for l in (doc.get("lob_census") or {}).get("lines_of_business") or []
    ) or "no line of business stated"
    if rejected:
        census += f" | rejected: {', '.join(sorted(rejected))}"
    return {"sub_vertical": sv,
            "evidence_mode": report["binding"]["evidence_mode"],
            "scope_mode": report["binding"]["scope_mode"],
            "sv_basis": sv_basis, "mode_basis": mode_basis,
            "lob_census": census, "preflight_sha": report["sha256"]}


# ── recording it into the run ────────────────────────────────────────────

def record(run, doc: dict, report: dict | None = None) -> dict:
    """Write the preflight into the workbook: the digest to Run_Metadata, the
    financial statements to the evidence register, and the review itself to
    Report_Narrative so the Client Research Profile can render it.

    The financial review is EVIDENCE, not a note. It grounds the firmographic
    section of the research report, and registering it here is what stops the
    report stage from researching the same statements a second time."""
    from . import ledger as L
    report = report or check(doc)
    wb = run.open()
    b = bases(doc, report)
    wb.set_metadata("preflight_sha", b["preflight_sha"])
    wb.set_metadata("lob_census", b["lob_census"])
    wb.set_metadata("sv_basis", b["sv_basis"])
    wb.set_metadata("mode_basis", b["mode_basis"])

    banked = []
    for s in (doc.get("financials") or {}).get("statements") or []:
        url = _clean(s.get("url"))
        excerpt = _clean(s.get("excerpt")) or _clean(
            f"{s.get('kind') or 'financial statement'} for "
            f"{s.get('period') or 'the stated period'}, reviewed during "
            f"binding preflight for revenue lines and lines of business: "
            f"{_clean(s.get('source_name'))}.")
        try:
            eid = L.append_evidence(
                wb, source_name=_clean(s.get("source_name")), source_url=url,
                tier=_clean(s.get("tier")) or "T2", excerpt=excerpt,
                subcaps=[], published=_clean(s.get("period_end"))
                or _clean(s.get("retrieved_at"))[:10] or None,
                claim_type="FACT", origin="public")
            banked.append(eid)
        except Exception as e:                              # noqa: BLE001
            banked.append(f"NOT_BANKED: {e}")

    lines = (doc.get("financials") or {}).get("revenue_lines") or []
    body = _render_review(doc, report, b)
    wb.append("Report_Narrative", {
        "Report": "client_research", "Section_ID": "PRELIM-FIN",
        "Heading": "Financial profile and lines of business",
        "Body": body,
        "Evidence_IDs": ", ".join(e for e in banked if not e.startswith("NOT_")),
        "Kind": "section", "Author": "preflight", "Written_At": _utcnow(),
    })
    return {"preflight_sha": b["preflight_sha"], "evidence_banked": banked,
            "revenue_lines": len(lines), "bases": b}


def _render_review(doc: dict, report: dict, b: dict) -> str:
    """The financial review as prose the research report can carry verbatim."""
    fin = doc.get("financials") or {}
    lines = fin.get("revenue_lines") or []
    ent = _clean((doc.get("entity") or {}).get("name"))
    out = []
    if lines:
        parts = []
        for ln in lines:
            share = ln.get("share_pct")
            amt = ln.get("amount")
            bits = _clean(ln.get("line"))
            if amt not in (None, ""):
                bits += f" ({ln.get('currency') or 'USD'} {amt:,})" if \
                    isinstance(amt, (int, float)) else f" ({amt})"
            if share not in (None, ""):
                bits += f", {float(share):.1f}% of revenue"
            lob = _clean(ln.get("implies_lob"))
            if lob:
                bits += f" — {lob}"
            parts.append(bits)
        out.append(
            f"{ent}'s published revenue divides across "
            f"{len(lines)} line(s): " + "; ".join(parts) + ".")
    elif _clean(fin.get("not_run")):
        out.append(
            f"{ent} publishes no revenue statement this review could reach. "
            f"The search that establishes that: {_clean(fin.get('not_run'))}")
    lobs = (doc.get("lob_census") or {}).get("lines_of_business") or []
    if lobs:
        out.append(
            "Lines of business: " + "; ".join(
                f"{_clean(l.get('lob'))} ({_clean(l.get('basis'))})"
                for l in lobs) + ".")
    rej = [k for k, v in report["census"]["verdicts"].items() if v == "REJECT"]
    if rej:
        out.append(
            f"Sub-verticals considered and set aside: {', '.join(sorted(rej))}.")
    q = doc.get("binding_question") or {}
    out.append(
        f"The assessment is bound to {b['sub_vertical']} on the engagement "
        f"owner's own answer ({_clean(q.get('answered_by')) or 'owner'}, "
        f"{_clean(q.get('answered_at')) or 'recorded'}): "
        f"“{_clean(q.get('answer'))}”.")
    return " ".join(out)


# ── command line ─────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.preflight",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="write the empty skeleton to fill")
    i.add_argument("--entity", required=True)
    i.add_argument("--entity-id", required=True)
    i.add_argument("--run")
    i.add_argument("--website")
    i.add_argument("--out", required=True)

    c = sub.add_parser("check", help="every refusal at once")
    c.add_argument("--file", required=True)
    c.add_argument("--json", action="store_true")

    r = sub.add_parser("record", help="write it into the run's workbook")
    r.add_argument("--run", required=True)
    r.add_argument("--root")
    r.add_argument("--file", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "init":
        doc = skeleton(entity=a.entity, entity_id=a.entity_id,
                       run_id=a.run, website=a.website)
        Path(a.out).write_text(json.dumps(doc, indent=2))
        print(f"preflight skeleton -> {a.out}\n"
              f"Fill it, then: python3 -m engine.preflight check --file {a.out}")
        return 0
    if a.cmd == "check":
        try:
            doc = load(a.file)
        except PreflightRefusal as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2
        rep = check(doc)
        if a.json:
            print(json.dumps(rep, indent=2))
        elif rep["ok"]:
            b = bases(doc, rep)
            print(f"PREFLIGHT OK — {b['sub_vertical']} / "
                  f"{b['evidence_mode']} / {b['scope_mode']}\n"
                  f"  sv_basis   : {b['sv_basis']}\n"
                  f"  mode_basis : {b['mode_basis']}\n"
                  f"  lob_census : {b['lob_census']}\n"
                  f"  sha256     : {b['preflight_sha'][:16]}…")
        else:
            print(f"REFUSED — {len(rep['problems'])} problem(s):")
            for p in rep["problems"]:
                print(f"  - {p}")
        return 0 if rep["ok"] else 1
    # record
    from . import runstate
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    doc = load(a.file)
    rep = check(doc)
    if not rep["ok"]:
        print("REFUSED: the preflight does not pass check; fix it first.",
              file=sys.stderr)
        for p in rep["problems"]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(json.dumps(record(run, doc, rep), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
