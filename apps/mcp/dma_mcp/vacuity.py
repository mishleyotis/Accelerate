"""CG-15 — a payload that says nothing (stage 2.4, pass 1).

Every other gate in this connector checks STRUCTURE, IDENTITY or
ARITHMETIC. None of them reads the prose for content. A six-page payload
with all 34 sections present, every required field populated with "N/A"
or `[]`, every id resolving and every figure agreeing with the workbook
produces zero blocking reasons and is eligible for `promote_run`. The
pipeline's own defences cannot tell a real assessment from an empty
shell, which for clients 2..50 is the failure mode that matters most.

Five shapes are refused, each with its arithmetic stated in the verdict:

  1. a placeholder scalar where the contract requires prose — "N/A",
     "TBD", "-", "none", "pending", the empty string, whitespace;
  2. a prose field under a credible floor for ITS OWN contract — the
     floor is read from the field's `doc` text, so a 6-14-word
     `consequence` and a 90-150-word `story_md` are held to different
     numbers and neither is hardcoded here;
  3. a section every one of whose present content fields is vacuous —
     the semantically-empty section, the headline case;
  4. template prose repeated across three or more items with only a name
     substituted, measured as 8-gram overlap;
  5. prose that only restates a score or band, or only inventories the
     evidence ("Two items speak to this cell"), measured as the count of
     content words left after the score and inventory registers are
     removed.

WHAT IT DELIBERATELY ALLOWS. An honest ABSENCE is a finding, and
refusing it would be worse than the hole this closes: it would push
producers toward fabricating content to get past a gate.

  · A section carrying a valid `empty_state` (reason + sources_searched)
    is not a shell — check 3 stands down for it. That, and only that:
    an empty_state on a POPULATED section does not exempt the prose it
    carries, or one declared absence would switch the gate off for
    everything beside it.
  · An ITEM recording an absence on the protocol's own ladder
    (`WORKED_ABSENT`, `UNWORKED`, `NOT_RUN`, `verified_absent`,
    `verified_sparse`, `cannot_estimate`, `insufficient_cohort`,
    `quarantined`) WITH the search that established it is exempt from
    the floor, the residual and the template checks. Eleven alerts whose
    ladder ran and found nothing say the same sentence eleven times
    because it is the same finding eleven times; demanding variation
    there would be demanding invention.

The one thing no absence excuses is a bare placeholder. "N/A" is not the
absence protocol — the protocol is a reason and a sources_searched
ladder, and it is available on every section that needs it.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

from .contracts import sections

GATE = "CG-15"

# ── thresholds, every one of them tuned against the promoted Baxter run ──
#
# FLOOR_FACTOR: the contract's stated floor times this is the refusal
# line. The promoted run's LOWEST ratio of actual words to stated floor is
# 0.64 (a 16-word timeline body against a 25-word floor — real content
# that undershoots its contract), so 0.5 refuses no prose that run
# carries while still refusing "N/A" (1/25) and a three-word stub.
FLOOR_FACTOR = 0.5
# Below this stated floor the field is a LABEL, not prose (a 1-3-word
# `theme`, an 8-16-word `title`), and only the placeholder check applies.
FLOOR_MIN_STATED = 6
FLOOR_MIN_WORDS = 3

# RESIDUAL: content words surviving the score and evidence-inventory
# registers. The promoted run's minimum is 4 (a 7-word `consequence`), so
# 2 leaves a clear margin and still catches a text made of nothing else.
RESIDUAL_FLOOR = 2
RESIDUAL_MIN_TOKENS = 5      # shorter than this and the word floor owns it

# TEMPLATE: 8-gram shingles, overlap = |A ∩ B| / min(|A|, |B|), refused
# when three or more items of the same field are mutually above the line.
# Measured over all 249,374 item-prose pairs of the promoted run: the
# highest overlap between two genuinely distinct arguments is 0.179 (two
# of the 706 heatmap cell syntheses), while the seventeen ceilings
# rationales — one template with the citation swapped, two pairs of them
# byte-identical — run 0.20 to 1.00. 0.40 puts the line between the two
# populations with better than a 2x margin above the honest maximum, and
# catches all seventeen template rows rather than the thirteen that a
# 0.60 line reached.
SHINGLE_N = 8
TEMPLATE_OVERLAP = 0.40
TEMPLATE_MIN_GROUP = 3
TEMPLATE_MIN_TOKENS = 12     # fewer tokens than this makes < 5 shingles


# ── placeholder scalars ───────────────────────────────────────────────
#
# Case- and punctuation-insensitive: "N/A." , "n.a", "—", "TBD" and
# "  " all normalise to the same key. The set is the vocabulary of NOT
# HAVING WRITTEN THE FIELD YET, which is what makes it refusable — an
# honest absence has a reason and a ladder, never a dash.
PLACEHOLDERS = frozenset((
    "", "na", "n a", "n/a", "tbd", "tba", "tk", "todo", "to do",
    "to be determined", "to be confirmed", "to be advised", "none",
    "none found", "none identified", "none available", "no data",
    "no data available", "not applicable", "not available", "not found",
    "not established", "not determined", "not assessed", "not known",
    "unknown", "unspecified", "undefined", "undetermined", "pending",
    "nil", "null", "nan", "empty", "blank", "placeholder", "xxx", "x",
    "lorem ipsum", "?", "??", "???",
))
_PUNCT = re.compile(r"[^\w\s/]+", re.UNICODE)
_WS = re.compile(r"\s+")


def normalise_scalar(text: str) -> str:
    """A placeholder key: lowercase, punctuation dropped (except the
    slash of `n/a`), whitespace collapsed. `"—"` and `"  "` both land on
    the empty string, which is in the set."""
    if not isinstance(text, str):
        return ""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


# The same set with separators squashed out, so "N / A", "n.a." and
# "not-applicable" land on the spellings above instead of slipping past
# them one punctuation mark at a time.
_SQUASHED = frozenset(p.replace(" ", "").replace("/", "")
                      for p in PLACEHOLDERS) - {""}


def is_placeholder(text: str) -> bool:
    key = normalise_scalar(text)
    if key in PLACEHOLDERS:
        return True
    return key.replace(" ", "").replace("/", "") in _SQUASHED


# ── the score and evidence-inventory registers ────────────────────────
#
# A synthesis that only restates the score ("P4C1 scores 2.1, below the
# peer median of 3.0") and one that only inventories the corpus ("Two
# items speak to this cell") are the two ways a producer fills a prose
# field without asserting anything about the institution. Both are
# measured the same way: strip the register, count what is left.
_STOP = frozenset("""
a an the this that these those it its their his her our your my we they he she
of in on at to for by with from into onto over under above below across through
during and or but nor so yet as than then also plus while whereas because if
when where which who whom whose what is are was were be been being am do does
did done has have had having not no none only just even still more most less
least very much many few one two three four five six seven eight nine ten
first second third same both each either neither other another such per via
about around already can could may might must shall should will would here
there now today currently there's it's
""".split())

_SCORE_REGISTER = frozenset("""
score scores scored scoring scorecard rating ratings rated band bands banded
maturity level levels median peer peers average averages mean means benchmark
benchmarks cohort percentile point points pct percent percentage sits sit sat
stands stand stood ranks rank ranked places placed below above under over
against versus vs compared comparison compare relative gap gaps delta
difference lower higher lowest highest bottom top activating building competing
differentiating cell cells capability capabilities subcapability
subcapabilities category categories pillar pillars overall composite assessment
assessed workbook figure figures
""".split())

_INVENTORY_REGISTER = frozenset("""
evidence item items source sources document documents documented row rows
record records artefact artifact artefacts artifacts cite cites cited citation
citations citing reference references referenced speak speaks speaking address
addresses addressed support supports supported relate relates relating cover
covers covered available found exists exist bear bears bearing touch touches
touching mention mentions mentioned grounded grounding corpus pack bundle
registered register
""".split())

_ID_TOKEN = re.compile(r"^p\d+c\d+(\.[\w]+)*$", re.I)
_NUM_TOKEN = re.compile(r"^[\$£€]?\d[\d,.%/x-]*[a-z]{0,3}$", re.I)
_WORD = re.compile(r"[^a-z0-9$£€%./-]+")


def tokens(text: str) -> list:
    stripped = _WORD.sub(" ", text.lower())
    return [w.strip(".-/") for w in stripped.split() if w.strip(".-/")]


def residual_content(text: str) -> tuple:
    """→ (content words left, score-register hits, inventory hits).

    Removed: stopwords, numerals, catalogue ids, band words and the two
    registers. What survives is what the sentence asserts that is not the
    number it is quoting or the pile it is counting."""
    left, score_hits, inv_hits = [], 0, 0
    for w in tokens(text):
        if w in _SCORE_REGISTER:
            score_hits += 1
            continue
        if w in _INVENTORY_REGISTER:
            inv_hits += 1
            continue
        if w in _STOP or _NUM_TOKEN.match(w) or _ID_TOKEN.match(w):
            continue
        left.append(w)
    return left, score_hits, inv_hits


def shingles(text: str, n: int = SHINGLE_N) -> set:
    t = tokens(text)
    if len(t) < n:
        return set()
    return {tuple(t[i:i + n]) for i in range(len(t) - n + 1)}


# ── the contract-derived floor registry ───────────────────────────────
#
# The floors are READ FROM THE CONTRACT, never hardcoded: the `doc` text
# is where the per-field budget is stated ("trigger: 25-45 words",
# "story_md 90-150 words", "b2b_b2c — 25-55 words"), and it is the only
# place item-level keys are named at all. A field that gains a budget
# gains its enforcement in the same edit, and a field the contract gives
# no budget is not policed for length by this gate — silence in the
# contract is not a licence to invent a number here.
_BARE_BUDGET = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*words", re.I)
_KEYED_BUDGET = re.compile(
    r"\b([a-z_][a-z0-9_]{2,})\s*(?::|—|–|-)?\s*(\d+)\s*[-–]\s*(\d+)\s*words",
    re.I)
_ITEM_SCHEMA = re.compile(r"\{([^{}]*)\}")
_KEY_RE = re.compile(r"[a-z_][a-z0-9_]*$")


def _schema_keys(doc: str) -> set:
    """The item keys the field's own doc declares — the same `{a, b, c}`
    schema AG-03 reads. A budget is only attached to a key the schema
    names, so a stray "(25-45 words)" in a prose aside binds nothing."""
    out = set()
    for m in _ITEM_SCHEMA.finditer(doc):
        for part in m.group(1).split(","):
            k = part.strip().rstrip("[]")
            if _KEY_RE.fullmatch(k or ""):
                out.add(k)
    return out


@lru_cache(maxsize=8)
def prose_floors(page: str) -> dict:
    """section -> {"scalars": {field: floor}, "items": {field: {key: floor}}}"""
    out = {}
    for name, sec in sections(page).items():
        scalars, items = {}, {}
        for fname, spec in sec["fields"].items():
            doc = spec.get("doc") or ""
            if spec["type"] == "string":
                m = _BARE_BUDGET.search(doc)
                if m:
                    scalars[fname] = int(m.group(1))
            elif spec["type"] == "object" or (
                    spec["type"] == "list" and spec.get("item_type") == "object"):
                keys = _schema_keys(doc)
                per = {m.group(1): int(m.group(2))
                       for m in _KEYED_BUDGET.finditer(doc)
                       if m.group(1) in keys}
                if per:
                    items[fname] = per
        if scalars or items:
            out[name] = {"scalars": scalars, "items": items}
    return out


# ── honest absence ────────────────────────────────────────────────────
#
# The absence protocol's own vocabulary, shared with AG-03 and CG-10. A
# recorded absence is a FINDING — "the ladder ran across every mandatory
# source and found nothing" — and the sentence that states it is the same
# sentence every time because it is the same finding every time. Refusing
# it would push a producer toward inventing distinctions that do not
# exist, which is a worse defect than the one this gate closes.
_ABSENCE_STATES = frozenset((
    "UNWORKED", "WORKED_ABSENT", "NOT_RUN", "verified_absent",
    "verified_sparse", "cannot_estimate", "insufficient_cohort",
    "empty_state", "quarantined", "UNVERIFIED", "NO_EVIDENCE",
))
# The four keys AG-03 reads for the same purpose, plus `result` for a
# gate row's NOT_RUN. Deliberately NOT here: `recency_band` (an undated
# SOURCE is CG-10's business, and it is no licence for the sentence
# beside it to say nothing) and `ceiling` (a band word, not a state).
_STATE_KEYS = ("state", "status", "basis", "peer_basis", "result")
# Unambiguous "we established there is nothing / not enough" markers.
# Deliberately NOT here: `thin`, which marks evidence a cell is short of
# while still owing the argument the contract asked for — a producer who
# could buy the exemption by setting thin=true would have a switch, not
# a gate.
_ABSENCE_FLAGS = ("verified_absent", "verified_sparse", "cannot_estimate",
                  "insufficient_cohort")


def records_absence(obj) -> bool:
    """True when the object states that somebody looked and found
    nothing, with the search that establishes it."""
    if not isinstance(obj, dict):
        return False
    if obj.get("quarantined") and obj.get("quarantine_reason"):
        return True
    ladder = any(isinstance(obj.get(k), list) and obj[k]
                 for k in ("sources_searched", "queries_run"))
    for key in _STATE_KEYS:
        value = obj.get(key)
        if isinstance(value, str) and value.strip() in _ABSENCE_STATES:
            return ladder or bool(str(obj.get("not_run_reason") or "").strip())
    for flag in _ABSENCE_FLAGS:
        if obj.get(flag) is True:
            return True
    return False


def valid_empty_state(es) -> bool:
    return (isinstance(es, dict) and bool(es.get("reason"))
            and isinstance(es.get("sources_searched"), list)
            and len(es["sources_searched"]) > 0)


# ── vacuity of a value, for the section-level sweep ───────────────────
_META_FIELDS = frozenset(("produced_at", "producer_version", "e_ids",
                          "internal_only", "empty_state", "r_layer"))


def _is_vacuous_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return is_placeholder(value)
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return False              # a number is a fact; it came from a row
    if isinstance(value, list):
        return all(_is_vacuous_value(v) for v in value)
    if isinstance(value, dict):
        return all(_is_vacuous_value(v) for v in value.values())
    return False


def _reason(section, path, message):
    return {"gate_id": GATE, "section": section, "path": path,
            "message": message, "severity": "block"}


# ── the checks ────────────────────────────────────────────────────────

def _check_section_vacuity(page, name, sec, body) -> list:
    """The headline case: every present content field of a section is
    vacuous, and no empty_state says so."""
    if valid_empty_state(body.get("empty_state")):
        return []
    present = {f: body[f] for f in sec["fields"]
               if f not in _META_FIELDS and body.get(f) is not None}
    if not present:
        return []                 # CG-01/CG-02 own a section with nothing in it
    vacuous = [f for f, v in present.items() if _is_vacuous_value(v)]
    if len(vacuous) < len(present):
        return []
    return [_reason(
        name, name,
        f"{len(vacuous)} of {len(present)} present content fields are "
        f"vacuous ({', '.join(sorted(vacuous)[:6])}"
        f"{', …' if len(vacuous) > 6 else ''}) — every one is a placeholder, "
        "an empty list or an empty object, so this section renders under a "
        "real client's name and asserts nothing. A section with nothing to "
        "say says so: declare empty_state with its reason and the "
        "sources_searched ladder that established the absence, and the "
        "surface renders the absence as the finding it is. What must not "
        "ship is the shape of an assessment with none of its content")]


def _check_value(page, name, path, key, text, floor, exempt) -> list:
    """Placeholder, then floor, then residual — first one wins, so a stub
    produces one actionable verdict rather than three."""
    if is_placeholder(text):
        shown = (repr(text[:40]) if text.strip()
                 else ("an empty string" if text == "" else
                       f"{len(text)} characters of whitespace"))
        return [_reason(
            name, path,
            f"{shown} is a placeholder where the {page}.{name} "
            f"contract requires prose ({floor}-word floor). A placeholder is "
            "not an absence: the absence protocol is a stated reason plus the "
            "sources_searched ladder that established it, on the section's "
            "empty_state or the item's own record. Write the prose, or record "
            "the absence — 'N/A' does neither and renders as itself")]
    if exempt:
        return []
    words = len(text.split())
    if floor >= FLOOR_MIN_STATED:
        line = max(FLOOR_MIN_WORDS, math.ceil(floor * FLOOR_FACTOR))
        if words < line:
            return [_reason(
                name, path,
                f"{words} words against a contract floor of {floor} — the "
                f"refusal line is {line} ({floor} × {FLOOR_FACTOR:g}, so real "
                "prose that undershoots its budget still passes and a stub "
                f"does not). The {key!r} field's own doc states {floor} words "
                "as the minimum for a finished argument; this is the shape of "
                "one, not one. Either write it or record the absence with its "
                "ladder")]
    toks = tokens(text)
    if len(toks) >= RESIDUAL_MIN_TOKENS:
        left, score_hits, inv_hits = residual_content(text)
        if len(left) <= RESIDUAL_FLOOR:
            if inv_hits > score_hits:
                what = ("an inventory of the evidence rather than what the "
                        "evidence establishes — counting the sources is not "
                        "reading them")
            elif score_hits:
                what = ("a restatement of the score and nothing else — the "
                        "figure is already on the card; this field is for what "
                        "the figure MEANS for this institution")
            else:
                what = ("made of no content words at all once the register is "
                        "removed")
            return [_reason(
                name, path,
                f"{len(toks)} words leave {len(left)} content words once the "
                f"score register ({score_hits} words) and the evidence-"
                f"inventory register ({inv_hits} words) are removed — at or "
                f"below the floor of {RESIDUAL_FLOOR}. The sentence is {what}. "
                "State something about the institution that a reader could "
                "disagree with, and cite it")]
    return []


def _check_templates(name, groups) -> list:
    """Template prose repeated across ITEMS with a name substituted.

    8-gram shingles, overlap = |A ∩ B| / min(|A|, |B|). A pair above the
    line is an edge; a connected component of three or more is a
    template, and every member of it is named — the repair is to write
    the per-item argument the contract asked for, not to reword one row.

    Items only, deliberately. A SCALAR field is one value per section,
    and the one that repeats across sections — `narrative_thread` — is
    the PAGE's single thread, which the contract carries onto every
    section of the page on purpose (10 of overview's 12 sections carry
    the identical string in the promoted run, correctly). Comparing
    scalars across sections would refuse that by design, so the check
    never sees them: repetition is only a defect where the contract asked
    for one argument PER ITEM.
    """
    out = []
    for (field_key, floor), values in sorted(groups.items()):
        rows = [(p, shingles(t), t) for p, t in values
                if len(tokens(t)) >= TEMPLATE_MIN_TOKENS]
        rows = [(p, s, t) for p, s, t in rows if s]
        if len(rows) < TEMPLATE_MIN_GROUP:
            continue
        # Only pairs that share at least one 8-gram can clear the line, so
        # an inverted index enumerates the candidates instead of all
        # n(n-1)/2 of them — the heatmap's 706 cell syntheses are 249,374
        # pairs, of which a handful share a span at all.
        index = {}
        for i, (_p, sh, _t) in enumerate(rows):
            for s in sh:
                index.setdefault(s, []).append(i)
        candidates = set()
        for members in index.values():
            if len(members) < 2:
                continue
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    candidates.add((members[a], members[b]))
        adj = {i: set() for i in range(len(rows))}
        best = {}
        for i, j in candidates:
            si, sj = rows[i][1], rows[j][1]
            ov = len(si & sj) / min(len(si), len(sj))
            if ov >= TEMPLATE_OVERLAP:
                adj[i].add(j)
                adj[j].add(i)
                best[i] = max(best.get(i, 0.0), ov)
                best[j] = max(best.get(j, 0.0), ov)
        seen = set()
        for i in range(len(rows)):
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
            if len(comp) < TEMPLATE_MIN_GROUP:
                continue
            comp.sort()
            paths = [rows[k][0] for k in comp]
            for k in comp:
                out.append(_reason(
                    name, rows[k][0],
                    f"{len(comp)} items of {field_key!r} share "
                    f"{SHINGLE_N}-word spans at an overlap of up to "
                    f"{max(best[k] for k in comp):.2f} (this one "
                    f"{best[k]:.2f}, against a line of {TEMPLATE_OVERLAP:g}) — "
                    "one template with a name substituted, rendered as "
                    f"{len(comp)} separate arguments. The group is "
                    f"{', '.join(paths[:4])}"
                    f"{', …' if len(paths) > 4 else ''}. A per-item field the "
                    "contract gives its own word budget is a per-item "
                    "argument: say what is true of THIS one. If the finding "
                    "genuinely is the same for all of them, it belongs once, "
                    "in the section's own prose — and if the finding is that "
                    "the ladder ran and found nothing, record the absence on "
                    "each item (state + sources_searched) and this gate stands "
                    "down"))
    return out


def check_vacuity(page: str, payload: dict) -> list:
    """CG-15 over a whole page payload."""
    if not isinstance(payload, dict):
        return []
    try:
        contract = sections(page)
    except KeyError:
        return []
    floors = prose_floors(page)
    out = []

    for name, sec in contract.items():
        body = payload.get(name)
        if not isinstance(body, dict):
            continue

        vacuous_section = _check_section_vacuity(page, name, sec, body)
        if vacuous_section:
            # One verdict for the whole shell beats twelve for its fields.
            out.extend(vacuous_section)
            continue

        # `empty_state` answers the SECTION question — "is this a shell?"
        # — and it is answered above. It is not a blanket exemption for
        # the prose a POPULATED section also carries: overview.sentiment
        # in the promoted run has bars, themes and a gap analysis AND an
        # empty_state saying which review text could not be cited, and a
        # producer who could switch the gate off for a whole section with
        # one declared absence would have a switch. Below this line an
        # exemption is the ITEM's own record of what it searched.
        reg = floors.get(name) or {"scalars": {}, "items": {}}

        for fname, floor in reg["scalars"].items():
            value = body.get(fname)
            # An EMPTY string is not a missing field: CG-02 fires on null
            # only, so `""` type-checks, passes every other gate and
            # renders as a blank line under a real client's name.
            if not isinstance(value, str):
                continue
            out.extend(_check_value(page, name, f"{name}.{fname}", fname,
                                    value, floor, records_absence(body)))

        for fname, per_key in reg["items"].items():
            value = body.get(fname)
            items = (value if isinstance(value, list)
                     else [value] if isinstance(value, dict) else [])
            groups = {}
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                index = "" if isinstance(value, dict) else f"[{i}]"
                exempt = records_absence(item)
                for key, floor in per_key.items():
                    text = item.get(key)
                    if not isinstance(text, str):
                        continue
                    path = f"{name}.{fname}{index}.{key}"
                    out.extend(_check_value(page, name, path, key, text,
                                            floor, exempt))
                    if not exempt:
                        groups.setdefault((f"{fname}[*].{key}", floor),
                                          []).append((path, text))
            out.extend(_check_templates(name, groups))

    return out
