#!/usr/bin/env python3
"""Gate J — a client's surfaces must not be thinner than the gold.

THE DEFECT THIS EXISTS FOR. Three rounds of reports on one client said the
same thing in different words: "this page is empty", "this card is missing",
"Baxter has it and Logix does not". Every one of those was true, none of them
was visible to any check we had, and each was found by a human opening two
browser tabs side by side. A contract gate asks "is this field allowed"; it
cannot ask "does this client carry what the client next to it carries",
because both answers are contract-legal.

AND THEN IT WAS BLIND ANYWAY (RC-02, SWBC gold audit 2026-10-04). This gate
compared top-level keys and called any non-empty list filled, so ten
firmographic rows with six held, one sentiment bar against seven, and two of
eight platform tiles carrying peer rows all read identical to gold. It now
compares at ROW grain — list lengths, per-member fill inside list items
(a null member is unfilled), nested lists, and the stated-value share of a
fields-type list — through `apps/mcp/dma_mcp/parity.py`, the one
implementation the connector's promote path (CG-PAR) runs too. The rules
and their floors are documented there.

It never compares VALUES. Two clients are different companies; a thinner
number is an assessment result and not a defect. Only the SHAPE of what is
served is comparable.

WHAT REFUSES, AND WHAT ONLY WARNS (owner decision B, 2026-10-04). Exit 1
only on a STRUCTURAL gap: a section or key the gold always serves is
missing, or a must-present field is null or held beyond the decision-2 cap.
List-length and fill-ratio differences print as "(warning)" lines and never
fail the gate: how many rows a client has is an assessment result, and the
floors that measure it were never adjudicated. Against the gold, a gold run
is left out of its own reference set (--run-id / --exclude-gold), and gold
of the target's sub-vertical is preferred (--sub-vertical); with none, the
other gold is the reference for structure only.

WITHHELD IS NOT MISSING. A section withheld by audience is a served decision,
reported separately under "withheld by audience" and never as a gap.

usage:
    # against the committed gold shapes (the standard every run is held to)
    gate_j_surface_parity.py --gold fixtures/surface_gold.json --target-dir DIR \
        [--sub-vertical CU] [--run-id RUN_UUID] [--exclude-gold LABEL]
    gate_j_surface_parity.py --gold fixtures/surface_gold.json --target-file P.json --page overview
    gate_j_surface_parity.py --gold fixtures/surface_gold.json --api URL --target SLUG [--token T]
    # one client against another
    gate_j_surface_parity.py --api URL --reference SLUG --target SLUG [--token T] [--audience A]
    gate_j_surface_parity.py --reference-file a.json --target-file b.json --page overview

Exits 1 on a structural gap, 0 otherwise (warnings included). Stdlib only, like every other gate here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import parity  # noqa: E402  stdlib-only module

PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")


def compare_page(page: str, ref: dict, tgt: dict) -> list:
    """Structural gaps on one page against one reference. Pure, so the tests
    can drive it."""
    return parity.compare_shapes(page, ref, tgt)


def _fetch(base, slug, page, audience, token):
    import urllib.error
    import urllib.request
    url = f"{base.rstrip('/')}/v1/entities/{slug}/{page}?audience={audience}"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, 0


def _where(g):
    return ".".join(str(x) for x in (g["page"], g["section"], g["key"]) if x)


def _report(blocking, warnings, withheld, compared, against,
            preamble=()) -> int:
    # A COMPARISON THAT COMPARED NOTHING IS NOT A CLEAN COMPARISON, and this
    # gate said otherwise on its first live run: a mistyped reference slug
    # 404ed on all six pages and it printed "no structural gap". That is the
    # CHECK_NEVER_RAN_READS_AS_UNKNOWN shape, in the gate written to catch a
    # sibling of it.
    if not compared:
        print("Gate J: the reference served NO page — nothing was "
              "compared, so nothing is clean. Check the reference slug "
              "against /v1/directory and the audience the token can read.")
        return 1
    for line in preamble:
        print(line)
    for w in withheld:
        print(f"  [withheld by audience — a decision, not a gap] "
              f"{w['page']}.{w['section']}")
    for g in warnings:
        print(f"  (warning) [{g['kind']}] {_where(g)} — {g['detail']}")
    if not blocking:
        print(f"Gate J: no structural gap against {against} "
              f"({compared} page(s) compared, {len(warnings)} warning(s)).")
        return 0
    print(f"Gate J: {len(blocking)} structural gap(s) against {against}:")
    for g in blocking:
        print(f"  [{g['kind']}] {_where(g)} — {g['detail']}")
    return 1


def _split(page, gaps, tgt):
    """Classify pairwise gaps by today's contract: (blocking, warnings)."""
    tsecs = parity.page_shape(tgt).get("sections") or {}
    blocking, warnings = [], []
    for g in gaps:
        sev, _why = parity.classify(page, g, tsecs.get(g["section"]))
        if sev == "block":
            blocking.append(g)
        elif sev == "warn":
            warnings.append(g)
    return blocking, warnings


def _gold_disposition_withheld(gold, page, audience):
    if audience != "customer":
        return []
    out = []
    for key, d in sorted((gold.get("dispositions") or {}).items()):
        p, _, s = key.partition(".")
        if p == page and d.get("customer") in ("withheld", "page_withheld",
                                               "never_served"):
            out.append({"page": p, "section": s,
                        "kind": "withheld_by_audience"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--reference")
    ap.add_argument("--target")
    ap.add_argument("--token")
    ap.add_argument("--audience", default="internal")
    ap.add_argument("--reference-file")
    ap.add_argument("--target-file")
    ap.add_argument("--target-dir",
                    help="a directory of <page>.json (staged or served)")
    ap.add_argument("--gold",
                    help="the committed gold shapes, fixtures/surface_gold.json")
    ap.add_argument("--sub-vertical",
                    help="the target's sub-vertical code (CU, CL, IB, ...): "
                         "gold of the same sub-vertical is preferred")
    ap.add_argument("--run-id",
                    help="the target's run id: a gold run with this id is "
                         "left out of the reference set")
    ap.add_argument("--exclude-gold", action="append", default=[],
                    help="a gold label to leave out (repeatable)")
    ap.add_argument("--page", default="overview")
    a = ap.parse_args()

    blocking, warnings, withheld, compared = [], [], [], 0
    if a.gold:
        gold = parity.load_gold(Path(a.gold))
        targets = {}
        if a.target_file:
            targets[a.page] = json.loads(Path(a.target_file).read_text())
        elif a.target_dir:
            for page in PAGES:
                p = Path(a.target_dir) / f"{page}.json"
                if p.exists():
                    targets[page] = json.loads(p.read_text())
        elif a.api and a.target:
            # The gold is cut from the INTERNAL record, so the served page it
            # is compared with is the internal one; what the customer
            # audience does not see is reported from the dispositions.
            for page in PAGES:
                tgt, ts = _fetch(a.api, a.target, page, "internal", a.token)
                if tgt is None:
                    blocking.append({"page": page, "section": None,
                                     "key": None, "kind": "page_unreadable",
                                     "detail": f"HTTP {ts} for the target"})
                    continue
                targets[page] = tgt
        else:
            ap.error("--gold needs --target-file, --target-dir or --api/--target")
        res = parity.check_run(targets, gold, run_id=a.run_id,
                               sub_vertical=a.sub_vertical,
                               exclude=a.exclude_gold)
        blocking += res["blocking"]
        warnings += res["warnings"]
        compared = len(targets)
        for page in sorted(targets):
            withheld.extend(_gold_disposition_withheld(gold, page, a.audience))
        tier = ("gold of the same sub-vertical" if res["tier"] == "sub_vertical"
                else "no gold of this sub-vertical, so the other gold, for "
                     "structure only")
        preamble = [f"  reference: {tier}; left out: "
                    f"{', '.join(res['left_out']) or 'none'}"]
        preamble += [f"  (disclosed) [{d['kind']}] {_where(d)}"
                     for d in res["disclosed"]]
        return _report(blocking, warnings, withheld, compared,
                       f"the gold ({', '.join(res['compared_against'])})",
                       preamble)

    if a.reference_file and a.target_file:
        ref = json.loads(Path(a.reference_file).read_text())
        tgt = json.loads(Path(a.target_file).read_text())
        blocking, warnings = _split(a.page, compare_page(a.page, ref, tgt), tgt)
        withheld = parity.withheld_sections(a.page, ref, tgt)
        compared = 1
    elif a.api and a.reference and a.target:
        for page in PAGES:
            ref, rs = _fetch(a.api, a.reference, page, a.audience, a.token)
            tgt, ts = _fetch(a.api, a.target, page, a.audience, a.token)
            if ref is None:
                print(f"  [skip] reference {page}: HTTP {rs}")
                continue
            compared += 1
            if tgt is None:
                # A page the target cannot serve at all is the largest gap
                # there is, and it is not a shape question.
                blocking.append({"page": page, "section": None, "key": None,
                                 "kind": "page_unreadable",
                                 "detail": f"HTTP {ts} for the target while "
                                           f"the reference served"})
                continue
            b, w = _split(page, compare_page(page, ref, tgt), tgt)
            blocking += b
            warnings += w
            withheld.extend(parity.withheld_sections(page, ref, tgt))
    else:
        ap.error("--gold with a target, --api with --reference/--target, "
                 "or both --*-file")
    return _report(blocking, warnings, withheld, compared, "the reference")


if __name__ == "__main__":
    sys.exit(main())
