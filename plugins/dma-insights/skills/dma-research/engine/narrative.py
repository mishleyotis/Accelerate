#!/usr/bin/env python3
"""The report sections — written as arguments, not as prose.

    python3 -m engine.narrative state   --run R [--report assessment] [--json]
    python3 -m engine.narrative write   --run R --report assessment \
            --section 3 --json section.json --actor <agent>
    python3 -m engine.narrative review  --run R --report assessment \
            --section 3 --verdict PASS --actor <a different agent> --note "…"
    python3 -m engine.narrative contract [--report assessment]

WHY THIS EXISTS. The 2026-08-30 audit measured the report chain and found
sixteen sections — eight per report — with **no owner at all**. The renderer
reads `Report_Narrative` and refuses a missing section; nothing wrote one.
Every run that reached the report stage would have failed there, and the
Golden 1 run stopped before it, so the hole was never exercised.

Filling that hole with "an agent that writes the section" would reproduce the
defect one level up, because the audit's real questions were not *who types
it* but:

    how are arguments weighed · how are absences confirmed against proxies ·
    how are assumptions and bias noted · how is inference tagged and
    confirmed · how is accuracy measured

Prose cannot answer those. So a section is a RECORD with those fields beside
its body, each refused when it is empty or when it contradicts the workbook:

  `Weighing`        what was weighed against what, and why the balance fell
                    where it did. Must name at least one thing weighed
                    AGAINST the section's conclusion — a weighing with only
                    one side is a summary.
  `Absence_Basis`   every absence the body asserts, with its proxy ladder.
                    Checked: a body that says "no evidence" with no ladder
                    is refused, because that is a statement about the search.
  `Assumptions`     what the author assumed and which way it cuts.
  `Bias_Notes`      what would bias this section — source-availability skew,
                    sub-vertical priors, the client's own publishing habits.
  `Inference_Tags`  every `[INF]` mark in the body, enumerated with what
                    would confirm it. Body and enumeration must agree in
                    count, so an untagged inference is a refusal.
  `Accuracy_Basis`  COMPUTED, never typed: citation density, ERS mass,
                    the share of cited claims that survived challenge.

And the verdict is somebody else's: `review` refuses an actor that authored
the section, the same independence rule `record_challenge` enforces on a
synthesis (AUD-0018 / AUD-0024).
"""
from __future__ import annotations

# Runnable both ways: -m engine.narrative, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from . import contract as C
from . import ers as ERS
from . import quality as Q
from . import report_spec as RS
from . import runstate
from .workbook import RunWorkbook, _split_ids

#: Floors. Short enough that a real answer clears them, long enough that a
#: gesture does not.
MIN_WEIGHING = 120
MIN_ASSUMPTIONS = 60
MIN_BIAS = 60
MIN_LADDER = 60

#: The inline mark for a claim the evidence does not carry on its own.
INF = "[INF]"

#: Phrases that assert an absence. A body carrying one must also carry the
#: ladder that establishes it — otherwise it is reporting on the search.
_ABSENCE = re.compile(
    r"\b(no (?:public )?(?:evidence|record|disclosure|source|indication)|"
    r"nothing (?:public|found|disclosed)|not disclosed|undisclosed|"
    r"we found no|there is no published)\b", re.I)

#: A verdict on a section, from an actor that did not write it.
VERDICTS = ("PASS", "REVISE", "FAIL")

#: Each dimension a review must address by name. Same principle as
#: CHALLENGE_DIMENSIONS: required by name, not by count, so the one that
#: matters cannot be silently omitted.
REVIEW_DIMENSIONS = ("evidence_support", "weighing_balance", "absence_rigour",
                     "inference_honesty", "bias_disclosure", "tone")


class NarrativeRefusal(ValueError):
    """The section is not an argument yet, and here is what is missing."""


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _words(text: str) -> int:
    return len([w for w in re.split(r"\s+", _clean(text)) if w])


# ── the contract, per section ────────────────────────────────────────────

def section_spec(report: str, section_id: str):
    spec = RS.SPECS.get(report)
    if spec is None:
        raise NarrativeRefusal(
            f"unknown report {report!r}; one of {', '.join(RS.SPECS)}")
    for sec in spec.sections:
        if str(sec.id) == str(section_id):
            return spec, sec
    raise NarrativeRefusal(
        f"{report} has no section {section_id!r}; it has "
        f"{', '.join(str(s.id) for s in spec.sections)}")


def all_rows_for(wb: RunWorkbook, report: str) -> dict[str, list[dict]]:
    """Every row per section id. `insight_card`, `finding` and
    `recommendation` sections legitimately carry SEVERAL rows — one card
    each — and a verdict on one of them is not a verdict on the section."""
    out: dict[str, list[dict]] = {}
    for r in wb.rows("Report_Narrative"):
        if _clean(r.get("Report")) == report:
            out.setdefault(_clean(r.get("Section_ID")), []).append(r)
    return out


def rows_for(wb: RunWorkbook, report: str) -> dict[str, dict]:
    """One representative row per section — the LEAST reviewed one, so a
    multi-row section cannot read as signed off because its last card was."""
    out = {}
    for sid, rows in all_rows_for(wb, report).items():
        unreviewed = [r for r in rows
                      if _clean(r.get("Review_Verdict")).upper() != "PASS"]
        out[sid] = (unreviewed or rows)[0]
    return out


# ── the accuracy term, computed ──────────────────────────────────────────

def accuracy(wb: RunWorkbook, body: str, eids: list[str]) -> dict:
    """What can be MEASURED about a section's grounding.

    Typed accuracy claims are worthless — an author who is wrong is also
    wrong about being wrong. These four are read off the workbook."""
    register = wb.evidence_index()
    rows = [register[e] for e in eids if e in register]
    scores = []
    all_rows = wb.rows("Evidence_Detail")
    for r in rows:
        v = r.get("ERS")
        if v in (None, ""):
            v = ERS.score_row(r, all_rows)["ers"]
        scores.append(float(v))
    words = _words(body)
    challenged = 0
    for r in rows:
        for cell in _split_ids(r.get("SubCap_IDs")):
            row = wb.scoring_row(cell) or {}
            if _clean(row.get("Challenge_Verdict")).upper() == "PASS":
                challenged += 1
                break
    return {
        "cited_ids": len(eids),
        "resolved_ids": len(rows),
        "unresolved_ids": sorted(set(eids) - set(register)),
        "citation_density_per_100w": (round(100 * len(eids) / words, 2)
                                      if words else 0.0),
        "ers_mass": round(sum(scores), 2),
        "ers_mean": round(sum(scores) / len(scores), 2) if scores else None,
        "thin_sources": [r.get("E_ID") for r, s in zip(rows, scores)
                         if s < ERS.THIN_ERS],
        "cited_claims_that_survived_challenge": challenged,
        "words": words,
    }


def render_accuracy(acc: dict) -> str:
    return (f"{acc['cited_ids']} citation(s) over {acc['words']} words "
            f"({acc['citation_density_per_100w']}/100w); ERS mass "
            f"{acc['ers_mass']}"
            + (f", mean {acc['ers_mean']}" if acc["ers_mean"] else "")
            + f"; {acc['cited_claims_that_survived_challenge']} of "
              f"{acc['resolved_ids']} cited source(s) support a subcap whose "
              f"synthesis passed an independent challenge"
            + (f"; THIN: {', '.join(acc['thin_sources'])}"
               if acc["thin_sources"] else ""))


# ── writing a section ────────────────────────────────────────────────────

def write(wb: RunWorkbook, report: str, section_id: str, record: dict, *,
          actor: str) -> dict:
    """Write one section, or refuse and say which field is not an argument."""
    spec, sec = section_spec(report, section_id)
    if not _clean(actor):
        raise NarrativeRefusal("every section records its author; --actor is "
                               "how the review can refuse a self-review")
    body = _clean(record.get("Body"))
    problems: list[str] = []

    if _words(body) < sec.min_words:
        problems.append(
            f"Body is {_words(body)} words; §{sec.id} '{sec.heading}' "
            f"requires {sec.min_words}. The floor is the section's job "
            f"description, not a style preference.")

    eids = [e for e in _split_ids(record.get("Evidence_IDs")) if e]
    register = wb.evidence_index()
    unknown = [e for e in eids if e not in register]
    if unknown:
        problems.append(
            f"Evidence_IDs {', '.join(unknown)} do not resolve in this run's "
            f"register. Invariant 4 is fail-closed and a report section is "
            f"not exempt — it is the artefact a client reads.")
    if not eids:
        problems.append(
            "Evidence_IDs is empty. A section of a client-facing report that "
            "cites nothing is the shape of a hallucination, whatever it says.")

    weighing = _clean(record.get("Weighing"))
    if len(weighing) < MIN_WEIGHING:
        problems.append(
            f"Weighing is {len(weighing)} chars; {MIN_WEIGHING} is the floor. "
            f"Say what was weighed AGAINST the conclusion and why the balance "
            f"fell where it did.")
    elif not re.search(r"\b(against|counter|contradict|weighed|outweigh|"
                       r"despite|however|on the other|rejected)\b",
                       weighing, re.I):
        problems.append(
            "Weighing names nothing on the other side. A weighing with one "
            "side is a summary; name the counter-evidence considered, or the "
            "reading rejected, and why it lost.")

    absence_claimed = bool(_ABSENCE.search(body))
    ladder = _clean(record.get("Absence_Basis"))
    if absence_claimed and len(ladder) < MIN_LADDER:
        problems.append(
            f"the body asserts an absence ('{_ABSENCE.search(body).group(0)}') "
            f"and Absence_Basis is {len(ladder)} chars. Name the registries, "
            f"queries and dates that came back empty ({MIN_LADDER}+ chars) — "
            f"an unladdered absence is a statement about the search, not a "
            f"finding about the client.")

    assumptions = _clean(record.get("Assumptions"))
    if len(assumptions) < MIN_ASSUMPTIONS:
        problems.append(
            f"Assumptions is {len(assumptions)} chars; {MIN_ASSUMPTIONS} is "
            f"the floor. Name what you assumed and which way it cuts — an "
            f"unnamed assumption reads to a client as a fact.")
    bias = _clean(record.get("Bias_Notes"))
    if len(bias) < MIN_BIAS:
        problems.append(
            f"Bias_Notes is {len(bias)} chars; {MIN_BIAS} is the floor. "
            f"Public-evidence runs over-read what a client publishes and "
            f"under-read what it does not; say what skews THIS section.")

    marks = body.count(INF)
    tags = [t for t in re.split(r"\n|;\s", _clean(record.get("Inference_Tags")))
            if _clean(t)]
    if marks != len(tags):
        problems.append(
            f"the body carries {marks} {INF} mark(s) and Inference_Tags "
            f"enumerates {len(tags)}. Every inference is marked in place AND "
            f"enumerated with what would confirm it; a mismatch means an "
            f"inference is travelling as a fact.")
    for t in tags:
        # The tag must name an ACTION that would settle the inference.
        # "disclosure" was in this list and matched the word inside the
        # CLAIM ("reflects disclosure habit"), so a tag that said only what
        # was inferred passed the check meant to catch exactly that.
        if not re.search(r"\b(confirm(?:ed|s|ing)?|would (?:show|settle|"
                         r"establish|resolve)|verif(?:y|ied)|ask(?:ing)?|"
                         r"request(?:ing)?|check(?:ing)?|interview|obtain|"
                         r"review the|see the|sight of)\b", t, re.I):
            problems.append(
                f"inference tag {t[:60]!r} says what is inferred but not what "
                f"would CONFIRM it. An inference nobody can settle is a guess "
                f"with a label.")

    for field in ("Body", "Weighing"):
        why = Q.accusatory(_clean(record.get(field)), impact_field=True)
        if why:
            problems.append(f"{field}: {why}")

    excerpts = [_clean(register[e].get("Excerpt")) for e in eids
                if e in register]
    for fig in Q.ungrounded_numbers({"Body": body}, excerpts):
        problems.append(f"Body: {fig}")

    if problems:
        raise NarrativeRefusal(
            f"{report} §{sec.id} ('{sec.heading}') is not an argument yet — "
            f"{len(problems)} problem(s):\n  - " + "\n  - ".join(problems))

    acc = accuracy(wb, body, eids)
    row = {
        "Report": report, "Section_ID": str(sec.id),
        "Heading": _clean(record.get("Heading")) or sec.heading,
        "Body": body, "Evidence_IDs": ", ".join(eids),
        "Kind": sec.kind, "Author": _clean(actor), "Written_At": _utcnow(),
        "Weighing": weighing, "Absence_Basis": ladder,
        "Assumptions": assumptions, "Bias_Notes": bias,
        "Inference_Tags": "; ".join(tags),
        "Accuracy_Basis": render_accuracy(acc),
        # Written blank on purpose: the verdict is somebody else's, and a
        # section that arrives pre-approved is the defect this prevents.
        "Review_Verdict": "", "Review_Actor": "", "Review_At": "",
    }
    have = rows_for(wb, report).get(str(sec.id))
    if have:
        # Re-writing a section CLEARS its verdict: the thing that was
        # reviewed no longer exists.
        wb.update_row("Report_Narrative", "Section_ID", str(sec.id), row)
    else:
        wb.append("Report_Narrative", row)
    return {"report": report, "section": str(sec.id), "words": acc["words"],
            "accuracy": acc, "inferences": len(tags),
            "absence_claimed": absence_claimed}


def review(wb: RunWorkbook, report: str, section_id: str, *, verdict: str,
           actor: str, dimensions: dict, note: str) -> dict:
    """An independent verdict on one section."""
    spec, sec = section_spec(report, section_id)
    row = rows_for(wb, report).get(str(sec.id))
    if row is None:
        raise NarrativeRefusal(
            f"{report} §{sec.id} has not been written; there is nothing to "
            f"review.")
    author = _clean(row.get("Author"))
    if _clean(actor).lower() == author.lower():
        raise NarrativeRefusal(
            f"{actor} wrote this section. A verdict from its own author is "
            f"not a review — dispatch an actor that did not write it, the "
            f"same rule record_challenge applies to a synthesis.")
    v = _clean(verdict).upper()
    if v not in VERDICTS:
        raise NarrativeRefusal(
            f"verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
    missing = [d for d in REVIEW_DIMENSIONS if d not in (dimensions or {})]
    if missing:
        raise NarrativeRefusal(
            f"the review omits {', '.join(missing)}. Every dimension is "
            f"required BY NAME — the one that gets silently dropped is the "
            f"one that mattered.")
    if len(_clean(note)) < 80:
        raise NarrativeRefusal(
            "a review note under 80 chars is a rubber stamp. Say what you "
            "checked and what you found.")
    failed = [d for d, r in dimensions.items() if _clean(r).upper() != "PASS"]
    if v == "PASS" and failed:
        raise NarrativeRefusal(
            f"verdict PASS while {', '.join(failed)} did not pass. A verdict "
            f"that contradicts its own dimensions is not a verdict.")
    # A section's verdict covers EVERY row of that section. `update_row`
    # touches the first match only, so a multi-row insight-card section
    # would otherwise be reviewed one card at a time by accident.
    rows = all_rows_for(wb, report).get(str(sec.id)) or []
    authors = {_clean(r.get("Author")).lower() for r in rows}
    if _clean(actor).lower() in authors:
        raise NarrativeRefusal(
            f"{actor} authored at least one row of §{sec.id}. A verdict from "
            f"an author of the section is not a review.")
    ws = wb._sheet("Report_Narrative")
    cols = list(C.REPORT_NARRATIVE_COLUMNS)
    ci = {c: cols.index(c) + 1 for c in
          ("Report", "Section_ID", "Review_Verdict", "Review_Actor",
           "Review_At")}
    now = _utcnow()
    touched = 0
    for r_ in range(2, ws.max_row + 1):
        if (str(ws.cell(row=r_, column=ci["Report"]).value or "").strip()
                == report
                and str(ws.cell(row=r_, column=ci["Section_ID"]).value
                        or "").strip() == str(sec.id)):
            ws.cell(row=r_, column=ci["Review_Verdict"], value=v)
            ws.cell(row=r_, column=ci["Review_Actor"], value=_clean(actor))
            ws.cell(row=r_, column=ci["Review_At"], value=now)
            touched += 1
    wb.save()
    wb.append("Provenance", {
        "SubCap_ID": "", "Step": f"report_review:{report}:{sec.id}",
        "Actor": _clean(actor), "At": _utcnow(),
        "Detail": f"{v} — " + json.dumps(dimensions, sort_keys=True)
                  + " — " + _clean(note)[:300]})
    return {"report": report, "section": str(sec.id), "verdict": v,
            "actor": actor, "author": author, "rows_marked": touched}


# ── the state of both reports ────────────────────────────────────────────

def state(wb: RunWorkbook, report: str | None = None) -> dict:
    reports = [report] if report else list(RS.SPECS)
    out = {"reports": {}, "blocking": []}
    for key in reports:
        spec = RS.SPECS[key]
        have = rows_for(wb, key)
        secs = []
        for sec in spec.sections:
            r = have.get(str(sec.id))
            body = _clean(r.get("Body")) if r else ""
            if not r or not body:
                st, detail = "OPEN", "not written"
            elif _words(body) < sec.min_words:
                st, detail = "SHORT", (f"{_words(body)} of {sec.min_words} "
                                       f"words")
            elif not _clean(r.get("Review_Verdict")):
                st, detail = "UNREVIEWED", (
                    f"{_words(body)} words, written by "
                    f"{_clean(r.get('Author')) or '?'}, no independent verdict")
            elif _clean(r.get("Review_Verdict")).upper() != "PASS":
                st, detail = "REVISE", (
                    f"{_clean(r.get('Review_Verdict'))} by "
                    f"{_clean(r.get('Review_Actor'))}")
            else:
                st, detail = "READY", (
                    f"{_words(body)} words, PASS by "
                    f"{_clean(r.get('Review_Actor'))}")
            secs.append({"section": str(sec.id), "heading": sec.heading,
                         "kind": sec.kind, "min_words": sec.min_words,
                         "status": st, "detail": detail,
                         "fix": (f"engine.narrative write --report {key} "
                                 f"--section {sec.id}") if st in
                                ("OPEN", "SHORT", "REVISE") else
                                (f"engine.narrative review --report {key} "
                                 f"--section {sec.id}") if st == "UNREVIEWED"
                                else None})
        open_ = [s["section"] for s in secs if s["status"] != "READY"]
        words = sum(_words(_clean((have.get(str(s.id)) or {}).get("Body")))
                    for s in spec.sections)
        out["reports"][key] = {
            "title": spec.title, "sections": secs, "open": open_,
            "words": words, "min_words": spec.min_words,
            "ready": not open_ and words >= spec.min_words,
        }
        if open_:
            out["blocking"].append(f"{key}: §{', §'.join(open_)} not READY")
        elif words < spec.min_words:
            out["blocking"].append(
                f"{key}: {words} words against a {spec.min_words} floor")
    out["ready"] = not out["blocking"]
    return out


def require_ready(wb: RunWorkbook, report: str | None = None) -> dict:
    st = state(wb, report)
    if not st["ready"]:
        raise NarrativeRefusal(
            "the report is not ready to render:\n  - "
            + "\n  - ".join(st["blocking"])
            + "\n\nRun `engine.narrative state` for the per-section fix line.")
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.narrative",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    s = common(sub.add_parser("state"))
    s.add_argument("--report", choices=sorted(RS.SPECS))
    s.add_argument("--json", action="store_true")

    w = common(sub.add_parser("write"))
    w.add_argument("--report", required=True, choices=sorted(RS.SPECS))
    w.add_argument("--section", required=True)
    w.add_argument("--json", required=True, help="the section record")
    w.add_argument("--actor", required=True)

    r = common(sub.add_parser("review"))
    r.add_argument("--report", required=True, choices=sorted(RS.SPECS))
    r.add_argument("--section", required=True)
    r.add_argument("--verdict", required=True, choices=VERDICTS)
    r.add_argument("--actor", required=True)
    r.add_argument("--note", required=True)
    r.add_argument("--dimensions",
                   help="JSON {dimension: PASS|FAIL}; default all PASS on a "
                        "PASS verdict, which the refusals then re-check")

    c = sub.add_parser("contract")
    c.add_argument("--report", choices=sorted(RS.SPECS))

    a = ap.parse_args(argv)
    if a.cmd == "contract":
        for key in ([a.report] if a.report else sorted(RS.SPECS)):
            spec = RS.SPECS[key]
            print(f"\n{key} — {spec.title} ({spec.min_words}+ words)")
            for sec in spec.sections:
                print(f"  §{sec.id:<3} {sec.kind:<14} {sec.min_words:>4}w  "
                      f"{sec.heading}")
        print("\nevery section also requires: Weighing (names the other "
              "side), Absence_Basis (a ladder, when the body asserts an "
              "absence), Assumptions, Bias_Notes, Inference_Tags (matching "
              "the body's [INF] marks), and an independent Review_Verdict.")
        print("Accuracy_Basis is COMPUTED from the workbook, never typed.")
        return 0

    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    try:
        if a.cmd == "state":
            st = state(wb, a.report)
            if a.json:
                print(json.dumps(st, indent=2))
            else:
                for key, rep in st["reports"].items():
                    print(f"\n{key} — {rep['title']}  "
                          f"{rep['words']}/{rep['min_words']} words  "
                          f"{'READY' if rep['ready'] else 'OPEN'}")
                    for sec in rep["sections"]:
                        mark = {"READY": "✓", "UNREVIEWED": "~",
                                "SHORT": "✗", "OPEN": "✗", "REVISE": "✗"}[
                            sec["status"]]
                        print(f"  {mark} §{sec['section']:<3} "
                              f"{sec['status']:<11} {sec['detail']}")
                        if sec["fix"]:
                            print(f"       fix: {sec['fix']}")
            return 0 if st["ready"] else 1
        if a.cmd == "write":
            rec = json.loads(Path(a.json).read_text())
            print(json.dumps(write(wb, a.report, a.section, rec,
                                   actor=a.actor), indent=2))
            return 0
        dims = (json.loads(a.dimensions) if a.dimensions
                else {d: "PASS" for d in REVIEW_DIMENSIONS})
        print(json.dumps(review(wb, a.report, a.section, verdict=a.verdict,
                                actor=a.actor, dimensions=dims, note=a.note),
                         indent=2))
        return 0
    except NarrativeRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
