"""Structural parity against the gold shape — Gate J's rules, and CG-PAR's.

THE DEFECT THIS EXISTS FOR (RC-02, SWBC gold audit 2026-10-04). Gate J used
to compare section keys and treat any non-empty list as "filled". Ten
firmographic rows with six held, one sentiment bar against seven, two of
eight platform tiles carrying peer rows — every one of those read identical
to gold, because every one of them had the key and a non-empty list. And it
ran only in CI, against a synthetic pair, so no parity measurement ever
touched a real run before it was promoted.

This module is the one implementation both callers share:

  · `scripts/gate_j_surface_parity.py` — the CLI, against files, the API, or
    the committed gold shapes (`fixtures/surface_gold.json`);
  · `promote.py` — CG-PAR, which compares the staged pages of the run being
    promoted against the same gold shapes and refuses on a structural gap.

It lives here, under the connector, because the promote path runs in the
connector's image and `scripts/` is not in it. Stdlib only, so the CLI keeps
the property every gate script has: it runs with nothing installed.

WHAT A SHAPE IS — and why it carries no values. A shape keeps the keys, the
list lengths and, for every row of a list of objects, which members are
filled, null or absent (the row's "null pattern"). A boolean in FLAG_KEYS
(`quarantined`) is recorded as y/n because a held row is a disposition, not
a value. Nothing else of the content survives: no strings, no numbers, no
names. Two clients are different companies; a thinner number is an
assessment result and never a defect, so the gate cannot see numbers.

A dict whose keys are not snake_case identifiers is a MAP keyed by data (a
category id, a platform name) and is shaped as the list of its values, so a
client's own identifiers never become structural keys and never reach a
committed fixture.

WHAT A GAP IS, against a reference shape:

  section_absent   the reference fills a section the target lacks
  section_empty    the target serves it empty without saying so
  key_absent       a key the reference fills is not on the target
  key_empty        the target carries the key, empty, without saying so
  list_len         target rows < LIST_FLOOR x reference rows
  item_key_missing every reference row carries a member; fewer than
                   ITEM_FLOOR of the target's rows carry it at all
  item_fill        a member's non-null share on the target is below
                   ITEM_FLOOR x the reference's (a null member inside a row
                   is unfilled, which is the half the old gate never saw)
  stated_share     on a fields-type list (rows with `value` and
                   `quarantined`) the share of rows with a value that is not
                   held, below ITEM_FLOOR x the reference's

Nested lists of objects inside rows are pooled across their parents and
compared the same way, with list length per parent.

WITHHELD IS NOT MISSING. A section withheld by audience is a served decision,
reported separately (`withheld_sections`) and never as a gap.

A STATED absence excuses emptiness (`section_empty`, `key_empty`) as before.
Thinness (`list_len`, `stated_share`) is excused only by a ladder whose every
rung reached a terminal outcome — RESOLVED, VERIFIED_ABSENT or
REFUSED+ALTERNATE_TRIED — because RC-05 measured a bare reason string
accepted in place of a search that was never run.

THE FLOORS ARE DEFAULTS, not adjudicated: LIST_FLOOR 0.5 and ITEM_FLOOR 0.6
are the ratios the RCA proposed (RC-02 "needs_owner_decision: floor
ratios"). They live here, named, so changing them is one line and a test.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SHAPE_VERSION = 1
GATE_ID = "CG-PAR"

LIST_FLOOR = 0.5
ITEM_FLOOR = 0.6

# Never compared: the reasoning trace is never served (redaction
# NEVER_SERVED_KEYS) and `internal_only` is redaction machinery, not content.
SKIP_KEYS = frozenset({"r_layer", "internal_only"})
FLAG_KEYS = frozenset({"quarantined"})

# A shape-row character: 1 filled · 0 present-but-null/empty · - absent ·
# y/n a FLAG_KEYS boolean · s a STATED null — null, with the row's own reason
# beside it (`<member>_basis`, or for a peer-comparison member the row's
# `peer_basis` / `proxy_disclosure`). A stated null renders as a stated
# absence with its reason, which is what owner decision 2 (2026-10-04) asks
# of a held field, so it counts as filled for item_fill — and never as a
# stated VALUE for stated_share, which reads `1` only.
_FILLED_CHARS = frozenset("1yns")
_PRESENT_CHARS = frozenset("10yns")

# The peer-comparison members of a score row. With no peer scored anywhere in
# the run ("identified, not scored" — owner, settled) these are one run-level
# fact, not N production gaps: CG-PAR discloses them once instead.
PEER_FAMILY = frozenset({"peer_median", "peer_n", "peer_score", "delta",
                         "direction"})
_PEER_REASON_KEYS = ("peer_basis", "proxy_disclosure")

_ID_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

STATED_EMPTY = ("empty", "none", "verified_absent")
AUDIENCE_DECIDED = ("withheld", "never_served", "redacted")
TERMINAL_OUTCOMES = ("RESOLVED", "VERIFIED_ABSENT", "REFUSED+ALTERNATE_TRIED")
NON_TERMINAL = re.compile(r"not retrieved|neither found nor ruled out|NOT_RUN",
                          re.I)

# Kinds that thinness, not emptiness, produces — excused only by a terminal
# ladder.
THINNESS = frozenset({"list_len", "stated_share"})


# ── shaping ──────────────────────────────────────────────────────────────
def _filled(value) -> bool:
    """A reader sees something. 0 and False are answers, not absences."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _is_map(d: dict) -> bool:
    return bool(d) and not all(_ID_KEY.match(str(k)) for k in d)


def _cell(row: dict, key: str) -> str:
    if key not in row:
        return "-"
    v = row[key]
    if key in FLAG_KEYS and isinstance(v, bool):
        return "y" if v else "n"
    if _filled(v):
        return "1"
    if _filled(row.get(f"{key}_basis")) or (
            key in PEER_FAMILY
            and any(_filled(row.get(k)) for k in _PEER_REASON_KEYS)):
        return "s"
    return "0"


def _list_shape(items: list) -> dict:
    out = {"n": len(items)}
    # A row that is itself a map keyed by data contributes its size only, so
    # its keys (a client's own identifiers) never become shape keys.
    dicts = [(it if not _is_map(it) else {"map_n": len(it)})
             for it in items if isinstance(it, dict) and it]
    if not dicts:
        return out
    keys = sorted({k for d in dicts for k in d if k not in SKIP_KEYS})
    out["keys"] = keys
    out["rows"] = ["".join(_cell(d, k) for k in keys) for d in dicts]
    nested = {}
    for k in keys:
        pooled, parents = [], 0
        for d in dicts:
            v = d.get(k)
            if isinstance(v, list) and any(isinstance(x, dict) for x in v):
                pooled.extend(x for x in v if isinstance(x, dict))
                parents += 1
            elif isinstance(v, dict) and v:
                if _is_map(v):
                    pooled.extend(x for x in v.values() if isinstance(x, dict))
                else:
                    pooled.append(v)
                parents += 1
        if pooled:
            nested[k] = _list_shape(pooled)
    if nested:
        out["nested"] = nested
    return out


def shape_of(value, key=None):
    """The structure of one value, with every value removed."""
    if isinstance(value, dict):
        if _is_map(value):
            return {"map": True, **_list_shape(list(value.values()))}
        return {"o": {k: shape_of(v, k) for k, v in sorted(value.items())
                      if k not in SKIP_KEYS}}
    if isinstance(value, list):
        return _list_shape(value)
    if key in FLAG_KEYS and isinstance(value, bool):
        return "y" if value else "n"
    return 1 if _filled(value) else 0


def node_filled(node) -> bool:
    if node in (1, "y", "n"):
        return True
    if isinstance(node, dict):
        if "o" in node:
            # An object with keys is a section a reader is handed; its empty
            # members are then reported by name (key_empty), which points at
            # the field rather than at the card.
            return len(node["o"]) > 0
        return node.get("n", 0) > 0
    return False


def _ladder_is_terminal(empty_state) -> bool:
    """Every rung of the declared search reached a terminal outcome."""
    if not isinstance(empty_state, dict):
        return False
    rungs = empty_state.get("sources_searched")
    if not isinstance(rungs, list) or not rungs:
        return False
    for r in rungs:
        text = json.dumps(r) if isinstance(r, dict) else str(r)
        if NON_TERMINAL.search(text):
            return False
        if not any(t in text for t in TERMINAL_OUTCOMES):
            return False
    return True


def _states_emptiness(envelope: dict, body) -> bool:
    for src in (envelope, body):
        if not isinstance(src, dict):
            continue
        if str(src.get("data_source") or "").strip().lower() in STATED_EMPTY:
            return True
        es = src.get("empty_state")
        if isinstance(es, dict) and (es.get("reason") or es.get("basis")):
            return True
    return False


def section_shape(envelope: dict, body) -> dict:
    """One section, from the API envelope ({data, withheld, …}) or, for a
    staged payload, the body itself as both envelope and data."""
    envelope = envelope if isinstance(envelope, dict) else {}
    es = None
    for src in (envelope, body):
        if isinstance(src, dict) and isinstance(src.get("empty_state"), dict):
            es = src["empty_state"]
            break
    return {
        "withheld": any(bool(envelope.get(k)) for k in AUDIENCE_DECIDED),
        "stated_empty": _states_emptiness(envelope, body),
        "ladder_terminal": _ladder_is_terminal(es),
        "data": None if body is None else shape_of(body),
    }


def page_shape(doc: dict) -> dict:
    """A page's shape from any of the three forms a page arrives in:

      · already a shape ({"shape_version": …, "sections": {…}})
      · the API's served page ({"sections": {name: {data, withheld…}}})
      · a staged payload ({name: body}, as get_staged_payload reassembles it)
    """
    doc = doc or {}
    if "shape_version" in doc:
        return doc
    out = {}
    if isinstance(doc.get("sections"), dict):
        for name, env in doc["sections"].items():
            env = env if isinstance(env, dict) else {}
            out[name] = section_shape(env, env.get("data"))
    else:
        for name, body in doc.items():
            if str(name).startswith("_") or not isinstance(body, dict):
                continue
            out[name] = section_shape(body, body)
    return {"shape_version": SHAPE_VERSION, "sections": out}


# ── comparing ────────────────────────────────────────────────────────────
def _ratio(rows, key_index, chars) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r[key_index] in chars) / len(rows)


def _col(node: dict, key: str):
    keys = node.get("keys") or []
    return keys.index(key) if key in keys else None


def _stated(node: dict) -> float | None:
    vi, qi = _col(node, "value"), _col(node, "quarantined")
    if vi is None or qi is None or not node.get("rows"):
        return None
    rows = node["rows"]
    return sum(1 for r in rows if r[vi] == "1" and r[qi] != "y") / len(rows)


def _gap(page, section, key, kind, detail):
    return {"page": page, "section": section, "key": key, "kind": kind,
            "detail": detail}


def _compare_list(page, section, path, r, t, out, excused, per_parent=None):
    rn, tn = r.get("n", 0), t.get("n", 0)
    if per_parent:
        r_par, t_par = per_parent
        r_avg = rn / r_par if r_par else 0.0
        t_avg = tn / t_par if t_par else 0.0
    else:
        r_avg, t_avg = float(rn), float(tn)
    if r_avg and t_avg < LIST_FLOOR * r_avg and not excused:
        unit = " per parent row" if per_parent else ""
        out.append(_gap(page, section, path, "list_len",
                        f"{t_avg:g} row(s){unit} against the reference's "
                        f"{r_avg:g} (floor {LIST_FLOOR:.0%})"))
    r_rows, t_rows = r.get("rows") or [], t.get("rows") or []
    if not r_rows or not t_rows:
        return
    fields_type = _stated(r) is not None
    for key in r.get("keys") or []:
        if fields_type and key == "value":
            continue              # stated_share below is the stricter measure
        ri, ti = _col(r, key), _col(t, key)
        r_present = _ratio(r_rows, ri, _PRESENT_CHARS)
        r_fill = _ratio(r_rows, ri, _FILLED_CHARS)
        t_present = 0.0 if ti is None else _ratio(t_rows, ti, _PRESENT_CHARS)
        t_fill = 0.0 if ti is None else _ratio(t_rows, ti, _FILLED_CHARS)
        where = f"{path}[].{key}"
        if r_present == 1.0 and r_fill > 0 and t_present < ITEM_FLOOR:
            out.append(_gap(page, section, where, "item_key_missing",
                            f"every reference row carries it; "
                            f"{t_present:.0%} of the target's {len(t_rows)} "
                            f"row(s) do (floor {ITEM_FLOOR:.0%})"))
        elif r_fill > 0 and t_fill < ITEM_FLOOR * r_fill:
            out.append(_gap(page, section, where, "item_fill",
                            f"filled on {t_fill:.0%} of the target's rows "
                            f"against {r_fill:.0%} on the reference's — a null "
                            f"member is unfilled (floor {ITEM_FLOOR:.0%} of "
                            f"the reference)"))
    rs, ts = _stated(r), _stated(t)
    if rs and ts is not None and ts < ITEM_FLOOR * rs and not excused:
        out.append(_gap(page, section, path, "stated_share",
                        f"{ts:.0%} of the target's rows state a value that is "
                        f"not held, against {rs:.0%} on the reference "
                        f"(floor {ITEM_FLOOR:.0%} of the reference)"))
    for key, rnest in (r.get("nested") or {}).items():
        tnest = (t.get("nested") or {}).get(key)
        if tnest is None:
            continue              # absent members are item_key_missing above
        _compare_list(page, section, f"{path}[].{key}", rnest, tnest, out,
                      excused, per_parent=(len(r_rows), len(t_rows)))


def _compare_object(page, section, prefix, r, t, out, stated, excused):
    for key in sorted(r["o"]):
        rn = r["o"][key]
        if not node_filled(rn):
            continue
        path = f"{prefix}{key}"
        if key not in t["o"]:
            out.append(_gap(page, section, path, "key_absent",
                            "carried by the reference, absent here"))
            continue
        tn = t["o"][key]
        if not node_filled(tn):
            if not stated:
                out.append(_gap(page, section, path, "key_empty",
                                "carried by the reference, empty here"))
            continue
        if isinstance(rn, dict) and isinstance(tn, dict):
            if "o" in rn and "o" in tn:
                _compare_object(page, section, path + ".", rn, tn, out,
                                stated, excused)
            elif "n" in rn and "n" in tn:
                _compare_list(page, section, path, rn, tn, out, excused)


def compare_shapes(page: str, ref: dict, tgt: dict) -> list:
    """Structural gaps of `tgt` against one reference. Pure."""
    out = []
    rs = (page_shape(ref) or {}).get("sections") or {}
    ts = (page_shape(tgt) or {}).get("sections") or {}
    for name in sorted(rs):
        r = rs[name] or {}
        r_data = r.get("data")
        if r.get("withheld") or not node_filled(r_data):
            continue                       # the reference carries nothing
        t = ts.get(name)
        if t is None:
            out.append(_gap(page, name, None, "section_absent",
                            "the reference serves this section and the "
                            "target's payload has no such section"))
            continue
        if t.get("withheld"):
            continue                       # an audience decision, not a gap
        t_data = t.get("data")
        if not node_filled(t_data):
            if not t.get("stated_empty"):
                out.append(_gap(page, name, None, "section_empty",
                                "the reference fills this section and the "
                                "target serves it empty, which renders as a "
                                "blank card rather than as an absence"))
            continue
        if isinstance(r_data, dict) and isinstance(t_data, dict) \
                and "o" in r_data and "o" in t_data:
            _compare_object(page, name, "", r_data, t_data, out,
                            bool(t.get("stated_empty")),
                            bool(t.get("ladder_terminal")))
    return out


def withheld_sections(page: str, ref: dict, tgt: dict) -> list:
    """Sections the reference fills and the target withholds by audience —
    reported, never counted as gaps."""
    rs = (page_shape(ref) or {}).get("sections") or {}
    ts = (page_shape(tgt) or {}).get("sections") or {}
    return [{"page": page, "section": n, "kind": "withheld_by_audience"}
            for n in sorted(rs)
            if node_filled((rs[n] or {}).get("data"))
            and (ts.get(n) or {}).get("withheld")]


def _gap_key(g):
    return (g["kind"], g["section"], g["key"])


def compare_against_gold(page: str, golds: dict, tgt: dict,
                         skip_sections=()) -> list:
    """Gaps the target shows against EVERY gold run that fills the section.

    A floor the reference fails is not a standard (GOLD-STANDARD.md). So a
    gap counts only when it holds against the thinnest gold that serves the
    section — the standard every gold meets by construction, which is what
    lets the gold runs promote against their own fixture.
    """
    tshape = page_shape(tgt)
    per_gold = {}                      # label -> {gap_key: gap}
    for label, pages in sorted((golds or {}).items()):
        gshape = (pages or {}).get(page)
        if gshape is None:
            continue
        per_gold[label] = {_gap_key(g): g
                           for g in compare_shapes(page, gshape, tshape)}
    # EVERY gold that has the page must show the gap. A gold that does not
    # fill a section (Golden 1 serves no value chain, which the contract
    # makes optional) has set no floor there, so nothing is owed.
    holders = sorted(per_gold)
    out = {}
    for label, gaps in per_gold.items():
        for k, g in gaps.items():
            if k in out or g["section"] in skip_sections:
                continue
            if holders and all(k in per_gold[lb] for lb in holders):
                out[k] = {**g, "against": holders,
                          "detail": "; ".join(f"{lb}: {per_gold[lb][k]['detail']}"
                                              for lb in holders)}
    return sorted(out.values(),
                  key=lambda g: (g["section"], str(g["key"]), g["kind"]))


# ── the committed gold ──────────────────────────────────────────────────
_GOLD = None


def gold_path() -> Path:
    """The connector's copy (always in the image); byte-identical to
    fixtures/surface_gold.json, which a test asserts."""
    return Path(__file__).with_name("surface_gold.json")


def load_gold(path: Path | None = None) -> dict:
    global _GOLD
    if path is not None:
        return json.loads(Path(path).read_text())
    if _GOLD is None:
        _GOLD = json.loads(gold_path().read_text())
    return _GOLD


def gold_runs(gold: dict) -> dict:
    """{label: {page: shape}} from the committed gold document."""
    return {label: run.get("pages") or {}
            for label, run in (gold.get("runs") or {}).items()}


def never_served(gold: dict) -> set:
    return {tuple(k.split(".", 1)) for k, v in
            (gold.get("dispositions") or {}).items()
            if v.get("internal") == "never_served"}


def check_run(pages: dict, gold: dict | None = None, declared=None) -> dict:
    """CG-PAR over a whole run's staged pages, internal audience.

    Sections the app serves to no audience (NEVER_SERVED) are skipped: a
    parity gap on a section no reader sees is not a gap a reader meets.

    `declared(page, section)` -> the field names today's contract declares,
    or None for a section it does not know. A gold run is cut on the
    contract of its day; a key the contract has since retired is not a key a
    new run can owe, so a gap on one is dropped rather than refused.
    """
    gold = gold if gold is not None else load_gold()
    runs = gold_runs(gold)
    skip = never_served(gold)
    gaps = []
    for page, payload in sorted((pages or {}).items()):
        skip_here = {s for (p, s) in skip if p == page}
        for g in compare_against_gold(page, runs, payload or {},
                                      skip_sections=skip_here):
            if declared is not None:
                fields = declared(page, g["section"])
                if fields is None:
                    continue
                top = str(g.get("key") or "").split(".")[0].split("[")[0]
                if top and top not in fields:
                    continue
            gaps.append(g)
    disclosed = []
    if not peers_scored(pages):
        keep = []
        for g in gaps:
            leaf = str(g.get("key") or "").split(".")[-1]
            if g["kind"] == "item_fill" and leaf in PEER_FAMILY:
                disclosed.append({**g, "kind": "peers_not_scored",
                                  "detail": "no peer figure exists anywhere "
                                            "in this run (identified, not "
                                            "scored); disclosed once, not "
                                            "refused per row"})
            else:
                keep.append(g)
        gaps = keep
    return {"gate_id": GATE_ID, "gaps": gaps, "disclosed": disclosed,
            "gold_runs": sorted(runs),
            "floors": {"list": LIST_FLOOR, "item": ITEM_FLOOR}}


def peers_scored(pages: dict) -> bool:
    """Does any peer figure exist in this run? Read from the overview's pillar
    rows — the one place every run states a peer median or says why not."""
    ov = page_shape((pages or {}).get("overview") or {})
    sec = (ov["sections"].get("scores") or {}).get("data") or {}
    pillars = (sec.get("o") or {}).get("pillars") if isinstance(sec, dict) else None
    if not isinstance(pillars, dict) or not pillars.get("rows"):
        return True               # cannot tell: excuse nothing
    i = _col(pillars, "peer_median")
    return i is not None and any(r[i] == "1" for r in pillars["rows"])
