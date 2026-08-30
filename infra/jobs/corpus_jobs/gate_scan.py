"""`corpus-gate-scanner` — the third of the charter's three mandatory
Scheduler triggers (nightly, and every CI run).

    python -m corpus_jobs.gate_scan [--pack gs://...|path] [--fail-on-regression]

Reads the exported pack and the ceilings in
`packages/shared/corpus_gates.json`, measures each configured gate corpus-wide
as a rate, writes the result to `gate_results`, and — with
`--fail-on-regression`, which CI passes — exits non-zero when a ceiling is
breached, so a regression fails the build.

## What it does when nothing is configured

`corpus_gates.json` ships `{"gates": {}}` on purpose: its own header says the
ceilings are "set by MEASUREMENT of the current corpus, never by aspiration",
and that measurement is stage 8's. So today this Job measures every rate it
knows how to measure, PRINTS them all, records the scan in `audit_log`, and
writes no gate result, because a gate with no ceiling has no verdict.

That is the useful shape rather than a placeholder: the nightly produces the
numbers a ceiling would be set FROM, in a dated audit row, from the first
night it runs. Setting a ceiling later is then a matter of reading a log, not
of guessing.

## What it will not do

Invent a ceiling. Pass a gate it could not measure. Or record PASS for a gate
whose measure it does not implement — an unknown measure name is a loud
failure, because a ceiling silently ignored is worse than no ceiling.

## The measures, and their denominators

Each measure returns (numerator, denominator, per-client detail). A ceiling is
compared against numerator/denominator, and `detail` names the clients that
contributed, so a breach points at a client rather than at a number. A measure
whose denominator is zero is NOT_RUN with that as the reason — never PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .db import close, connect

CEILINGS_PATH = os.environ.get("CORPUS_GATES_PATH", "corpus_gates.json")
DEFAULT_PACK = os.environ.get(
    "PACK_URI",
    f"gs://{os.environ.get('GCP_PROJECT', 'digital-maturity-assessor')}"
    "-dmai-corpus-packs/packs/latest.json")


# ── the measures ───────────────────────────────────────────────────────
# Each takes the pack and returns (numerator, denominator, contributors).
# `contributors` is [(display_id, numerator, denominator)], so a breach names
# clients rather than a rate.

def _per_client(pack, num, den):
    rows = [(c["display_id"], num(c), den(c)) for c in pack["clients"]]
    return (sum(r[1] for r in rows), sum(r[2] for r in rows), rows)


def m_pages_not_promoted(pack):
    return _per_client(pack,
                       lambda c: c["pages_expected"] - c["pages_promoted"],
                       lambda c: c["pages_expected"])


def m_cells_thin_evidence(pack):
    return _per_client(pack, lambda c: c["cells_thin_evidence"],
                       lambda c: c["cells"])


def m_cells_without_catalogue_name(pack):
    return _per_client(pack, lambda c: c["cells_without_catalogue_name"],
                       lambda c: c["cells"])


def m_cells_without_score(pack):
    return _per_client(pack, lambda c: c["cells_without_score"],
                       lambda c: c["cells"])


def m_assessment_date_not_stated(pack):
    """The defect this build set out to remove: a date nobody stated,
    rendered beside a maturity score as though somebody had."""
    return _per_client(pack,
                       lambda c: 0 if c["assessment_date_is_stated"] else 1,
                       lambda c: 1)


def m_assessment_date_unknown(pack):
    return _per_client(
        pack,
        lambda c: 1 if c["assessment_date_basis"] == "UNKNOWN" else 0,
        lambda c: 1)


def m_refresh_overdue(pack):
    return _per_client(pack, lambda c: 1 if c["refresh_overdue"] else 0,
                       lambda c: 1)


def m_gates_not_run(pack):
    return _per_client(pack, lambda c: c["gates_not_run"],
                       lambda c: c["gates_recorded"])


def m_alerts_open(pack):
    return _per_client(pack, lambda c: c["alerts_open"], lambda c: c["cells"])


MEASURES = {
    "pages_not_promoted": m_pages_not_promoted,
    "cells_thin_evidence": m_cells_thin_evidence,
    "cells_without_catalogue_name": m_cells_without_catalogue_name,
    "cells_without_score": m_cells_without_score,
    "assessment_date_not_stated": m_assessment_date_not_stated,
    "assessment_date_unknown": m_assessment_date_unknown,
    "refresh_overdue": m_refresh_overdue,
    "gates_not_run": m_gates_not_run,
    "alerts_open": m_alerts_open,
}


# ── reading the inputs ─────────────────────────────────────────────────
def read_pack(uri: str) -> dict:
    if uri.startswith("gs://"):
        from google.cloud import storage
        bucket, _, path = uri[5:].partition("/")
        client = storage.Client()
        return json.loads(client.bucket(bucket).blob(path).download_as_bytes())
    with open(uri, "rb") as fh:
        return json.load(fh)


def read_ceilings(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            return json.load(fh).get("gates") or {}
    except FileNotFoundError:
        return {}


def evaluate(pack: dict, ceilings: dict) -> list[dict]:
    """One verdict per configured ceiling. Never a verdict for a gate that
    was not configured, and never a PASS for one that could not be measured.
    """
    out = []
    for gate_id, spec in sorted(ceilings.items()):
        measure = (spec or {}).get("measure", gate_id)
        fn = MEASURES.get(measure)
        if fn is None:
            out.append({"gate_id": gate_id, "measure": measure,
                        "result": "NOT_RUN",
                        "not_run_reason": (
                            f"no measure named {measure!r}; this scanner "
                            f"implements {', '.join(sorted(MEASURES))}"),
                        "detail": {"ceiling": (spec or {}).get("ceiling")}})
            continue
        num, den, rows = fn(pack)
        if den == 0:
            out.append({"gate_id": gate_id, "measure": measure,
                        "result": "NOT_RUN",
                        "not_run_reason": (
                            "the measure's denominator is zero — nothing in "
                            "the corpus could be measured, which is not a pass"),
                        "detail": {"numerator": num, "denominator": den,
                                   "ceiling": (spec or {}).get("ceiling")}})
            continue
        rate = num / den
        ceiling = (spec or {}).get("ceiling")
        if ceiling is None:
            out.append({"gate_id": gate_id, "measure": measure,
                        "result": "NOT_RUN",
                        "not_run_reason": "the gate states no ceiling",
                        "detail": {"numerator": num, "denominator": den,
                                   "rate": round(rate, 4)}})
            continue
        out.append({
            "gate_id": gate_id, "measure": measure,
            "result": "PASS" if rate <= ceiling else "FAIL",
            "not_run_reason": None,
            "detail": {
                "numerator": num, "denominator": den,
                "rate": round(rate, 4), "ceiling": ceiling,
                "direction": (spec or {}).get("direction", "max"),
                # The arithmetic, in the verdict (invariant 12).
                "arithmetic": f"{num}/{den} = {rate:.4f} vs ceiling {ceiling}",
                "worst_clients": sorted(
                    [{"display_id": d, "numerator": n, "denominator": t,
                      "rate": round(n / t, 4) if t else None}
                     for d, n, t in rows if n],
                    key=lambda r: -(r["rate"] or 0))[:10],
            }})
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="corpus_jobs.gate_scan")
    p.add_argument("--pack", default=DEFAULT_PACK)
    p.add_argument("--ceilings", default=CEILINGS_PATH)
    p.add_argument("--fail-on-regression", action="store_true",
                   help="exit non-zero on any FAIL (CI passes this)")
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        pack = read_pack(args.pack)
    except Exception as e:                                    # noqa: BLE001
        # A missing pack is a FAILURE, never an empty corpus: from the
        # outside the two are indistinguishable, and that mistake is silent.
        print(f"corpus-gate-scanner: cannot read pack {args.pack}: "
              f"{type(e).__name__}: {str(e)[:200]}", flush=True)
        return 1

    ceilings = read_ceilings(args.ceilings)
    print(f"corpus-gate-scanner: pack {args.pack} generated "
          f"{pack.get('generated_at')}, {pack['counts']['clients']} client(s); "
          f"{len(ceilings)} ceiling(s) configured", flush=True)

    # Every measure, every night, whether or not a ceiling names it — these
    # are the numbers a ceiling would be set FROM.
    measured = {}
    for name, fn in sorted(MEASURES.items()):
        num, den, _rows = fn(pack)
        measured[name] = {"numerator": num, "denominator": den,
                          "rate": round(num / den, 4) if den else None}
        rate = f"{num / den:.4f}" if den else "n/a (denominator 0)"
        print(f"  {name}: {num}/{den} = {rate}", flush=True)

    verdicts = evaluate(pack, ceilings)
    for v in verdicts:
        print(f"  gate {v['gate_id']} [{v['measure']}]: {v['result']}"
              + (f" — {v['not_run_reason']}" if v["not_run_reason"] else
                 f" — {v['detail'].get('arithmetic')}"), flush=True)

    if not args.no_write:
        conn = connect()
        try:
            cur = conn.cursor()
            for v in verdicts:
                # run_id NULL: a corpus gate is a claim about the corpus, not
                # about one run. The column is nullable for exactly this.
                cur.execute(
                    """INSERT INTO gate_results
                         (run_id, gate_id, result, not_run_reason, detail,
                          evaluated_at)
                       VALUES (NULL, %s, %s, %s, %s, %s)""",
                    (v["gate_id"], v["result"], v["not_run_reason"],
                     json.dumps(v["detail"]), now))
            # The scan itself is recorded even when no gate had a ceiling, so
            # a nightly that measured a clean corpus is distinguishable from
            # one that did not run.
            cur.execute(
                """INSERT INTO audit_log (actor, action, target, after_json,
                                          occurred_at)
                   VALUES ('corpus-gate-scanner', 'corpus_scan', %s, %s, %s)""",
                (args.pack, json.dumps({"ceilings": len(ceilings),
                                        "verdicts": len(verdicts),
                                        "measured": measured,
                                        "clients": pack["counts"]["clients"],
                                        "pack_generated_at":
                                            pack.get("generated_at")}), now))
            conn.commit()
            print(f"corpus-gate-scanner: recorded {len(verdicts)} gate "
                  "result(s) and one audit row", flush=True)
        finally:
            conn.close()
            close()

    failed = [v for v in verdicts if v["result"] == "FAIL"]
    if failed:
        print("corpus-gate-scanner: REGRESSION — "
              + ", ".join(v["gate_id"] for v in failed), flush=True)
        return 1 if args.fail_on_regression else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
