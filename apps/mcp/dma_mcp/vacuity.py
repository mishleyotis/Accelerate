"""CG-15 — a payload that says nothing (stage 2.4, pass 2).

PASS 2 (2026-08-08) — measured against four real heatmaps after the gate
refused two 700-cell payloads on the day it shipped. What the measurement
found, and what changed:

  · The template rule has NO measured false positives. Over the promoted
    Baxter run's 706 cell syntheses — genuinely per-cell arguments, one
    taxonomy, one institution, one contract-mandated shape — the highest
    8-gram overlap between any two is 0.179 against a line of 0.40, and
    the gate refuses none of them. Over Kitsap's 37, 0.070. A 700-cell
    per-cell synthesis is demonstrably writable and demonstrably passes.
  · The two refused payloads are refused correctly. Fisher's 708 differ
    only in the capability name and the category record they name: the
    claim ("read from the category record, so the reading is inferred")
    is one claim 708 times. Frost's 283 are one of two sentences. Both
    populations still share 43-100% of their CONTENT vocabulary once the
    contract's mandated scaffolding is removed — this is not two honest
    arguments that happen to rhyme.
  · What WAS broken is the escape hatch. The verdict ended "record the
    absence on each item (state + sources_searched) and this gate stands
    down". Of the 19 item shapes that carry a per-item prose budget,
    exactly ONE — heatmap.alerts.alerts — declares those keys. On the
    other 18, including every shape in both refusals, the route the gate
    named did not exist. A producer who refused to invent a field (the
    standing clause forbids it) had nowhere to go.
  · And the hatch was buyable with a field nobody stores. CG-04 sweeps
    SECTION keys only, so an item key the contract never declared passed
    validation, bought the exemption here, bought it from AG-03 too, and
    was dropped at promote for want of a column. Measured: 394 of Frost's
    697 cells were exempted on `state` + `sources_searched`, which
    heatmap.cell_evidence.cells does not declare and heatmap_cell_evidence
    has no column for. Strip the invented keys and AG-03 refuses all 394.

So: the measure now scores the CLAIM and not the scaffolding, the
exemption is bound to the item's own contract shape, and the verdict names
only a route that shape actually has. The rule was not loosened — the
refusals above are unchanged in number — it was made honest.

Every other gate in this connector checks STRUCTURE, IDENTITY or
ARITHMETIC. None of them reads the prose for content. A six-page payload
with all 34 sections present, every required field populated with "N/A"
or `[]`, every id resolving and every figure agreeing with the workbook
produces zero blocking reasons and is eligible for `promote_run`. The
pipeline's own defences cannot tell a real assessment from an empty
shell, which for clients 2..50 is the failure mode that matters most.

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
     substituted, measured as 8-gram overlap AND content-word overlap —
     both, so prose that shares only the frame the contract mandates is
     not mistaken for prose that shares the argument;
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

    ON THE KEYS THE ITEM'S OWN CONTRACT DECLARES, and no others. A key
    the item shape does not name is a key CG-04 never sweeps, the writer
    has no `item:` binding for and promote drops — so honouring it here
    would trade a real refusal for a field the client never sees. The
    exemption is a contract route or it is nothing.

The one thing no absence excuses is a bare placeholder. "N/A" is not the
absence protocol — the protocol is a reason and a sources_searched
ladder, and it is available on every section that needs it.

WHERE THE ROUTE DOES NOT EXIST, THE VERDICT SAYS SO. `_absence_route`
reads the item shape and names what that shape actually offers: the
ladder keys where they are declared; otherwise, for a shape that cites
evidence, the fact that a per-item argument needs per-item evidence and
an item nothing reached belongs out of the array, not in it with a
sentence shared by four hundred siblings. Naming a key the shape does not
have is how this gate became a trap the first time.
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

# CLAIM: the same overlap, over the CONTENT WORDS only — what is left of
# the sentence once the stopwords, the numerals, the catalogue ids, the
# score register and the evidence-inventory register are removed. Those
# registers ARE the scaffolding the contract mandates: H2 requires every
# synthesis to say "where the score sits against the peer median" and to
# "cite inline", so two honest syntheses are REQUIRED to share that
# phrasing. Scoring it would refuse prose for obeying its own contract.
#
# Measured over the same four heatmaps, on pairs that already clear the
# 8-gram line, as |A ∩ B| / min(|A|, |B|) on the content-word sets:
#
#   promoted Baxter, 706 honest cells   no pair clears the 8-gram line at
#                                       all (max 0.179); the highest
#                                       CONTENT overlap anywhere in the
#                                       corpus is 0.793 — two honest
#                                       arguments about one institution
#                                       share vocabulary freely, and it is
#                                       the phrasing that separates them
#   Kitsap, 37 honest cells             max 0.115
#   Fisher, 708 refused                 min 0.433, median 0.591
#   Frost, 283 refused                  min 0.615, median 0.800
#   Baxter's 17 ceilings, refused       min 0.630, median 0.850
#
# 0.40 therefore keeps every measured refusal refused (the tightest is
# Fisher at 0.433) while making the rule a CONJUNCTION: an edge needs both
# the phrasing and the substance. A conjunction can only ever remove
# refusals, never add one, so the honest population is strictly safer than
# it was — and prose that shares the contract's frame while arguing
# different things now has somewhere to land.
CLAIM_OVERLAP = 0.40
# Below this many distinct content words the overlap is noise, and a text
# with almost no content words is the RESIDUAL check's business anyway —
# so the claim term abstains and the 8-gram term decides alone. Sparing
# them instead would hand a producer 700 near-contentless sentences.
CLAIM_MIN_WORDS = 6

# CLAIM ALONE (pass 3, 2026-08-09). The conjunction above closed the
# INSTANCE and not the class: a hostile 706-cell round robin built against
# this connector's own modules passed all six pages with zero blocking
# reasons, because its phrasing overlap (0.306) sits under the 0.40 8-gram
# line and the claim term only ever ran on pairs that share an 8-gram.
# Phrasing is the cheapest thing a generator can vary — eight opening
# frames and four connectives put every pair under the line while the
# CLAIM overlap of the same field ran 0.769. So the claim term now also
# decides ALONE, over all measurable pairs, at a higher line:
#
#   Odlum's 517 round robin    claim 0.938   refused (475 named)
#   the hostile round robin    claim 0.769   refused — was PASSING
#   Baxter, hand-written       max 0.793 on a pair; components of 3+ are
#                              what refuse, measured ≤3% of cells
#
# 0.50 splits the populations: a generator cannot push claim overlap down
# without changing what the sentences SAY, which is the work the gate
# exists to demand. The conjunction route above is kept as well — it can
# only add refusals a phrasing-heavy template earns — and an edge from
# either route joins the same components.
CLAIM_ALONE = 0.50
# Candidate pruning for the all-pairs pass: two sets of ≥ CLAIM_MIN_WORDS
# words need ⌈0.5·min⌉ ≥ 3 shared words to clear 0.50, so only pairs
# sharing at least this many content words are measured at all.
CLAIM_MIN_SHARED = 3


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


def claim_words(text: str) -> set:
    """The distinct content words a sentence asserts with.

    The same residual the vacuity check counts, kept as a SET rather than
    a sequence: word order is phrasing, and phrasing is what the 8-gram
    term already measures. What this term asks is narrower and harder to
    fake — do these two sentences talk about the same things?"""
    left, _score_hits, _inv_hits = residual_content(text)
    return set(left)


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


@lru_cache(maxsize=256)
def item_keys(page: str, section: str, field: str) -> frozenset:
    """The keys THIS item shape declares, read from the contract.

    Read with `validation2._PER_ITEM_RE` — the same expression AG-03 and
    the item-level field census use — so a shape those two can see is a
    shape this one can see, and a shape none of them can parse fails all
    three together instead of one of them silently opting out. Two of the
    nineteen budgeted shapes state their schema inline rather than behind
    a "Per item:" lead-in (`overview.sentiment.gap_analysis`,
    `platform.platform_story.platforms`); for those the brace-schema
    reader above is the fallback, which is still the CONTRACT talking.
    """
    from .validation2 import _PER_ITEM_RE     # local: avoids an import cycle

    spec = sections(page)[section]["fields"].get(field)
    if spec is None:
        return frozenset()
    doc = spec.get("doc") or ""
    m = _PER_ITEM_RE.search(doc)
    if m:
        return frozenset(k for k in (p.strip().rstrip("[]")
                                     for p in m.group(1).split(","))
                         if _KEY_RE.fullmatch(k or ""))
    return frozenset(_schema_keys(doc))


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
# …and it stays out of that list. `thin` becomes a finding only in the PAIR
# the TRD states at `Representing absence` for cell grain — thin true, the
# ladder, AND the closure condition saying what would settle it. Three keys is
# not a switch: a producer who can write what would close the question has
# done the work the gate is asking for. (flag, required companion); the ladder
# is required on top of both, in records_absence.
_PAIRED_ABSENCE = (("thin", "closure_condition"),)
_LADDER_KEYS = ("sources_searched", "queries_run")
# The citation keys AG-03 reads, kept in step with it deliberately: a shape
# that owes a citation per item is a shape whose per-item prose has per-item
# evidence behind it, and that is what decides which route the verdict names.
_EV_KEYS = frozenset(("e_ids", "supporting_e_ids", "evidence_ids",
                      "new_evidence_ids", "source_e_id", "e_id"))


# ── what a ladder rung has to BE (pass 3, 2026-08-09) ─────────────────
#
# REF-0012 bound the exemption to declared keys, so an INVENTED key buys
# nothing. Twelve hours later a promoted run bought it with DECLARED keys
# filled with a constant: 517 of 517 uncited cells carried the two-rung
# ladder ["Run ladder in section r_layer", "Corpus search: <the cell's own
# catalogue topic> - nil"] — rung 1 a pointer to another section, naming
# no host, no query and no result, on every cell identically; rung 2 the
# cell's own name substituted into one sentence. 98 alerts shared ONE
# ladder string. The predicate was "is the field present and well-shaped",
# and a template satisfies that for free (MEM-0038).
#
# So the ladder itself now has to look like a search somebody ran:
#
#   1. No rung may be a POINTER — an instruction to a reader ("run the
#      ladder", "see section X", "refer to r_layer") is not a search.
#   2. At least one rung must NAME what was attempted: a host, a URL, a
#      quoted query, or an explicit query/site form. "Corpus search:
#      roadmap visualization - nil" names nothing a reader could re-run;
#      'corpus search: "roadmap visualization" — nil' names the query.
#   3. `thin` must agree with the evidence beside it: a cell asserting
#      thin while citing three or more items is not thin by the
#      contract's own line, so the trio cannot exempt it.
#
# And at the GROUP grain, in check_vacuity: a byte-identical full ladder
# across three or more exempted items of one field is one search pasted N
# times — one search can establish one absence, not N distinct ones. Each
# item's ladder must record the rung that asked about THAT item.
_POINTER_RUNG = re.compile(
    r"\b(?:run|rerun|see|refer(?:\s+to)?|per|consult)\b[^.]{0,40}"
    r"\b(?:ladder|section|r_layer|above|elsewhere)\b", re.I)
# Case-sensitive TLD with a hard boundary: the case-insensitive version read
# glued prose as hosts — 'tooling.Nil' in "…tooling.Nil results returned",
# 'roadmap.The' in "…the roadmap.The board" — so any sentence missing a space
# after its full stop was a "search somebody could re-run" (found by the
# pass-4 adversarial run, measured 600/600 exempted).
_HOST_RUNG = re.compile(
    r"\b[a-z0-9][a-z0-9-]{1,63}\.(?:[a-z]{2,12})(?:\.[a-z]{2,12})?"
    r"(?=[\s/,;:)\"'”]|$)")
_QUOTED_RUNG = re.compile(r"[\"“‘']([^\"”’']{3,120})[\"”’']")
_QUERY_RUNG = re.compile(r"\b(?:site|query|queried|searched\s+for)\s*[:=]", re.I)


def _rung_content(text: str) -> tuple:
    """A rung's content words, with everything an item varies for free
    masked out: catalogue ids, numerals, stopwords and the two registers.

    Both halves of the pass-4 hardening stand on this. SUBSTANCE: a rung is
    a search only if something a reader could re-run SURVIVES the masking —
    a quoted subcap id ('\"P2C2.5\"') and a counter ('reviewed #7') survive
    as nothing, and both bought the exemption for 600 of 600 hostile cells
    when the test was a regex hit or a word count. DISTINCTNESS: the group
    rule compares rungs by this tuple, so 'Searched ncua.gov for capability
    7 - nil' with the number rotated collapses to ONE masked form across
    517 cells — the byte-identity rule it replaces was defeated by exactly
    that substitution."""
    return tuple(claim_words(text))


def _rungs(obj, declared) -> list:
    """(key, text) pairs — the key travels because it carries meaning: a
    string under `queries_run` IS a query by the field's own semantics."""
    def named(key):
        return declared is None or key in declared
    out = []
    for k in _LADDER_KEYS:
        if named(k) and isinstance(obj.get(k), list):
            out.extend((k, r) for r in obj[k]
                       if isinstance(r, str) and r.strip())
    return out


def _ladder_claimed(obj, declared) -> bool:
    """A ladder key is PRESENT with any truthy value at all.

    Distinct from _rungs on purpose, and the distance between the two was a
    bypass: records_absence used raw list truthiness, so `[\"\"]`, `[0]` and
    `[None]` read as \"a ladder is present\", while ladder_flaw's _rungs
    filtered them to nothing and answered \"no ladder → nothing to flaw\".
    517 byte-identical cells rode through the gap with zero reasons. One
    question, one answer: anything truthy under a ladder key is a CLAIMED
    ladder, and a claimed ladder that yields no valid rung is a flawed one,
    never an absent one."""
    def named(key):
        return declared is None or key in declared
    return any(named(k) and obj.get(k) for k in _LADDER_KEYS)


def _citation_count(obj, declared) -> int:
    def named(key):
        return declared is None or key in declared
    n = 0
    for k in _EV_KEYS:
        if not named(k):
            continue
        v = obj.get(k)
        if isinstance(v, list):
            n += len(v)
        elif isinstance(v, str) and v.strip():
            n += 1
    return n


def _rung_is_substantive(key: str, text: str) -> bool:
    """Something a reader could re-run survives in this rung.

    Every branch requires CONTENT to survive the masking, because every
    regex-only version of this predicate was bought with content-free
    tokens: a quoted subcap id satisfied the quote pattern, a constant
    host satisfied the host pattern on all 600 cells of a hostile payload,
    and 'did entity adopt capability number 13' satisfied a bare word
    count. The masking is `claim_words` — the same residual the rest of
    this gate scores syntheses with."""
    if _HOST_RUNG.search(text):
        return True                       # a host IS re-runnable as written
    m = _QUOTED_RUNG.search(text)
    if m and len(claim_words(m.group(1))) >= 2:
        return True                       # a quoted QUERY, not a quoted id
    if _QUERY_RUNG.search(text) and len(claim_words(text)) >= 2:
        return True
    # A string under `queries_run` is a query by the field's own semantics —
    # "INT-020: Does BCU hold proprietary technology patents?" is re-runnable
    # as written. Four CONTENT words is the line: ids, numerals, stopwords
    # and the registers are masked first, so a counter buys nothing.
    return key == "queries_run" and len(claim_words(text)) >= 4


def ladder_flaw(obj, declared=None) -> str | None:
    """Why this item's ladder cannot buy an absence exemption — or None.

    Shared with AG-03 (validation2._asserts_nothing) deliberately: the two
    gates honour the same trio, and a predicate held in two places drifts.
    Returns prose that names the flaw and the repair, because the last
    time this gate refused without naming a route, five producers stalled
    on the same day.
    """
    rungs = _rungs(obj, declared)
    if not rungs:
        if _ladder_claimed(obj, declared):
            return ("a ladder key is present and holds no usable rung — "
                    "empty strings, whitespace or non-text entries. A "
                    "ladder full of blanks is a flawed ladder, not an "
                    "absent one: record the searches, or drop the key")
        return None                      # no ladder → no ladder-based route
    pointers = [(k, r) for k, r in rungs if _POINTER_RUNG.search(r)]
    if pointers:
        k, r = pointers[0]
        return (f"rung {rungs.index(pointers[0]) + 1} "
                f"({r[:60]!r}) is a pointer to another section, "
                "not a search — a reader following the ladder must find the "
                "searches themselves, on the item, not an instruction to "
                "look elsewhere")

    if not any(_rung_is_substantive(k, r) for k, r in rungs):
        return (f"none of the {len(rungs)} rungs names a host, a URL, a "
                "quoted query or a re-runnable query string — a ladder "
                "establishes an absence only if it records searches "
                "somebody could re-run, and catalogue ids, counters and "
                "bare numbers do not survive that test. Name the source "
                "attempted (its domain or document) or record the query "
                "itself, in real words, per rung")
    if (obj.get("thin") is True
            and _citation_count(obj, declared) >= 3):
        return (f"thin is asserted beside {_citation_count(obj, declared)} "
                "citations — at or above the contract's own three-item "
                "line, the cell is not thin, and the absence route is not "
                "available to it")
    return None


def records_absence(obj, declared=None) -> bool:
    """True when the object states that somebody looked and found
    nothing, with the search that establishes it.

    `declared` is the key set the object's own contract shape names. A key
    outside it buys nothing, however well-formed it looks. That is not
    pedantry about spelling: CG-04 sweeps SECTION keys only, so an
    undeclared item key passes validation, and the writer has no `item:`
    binding for it, so promote drops it. An exemption bought with such a
    key trades a real refusal for a field the client never sees — which is
    what happened, 394 times, on one run measured today. Pass None only
    where the caller genuinely has no shape to bind to."""
    if not isinstance(obj, dict):
        return False

    def named(key):
        return declared is None or key in declared

    if (named("quarantined") and obj.get("quarantined")
            and named("quarantine_reason") and obj.get("quarantine_reason")):
        return True
    # A ladder is a ladder only if it survives the rung predicate: present
    # and well-shaped stopped being enough the morning 517 cells bought
    # this exemption with a pointer and a template (MEM-0038). Presence is
    # judged on the FILTERED rungs, never on raw list truthiness — `[""]`
    # was truthy here and rungless in ladder_flaw, and the distance between
    # the two answers exempted 517 hostile cells with zero reasons.
    ladder = (bool(_rungs(obj, declared))
              and ladder_flaw(obj, declared) is None)
    # The paired routes: a flag that is a switch on its own becomes a finding
    # only beside its companion AND the ladder. `thin` is the cell-grain case
    # the TRD states at `Representing absence` (thin + sources_searched +
    # closure_condition) and the one this file's comment above deliberately
    # keeps out of _ABSENCE_FLAGS: thin alone marks a cell short of evidence
    # that still owes its argument.
    for flag, companion in _PAIRED_ABSENCE:
        if (named(flag) and obj.get(flag) is True and ladder
                and named(companion)
                and str(obj.get(companion) or "").strip()):
            return True
    for key in _STATE_KEYS:
        if not named(key):
            continue
        value = obj.get(key)
        if isinstance(value, str) and value.strip() in _ABSENCE_STATES:
            return ladder or bool(named("not_run_reason")
                                  and str(obj.get("not_run_reason") or "").strip())
    for flag in _ABSENCE_FLAGS:
        if named(flag) and obj.get(flag) is True:
            return True
    return False


def _absence_route(declared) -> str:
    """The tail of a template verdict: what THIS item shape offers.

    The pass-1 verdict ended with one sentence for all nineteen shapes —
    "record the absence on each item (state + sources_searched)". Exactly
    one shape declares those keys. On the other eighteen the gate was
    naming a door that is not in the wall, and a producer who would not
    invent a field (the standing clause forbids it) was stuck between a
    refusal and a rule. Never name a key the shape does not have."""
    declared = declared or frozenset()
    ladder = [k for k in _LADDER_KEYS if k in declared]
    states = [k for k in _STATE_KEYS if k in declared]
    flags = [k for k in _ABSENCE_FLAGS if k in declared]
    paired = [(f, c) for f, c in _PAIRED_ABSENCE
              if f in declared and c in declared]
    if paired and ladder:
        flag, companion = paired[0]
        return (f" And if the finding is that the ladder ran and found "
                f"nothing, this item shape declares {flag} + {ladder[0]} + "
                f"{companion} — all three, because {flag} on its own marks a "
                f"cell short of evidence that still owes its argument. The "
                f"ladder must record searches a reader could re-run: at "
                f"least one rung naming a host, a URL or a quoted query, no "
                f"rung pointing at another section, and each item carrying "
                f"the rung that asked about IT — a template rung repeated "
                f"across items records one search, not many. Name what was "
                f"searched and what would settle it, on the cell itself, "
                f"and this gate stands down.")
    if states and ladder:
        return (f" And if the finding is that the ladder ran and found "
                f"nothing, this item shape declares {states[0]} + "
                f"{ladder[0]} — record the absence on each item and this "
                f"gate stands down.")
    if flags and ladder:
        return (f" And if the finding is that the ladder ran and found "
                f"nothing, this item shape declares {flags[0]} + "
                f"{ladder[0]} — record the absence on each item and this "
                f"gate stands down.")
    cites = sorted(declared & _EV_KEYS)
    if cites:
        return (" This item shape declares no absence keys, so there is no "
                "per-item way to record 'the ladder ran and found nothing' "
                f"here. What it does declare is {cites[0]}: a per-item "
                "argument is owed per-item evidence. Where an item has none, "
                "the two honest routes are to leave it out of the array — its "
                "absence is then carried by the section's own reach counters "
                "and empty_state, which is where an absence at this scale is "
                "one finding rather than N copies of one — or, where the "
                "array's membership is fixed, to state once in the section's "
                "prose what the ladder established for all of them. Do not "
                "invent a key to declare the absence with: an item key the "
                "contract does not name is one CG-04 never sweeps and promote "
                "has no column for, so it would buy this exemption and then "
                "be dropped before the client ever saw it.")
    return (" This item shape declares no absence keys and no citation key, "
            "so a finding shared by every item belongs once — in the "
            "section's own prose, or in its empty_state with the "
            "sources_searched ladder that established it. Do not invent a "
            "per-item key to declare it with: a key the contract does not "
            "name is dropped at promote, so it would buy this exemption and "
            "render as nothing.")


def _absence_pass(name, fname, items, value_is_dict, declared):
    """Per-item exemptions, with the verdicts that void a claimed ladder.

    Two things the per-item predicate cannot see happen here. First, an
    item whose ladder is FLAWED gets a verdict naming the flaw — falling
    silently through to the template check would refuse the prose without
    ever telling the producer the ladder was the problem. Second, the
    GROUP rule: a byte-identical full ladder across three or more exempted
    items is one search pasted N times, and one search establishes one
    absence, not N distinct ones — each item's ladder must record the rung
    that asked about THAT item. Measured before this existed: 98 alerts on
    one promoted run shared one ladder string, and 517 cells shared their
    first rung verbatim.
    """
    reasons, exempt, laddered = [], [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            exempt.append(False)
            continue
        path = f"{name}.{fname}" + ("" if value_is_dict else f"[{i}]")
        flaw = (ladder_flaw(item, declared)
                if (_rungs(item, declared)
                    or _ladder_claimed(item, declared)) else None)
        if flaw and (_citation_count(item, declared) == 0
                     or item.get("thin") is True):
            reasons.append(_reason(
                name, path,
                f"the recorded absence ladder cannot exempt this item: "
                f"{flaw}. The exemption is the RECORD of a search, and a "
                "record a reader could not re-run records nothing"))
        e = records_absence(item, declared)
        exempt.append(e)
        if e and not flaw:
            rungs = _rungs(item, declared)
            if rungs:
                laddered.append((i, path, rungs))

    # The GROUP rule, over masked rung content rather than bytes. Its
    # byte-identity predecessor was defeated by exactly the substitution it
    # was built to catch: 'Searched ncua.gov for capability 7 - nil' with
    # the number rotated made 517 "distinct" ladders that are one search.
    # Under masking (_rung_content) they collapse to one form. The rule:
    # among three or more ladder-exempted items of one field, each item
    # must carry at least one SUBSTANTIVE rung whose masked content is its
    # own — shared corpus rungs ("package evidence index") stay legitimate,
    # they just do not count as the rung that asked about THIS item.
    if len(laddered) >= TEMPLATE_MIN_GROUP:
        form_counts: dict = {}
        for _i, _p, rungs in laddered:
            for k, t in rungs:
                if _rung_is_substantive(k, t):
                    form_counts[_rung_content(t)] = \
                        form_counts.get(_rung_content(t), 0) + 1
        for i, path, rungs in laddered:
            distinctive = any(
                _rung_is_substantive(k, t)
                and form_counts.get(_rung_content(t), 0) < TEMPLATE_MIN_GROUP
                for k, t in rungs)
            if distinctive:
                continue
            exempt[i] = False
            shared = max((form_counts.get(_rung_content(t), 0)
                          for k, t in rungs if _rung_is_substantive(k, t)),
                         default=0)
            reasons.append(_reason(
                name, path,
                f"{len(laddered)} items of {fname!r} claim a recorded "
                f"absence and this one carries no rung of its own: every "
                f"substantive rung it names is the same search, shared "
                f"with up to {shared} sibling items once numbers, ids and "
                "counters are masked out. One search establishes one "
                "absence, not many. Record, per item, the rung that asked "
                "about THIS item — the query or the source checked for "
                "this capability — or state the shared finding once, in "
                "the section's own prose"))
    return exempt, reasons


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
                "one, not one. Write it, or record the absence on the route "
                "this item shape offers")]
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


def _overlap(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _check_templates(name, groups, declared=None) -> list:
    """Template prose repeated across ITEMS with a name substituted.

    TWO TERMS, BOTH REQUIRED. An edge needs the phrasing — 8-gram
    shingles, overlap = |A ∩ B| / min(|A|, |B|), at or above 0.40 — AND
    the substance: the same overlap over the CONTENT WORDS, the residual
    after the stopwords, numerals, catalogue ids, score register and
    evidence-inventory register are stripped out.

    The second term exists because the first one alone scores the
    contract's own scaffolding. H2 requires every synthesis to say "where
    the score sits against the peer median" and to cite inline; C1
    requires every event body to date itself. Two honest arguments obeying
    the same contract are SUPPOSED to share those spans, and a rule that
    reads shared scaffolding as a shared claim refuses prose for being
    well-formed. Stripping the registers leaves what the sentence asserts,
    and asking for agreement THERE is asking the question the gate is
    actually for: not "are these worded alike" but "do these say the same
    thing about different capabilities".

    Measured, the two terms are near-independent: the promoted Baxter run's
    highest CONTENT overlap between two honest cell syntheses is 0.793
    (one institution, one domain — of course they share vocabulary) while
    its highest PHRASING overlap is 0.179. The refused populations are high
    on both. A conjunction can only remove edges, never add one, so this
    strictly narrows what CG-15 refuses, and it removed none of the 1,053
    refusals measured today.

    A connected component of three or more is a template, and every member
    of it is named — the repair is to write the per-item argument the
    contract asked for, not to reword one row.

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
    route = _absence_route(declared)
    for (field_key, floor), values in sorted(groups.items()):
        rows = [(p, shingles(t), claim_words(t))
                for p, t in values if len(tokens(t)) >= TEMPLATE_MIN_TOKENS]
        if len(rows) < TEMPLATE_MIN_GROUP:
            continue

        # Route 1 — the phrasing conjunction. Only pairs that share at
        # least one 8-gram can clear its line, so an inverted index
        # enumerates the candidates instead of all n(n-1)/2 of them.
        index = {}
        for i, (_p, sh, _c) in enumerate(rows):
            for s in sh:
                index.setdefault(s, []).append(i)
        candidates = set()
        for members in index.values():
            if len(members) < 2:
                continue
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    candidates.add((members[a], members[b]))

        # Route 2 — the claim term alone, over ALL measurable pairs. The
        # candidate set is pruned by content-word postings: clearing 0.50
        # on two sets of ≥6 words requires ≥3 shared words, so a pair
        # sharing fewer is never measured. This route exists because the
        # conjunction's candidate filter IS the 8-gram index above, and a
        # generator that varies its phrasing never enters it — the hostile
        # round robin passed at phrasing 0.306 / claim 0.769.
        postings = {}
        for i, (_p, _sh, cw) in enumerate(rows):
            if len(cw) < CLAIM_MIN_WORDS:
                continue
            for w in cw:
                postings.setdefault(w, []).append(i)
        shared = {}
        for members in postings.values():
            if len(members) < 2:
                continue
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    pair = (members[a], members[b])
                    shared[pair] = shared.get(pair, 0) + 1
        claim_candidates = {p for p, n in shared.items()
                            if n >= CLAIM_MIN_SHARED}

        adj = {i: set() for i in range(len(rows))}
        best, claim_best = {}, {}

        def _edge(i, j, ov, claim):
            adj[i].add(j)
            adj[j].add(i)
            best[i] = max(best.get(i, 0.0), ov)
            best[j] = max(best.get(j, 0.0), ov)
            claim_best[i] = max(claim_best.get(i, 0.0), claim)
            claim_best[j] = max(claim_best.get(j, 0.0), claim)

        for i, j in candidates | claim_candidates:
            ov = _overlap(rows[i][1], rows[j][1])
            ci, cj = rows[i][2], rows[j][2]
            claim = _overlap(ci, cj)
            measurable = min(len(ci), len(cj)) >= CLAIM_MIN_WORDS
            if measurable and claim >= CLAIM_ALONE:
                _edge(i, j, ov, claim)          # the claim decides alone
            elif ov >= TEMPLATE_OVERLAP and (
                    not measurable or claim >= CLAIM_OVERLAP):
                _edge(i, j, ov, claim)          # the phrasing conjunction

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
                phr = best.get(k, 0.0)
                phrase_note = (
                    f"share {SHINGLE_N}-word spans at up to {phr:.2f} "
                    f"(line {TEMPLATE_OVERLAP:g})" if phr >= TEMPLATE_OVERLAP
                    else f"share almost no phrasing (max {phr:.2f}) — the "
                         "wording was varied; the argument was not")
                out.append(_reason(
                    name, rows[k][0],
                    f"{len(comp)} items of {field_key!r} make the same "
                    f"claim: {claim_best.get(k, 0.0):.2f} of their content "
                    f"words agree once the score and evidence registers are "
                    f"stripped (refusal at {CLAIM_ALONE:g} alone, or "
                    f"{CLAIM_OVERLAP:g} with matching phrasing), and they "
                    f"{phrase_note}. One argument rendered as "
                    f"{len(comp)} separate arguments. The group is "
                    f"{', '.join(paths[:4])}"
                    f"{', …' if len(paths) > 4 else ''}. A per-item field "
                    "the contract gives its own word budget is a per-item "
                    "argument: say what is true of THIS one. If the finding "
                    "genuinely is the same for all of them, it belongs once, "
                    "in the section's own prose." + route))
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
        # The SECTION's own contract field set. Four sections declare a
        # section-level absence field — leadership.verified_absent,
        # financial_series.verified_sparse/quarantine_reason,
        # timeline.verified_sparse, issue_register.verified_absent, which
        # is exactly the TRD's "Representing absence" table — and those
        # keep working. A key outside the set buys nothing.
        sec_keys = frozenset(sec["fields"])

        for fname, floor in reg["scalars"].items():
            value = body.get(fname)
            # An EMPTY string is not a missing field: CG-02 fires on null
            # only, so `""` type-checks, passes every other gate and
            # renders as a blank line under a real client's name.
            if not isinstance(value, str):
                continue
            out.extend(_check_value(page, name, f"{name}.{fname}", fname,
                                    value, floor,
                                    records_absence(body, sec_keys)))

        for fname, per_key in reg["items"].items():
            value = body.get(fname)
            items = (value if isinstance(value, list)
                     else [value] if isinstance(value, dict) else [])
            declared = item_keys(page, name, fname)
            exempts, ladder_reasons = _absence_pass(
                name, fname, items, isinstance(value, dict), declared)
            out.extend(ladder_reasons)
            groups = {}
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                index = "" if isinstance(value, dict) else f"[{i}]"
                exempt = exempts[i]
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
            out.extend(_check_templates(name, groups, declared))

    return out
