#!/usr/bin/env python3
"""Run the connector's blocking gates locally, before spending a submission.

    python scripts/precheck_gates.py <payload.json> --page heatmap \
        --evidence <get_evidence.json> --bundle <get_report_bundle.json>

`check_payload.py` catches the cheap contract failures. This catches the
next tier — the gates that need the RUN's own facts (which evidence rows
exist, what they carry, which cells the run serves) but not a database:

    pass 1        the contract, verbatim from the connector's own module
    ET-01/ET-04   every cited id resolves, and carries a 50-500 char excerpt
    CG-10         a cited row is dated, or bands UNVERIFIED and says so
    ET-05         no cell belongs to another sub-vertical
    ET-06         no discard names a platform from another vertical
    CG-14         every cited cell is one the run actually serves

Why it earns its place: a page submission is not free — it supersedes the
staged row, so a FAIL on a page that was passing costs you the pass until
you repair it, and during a promotion window that blocks the promote. On
the run this was written for, the promoted heatmap returned **120** blocking
reasons when checked this way — 79 foreign-sub-vertical cells inside focus
areas, 11 alerts naming cells the run does not carry, 28 uncitable evidence
rows, 2 lowercase openings — none of which the producer could see without
either spending a submission or running this.

The two inputs are tool output you already have:

    get_evidence(run_id, e_ids=[...])   -> --evidence
    get_report_bundle(run_id)           -> --bundle

Ask `get_evidence` for every id the payload cites (`--list-cited` prints
them, so the round trip is one call). Anything this reports is a refusal
the connector would have made; anything it cannot see — grain arithmetic,
grounding, identity against the registry — still belongs to the server.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _candidate_roots(repo_root: str | None):
    """Where a checkout of the connector might be, most explicit first.

    Packaged as a plugin this script no longer sits inside the repository,
    so a hardcoded sibling path is a coupling that cannot hold. It searches
    instead, and each rung is something the caller actually controls:

        --repo                      you said so
        $DMA_INSIGHTS_REPO / $DMA_REPO   the environment said so
        $CLAUDE_PROJECT_DIR         the session is in the repo
        cwd and its parents         you are standing in the repo
        (last) an installed dma_mcp already importable on sys.path
    """
    seen, out = set(), []
    for c in (repo_root,
              os.environ.get("DMA_INSIGHTS_REPO"),
              os.environ.get("DMA_REPO"),
              os.environ.get("CLAUDE_PROJECT_DIR")):
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    here = os.path.abspath(os.getcwd())
    while True:
        if here not in seen:
            seen.add(here)
            out.append(here)
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return out


def _load_connector(repo_root: str | None):
    """The gates are imported, never re-implemented.

    A second copy of a gate is a second answer to the same question, and
    the one that matters is the connector's. Vendoring `validation2` into
    this plugin would give a payload two verdicts — the vendored one, which
    goes stale the first time a gate changes, and the server's, which is
    the only one that decides. A precheck that passes a payload the server
    then refuses is worse than no precheck, because it was believed.

    So: find the connector, or say exactly what could not run and stop.
    There is no degraded mode where the gates quietly do not fire.
    """
    tried = []
    for root in _candidate_roots(repo_root):
        mcp = os.path.join(root, "apps", "mcp")
        tried.append(mcp)
        if not os.path.isdir(mcp):
            continue
        if mcp not in sys.path:
            sys.path.insert(0, mcp)
        try:
            from dma_mcp import validation, validation2          # noqa: E402
            from dma_mcp.subverticals import resolve_subvertical  # noqa: E402
        except Exception as exc:                                  # noqa: BLE001
            sys.exit(f"found {mcp} but could not import its gates: {exc!r}")
        return validation, validation2, resolve_subvertical, mcp

    # Already importable? An editable install of the connector counts.
    try:
        from dma_mcp import validation, validation2          # noqa: E402
        from dma_mcp.subverticals import resolve_subvertical  # noqa: E402
    except Exception:                                         # noqa: BLE001
        pass
    else:
        return (validation, validation2, resolve_subvertical,
                "installed dma_mcp on sys.path")

    sys.exit(
        "cannot reach the connector's gate modules, so ET-01, ET-04, ET-05,\n"
        "ET-06, CG-10, CG-14 and the contract pass did NOT run. This does not\n"
        "mean the payload is clean — it means nothing was checked.\n\n"
        "Give it a checkout of the DMA Insights repository, any one of:\n"
        "  precheck_gates.py ... --repo /path/to/Accelerate\n"
        "  export DMA_INSIGHTS_REPO=/path/to/Accelerate\n"
        "  run it from inside the checkout\n"
        "  pip install -e /path/to/Accelerate/apps/mcp\n"
        "or set repo_root in the plugin's configuration.\n\n"
        "Without one, run scripts/check_payload.py (no repo needed, catches the\n"
        "contract failures) and let submit_page_payload return the rest.\n\n"
        "looked for apps/mcp under:\n  " + "\n  ".join(tried[:8]))


def cited_ids(payload: dict, validation2) -> dict:
    """{e_id: [json paths that cite it]} — the same walk the gates use."""
    out: dict[str, list[str]] = {}
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, obj in validation2._walk(body, name):
            for key in validation2._EV_KEYS:
                val = obj.get(key)
                seq = [val] if isinstance(val, str) else (val or [])
                for e in seq:
                    if isinstance(e, str):
                        out.setdefault(e, []).append(f"{path}.{key}")
    return out


def check(payload, page, evidence, bundle, mods) -> list[dict]:
    validation, validation2, resolve_subvertical = mods
    reasons = list(validation.validate_pass1(page, payload))

    store = {e["e_id"]: e for e in (evidence or {}).get("found", [])}
    for e_id, paths in sorted(cited_ids(payload, validation2).items()):
        row = store.get(e_id)
        if row is None:
            # Either the id does not exist, or it was not asked for. Both
            # are worth stopping on: an unchecked citation is not a checked
            # one, and the connector will resolve every single id.
            reasons.append({"gate_id": "ET-01", "path": paths[0],
                            "message": f"{e_id} does not resolve in the "
                                       "supplied evidence snapshot"})
            continue
        excerpt = (row.get("excerpt") or "").strip()
        if not 50 <= len(excerpt) <= 500:
            reasons.append({"gate_id": "ET-04", "path": paths[0],
                            "message": f"{e_id} excerpt is {len(excerpt)} "
                                       "chars; a citation a reader can open "
                                       "needs 50-500 verbatim"})
        band = row.get("recency_band")
        if not row.get("published_date") and band not in (None, "UNVERIFIED"):
            reasons.append({"gate_id": "CG-10", "path": paths[0],
                            "message": f"{e_id} carries band {band} with no "
                                       "published_date — a band follows a "
                                       "real date or there is no band"})

    if bundle:
        run_cells = {s["subcap_id"] for s in bundle.get("scores", [])
                     if s.get("subcap_id")}
        code = resolve_subvertical(bundle.get("sub_vertical"))
        if code:
            reasons.extend(validation2._check_subvertical_scope(page, payload, code))
            reasons.extend(validation2._check_candidate_vertical(page, payload, code))
        if run_cells:
            reasons.extend(validation2._check_cell_linkage(page, payload, run_cells))
    return reasons


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("payload")
    ap.add_argument("--page", required=True)
    ap.add_argument("--evidence", help="get_evidence(...) output, as JSON")
    ap.add_argument("--bundle", help="get_report_bundle(...) output, as JSON")
    ap.add_argument("--repo", default=None,
                    help="checkout of the DMA Insights repository, whose "
                         "apps/mcp holds the gates this imports. Falls back to "
                         "$DMA_INSIGHTS_REPO, $DMA_REPO, $CLAUDE_PROJECT_DIR, "
                         "the cwd and its parents, then an installed dma_mcp.")
    ap.add_argument("--list-cited", action="store_true",
                    help="print every id the payload cites and stop, so one "
                         "get_evidence call can cover the whole page")
    a = ap.parse_args(argv)

    payload = json.load(open(a.payload))
    payload = payload.get("payload", payload)
    *mods, gates_from = _load_connector(a.repo)
    print(f"gates imported from: {gates_from}", file=sys.stderr)

    if a.list_cited:
        for e in sorted(cited_ids(payload, mods[1])):
            print(e)
        return 0

    evidence = json.load(open(a.evidence)) if a.evidence else None
    bundle = json.load(open(a.bundle)) if a.bundle else None
    if evidence is None:
        print("no --evidence: skipping ET-01/ET-04/CG-10 (citation gates)",
              file=sys.stderr)
    if bundle is None:
        print("no --bundle: skipping ET-05/ET-06/CG-14 (cell gates)",
              file=sys.stderr)

    reasons = check(payload, a.page, evidence, bundle, mods)
    if not reasons:
        print(f"{a.page}: 0 blocking reasons from the gates checkable here")
        return 0

    by_gate: dict[str, list[dict]] = {}
    for r in reasons:
        by_gate.setdefault(r.get("gate_id", "?"), []).append(r)
    print(f"{a.page}: {len(reasons)} blocking reason(s)")
    for gate, items in sorted(by_gate.items()):
        print(f"\n== {gate} ({len(items)}) ==")
        for i in items[:12]:
            print("  ", i.get("path"), "|", str(i.get("message"))[:150])
        if len(items) > 12:
            print(f"   … {len(items) - 12} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
