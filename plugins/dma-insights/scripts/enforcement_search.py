#!/usr/bin/env python3
"""Enforcement-register sweep with controls — the structured ladder C3 cites.

Arbor Bank (2026-10-06) spent most of a context-page round discovering, by
hand, that the FDIC's Enforcement Decisions & Orders site is a Lightning app
behind a form (no HTTP query), that the CFPB's actions index answers a plain
`?title=` query, and that Nebraska's banking department has its own CGI
search — and then that a sweep returning zero proves nothing until the SAME
mechanism returns hits for a name known to carry orders. None of that was
written down anywhere a producer reads. This script is that knowledge, as
code, producing the rung shape CG-46 accepts:

    {"source": "...", "query": "...", "outcome": "VERIFIED_ABSENT|RESOLVED|NOT_RUN",
     "hits": n, "url": "...", "retrieved_at": "...", "control": {...}, "reason": "..."}

Rules it enforces, so a producer cannot forget them:

  * a rung whose mechanism did not complete (403, timeout, selector missing,
    unrecognised page) is NOT_RUN with the reason — never a clean negative;
  * a zero is VERIFIED_ABSENT only when the control name returned hits on the
    same source in the same session; otherwise the rung is NOT_RUN
    ("mechanism unverified");
  * every name the entity trades under is searched (`--name` repeats), and
    the rung says which;
  * a state with no configured order search is a NOT_RUN rung naming the
    department, so the producer records a manual search rather than silence.

Browser sources run through node + playwright-core (the container's
`/opt/node-tools/node_modules/playwright-core` and the pre-installed Chromium);
the CFPB index is plain HTTPS. Nothing here registers evidence: the producer
reads the rungs and cites the registry pages through the connector.

    python3 enforcement_search.py --name "Arbor Bank" --name "Arbor Banking Group" \
        --cert 12345 --state NE --out /path/enforcement_rungs.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

PW_CORE = os.environ.get("DMA_PLAYWRIGHT_CORE", "/opt/node-tools/node_modules/playwright-core")
CHROMIUM = os.environ.get("DMA_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

OUTCOMES = ("VERIFIED_ABSENT", "RESOLVED", "NOT_RUN")

#: Names KNOWN to carry orders on each source — the positive control. A
#: mechanism that returns zero for these is not searching.
CONTROLS = {
    "fdic_edo": "Wells Fargo",
    "cfpb": "Wells Fargo",
    "state:NE": "Bank",            # any order list with a bank in it
}

#: State banking-department order searches this script knows how to drive.
#: Add a state here — with its URL, the subject field and the result marker —
#: rather than teaching a producer the form by hand again.
STATE_ORDER_SEARCHES = {
    "NE": {
        "department": "Nebraska Department of Banking and Finance",
        "url": "https://www.nebraska.gov/ndbf/searches/orders.cgi",
        "field": "#subjname",
        "submit": "input[type=submit], button[type=submit]",
        "result_rows": "table tr",
    },
}

CFPB_URL = "https://www.consumerfinance.gov/enforcement/actions/"
FDIC_URL = "https://orders.fdic.gov/s/"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rung(source: str, query: str, outcome: str, *, hits=None, url: str = "",
         reason: str = "", control: dict | None = None) -> dict:
    """One ladder rung in the shape the context page's
    `absence_of_enforcement.sources_searched[]` and CG-46 accept."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome {outcome!r} not in {OUTCOMES}")
    if outcome == "NOT_RUN" and not reason.strip():
        raise ValueError("NOT_RUN carries the reason it did not run")
    out = {"source": source, "query": query, "outcome": outcome,
           "retrieved_at": _now()}
    if hits is not None:
        out["hits"] = int(hits)
    if url:
        out["url"] = url
    if reason:
        out["reason"] = reason
    if control is not None:
        out["control"] = control
    return out


def apply_control(zero_rung: dict, control_hits, control_name: str) -> dict:
    """A zero becomes VERIFIED_ABSENT only when the control found orders on
    the same source; otherwise the mechanism is unverified and the rung is
    NOT_RUN. A rung with hits is RESOLVED regardless."""
    r = dict(zero_rung)
    r["control"] = {"name": control_name, "hits": control_hits}
    if r.get("outcome") == "RESOLVED":
        return r
    if control_hits is None or int(control_hits) <= 0:
        r["outcome"] = "NOT_RUN"
        r["reason"] = (f"mechanism unverified: the control name {control_name!r}, "
                       f"known to carry orders, returned {control_hits!r} on this "
                       f"source in the same session; a zero from a search that "
                       f"finds nothing proves nothing")
    else:
        r["outcome"] = "VERIFIED_ABSENT"
        r.pop("reason", None)
    return r


# ── CFPB: plain HTTPS ─────────────────────────────────────────────────────

_CFPB_RESULT = re.compile(r'class="[^"]*\bo-post-preview\b', re.I)
_CFPB_NONE = re.compile(r"no (?:results|enforcement actions) (?:were )?found|"
                        r"there are no results|0 results", re.I)
_CFPB_COUNT = re.compile(r"(\d[\d,]*)\s+results?", re.I)


def cfpb_count(page_html: str):
    """Hits on a CFPB actions index page, or None when the page's shape is
    not one this parser knows (which is NOT_RUN, never zero)."""
    if not page_html:
        return None
    n = len(_CFPB_RESULT.findall(page_html))
    if n:
        m = _CFPB_COUNT.search(_html.unescape(page_html))
        if m:
            try:
                return max(n, int(m.group(1).replace(",", "")))
            except ValueError:
                pass
        return n
    if _CFPB_NONE.search(_html.unescape(page_html)):
        return 0
    return None


def _http_get(url: str, timeout: int = 60) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "dma-insights enforcement sweep"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:                                           # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def cfpb_rung(name: str) -> dict:
    url = CFPB_URL + "?" + urllib.parse.urlencode({"title": name})
    status, body = _http_get(url)
    src = "Consumer Financial Protection Bureau enforcement actions index"
    if status != 200:
        return rung(src, name, "NOT_RUN", url=url,
                    reason=f"HTTP {status or 'error'}: {body[:120] if status == 0 else 'no page'}")
    n = cfpb_count(body)
    if n is None:
        return rung(src, name, "NOT_RUN", url=url,
                    reason="page shape unrecognised (neither result cards nor a "
                           "no-results notice); read it by hand")
    return rung(src, name, "RESOLVED" if n else "VERIFIED_ABSENT", hits=n, url=url)


# ── browser sources: node + playwright-core ──────────────────────────────

_JS = r"""
const pw = require(process.env.PW_CORE);
const job = JSON.parse(process.argv[2]);
(async () => {
  const launch = {headless: true, args: ["--no-sandbox"]};
  if (process.env.CHROMIUM) launch.executablePath = process.env.CHROMIUM;
  const browser = await pw.chromium.launch(launch);
  const out = [];
  try {
    const page = await browser.newPage();
    for (const step of job.steps) {
      const r = {id: step.id, url: step.url};
      try {
        await page.goto(step.url, {waitUntil: "domcontentloaded", timeout: 60000});
        if (step.kind === "fdic") {
          const byLabel = page.getByLabel(step.label, {exact: false});
          await byLabel.first().waitFor({timeout: 30000});
          await byLabel.first().fill(step.value);
          await page.locator("button.searchButton").first().click({timeout: 15000});
          await page.waitForTimeout(6000);
          const text = await page.locator("body").innerText();
          r.rows = await page.locator("table tbody tr, lightning-datatable tr, .slds-table tbody tr").count();
          r.no_results = /no (results|records)/i.test(text);
          r.text = text.slice(0, 4000);
        } else if (step.kind === "state") {
          await page.locator(step.field).first().fill(step.value, {timeout: 30000});
          await page.locator(step.submit).first().click({timeout: 15000});
          await page.waitForLoadState("domcontentloaded", {timeout: 60000});
          await page.waitForTimeout(2000);
          const text = await page.locator("body").innerText();
          r.rows = Math.max(0, (await page.locator(step.result_rows).count()) - 1);
          r.no_results = /no (results|records|orders)/i.test(text);
          r.text = text.slice(0, 4000);
        }
        r.ok = true;
      } catch (e) {
        r.ok = false; r.error = String(e).slice(0, 300);
      }
      out.push(r);
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e)); process.exit(2); });
"""


def run_browser_steps(steps: list) -> list:
    """Drive the browser once for every step; a missing runtime is one
    NOT_RUN per step, with the reason, never an exception the sweep hides."""
    if not steps:
        return []
    if not os.path.isdir(PW_CORE):
        return [{"id": s["id"], "ok": False,
                 "error": f"playwright-core not found at {PW_CORE} (set DMA_PLAYWRIGHT_CORE)"}
                for s in steps]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_JS)
        js = fh.name
    env = {**os.environ, "PW_CORE": PW_CORE}
    if os.path.exists(CHROMIUM):
        env["CHROMIUM"] = CHROMIUM
    try:
        r = subprocess.run(["node", js, json.dumps({"steps": steps})], capture_output=True,
                           text=True, timeout=600, env=env)
    except Exception as e:                                           # noqa: BLE001
        return [{"id": s["id"], "ok": False, "error": f"{type(e).__name__}: {e}"} for s in steps]
    finally:
        try:
            os.unlink(js)
        except OSError:
            pass
    if r.returncode != 0 or not r.stdout.strip():
        return [{"id": s["id"], "ok": False,
                 "error": f"node exit {r.returncode}: {(r.stderr or '')[:200]}"} for s in steps]
    try:
        return json.loads(r.stdout)
    except ValueError:
        return [{"id": s["id"], "ok": False, "error": "unparseable browser output"} for s in steps]


def _browser_rung(source: str, query: str, res: dict, url: str) -> dict:
    if not res or not res.get("ok"):
        return rung(source, query, "NOT_RUN", url=url,
                    reason=f"mechanism did not complete: {(res or {}).get('error', 'no result')}")
    rows = int(res.get("rows") or 0)
    if rows == 0 and not res.get("no_results"):
        return rung(source, query, "NOT_RUN", url=url, hits=0,
                    reason="zero rows and no no-results notice: the page may not "
                           "have rendered; read it by hand")
    return rung(source, query, "RESOLVED" if rows else "VERIFIED_ABSENT", hits=rows, url=url)


def sweep(names: list, *, cert: str = "", state: str = "", with_controls: bool = True,
          fdic: bool = True) -> dict:
    names = [n for n in dict.fromkeys(str(x).strip() for x in names) if n]
    rungs = []
    # CFPB — one rung per name, controlled once
    cf = [cfpb_rung(n) for n in names]
    if with_controls and any(r["outcome"] == "VERIFIED_ABSENT" for r in cf):
        ctl = cfpb_rung(CONTROLS["cfpb"])
        cf = [apply_control(r, ctl.get("hits"), CONTROLS["cfpb"]) for r in cf]
    rungs.extend(cf)
    # browser steps
    steps = []
    fdic_src = "FDIC Enforcement Decisions & Orders (orders.fdic.gov)"
    if fdic and cert:
        steps.append({"id": "fdic:cert", "kind": "fdic", "url": FDIC_URL,
                      "label": "Cert Number", "value": str(cert), "query": f"cert {cert}"})
    for n in (names if fdic else []):
        steps.append({"id": f"fdic:name:{n}", "kind": "fdic", "url": FDIC_URL,
                      "label": "Institution Name", "value": n, "query": n})
    if with_controls and fdic:
        steps.append({"id": "fdic:control", "kind": "fdic", "url": FDIC_URL,
                      "label": "Institution Name", "value": CONTROLS["fdic_edo"],
                      "query": CONTROLS["fdic_edo"]})
    st = STATE_ORDER_SEARCHES.get(str(state or "").upper())
    if state and st:
        for n in names:
            steps.append({"id": f"state:{n}", "kind": "state", "url": st["url"],
                          "field": st["field"], "submit": st["submit"],
                          "result_rows": st["result_rows"], "value": n, "query": n})
        if with_controls:
            steps.append({"id": "state:control", "kind": "state", "url": st["url"],
                          "field": st["field"], "submit": st["submit"],
                          "result_rows": st["result_rows"],
                          "value": CONTROLS.get(f"state:{state.upper()}", "Bank"),
                          "query": "control"})
    results = {r.get("id"): r for r in run_browser_steps(steps)}
    fdic_ctl = results.get("fdic:control", {})
    fdic_ctl_hits = int(fdic_ctl.get("rows") or 0) if fdic_ctl.get("ok") else None
    for s in steps:
        if s["id"].endswith(":control"):
            continue
        res = results.get(s["id"], {})
        if s["kind"] == "fdic":
            r = _browser_rung(fdic_src, s["query"], res, FDIC_URL)
            if with_controls:
                r = apply_control(r, fdic_ctl_hits, CONTROLS["fdic_edo"])
        else:
            sc = results.get("state:control", {})
            sc_hits = int(sc.get("rows") or 0) if sc.get("ok") else None
            r = _browser_rung(f"{st['department']} orders search", s["query"], res, st["url"])
            if with_controls:
                r = apply_control(r, sc_hits, CONTROLS.get(f"state:{state.upper()}", "Bank"))
        rungs.append(r)
    if state and not st:
        rungs.append(rung(f"{state.upper()} state banking department orders", ", ".join(names),
                          "NOT_RUN", reason=f"no order search is configured for {state.upper()} "
                                             f"in enforcement_search.STATE_ORDER_SEARCHES; search "
                                             f"the department's orders page by hand and record "
                                             f"the rung with its URL and outcome"))
    return summarise(rungs, names=names, cert=cert, state=state)


def summarise(rungs: list, **meta) -> dict:
    """`verified` is true only when every rung completed and none RESOLVED
    an action — the predicate `absence_of_enforcement.verified` states."""
    by = {o: sum(1 for r in rungs if r["outcome"] == o) for o in OUTCOMES}
    return {"names": meta.get("names"), "cert": meta.get("cert") or None,
            "state": (meta.get("state") or "").upper() or None,
            "sources_searched": rungs, "counts": by,
            "actions_found": by["RESOLVED"] > 0,
            "verified": by["NOT_RUN"] == 0 and by["RESOLVED"] == 0 and bool(rungs),
            "retrieved_at": _now()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", action="append", default=[], required=True,
                    help="a name the entity trades under (repeat for every brand)")
    ap.add_argument("--cert", default="", help="FDIC certificate number, when the entity is FDIC-insured")
    ap.add_argument("--state", default="", help="two-letter state of charter (drives the state order search)")
    ap.add_argument("--no-fdic", action="store_true",
                    help="skip the FDIC register (a credit union answers to the NCUA)")
    ap.add_argument("--no-controls", action="store_true",
                    help="skip the positive controls (every zero then stays NOT_RUN)")
    ap.add_argument("--out", help="write the rung document here (stdout otherwise)")
    a = ap.parse_args(argv)
    doc = sweep(a.name, cert=a.cert, state=a.state, with_controls=not a.no_controls,
                fdic=not a.no_fdic)
    text = json.dumps(doc, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"{a.out}: {doc['counts']}  verified={doc['verified']}  actions_found={doc['actions_found']}")
    else:
        print(text)
    return 0 if doc["counts"]["NOT_RUN"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
