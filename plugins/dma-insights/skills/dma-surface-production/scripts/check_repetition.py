#!/usr/bin/env python3
"""Will this way of writing a cell synthesis survive seven hundred of them?

    python scripts/check_repetition.py drafts.json --page heatmap

Run it on TWENTY drafts before you write seven hundred. That is the whole
point of it.

CG-15's template rule compares a field's items against each other, so it
cannot be seen one item at a time — and a producer who discovers it after
building all 708 cells has lost the day, which is exactly what happened on
2026-08-08 to two producers on the same tranche. What refuses a payload is
not any single synthesis. It is the SHAPE all of them share, and the shape
is visible in the first twenty.

WHAT IT MEASURES. Two numbers per pair, both of which must clear 0.40
before CG-15 draws an edge, and three or more connected items are a
template:

    phrasing   8-word spans shared, over the smaller set
    claim      content words shared, over the smaller set — the residual
               after stopwords, numbers, catalogue ids and the score and
               evidence-inventory registers come out

The second number is the one worth understanding, because it is the one
that tells you what to change. The registers it strips are the frame the
contract MANDATES: H2 requires every synthesis to say where the score sits
against the peer median and to cite inline. Every honest synthesis on the
page shares that frame. Sharing it is not the defect and never was — the
defect is when what is left, once the frame comes out, is also the same.

Measured on the promoted Baxter run, whose 706 cell syntheses are the
existence proof that a 700-cell page passes: the highest phrasing overlap
between any two of them is 0.179 and none is refused. Its 8 cells with no
evidence at all also pass, and they are the interesting case — each names
the artefact THAT capability would have left ("test plans, sign-off
records, defect logs"), so four sentences reporting the same outcome share
almost no content words. On the two payloads refused the same day, the
outcome was named and the artefact was not, and 703 of 708 syntheses were
one claim.

IT IMPORTS THE GATE, IT DOES NOT RESTATE IT. A second copy of a threshold
is a second answer, and the one that decides is the connector's.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _candidate_roots(repo_root):
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


def _load_connector(repo_root):
    tried = []
    for root in _candidate_roots(repo_root):
        mcp = os.path.join(root, "apps", "mcp")
        tried.append(mcp)
        if not os.path.isdir(mcp):
            continue
        if mcp not in sys.path:
            sys.path.insert(0, mcp)
        try:
            from dma_mcp import contracts, vacuity              # noqa: E402
        except Exception as exc:                                # noqa: BLE001
            sys.exit(f"found {mcp} but could not import it: {exc!r}")
        return contracts, vacuity, mcp
    try:
        from dma_mcp import contracts, vacuity                  # noqa: E402
    except Exception:                                           # noqa: BLE001
        pass
    else:
        return contracts, vacuity, "installed dma_mcp on sys.path"
    sys.exit(
        "cannot reach the connector's CG-15 module, so NOTHING was measured.\n"
        "Give it a checkout of the DMA Insights repository, any one of:\n"
        "  check_repetition.py ... --repo /path/to/Accelerate\n"
        "  export DMA_INSIGHTS_REPO=/path/to/Accelerate\n"
        "  run it from inside the checkout\n"
        "looked for apps/mcp under:\n  " + "\n  ".join(tried[:8]))


def _texts(payload, page, contracts, vacuity):
    """Every (section, field[*].key, [(label, text)]) the page budgets.

    Accepts a whole page payload, a single section, or a bare list of
    strings under any key — a producer with twenty drafts in a scratch file
    should not have to build a payload to ask this question."""
    out = []
    floors = vacuity.prose_floors(page)
    for name, reg in sorted(floors.items()):
        body = payload.get(name)
        if not isinstance(body, dict):
            continue
        for fname, per_key in sorted(reg["items"].items()):
            value = body.get(fname)
            items = (value if isinstance(value, list)
                     else [value] if isinstance(value, dict) else [])
            # The gate's own exemption, applied here for the same reason it
            # exists there: an item that records an absence ON THE KEYS ITS
            # CONTRACT SHAPE DECLARES is saying the same thing as its
            # siblings because it IS the same finding. Skipping this made
            # the promoted run's eleven honest alerts read as a template.
            declared = vacuity.item_keys(page, name, fname)
            for key in sorted(per_key):
                rows, exempt = [], 0
                for i, item in enumerate(items):
                    if not isinstance(item, dict) or not isinstance(item.get(key), str):
                        continue
                    if vacuity.records_absence(item, declared):
                        exempt += 1
                        continue
                    label = (item.get("subcap_id") or item.get("f_id")
                             or item.get("ic_id") or item.get("category_id")
                             or f"[{i}]")
                    rows.append((str(label), item[key]))
                if len(rows) >= 2 or exempt:
                    out.append((name, fname, key, rows, exempt))
    return out


def _clusters(rows, vacuity):
    """The same connected components CG-15 builds, with both numbers kept."""
    prepared = [(lab, vacuity.shingles(t), vacuity.claim_words(t))
                for lab, t in rows
                if len(vacuity.tokens(t)) >= vacuity.TEMPLATE_MIN_TOKENS]
    prepared = [p for p in prepared if p[1]]
    index = {}
    for i, (_l, sh, _c) in enumerate(prepared):
        for s in sh:
            index.setdefault(s, []).append(i)
    cand = set()
    for members in index.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                cand.add((members[a], members[b]))

    adj = {i: set() for i in range(len(prepared))}
    top_raw = top_claim = 0.0
    worst = None
    for a, b in cand:
        raw = vacuity._overlap(prepared[a][1], prepared[b][1])
        claim = vacuity._overlap(prepared[a][2], prepared[b][2])
        if raw > top_raw:
            top_raw, worst = raw, (prepared[a][0], prepared[b][0], raw, claim)
        top_claim = max(top_claim, claim)
        if raw < vacuity.TEMPLATE_OVERLAP:
            continue
        measurable = min(len(prepared[a][2]),
                         len(prepared[b][2])) >= vacuity.CLAIM_MIN_WORDS
        if measurable and claim < vacuity.CLAIM_OVERLAP:
            continue
        adj[a].add(b)
        adj[b].add(a)

    comps, seen = [], set()
    for i in range(len(prepared)):
        if i in seen or not adj[i]:
            continue
        stack, comp = [i], []
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(k)
            stack.extend(adj[k] - seen)
        if len(comp) >= vacuity.TEMPLATE_MIN_GROUP:
            comps.append(sorted(prepared[k][0] for k in comp))
    return len(prepared), comps, top_raw, top_claim, worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("payload")
    ap.add_argument("--page", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--at-scale", type=int, default=0, metavar="N",
                    help="how many items this field will eventually carry; "
                         "prints what the drafts imply for the full set")
    a = ap.parse_args(argv)

    contracts, vacuity, whence = _load_connector(a.repo)
    print(f"CG-15 imported from: {whence}", file=sys.stderr)
    print(f"lines: phrasing {vacuity.TEMPLATE_OVERLAP:g} · "
          f"claim {vacuity.CLAIM_OVERLAP:g} · group "
          f"{vacuity.TEMPLATE_MIN_GROUP}+\n", file=sys.stderr)

    payload = json.load(open(a.payload))
    payload = payload.get("payload", payload)
    # a served page ({sections: {name: {data: {…}}}}) unwraps to the shape
    # a submission has, so a promoted run can be measured with the same call
    if "sections" in payload and isinstance(payload["sections"], dict):
        payload = {n: {**{k: v for k, v in b.items() if k != "data"},
                       **(b.get("data") or {})}
                   for n, b in payload["sections"].items()}

    groups = _texts(payload, a.page, contracts, vacuity)
    if not groups:
        print(f"no per-item prose fields found for page {a.page!r} — check "
              "the payload has its sections at the top level")
        return 0

    bad = 0
    for name, fname, key, rows, exempt in groups:
        n, comps, top_raw, top_claim, worst = _clusters(rows, vacuity)
        refused = sum(len(c) for c in comps)
        head = f"{name}.{fname}[*].{key}"
        note = (f" · {exempt} exempt (recorded absence on a key this shape "
                f"declares)" if exempt else "")
        if not comps:
            print(f"PASS  {head}  {n} measured{note} · highest phrasing "
                  f"{top_raw:.3f} · highest claim {top_claim:.3f}")
            if worst and top_raw >= vacuity.TEMPLATE_OVERLAP * 0.75:
                print(f"      closest pair {worst[0]} / {worst[1]} — "
                      f"{worst[2]:.2f} phrasing, {worst[3]:.2f} claim. Under "
                      "the line, but this is the shape to watch.")
            continue
        bad += 1
        print(f"REFUSE {head}  {refused} of {n} in {len(comps)} template "
              f"group(s){note} · highest phrasing {top_raw:.3f} · highest "
              f"claim {top_claim:.3f}")
        for c in comps[:4]:
            shown = ", ".join(c[:6]) + (", …" if len(c) > 6 else "")
            print(f"       group of {len(c)}: {shown}")
        if len(comps) > 4:
            print(f"       … {len(comps) - 4} more group(s)")
        if a.at_scale and n:
            print(f"       at {a.at_scale} items this rate is roughly "
                  f"{round(a.at_scale * refused / n)} refusals — the shape "
                  "does not scale, and it will not become distinct by being "
                  "repeated more times.")

    if not bad:
        print("\nNothing here is a template. Write the rest the same way.")
        return 0
    print("\nWhat to change, in the order that works:\n"
          "  1. Name the ARTEFACT this item would leave, not the outcome. "
          "'Test plans, sign-off records, defect logs' differs per\n"
          "     capability; 'no entity-specific artefact was returned' does "
          "not, however many capabilities you paste it under.\n"
          "  2. If an item genuinely has nothing of its own to say, it does "
          "not belong in the array. Leave it out and let the\n"
          "     section's reach counters and empty_state carry the absence — "
          "one finding, not N copies of one.\n"
          "  3. Do NOT add an item key to declare the absence with unless "
          "the item's own contract shape declares it. An invented\n"
          "     key validates, buys the exemption, and is dropped at "
          "promotion for want of a column.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
