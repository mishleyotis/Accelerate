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
ratios"). They live here, named, so changing them is one line and a test —
and since owner decision B (2026-10-04) they measure WARNINGS only.

WHAT REFUSES. The kinds above are measurements; `classify` decides which of
them refuse, against today's contract — structural gaps only (a section or
key the gold always serves is missing; a must-present field null or held
beyond the cap, `must_present_gaps`). `check_run` picks the gold a run is
held to: leave-one-out, and the run's own sub-vertical first, with the
other gold used for structure only. See the block above `classify`.
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
_NAMED_KEY = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

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
    out = {
        "withheld": any(bool(envelope.get(k)) for k in AUDIENCE_DECIDED),
        "stated_empty": _states_emptiness(envelope, body),
        "ladder_terminal": _ladder_is_terminal(es),
        "data": None if body is None else shape_of(body),
    }
    # The snake_case identifiers the empty_state names — a key a section
    # says it omits, and why ("gap_analysis is omitted: only one audience
    # was established"). Identifiers only, never the sentence around them.
    named = sorted(set(_NAMED_KEY.findall(json.dumps(es)))) if es else []
    if named:
        out["named"] = named
    return out


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

    "Every" is what makes a structural gap a statement about the gold rather
    than about one gold run: a key Golden 1 serves and Baxter does not is not
    a key "the gold always serves", so nothing is owed (Golden 1 serves no
    value chain, which the contract makes optional). `golds` is the
    reference set check_run chose — leave-one-out, sub-vertical first — so
    the target is never in it.
    """
    tshape = page_shape(tgt)
    per_gold = {}                      # label -> {gap_key: gap}
    for label, pages in sorted((golds or {}).items()):
        gshape = (pages or {}).get(page)
        if gshape is None:
            continue
        per_gold[label] = {_gap_key(g): g
                           for g in compare_shapes(page, gshape, tshape)}
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


# ── what blocks, and what only warns — owner decision B, 2026-10-04 ──────
#
# THE FIRST CG-PAR BLOCKED ON EVERYTHING ABOVE, and the review measured what
# that did to a client that is not a gold run: goeasy-ltd's promoted run
# 02e840d4 (CL) drew 16 refusals, most of them COUNTS — 15 tech rows against
# 56, 2 cited ids against 12, 2 addressable cells against 5. How many rows a
# client has is an assessment result; refusing on it pushes producers to pad,
# and the floors that decided it (LIST_FLOOR, ITEM_FLOOR) were never
# adjudicated. The owner's rule:
#
#   BLOCK  a section or key the gold always serves is missing, or a
#          must-present field is null or held beyond the decision-2 cap;
#   WARN   list-length and fill-ratio differences — reported in the
#          verdict, never a refusal.
#
# "Missing" is read against TODAY'S CONTRACT, because the gold runs were cut
# on the contract of their day and the gold set itself disagrees about keys
# the contract has since made optional:
#
#   · a section or key the contract no longer declares is owed by nobody;
#   · an OPTIONAL section, or an optional key with no stated condition
#     (`storyline_challenge`), warns — the contract permits the omission;
#   · an optional key whose absence the contract makes CONDITIONAL
#     (`absence_is_correct_when`: `gap_analysis` — "only one audience was
#     established") blocks unless the section says the condition holds, by
#     naming the key in its empty_state. The gold always serves it, so an
#     unexplained omission is the gap;
#   · a REQUIRED key is excused only when the section's empty_state names
#     it, or when every list in the section is empty and it says why — an
#     empty_state about some other key excuses nothing.

STRUCTURAL = frozenset({"section_absent", "section_empty", "key_absent",
                        "key_empty"})
COUNTS = frozenset({"list_len", "item_key_missing", "item_fill",
                    "stated_share"})
HELD_BEYOND_CAP = "held_beyond_cap"
# Never owed by a target: stated-absence and reasoning machinery.
NEVER_OWED = frozenset({"empty_state", "r_layer", "internal_only"})
# Envelope members that say nothing about whether a section has content.
_ENVELOPE = frozenset({"e_ids", "internal_only", "empty_state", "r_layer",
                       "narrative_thread", "produced_at", "producer_version"})
#: The sub-vertical codes a gold run may be recorded under
#: (dma_mcp.subverticals.SUBVERTICAL_NAMES; restated so this stays stdlib).
SUB_VERTICALS = frozenset({"RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC",
                           "IB"})


def _contract_sections():
    from .contracts import sections      # stdlib-only, like this module
    return sections


def _content_empty(t_sec: dict) -> bool:
    """No list, map or object member of the section carries anything."""
    data = (t_sec or {}).get("data")
    if not isinstance(data, dict) or "o" not in data:
        return True
    for key, node in data["o"].items():
        if key in _ENVELOPE or not isinstance(node, dict):
            continue
        if node_filled(node):
            return False
    return True


def classify(page: str, gap: dict, t_sec: dict | None = None,
             sections=None) -> tuple:
    """("block" | "warn" | None, why) for one gap. None: nothing is owed."""
    kind = gap["kind"]
    if kind == HELD_BEYOND_CAP:
        return "block", "a must-present field null or held beyond the cap"
    if kind not in STRUCTURAL | COUNTS:
        return "block", "unclassified gap kind — fail closed"
    sections = sections or _contract_sections()
    try:
        sec = sections(page).get(gap["section"])
    except Exception:                                 # noqa: BLE001
        sec = None
    if kind == "item_key_missing" and sec is not None \
            and _row_key_required(sec, str(gap.get("key") or "")):
        return "block", ("a row key today's contract requires (item_shape) "
                         "and every gold row carries")
    if kind in COUNTS:
        return "warn", ("a count or fill ratio — an assessment result, "
                        "reported and never refused (owner decision B)")
    if sec is None:
        return None, "a section today's contract does not declare"
    if kind in ("section_absent", "section_empty"):
        if sec.get("required"):
            return "block", "a required section the gold always serves"
        return "warn", "the contract makes this section optional"
    key = str(gap.get("key") or "")
    top = re.split(r"[.\[]", key)[0]
    if top in NEVER_OWED:
        return None, "stated-absence machinery, never owed"
    fs = (sec.get("fields") or {}).get(top)
    if fs is None:
        return None, "a key today's contract no longer declares"
    if top != key:
        return "warn", (f"a member inside `{top}`, which the contract does "
                        "not enumerate")
    t_sec = t_sec or {}
    stated = bool(t_sec.get("stated_empty"))
    if stated and _content_empty(t_sec):
        return "warn", "the section's lists are empty and it says why"
    if top in (t_sec.get("named") or ()):
        return "warn", "the section's empty_state names this key"
    cond = fs.get("absence_is_correct_when")
    if kind == "key_empty":
        if fs.get("may_be_empty"):
            return None, "the contract says this list may be empty"
        if top == "e_ids":
            return "warn", "a citation count"
        if cond:
            return "warn", f"empty is contract-legal when {cond}"
        if fs.get("required"):
            return "block", ("a required key, served empty without a "
                             "stated reason")
        return "warn", "an optional key, served empty"
    if fs.get("required"):
        # An empty_state excuses a missing required key only when it NAMES
        # that key (handled above) or the whole section is empty and says
        # why. An empty_state about something else excuses nothing — it was
        # the hole review found: any stated reason waved every required key
        # through (owner decision B: a key the gold always serves blocks).
        # One exception, by construction: inside an OPTIONAL section that
        # states its emptiness, the whole section could have been omitted
        # (a warning), so a partial stated-empty body must not block harder
        # than omitting it would (Baxter's insufficient-cohort H8).
        if stated and not sec.get("required"):
            return "warn", ("a required key inside an optional section that "
                            "states why it is empty")
        return "block", "a required key the gold always serves"
    if cond:
        return "block", (f"the contract allows omitting `{top}` only when "
                         f"{cond}; every gold run serves it and this section "
                         f"does not say the condition holds — serve it, or "
                         f"name `{top}` in empty_state with the reason")
    return "warn", "the contract makes this key optional"


def _row_key_required(sec: dict, path: str) -> bool:
    """Is `list[].member` (or `list[].object[].member`) a row key the
    contract's machine-readable item_shape requires? Only those are KEYS the
    gold always serves in the decision's sense; every other row member is
    described in prose, and the gold runs — cut on the contracts of their
    day — disagree about them, so a missing one is reported, not refused."""
    parts = path.split("[].")
    if len(parts) not in (2, 3):
        return False
    fs = (sec.get("fields") or {}).get(parts[0]) or {}
    shape = fs.get("item_shape") or {}
    if len(parts) == 3:
        shape = shape.get(parts[1])
        if not isinstance(shape, dict):
            return False
        want = (shape.get("required_keys") or shape.get("item_required_keys")
                or [])
    else:
        want = shape.get("required_keys") or []
    return parts[-1] in want


# ── must-present, null or held beyond the cap (CG-18b's rule) ────────────
def _norm_member(s) -> str:
    """validation._norm_member, restated (stdlib): case and punctuation fold,
    so `Primary_regulator`, `primary regulator` and `primary-regulator` are
    one member."""
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def _member_groups(fs: dict) -> list:
    groups = []
    for want in fs.get("must_present") or []:
        groups.append(list(want) if isinstance(want, (list, tuple)) else [want])
    for group in fs.get("must_present_any") or []:
        groups.append(list(group))
    return groups


def _held_cap(fs: dict, n: int):
    hc = fs.get("held_ceiling")
    if not isinstance(hc, dict) or n <= 0:
        return None
    return min(float(hc.get("max_count", n)),
               float(hc.get("max_share", 1.0)) * n)


def _bodies(payload):
    """{section: raw body} from a staged payload or a served page; a page
    that is already a shape has no values to read and yields nothing."""
    payload = payload or {}
    if "shape_version" in payload:
        return {}
    if isinstance(payload.get("sections"), dict):
        return {n: (e or {}).get("data")
                for n, e in payload["sections"].items()
                if isinstance(e, dict)}
    return {n: b for n, b in payload.items() if not str(n).startswith("_")}


def must_present_gaps(page: str, payload, sections=None) -> list:
    """Must-present members not stated — held, null, or absent — beyond the
    owner's cap: at most 2, or 25% of the set, whichever is smaller (decision
    2). The set is the contract's (`must_present`, `must_present_any`), the
    one CG-18b reads at pass 1; the sub-vertical's own set is CG-18c's, at
    submit. A list that is empty beside a stated empty_state has said so."""
    sections = sections or _contract_sections()
    try:
        secs = sections(page)
    except Exception:                                 # noqa: BLE001
        return []
    out = []
    for name, body in sorted(_bodies(payload).items()):
        if not isinstance(body, dict) or name not in secs:
            continue
        for fname, fs in sorted((secs[name].get("fields") or {}).items()):
            groups = _member_groups(fs)
            cap = _held_cap(fs, len(groups))
            val = body.get(fname)
            if cap is None or not isinstance(val, list):
                continue
            if not val and _states_emptiness(body, body):
                continue
            key = fs.get("must_present_key", "field")
            stated, held = set(), set()
            for item in val:
                if not isinstance(item, dict):
                    continue
                m = _norm_member(item.get(key))
                if item.get("value") not in (None, "", []):
                    stated.add(m)
                elif item.get("quarantined"):
                    held.add(m)
            unstated = []
            for g in groups:
                norms = [_norm_member(a) for a in g]
                if any(n in stated for n in norms):
                    continue
                state = ("held" if any(n in held for n in norms)
                         else "null or absent")
                unstated.append(f"{g[0]} ({state})")
            if len(unstated) > cap:
                out.append(_gap(page, name, fname, HELD_BEYOND_CAP,
                                f"{len(unstated)} of {len(groups)} "
                                f"must-present members are not stated — "
                                f"{', '.join(unstated)}; the cap is "
                                f"{int(cap)} (at most 2, or 25% of the set, "
                                f"whichever is smaller — owner decision 2)"))
    return out


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


def reference_set(gold: dict, run_id=None, sub_vertical=None,
                  exclude=()) -> dict:
    """Which gold runs a target is held to, and on what terms.

    LEAVE-ONE-OUT. A gold run in its own reference set can never show a gap
    against it, which made "the gold runs pass" a statement about nothing
    (review of fix/gold-parity-promote). The target's own run — matched on
    the recorded run-id prefix, or named in `exclude` — is left out.

    SUB-VERTICAL FIRST. Gold runs of the target's sub-vertical, when any
    remain, are the reference for structure AND for the count/fill warnings.
    When none does, every remaining gold run is the reference for STRUCTURE
    ONLY: a consumer lender is not thinner than three credit unions in any
    sense worth reporting, but a section every gold run serves is a section
    every run serves."""
    meta = gold.get("runs") or {}
    prefix = str(run_id or "").strip().lower()[:8]
    excluded = set(exclude or ())
    left_out = sorted(
        lb for lb in meta
        if lb in excluded
        or (prefix and str(meta[lb].get("run_id_prefix") or "").lower()
            == prefix))
    refs = sorted(lb for lb in meta if lb not in left_out)
    matched = [lb for lb in refs
               if sub_vertical and meta[lb].get("sub_vertical") == sub_vertical]
    return {"left_out": left_out,
            "compared_against": matched or refs,
            "tier": "sub_vertical" if matched else "cross_sub_vertical",
            "sub_vertical": sub_vertical}


def check_run(pages: dict, gold: dict | None = None, *, run_id=None,
              sub_vertical=None, exclude=(), sections=None) -> dict:
    """CG-PAR over a whole run's pages, internal audience.

    Returns `blocking` (structural gaps, and must-present members null or
    held beyond the cap) and `warnings` (counts and fill ratios, and the
    structural differences today's contract makes optional). `gaps` is
    `blocking`, for readers of the first version.

    Sections the app serves to no audience (NEVER_SERVED) are skipped: a
    parity gap on a section no reader sees is not a gap a reader meets.
    """
    gold = gold if gold is not None else load_gold()
    runs = gold_runs(gold)
    ref = reference_set(gold, run_id, sub_vertical, exclude)
    if not ref["compared_against"]:
        # CHECK_NEVER_RAN_READS_AS_UNKNOWN: nothing compared is not clean.
        raise ValueError("no gold run is left to compare against "
                         f"(left out: {ref['left_out']})")
    golds = {lb: runs[lb] for lb in ref["compared_against"]}
    structure_only = ref["tier"] != "sub_vertical"
    skip = never_served(gold)
    blocking, warnings = [], []
    for page, payload in sorted((pages or {}).items()):
        tshape = page_shape(payload or {})
        tsecs = tshape.get("sections") or {}
        skip_here = {s for (p, s) in skip if p == page}
        for g in compare_against_gold(page, golds, tshape,
                                      skip_sections=skip_here):
            sev, why = classify(page, g, tsecs.get(g["section"]), sections)
            if sev is None:
                continue
            if structure_only and sev == "warn" and g["kind"] in COUNTS:
                continue      # another sub-vertical's counts are not ours
            (blocking if sev == "block" else warnings).append(
                {**g, "severity": sev, "why": why})
        for g in must_present_gaps(page, payload, sections):
            if g["section"] in skip_here:
                continue
            blocking.append({**g, "severity": "block", "against": [],
                             "why": "a must-present field null or held "
                                    "beyond the cap"})
    disclosed = []
    if not peers_scored(pages):
        keep = []
        for g in warnings:
            leaf = str(g.get("key") or "").split(".")[-1]
            if g["kind"] == "item_fill" and leaf in PEER_FAMILY:
                disclosed.append({**g, "kind": "peers_not_scored",
                                  "detail": "no peer figure exists anywhere "
                                            "in this run (identified, not "
                                            "scored); disclosed once, not "
                                            "warned per row"})
            else:
                keep.append(g)
        warnings = keep
    return {"gate_id": GATE_ID, "blocking": blocking, "gaps": blocking,
            "warnings": warnings, "disclosed": disclosed,
            "gold_runs": sorted(runs), **ref,
            "floors": {"list": LIST_FLOOR, "item": ITEM_FLOOR,
                       "blocking": False}}


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
