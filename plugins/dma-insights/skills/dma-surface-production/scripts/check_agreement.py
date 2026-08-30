#!/usr/bin/env python3
"""Do the LOCAL checkers agree with the connector's own gates?

    python scripts/check_agreement.py <payload.json> --page heatmap
    python scripts/check_agreement.py <rundir>/ --all-pages

The plan that produced this file proposed deleting the local checkers
because one of them returned 630 blocking findings where the real gates
returned 0. Measuring first changed the decision: 517 of that 630 were
AG-03 on `cell_evidence.cells` — the headline defect of the run, which
the connector's own gates were exempting at the time through a hole that
has since been closed. Deleting the checker would have deleted the only
detector that found the defect the repair exists for.

So the rule is not "delete the private copy", it is **the private copy may
never be stricter than the gate without saying so**, and this script is
how that claim is checked rather than asserted:

    LOCAL ⊆ SERVER, on the classes both of them police.

A local BLOCK the server does not raise is a FALSE ALARM — it costs a
producer a repair cycle on content that would have passed, which is how
five producers spent a day on variant cell ids that `_SUBCAP_RE` accepts.
A server BLOCK the local checker misses is a GAP: not a defect in itself
(the server is the authority and it caught it), but a round trip the
producer paid for that a local run could have saved.

Neither is fatal on its own. What is fatal is not knowing which you have.

WHAT IT COMPARES. `precheck_gates.py` runs the connector's real modules
against a payload — the contract pass, ET-01/04/05/06, CG-10, CG-14 — and
CG-15 comes from `dma_mcp.vacuity` directly. Those are the server side.
`check_payload.py` is the local side. Findings are matched on (path,
class) rather than on message text, because the two write for different
readers and only the class is a claim about the payload.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = ("overview", "insights", "heatmap", "platform", "context", "techstack")

# Local message -> the class it asserts. Only classes the SERVER also
# polices appear here; a local check with no server counterpart (language
# register, card budgets) is reported separately and never as a mismatch,
# because "stricter than the gate, deliberately" is a real category.
LOCAL_CLASSES = (
    (re.compile(r"is not a well-formed cell id", re.I), "cell_id_shape"),
    (re.compile(r"asserts a claim and cites nothing", re.I), "AG-03"),
    (re.compile(r"sentinel value", re.I), "sentinel"),
    (re.compile(r"every array is empty", re.I), "empty_section"),
    (re.compile(r"declares no internal_only", re.I), "internal_only_marking"),
    (re.compile(r"does not resolve|not_found|foreign", re.I), "evidence_resolves"),
)
SERVER_CLASSES = (
    (re.compile(r"is not a well-formed|malformed cell id|_SUBCAP_RE", re.I), "cell_id_shape"),
    (re.compile(r"asserts a claim and cites nothing|AG-03", re.I), "AG-03"),
    (re.compile(r"placeholder where the .* contract requires prose", re.I), "sentinel"),
    (re.compile(r"present content fields are vacuous", re.I), "empty_section"),
    (re.compile(r"not_found|foreign|does not resolve", re.I), "evidence_resolves"),
)

# Classes the local checker owns ALONE, by design. Listed so a producer
# reading a mismatch report can tell "the gate does not police this" from
# "the gate disagrees with this".
LOCAL_ONLY = {"internal_only_marking"}


def _classify(message: str, table) -> str | None:
    for pattern, name in table:
        if pattern.search(message):
            return name
    return None


def _run(script: str, args: list) -> str:
    out = subprocess.run([sys.executable, str(HERE / script), *args],
                         capture_output=True, text=True, timeout=600)
    return (out.stdout or "") + (out.stderr or "")


_BLOCK_RE = re.compile(r"^\s*\[BLOCK\]\s*(\S+)\s*$")


def _local_findings(payload_path: str, page: str) -> list:
    """(path, class) for every local BLOCK, from check_payload's own output.

    The output is two lines per finding — `[BLOCK] <path>` then an indented
    message — which a naive `grep -c "^\\[BLOCK\\]"` misses entirely because
    the marker is indented. That miscount reported a clean sweep over 527
    real blocks in this session; parsing the pair is the fix.
    """
    text = _run("check_payload.py", [payload_path, "--page", page])
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        m = _BLOCK_RE.match(line)
        if not m:
            continue
        message = lines[i + 1].strip() if i + 1 < len(lines) else ""
        out.append((m.group(1), _classify(message, LOCAL_CLASSES), message))
    return out


def _server_findings(payload_path: str, page: str, extra: list) -> list:
    text = _run("precheck_gates.py", [payload_path, "--page", page, *extra])
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        m = _BLOCK_RE.match(line)
        if not m:
            continue
        message = lines[i + 1].strip() if i + 1 < len(lines) else ""
        out.append((m.group(1), _classify(message, SERVER_CLASSES), message))

    # CG-15 is not in precheck's list and is a server gate: run it directly
    # from the connector's own module so the comparison covers it.
    sys.path.insert(0, str(HERE.parents[4] / "apps" / "mcp"))
    try:
        from dma_mcp.vacuity import check_vacuity
        payload = json.loads(Path(payload_path).read_text())
        for r in check_vacuity(page, payload):
            out.append((r["path"], "CG-15", r["message"]))
    except Exception as exc:                      # noqa: BLE001
        print(f"  note: CG-15 could not run here ({type(exc).__name__}); "
              "the comparison below excludes it")
    return out


def compare(payload_path: str, page: str, extra: list) -> dict:
    local = _local_findings(payload_path, page)
    server = _server_findings(payload_path, page, extra)
    lkeys = {(p, c) for p, c, _m in local if c}
    skeys = {(p, c) for p, c, _m in server if c}

    # A local block the server did not raise is one of two very different
    # things, and calling both "false alarm" was this script's own first
    # defect. If the server raised NO finding of that class anywhere on the
    # page, the class is not policed there — the local checker may well be
    # right and the GATE may be the gap. Measured on the reference client:
    # five `named_gap_subcap_id` values carrying a capability NAME where the
    # contract wants a cell id. The local checker is correct; no gate looks
    # at that field; and check_consistency independently reports the same
    # five as cited-but-absent from the grid. Reporting that as the local
    # checker crying wolf would have got the checker weakened and the
    # defect kept.
    server_classes_seen = {c for _p, c, _m in server if c}
    disagree = sorted(k for k in lkeys - skeys if k[1] not in LOCAL_ONLY)
    false_alarms = [k for k in disagree if k[1] in server_classes_seen]
    unpoliced = [k for k in disagree if k[1] not in server_classes_seen]
    gaps = sorted(skeys - lkeys)
    unclassified_local = [(p, m) for p, c, m in local if c is None]
    local_only = sorted(k for k in lkeys if k[1] in LOCAL_ONLY)

    return {"page": page, "local_blocks": len(local),
            "server_blocks": len(server),
            "false_alarms": false_alarms, "unpoliced": unpoliced,
            "gaps": gaps, "local_only": local_only,
            "unclassified_local": unclassified_local}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a payload file, or a rundir with --all-pages")
    ap.add_argument("--page")
    ap.add_argument("--all-pages", action="store_true")
    ap.add_argument("--evidence"); ap.add_argument("--bundle")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when a false alarm is found")
    a = ap.parse_args()

    extra = []
    if a.evidence:
        extra += ["--evidence", a.evidence]
    if a.bundle:
        extra += ["--bundle", a.bundle]

    jobs = []
    if a.all_pages:
        for page in PAGES:
            f = os.path.join(a.target, f"{page}.json")
            if os.path.exists(f):
                jobs.append((f, page))
    else:
        if not a.page:
            print("  --page is required unless --all-pages"); return 2
        jobs.append((a.target, a.page))

    worst = 0
    for path, page in jobs:
        r = compare(path, page, extra)
        print(f"\n  {page}: local {r['local_blocks']} blocks · "
              f"server {r['server_blocks']} blocks")
        if r["false_alarms"]:
            worst = 1
            print(f"    FALSE ALARMS ({len(r['false_alarms'])}) — the gate "
                  "polices this class on this page and accepted these; the "
                  "local checker is stricter and costs a repair cycle on "
                  "content that would have passed:")
            for p, c in r["false_alarms"][:10]:
                print(f"      {c:<22} {p}")
            if len(r["false_alarms"]) > 10:
                print(f"      … {len(r['false_alarms']) - 10} more")
        if r["unpoliced"]:
            print(f"    unpoliced by any gate ({len(r['unpoliced'])}) — no "
                  "gate raised this class anywhere on this page, so the "
                  "local checker may be RIGHT and the gate may be the gap. "
                  "Read the finding before weakening the checker:")
            for p, c in r["unpoliced"][:10]:
                print(f"      {c:<22} {p}")
            if len(r["unpoliced"]) > 10:
                print(f"      … {len(r['unpoliced']) - 10} more")
        if r["gaps"]:
            print(f"    gaps ({len(r['gaps'])}) — the gate refuses what the "
                  "local checker misses; a round trip a local run could have "
                  "saved:")
            for p, c in r["gaps"][:10]:
                print(f"      {c:<22} {p}")
            if len(r["gaps"]) > 10:
                print(f"      … {len(r['gaps']) - 10} more")
        if r["local_only"]:
            print(f"    local-only by design ({len(r['local_only'])}): "
                  f"{sorted({c for _p, c in r['local_only']})}")
        if not (r["false_alarms"] or r["unpoliced"] or r["gaps"]):
            print("    agrees with the gate on every class both police")
    return worst if a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
