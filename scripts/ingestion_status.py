#!/usr/bin/env python3
"""How many clients are actually INGESTED — the owner's definition, not the run row's.

    python3 scripts/ingestion_status.py [--json] [--drive]

WHY THIS EXISTS. The word "ingested" names two different things in this system
and a diagnostic report quoted the wrong one, concluding that 178 clients were
ingested when the true number was 2.

    status = INGESTED   a package scan parsed a workbook into a run row.
                        The START of the pipeline. Nothing is promoted,
                        nothing serves, no client can see anything.

    ingested            (owner, 2026-08-21) promoted, serving, and visually
                        present on the live web app; carrying a Drive folder
                        named "DMAI - <Client Name>"; not older than 6 months.

Both are true statements about a run; only the second is what anyone means
when they ask how many clients are ingested. A run row is a claim about a
FILE. This script asks the serving layer instead, because the live directory
is the only thing that can answer "does a client actually see this".

That gap is not a rounding error — 178 against 2 is the whole pipeline, and a
report that quotes the parse count reads as "we are nearly done" when almost
nothing has been produced. So this script leads with the true number and
labels the parse count as what it is.

Requires an identity token for the API. Every internal endpoint here
DEFAULT-DENIES to the customer audience (invariant 5), so `audience=internal`
is passed explicitly — omitting it is a 403 that reads like a permissions
problem and was filed as one (MEM-0117).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("DMA_API_HOST", "https://dmai-api-dukrne5v4a-uc.a.run.app")
PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
FRESH_MONTHS = 6


def _gcloud(args):
    return subprocess.run(["gcloud", *args], capture_output=True, text=True)


def _id_token(audience: str) -> str:
    r = _gcloud(["auth", "print-identity-token", f"--audiences={audience}"])
    return r.stdout.strip() if r.returncode == 0 else ""


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:                                    # noqa: BLE001
            return e.code, {"raw": body[:200]}
    except Exception as e:                                   # noqa: BLE001
        return 0, {"error": f"{type(e).__name__}: {e}"}


def _months_since(iso: str | None):
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:                                        # noqa: BLE001
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).days / 30.44


def insights_folder(client_name: str):
    """Does this client carry its 'DMAI - <Client Name>' folder? READ ONLY.

    Composed from drive_fetch's primitives rather than calling its
    `_insights_root`, because that function finds-or-CREATES and heals names.
    A status report that creates the thing it is reporting on cannot be run
    twice and cannot be trusted once — the first run would make every client
    compliant and every later run would agree.

    Returns True / False / None, where None is "could not look" (no service
    account on this machine). "Nobody looked" and "it is not there" must stay
    distinguishable — that distinction is most of what this file is about.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "plugins", "dma-insights",
                                    "scripts"))
    try:
        import drive_fetch as df                             # noqa: PLC0415
        tok = df._token()
        folder = df._find_client_folder(tok, client_name)
        want = df._insights_name(folder["name"])
        kids = [f for f in df._list_children(tok, folder["id"])
                if f["mimeType"] == df.FOLDER_MIME]
        exact = any(f["name"] == want for f in kids)
        legacy = any(f["name"].startswith("DMAI - ") for f in kids)
        return {"present": exact or legacy, "expected": want,
                "exact": exact, "needs_heal": legacy and not exact}
    # SystemExit, DELIBERATELY. drive_fetch._find_client_folder raises
    # SystemExit when no folder matches — a BaseException, which sails
    # straight through `except Exception` and would kill the whole report
    # rather than marking one client unknown. Caught by the test that asserts
    # a lookup failure reads as unknown.
    except (Exception, SystemExit) as e:                     # noqa: BLE001
        return {"present": None, "why": f"{type(e).__name__}: {str(e)[:90]}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable")
    ap.add_argument("--drive", action="store_true",
                    help="also check each client's 'DMAI - <Client Name>' "
                         "folder (read-only; needs the routine service account)")
    args = ap.parse_args()

    token = _id_token(API)
    if not token:
        print("no identity token for the API — run gcloud auth login",
              file=sys.stderr)
        return 2

    # THE SERVING LAYER IS THE AUTHORITY. A run row says a file was parsed; the
    # directory says a client can see something.
    s, directory = _get(f"{API}/v1/directory?audience=internal", token)
    if s != 200:
        print(f"directory unreadable: HTTP {s} {directory}", file=sys.stderr)
        return 2
    serving = directory.get("entities") or []

    # THE DIRECTORY DOES NOT CARRY A PROMOTION DATE — it answers "who serves",
    # not "how fresh". The date lives per page in get_client_state's
    # served_pages, so the six-month rule needs that second call. Reading the
    # freshest page's date, because a client is as current as its most recent
    # promotion; the pages move together under atomic promote anyway.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from dma_connector import call                       # noqa: PLC0415
    except Exception:                                        # noqa: BLE001
        call = None

    rows = []
    for e in serving:
        slug = e.get("slug") or e.get("id")
        promoted, pages = None, None
        if call:
            try:
                st = call("get_client_state", display_id=slug)
                sp = st.get("served_pages") or []
                pages = len(sp)
                dates = [p.get("promoted_at") for p in sp if p.get("promoted_at")]
                promoted = max(dates) if dates else None
            except Exception:                                # noqa: BLE001
                pass
        age = _months_since(promoted)
        row = {
            "slug": slug,
            "name": e.get("name"),
            "subvertical": e.get("subvertical"),
            "status": e.get("status"),
            "served_pages": pages,
            "promoted_at": promoted,
            "months_old": None if age is None else round(age, 1),
            "within_6_months": None if age is None else age <= FRESH_MONTHS,
        }
        if args.drive:
            row["insights_folder"] = insights_folder(e.get("name") or slug)
        rows.append(row)

    # The parse count, reported ONLY beside its true meaning so it cannot be
    # quoted as an ingestion figure again.
    parsed = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from dma_connector import call            # noqa: PLC0415
        pend = call("list_pending_runs")
        pr = pend.get("runs") or pend.get("pending") or []
        parsed = sum(1 for r in pr if r.get("is_latest_for_request"))
    except Exception:                                        # noqa: BLE001
        parsed = None

    out = {
        "ingested_clients": len(rows),
        "definition": ("promoted, serving, and visible on the live web app; "
                       "carries a 'DMAI - <Client Name>' Drive folder; not "
                       "older than 6 months"),
        "clients": rows,
        "runs_parsed_not_ingested": parsed,
        "parsed_note": ("runs at status=INGESTED — a workbook was parsed into "
                        "a run row. This is the START of the pipeline and is "
                        "NOT an ingested client."),
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print("DMA Insights — ingestion status\n")
    print(f"  INGESTED CLIENTS: {len(rows)}")
    print(f"  (definition: {out['definition']})\n")
    for r in rows:
        age = ("unknown age" if r["months_old"] is None
               else f"{r['months_old']} months old")
        fresh = ("" if r["within_6_months"] is None
                 else ("  [FRESH]" if r["within_6_months"]
                       else f"  [STALE — over {FRESH_MONTHS} months]"))
        print(f"   - {r['slug']:36} {r['name']}")
        pg = ("" if r["served_pages"] is None
              else f"  {r['served_pages']}/6 pages"
                   + ("" if r["served_pages"] == 6 else "  [INCOMPLETE]"))
        print(f"     {r['subvertical']}  status={r['status']}  {age}{fresh}{pg}")
        if r.get("promoted_at"):
            print(f"     promoted {r['promoted_at'][:19]}Z")
        f = r.get("insights_folder")
        if f is not None:
            if f.get("present") is None:
                print(f"     DMAI folder: could not look ({f.get('why','')})")
            elif f["present"]:
                print(f"     DMAI folder: {f['expected']!r}"
                      + ("  [needs heal to taxonomy]" if f.get("needs_heal") else ""))
            else:
                print(f"     DMAI folder: MISSING — expected {f['expected']!r}")
    if parsed is not None:
        print(f"\n  runs merely PARSED (status=INGESTED): {parsed}")
        print("  These are not ingested clients. A parsed run row means a")
        print("  workbook was read; nothing is promoted and no client can see")
        print("  anything until it serves in the directory above.")
        if parsed and not rows:
            print("\n  >>> every run is parsed and NOTHING serves.")
        elif parsed:
            print(f"\n  >>> {parsed} parsed vs {len(rows)} serving — the gap "
                  f"is the unproduced pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
