#!/usr/bin/env python3
"""Gate J — a client's surfaces must not be thinner than the reference client's.

THE DEFECT THIS EXISTS FOR. Three rounds of reports on one client said the
same thing in different words: "this page is empty", "this card is missing",
"Baxter has it and Logix does not". Every one of those was true, none of them
was visible to any check we had, and each was found by a human opening two
browser tabs side by side. A contract gate asks "is this field allowed"; it
cannot ask "does this client carry what the client next to it carries",
because both answers are contract-legal.

WHAT IT COMPARES, and what it deliberately does not. Structure only:

  · a section the reference serves and the target withholds or serves empty
  · a KEY the reference's section carries and the target's does not
  · a key present on both where the reference has rows and the target has none

It never compares VALUES. Two clients are different companies; a thinner
number is an assessment result and not a defect, and a gate that argued
otherwise would be pushing every client toward the reference's answers, which
is the one thing this build must never do. Only the SHAPE of what is served
is comparable, and a shape the reference fills and the target leaves empty is
a production gap rather than a finding about the client.

WITHHELD IS NOT MISSING. A section the API withholds by audience — the
redaction rung table — is a served decision, so it is reported separately and
never as a gap. Otherwise every customer-audience run would fail against an
internal-audience reference.

usage:
    gate_j_surface_parity.py --api URL --reference SLUG --target SLUG [--token T]
    gate_j_surface_parity.py --reference-file a.json --target-file b.json --page overview

Exits 1 on a gap, 0 otherwise. Stdlib only, like every other gate here.
"""
from __future__ import annotations

import argparse
import json
import sys

PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")

# A section whose absence on the target is a decision rather than a gap.
# `context` is internal-only, so a customer read 403s by design.
AUDIENCE_DECIDED = ("withheld", "never_served", "redacted")


def _sections(doc: dict) -> dict:
    return (doc or {}).get("sections") or {}


def _is_withheld(sec: dict) -> bool:
    return any(bool(sec.get(k)) for k in AUDIENCE_DECIDED)


def _filled(value) -> bool:
    """Does this key carry anything a reader would see?

    An empty list and an empty dict are the shapes that read as a blank card,
    which is the whole complaint. `0` and `False` are real answers and count
    as filled — a count of zero is information, and treating it as absence is
    how a computed zero gets mistaken for a drop.
    """
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return len(value) > 0
    return True


def compare_page(page: str, ref: dict, tgt: dict) -> list:
    """Structural gaps on one page. Pure, so the tests can drive it."""
    out = []
    rs, ts = _sections(ref), _sections(tgt)
    for name in sorted(rs):
        r_sec, t_sec = rs[name] or {}, ts.get(name)
        r_data = r_sec.get("data")
        if not _filled(r_data):
            continue                      # the reference carries nothing here
        if t_sec is None:
            out.append({"page": page, "section": name, "key": None,
                        "kind": "section_absent",
                        "detail": "the reference serves this section and the "
                                  "target's payload has no such section"})
            continue
        if _is_withheld(t_sec):
            continue                      # an audience decision, not a gap
        t_data = t_sec.get("data")
        if not _filled(t_data):
            out.append({"page": page, "section": name, "key": None,
                        "kind": "section_empty",
                        "detail": "the reference fills this section and the "
                                  "target serves it empty, which renders as a "
                                  "blank card rather than as an absence"})
            continue
        if not (isinstance(r_data, dict) and isinstance(t_data, dict)):
            continue
        for key in sorted(r_data):
            if not _filled(r_data[key]):
                continue
            if key not in t_data:
                out.append({"page": page, "section": name, "key": key,
                            "kind": "key_absent",
                            "detail": "carried by the reference, absent here"})
            elif not _filled(t_data[key]):
                out.append({"page": page, "section": name, "key": key,
                            "kind": "key_empty",
                            "detail": "carried by the reference, empty here"})
    return out


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--reference")
    ap.add_argument("--target")
    ap.add_argument("--token")
    ap.add_argument("--audience", default="internal")
    ap.add_argument("--reference-file")
    ap.add_argument("--target-file")
    ap.add_argument("--page", default="overview")
    a = ap.parse_args()

    gaps, compared = [], 0
    if a.reference_file and a.target_file:
        ref = json.loads(open(a.reference_file).read())
        tgt = json.loads(open(a.target_file).read())
        gaps, compared = compare_page(a.page, ref, tgt), 1
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
                gaps.append({"page": page, "section": None, "key": None,
                             "kind": "page_unreadable",
                             "detail": f"HTTP {ts} for the target while the "
                                       f"reference served"})
                continue
            gaps.extend(compare_page(page, ref, tgt))
    else:
        ap.error("--api with --reference/--target, or both --*-file")

    # A COMPARISON THAT COMPARED NOTHING IS NOT A CLEAN COMPARISON, and this
    # gate said otherwise on its first live run: a mistyped reference slug
    # 404ed on all six pages and it printed "no structural gap". That is the
    # CHECK_NEVER_RAN_READS_AS_UNKNOWN shape, in the gate written to catch a
    # sibling of it.
    if not compared:
        print("Gate J: the reference client served NO page — nothing was "
              "compared, so nothing is clean. Check the reference slug "
              "against /v1/directory and the audience the token can read.")
        return 1
    if not gaps:
        print(f"Gate J: no structural gap against the reference client "
              f"({compared} page(s) compared).")
        return 0
    print(f"Gate J: {len(gaps)} structural gap(s) against the reference:")
    for g in gaps:
        where = ".".join(str(x) for x in (g["page"], g["section"], g["key"])
                         if x)
        print(f"  [{g['kind']}] {where} — {g['detail']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
