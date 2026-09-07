#!/usr/bin/env python3
"""Is this client an intake, a scoring job, a synthesis, or already served?

WHY THIS EXISTS. Measured 2026-08-30. A session was asked to finalise GoEasy.
It called `get_client_state("goeasy")`, got `unknown_entity`, read that as "no
package yet" and fired the ASSESSMENT INTAKE routine — the entry point for a
client with nothing in the system. GoEasy's real display_id is `goeasy-ltd`;
it already had four ingested runs and a finished research package. The firing
had to be interrupted before it pushed a preflight recommending research that
was already done.

Two separate misjudgements, each cheap to make and expensive to make often:

  1. THE NAME. `goeasy` is not `goeasy-ltd`, and a bare `unknown_entity` gave
     the caller nothing to notice that with. `get_client_state` now returns
     `did_you_mean`; this script uses it rather than making the caller read
     an error and infer.
  2. THE STAGE. Even with the right id, "has a package" is not one state. A
     research package with 0 scored cells is NOT synthesis work — the score
     column is empty by contract (rule 4) and synthesis may not derive one.
     Sending it to a producer spends a session to be told so; sending it to
     intake spends one re-preparing research that exists.

So the decision is made ONCE, here, from the connector's own answer, and
printed with the exact next command. A routing rule that lives only in a
prompt is re-derived by every session that reads it, and this one was
re-derived wrongly.

    python3 route_client.py --client "GoEasy"
    python3 route_client.py --client goeasy-ltd --json

Read-only. It calls `get_client_state` and nothing else, and it starts
nothing: the command it prints is for a human or a routine to run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The four answers. Each names the SKILL that owns the next step, because
#: "this client needs work" without naming which tier does it is how GoEasy
#: reached the wrong routine in the first place.
NEW_ENGAGEMENT = "NEW_ENGAGEMENT"
NEEDS_SCORING = "NEEDS_SCORING"
READY_TO_SYNTHESISE = "READY_TO_SYNTHESISE"
ALREADY_SERVED = "ALREADY_SERVED"
AMBIGUOUS = "AMBIGUOUS"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def client_state(display_id: str, runner=None) -> dict:
    """`get_client_state` through the raw bridge.

    The bridge rather than an MCP tool call on purpose: the intake Routine
    carries no connector of any kind (measured 2026-08-30), so a routing
    check that needed one would be exactly as unavailable as the thing it
    is meant to prevent.
    """
    runner = runner or _run_bridge
    return runner(display_id)


def _run_bridge(display_id: str) -> dict:
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "mcp_raw.py"), "call",
         "get_client_state", "--args", json.dumps({"display_id": display_id})],
        capture_output=True, text=True, timeout=180)
    if out.returncode != 0 and not out.stdout.strip():
        raise RuntimeError(
            f"the connector could not be reached: "
            f"{(out.stderr or '').strip()[:300]}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"get_client_state returned no JSON: {out.stdout[:300]!r}")


def _scored(runs: list) -> list:
    return [r for r in runs if int(r.get("scored_cells") or 0) > 0]


def decide(state: dict, asked_for: str) -> dict:
    """The verdict, from what the connector said and nothing else."""
    if state.get("error") == "unknown_entity":
        near = state.get("did_you_mean") or []
        if near:
            # NOT resolved automatically. Picking a client on a trigram score
            # is the same silent inference that routed GoEasy wrong, one
            # layer down — it would just be wrong less visibly.
            return {
                "verdict": AMBIGUOUS, "asked_for": asked_for,
                "did_you_mean": near,
                "why": (f"no entity has display_id {asked_for!r}, but "
                        f"{len(near)} near match(es) do. One of them may be "
                        f"this client under its real id — re-run against the "
                        f"id you mean rather than treating this as new."),
                "next": (f"python3 route_client.py --client "
                         f"{near[0]['display_id']}"),
            }
        return {
            "verdict": NEW_ENGAGEMENT, "asked_for": asked_for,
            "did_you_mean": [],
            "why": ("nothing in the corpus resembles this client, so it has "
                    "no package and no runs."),
            "next": ("the assessment intake path: preflight, binding, then "
                     "`dma-research` produces the package"),
        }

    runs = state.get("runs") or []
    served = state.get("served_pages") or []
    display_id = state.get("display_id") or asked_for
    scored = _scored(runs)

    if served:
        return {
            "verdict": ALREADY_SERVED, "display_id": display_id,
            "runs": len(runs), "scored_runs": len(scored),
            "served_pages": len(served),
            "why": (f"{len(served)} page(s) are already promoted. Anything "
                    f"further is a RERUN, which the skill requires be "
                    f"produced knowing what the last one said."),
            "next": "dma-surface-production, as a rerun",
        }
    if not runs:
        return {
            "verdict": NEW_ENGAGEMENT, "display_id": display_id,
            "runs": 0, "scored_runs": 0,
            "why": ("the entity exists but carries no runs, so no package "
                    "has been ingested for it."),
            "next": ("the assessment intake path: preflight, binding, then "
                     "`dma-research` produces the package"),
        }
    if not scored:
        return {
            "verdict": NEEDS_SCORING, "display_id": display_id,
            "runs": len(runs), "scored_runs": 0,
            "why": (f"{len(runs)} run(s) ingested and not one scored a "
                    f"cell. That is a RESEARCH package: its score column is "
                    f"empty by contract and synthesis may not derive one. It "
                    f"is not an intake either — a package exists. WHETHER "
                    f"THAT PACKAGE IS FINISHED, THIS CANNOT SEE: "
                    f"`get_client_state` reports scored_cells and nothing "
                    f"about coverage, so a complete research run awaiting "
                    f"scoring and one abandoned halfway are the same shape "
                    f"here. Measured 2026-08-31 on this very client: four "
                    f"INGESTED runs, 0 scored — and 11 of 16 category "
                    f"notebooks, a manifest at IN_PROGRESS and an empty "
                    f"deliverables_present. Scoring that would score an "
                    f"unfinished package."),
            "next": ("read the client folder's run_manifest.json first "
                     "(`drive_fetch.py find-artifact --client ...`): "
                     "status COMPLETE with deliverables_present populated "
                     "means `dma-assessment` against the existing package, "
                     "producing a DMA-ASM-* scoring workbook; IN_PROGRESS or "
                     "an empty deliverables_present means the research run "
                     "is unfinished and RESUMES under dma-research — never "
                     "restarts, and never gets scored as it stands"),
        }
    return {
        "verdict": READY_TO_SYNTHESISE, "display_id": display_id,
        "runs": len(runs), "scored_runs": len(scored),
        "why": (f"{len(scored)} of {len(runs)} run(s) carry scored cells and "
                f"no page is promoted yet."),
        "next": "`dma-surface-production` on the newest scored run",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--client", required=True,
                    help="display_id, or the client's name (it is slugged)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    did = a.client if re.fullmatch(r"[a-z0-9-]+", a.client) else _slug(a.client)
    try:
        out = decide(client_state(did), did)
    except RuntimeError as e:
        print(f"ROUTE: UNKNOWN — {e}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"ROUTE: {out['verdict']}  "
              f"{out.get('display_id') or out.get('asked_for')}")
        print(f"  why   {out['why']}")
        print(f"  next  {out['next']}")
        for m in out.get("did_you_mean") or []:
            print(f"    near  {m['display_id']}  ({m['similarity']:.2f})  "
                  f"{m.get('legal_name') or ''}")
    # Exit code carries the verdict so a routine can branch without parsing:
    # 0 = synthesise, 3 = score first, 4 = new engagement, 5 = already
    # served, 6 = ambiguous. Never 1: that is reserved for the script itself
    # failing, and a routine must not read its own crash as a routing answer.
    return {READY_TO_SYNTHESISE: 0, NEEDS_SCORING: 3, NEW_ENGAGEMENT: 4,
            ALREADY_SERVED: 5, AMBIGUOUS: 6}[out["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
