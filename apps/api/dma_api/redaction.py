"""Audience redaction — one enforcement point, server-side, default-deny.

The frontend never decides what is internal, because it never receives the
internal fields (TRD §11). Four mechanisms, in order of authority:

1. `internal_only` — JSON paths the producer marked, deleted for the
   customer audience. This is the primary mechanism and the reason the
   marking is a payload field: an unmarked rung is invisible here, so the
   contract, the walker and the tests all push the marking upstream.
2. ALWAYS_STRIP — paths stripped for EVERY audience, whatever the payload
   said. Cross-entity pattern entity ids are audit-only and never leave
   the audit trail (charter invariant 5), so they do not depend on a
   producer remembering to mark them.
3. CUSTOMER_ALWAYS — paths and keys stripped for the customer audience
   whatever the payload said. Producer marking is necessary and has been
   measured insufficient; these are the shapes that are internal by their
   own definition, so they are not left to be remembered.
4. CUSTOMER_WITHHELD — sections withheld whole rather than redacted: a
   page that renders half its cards invites the question of what the other
   half said (TRD §11).

## Why this module was rewritten

Measured on both promoted clients, 2026-08-09: **6 of 6 declared redactions
were announced and not performed.** The customer body was LARGER than the
internal one on both platform pages (132,711 against 132,462 for the reference client;
33,165 against 33,126 for the second client) — the receipt naming the removals was the
only thing the redaction added. Three defects, compounding:

* `strip_paths` appended to `applied` unconditionally, so the receipt
  reported the INPUT rather than the deletions. A path that matched
  nothing was indistinguishable from one that matched and was removed.
* The walker was handed the SECTION's data as its root, while producers
  write section-qualified paths (`starters.starters`,
  `platform_story.platforms[0].zennify_pathway`). The first segment names
  the section, so every one of them walked into a key that does not exist.
* `[*]` was understood and `[0]` was not, so an index-qualified path
  silently did nothing even after the prefix was resolved.

Any one of those alone produces a receipt that lies. The rule this module
now holds to: **a path is reported as stripped only if this walker deleted
something, and a path that matched nothing is reported by name.** An
unmatched marking is a producer defect that must be visible, not a silent
pass.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import os
import re

# (page, section) withheld entirely from the customer audience.
CUSTOMER_WITHHELD = frozenset((
    ("overview", "ceilings"),            # O1b — TRD §11 rung table
    ("overview", "sentiment"),            # O9  — TRD §11 rung table
    ("overview", "thought_leadership"),   # O12 — TRD §11 rung table
    # O10. The evidence CENSUS, not the evidence: tier histogram, item and
    # fact counts, the self-sourced share and the gate line. It is how well
    # WE evidenced the assessment, which is our method showing through, and
    # it belongs beside the ceilings it explains rather than in front of the
    # client. It sat outside this set until 2026-08-18 and was reaching the
    # customer body in full; nothing rendered it only because the web
    # adapter happens to drop those keys (live-adapter.jsx adaptCoverage),
    # so a wire leak was standing behind a UI accident. Both promoted
    # clients were affected, not one.
    ("overview", "evidence_coverage"),    # O10 — the census, not the scores
    ("heatmap", "alerts"),                # D7 Health, operational
    ("heatmap", "evidence_age"),          # D7 Health, operational
    ("heatmap", "cohort_patterns"),       # D7 Health + cross-entity
    # P-starters: conversation openers WRITTEN FOR THE SELLER ("ask them
    # which system…", "follow-up question"). MEM-0081 / T-2: key-stripping
    # it left a customer card list whose every remaining field was a line
    # of our talk track, so it is withheld whole — a section that is our
    # preparation for the room has no redacted form.
    ("platform", "starters"),
))

# Whole pages withheld from the customer audience: a locked state, not a
# partial page. Requested with audience=customer -> 403 audience_forbidden.
CUSTOMER_WITHHELD_PAGES = frozenset(("context",))

# Pages an AE has no route to (TRD §"403 audience_forbidden").
#
# USER ADJUDICATION 2026-08-07: the context dashboard IS available to the AE
# role — reported as a defect from the client pages ("Context page unavailable
# for AEs"). The Implementation Plan's QA bullet reads "An AE token is refused
# on Context and Health by the API", so this is a recorded override, not an
# oversight: the AUDIENCE boundary stands (context stays customer-withheld
# above), the ROLE gate on context is lifted, and Health/alerts remains
# ANALYST+. A side effect this fixes: the firmographics footprint reads
# regulatory_standing.jurisdictions from the context page, so the AE landing
# view rendered an empty footprint purely because this fetch 403'd.
ROLE_FORBIDDEN_PAGES = {"AE": frozenset()}

# Stripped for EVERY audience, marked or not (charter invariant 5).
ALWAYS_STRIP = {
    ("heatmap", "cohort_patterns"): ("patterns[*].entity_ids",
                                     "insufficient_cohorts[*].entity_ids"),
}

# ── The surface-contract allowlist ─────────────────────────────────────
#
# Sections that are OUR RECORD OF OUR OWN METHOD rather than the client's
# assessment, and therefore reach no audience at all. Owner instruction,
# 2026-08-19, third round on the same material: "internal artifacts
# (reasoning traces, capability ceiling, evidence coverage, tiers, counts,
# uncertainty) are dropped at the payload boundary and render nowhere."
#
# Withholding them from the CUSTOMER audience was the previous rule, and it
# was measured insufficient twice: the audience is a toggle in the browser,
# so anybody who moved it met the capability-ceiling table, the evidence
# census and a reasoning trace on the same screen as the client's own
# scores. "Nowhere" is a different rule from "not by default", and it is
# the one that was asked for.
#
# The sections are not deleted from the database or from the producer's
# contract — they are still promoted, still validated, still auditable
# through the connector. They are removed at the point where bytes leave
# for a browser, which is the only boundary that decides what renders.
NEVER_SERVED = frozenset((
    ("overview", "ceilings"),            # O1b — the capability ceiling and
                                         #       uncertainty table
    ("overview", "evidence_coverage"),   # O10 — the census: tiers, counts,
                                         #       the gate line, the share
))

# Keys stripped at any depth for EVERY audience, in every section.
#
#   r_layer  the reasoning trace: hypothesis, counter, domain test, probes,
#            verdict, confidence. It renders as the "REASONING TRACE ·
#            Self-check · ACCEPT · Show" strip that appeared on twelve of
#            twelve overview sections, three times on one screen. It is the
#            record of us arguing with ourselves, which is a thing we owe
#            the assessment and not a thing we owe the reader.
NEVER_SERVED_KEYS = ("r_layer",)

# Keys stripped for the CUSTOMER audience wherever they appear, at any depth,
# in any section. These are internal by their own definition rather than by a
# producer's decision:
#
#   r_layer   hypothesis · counter-argument · domain test · verdict. The
#             record of arguing against our own conclusion. It reached the
#             customer body on 36 paths across both clients, because it is
#             declared per SECTION and the marking was per PATH.
#   storyline_challenge
#             the five adversarial volleys the storyline survived before
#             promotion — the incumbent vendor's strongest objection and
#             why it does not hold. Same family and the same reason: it is
#             our preparation for the room, and a client reading it is
#             reading our sales notes about their own assessment. Marked
#             here rather than left to a producer, from the moment the
#             field exists (0044), so it can never arrive unmarked.
#   enrichment_basis · enriched_at
#             the enrichment tool's own account of itself. Measured on the
#             customer body of the reference client: three named
#             executives each carried, under their own name, "the
#             enrichment search returned no profile whose TITLE matched
#             this person (a name-similar match is an identity failure,
#             not a near-miss)". That is our process vocabulary attached
#             to a real person on their employer's dashboard, and
#             standing clause 12 says never describe a person.
# `r_layer` used to live here. It is now in NEVER_SERVED_KEYS above,
# stripped for every audience rather than for one of them.
CUSTOMER_STRIP_KEYS = ("storyline_challenge",
                       "enrichment_basis", "enriched_at")

# Contact routes for NAMED INDIVIDUALS. Personal work email, direct line
# and personal LinkedIn profile are how an AE reaches somebody; they are
# not part of a client's assessment of itself, and three of six roster
# rows were serving personal LinkedIn URLs to the customer audience.
#
# Stripped by KEY rather than by path, because the roster is not the only
# place a person can appear and a per-path rule is one a producer has to
# remember. The person's NAME, TITLE, TENURE and relevance stay — those
# are the finding; the route to their inbox is not.
CUSTOMER_STRIP_CONTACT_KEYS = ("email", "linkedin_url", "phone",
                               "contact_email", "direct_line", "mobile")

# Paths stripped for the CUSTOMER audience whatever the payload said, per
# (page, section). Producer marking is the primary mechanism and it is not
# sufficient on its own — these two are vendor positioning about the assessing
# firm, written into fields that render on the client's own product register.
CUSTOMER_ALWAYS = {
    ("platform", "platform_story"): ("platforms[*].zennify_pathway",),
    # dma_impact is contract-legitimate (0019: the REASONING connecting a
    # product to the cells it bears on) and was measured carrying sell copy on
    # 51 of 51 rows of one client — 26 of them opening "Zennify's pathway
    # is…". Withheld from the customer audience until a submit-time gate can
    # tell the reasoning from the pitch; that gate, not this line, is the
    # real fix, and this is default-deny in the meantime.
    # The SECTION is named `techstack`, not `items` — `items` is the field
    # inside it. Keyed on the wrong name this rule was unreachable for the
    # whole of its life: `pages.py` passes the real section name, the lookup
    # missed, and `del missed` made the miss silent by design. Nothing showed
    # it because the only test exercising it called redact_section with the
    # wrong name too, so a green test and a dead rule agreed with each other.
    # All 51 rows were removed anyway — by the vendor safety net, which this
    # module says in as many words is "not a substitute" for the rule.
    ("techstack", "techstack"): ("items[*].dma_impact",),
}

# Seller-role vocabulary: sentences written to the assessing firm's own
# account executive. A SECOND safety net beside VENDOR_NAME, because the
# measured leak named no vendor at all — "The searched absence is itself
# informative for the AE", served byte-identical to the customer on the
# client's own platform page, reachable by none of the four declared
# mechanisms and invisible to the vendor net because it does not contain the
# vendor's name. One string of 1,345 on that body, which is why a rule is
# needed rather than a reading.
SELLER_VOCABULARY = re.compile(
    r"\bAEs?\b|\baccount executives?\b|\bdiscovery call\b|\bfirst call\b"
    # "account team" (SWBC, 2026-10-02: "…for the account team to raise") and
    # the hyphenated / abbreviated spellings of the executive. Bounded on
    # both words, so "account", "accountable", "take into account" and
    # "team" alone never match.
    r"|\baccount[- ]teams?\b|\baccount[- ]exec(?:utive)?s?\b"
    r"|\btalk track\b|\bthe seller\b|\bour offering\b|\bour pathway\b"
    r"|\bsay it aloud\b|\bin the room\b|\bpitch\b",
    re.I)

# The assessing firm's own name. A customer-audience string that names it is
# sell copy on the client's dashboard, whatever field it arrived in. This is a
# SAFETY NET under the two rules above, not a substitute for them: it fires on
# the shape nobody marked and nobody predicted, and it records every path it
# fires on so the content defect is visible rather than merely absent.
VENDOR_NAME = os.environ.get("ASSESSING_VENDOR_NAME", "Zennify")
_VENDOR_RE = re.compile(re.escape(VENDOR_NAME), re.I) if VENDOR_NAME else None

# Our PIPELINE's vocabulary in a sentence a client reads — a third net beside
# the vendor and seller nets, and like them a backstop: producers are fixing
# the prose (SWBC, 2026-10-02, measured on the withdrawn run), and this is
# what still stands if one does not.
#
#   NOT_RUN            a gate status, inside PROSE. A safeguard gate's
#                      `status: "NOT_RUN"` is designed to render (invariant
#                      12) — so a value that IS the bare token is never
#                      matched, and heatmap.safeguard_gates is exempt from
#                      this one term: its reason text explains a NOT_RUN by
#                      design.
#   connector credit   the enrichment budget.
#   Clay · Explorium · Exa · Tavily · Firecrawl
#                      the enrichment and search tools. CASE-SENSITIVE and
#                      bounded, so "clay", "exactly", "example" never match;
#                      "Clay" followed by a capitalised word ("Clay Thompson,
#                      CFO") is a person, not the tool, and is left alone.
#   RRF · k=60 · engine v2 · hot band
#                      retrieval-fusion and ranking internals.
#
# Same convention as the other nets: the FIELD holding the sentence goes
# (a list element is blanked), never half a sentence, and every path is
# recorded in the receipt.
_INTERNAL_VOCAB_TERMS = (
    ("NOT_RUN", re.compile(r"\bNOT_RUN\b")),
    ("connector credit", re.compile(r"\bconnector[- ]credits?\b", re.I)),
    ("Clay", re.compile(r"\bClay(?:\.com|'s)?\b(?!\s+[A-Z][a-z])")),
    ("Explorium", re.compile(r"\bExplorium\b", re.I)),
    ("Exa", re.compile(r"\bExa(?:\.ai)?\b")),
    ("Tavily", re.compile(r"\bTavily\b", re.I)),
    ("Firecrawl", re.compile(r"\bFire[- ]?crawl\b", re.I)),
    ("RRF", re.compile(r"\bRRF\b")),
    ("k=60", re.compile(r"\bk\s*=\s*60\b")),
    ("engine v2", re.compile(r"\bengine[- ]v2\b", re.I)),
    ("hot band", re.compile(r"\bhot[- ]bands?\b", re.I)),
)
# A value that is nothing but an enum token is a STATUS, not prose.
_BARE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Keys that hold a person's or an organisation's NAME: a client whose CFO is
# called Clay is not leaking a tool.
_VOCAB_EXEMPT_KEYS = frozenset({"name", "full_name", "person", "person_name",
                                "display_name", "e_id", "gate_id", "gate"})


def internal_vocabulary(text, exempt=()) -> str | None:
    """The first pipeline term `text` names, or None."""
    if not isinstance(text, str) or _BARE_TOKEN.match(text.strip()):
        return None
    for term, rx in _INTERNAL_VOCAB_TERMS:
        if term not in exempt and rx.search(text):
            return term
    return None


def _strip_internal_vocabulary(node, path="", found=None, exempt=()) -> list:
    """Delete every field whose string names a pipeline term (list elements
    are blanked, as the vendor net does, so a ranked list keeps its order)."""
    found = [] if found is None else found
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            here = f"{path}.{k}" if path else k
            hit = (internal_vocabulary(v, exempt)
                   if k not in _VOCAB_EXEMPT_KEYS else None)
            if hit:
                node.pop(k, None)
                found.append(f"{here} ({hit})")
            else:
                _strip_internal_vocabulary(v, here, found, exempt)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            here = f"{path}[{i}]"
            hit = internal_vocabulary(v, exempt)
            if hit:
                node[i] = None
                found.append(f"{here} ({hit})")
            else:
                _strip_internal_vocabulary(v, here, found, exempt)
    return found


#: Terms a section is exempt from, because it renders them by design.
_VOCAB_SECTION_EXEMPT = {("heatmap", "safeguard_gates"): ("NOT_RUN",)}

# `name`, `name[*]`, `name[0]`, `name[*][2]` — the index forms producers
# actually write. A segment with no bracket carries an empty index list.
_SEG_RE = re.compile(r"^([^\[\]]*)((?:\[(?:\*|\d+)\])*)$")
_IDX_RE = re.compile(r"\[(\*|\d+)\]")


def _parse(path: str) -> list[tuple[str, list[str]]] | None:
    """('platforms[0].zennify_pathway') -> [('platforms',['0']),
    ('zennify_pathway',[])]. None when the path is not parseable, which is
    reported rather than silently treated as a miss."""
    segs = []
    for raw in path.split("."):
        m = _SEG_RE.match(raw)
        if not m or (not m.group(1) and not m.group(2)):
            return None
        segs.append((m.group(1), _IDX_RE.findall(m.group(2))))
    return segs


def _descend_indices(node, indices: list[str]) -> list:
    """The nodes reached by applying `[...]` to `node`, in order."""
    current = [node]
    for idx in indices:
        nxt = []
        for n in current:
            if not isinstance(n, list):
                continue
            if idx == "*":
                nxt.extend(n)
            elif int(idx) < len(n):
                nxt.append(n[int(idx)])
        current = nxt
    return current


def _delete(node, segs: list[tuple[str, list[str]]]) -> int:
    """Delete what segs names, returning HOW MANY deletions happened.

    The count is the whole point. A walker that cannot say whether it did
    anything cannot be the source of a receipt, and a receipt that reports
    its input is what shipped five vendor-pitch strings to a customer under
    a note saying they had been removed.
    """
    if node is None or not segs:
        return 0
    (key, indices), rest = segs[0], segs[1:]

    # A list met where a key is expected: fan out. Producers write
    # `platforms.zennify_pathway` as well as `platforms[*].zennify_pathway`
    # and both mean the same thing to a reader.
    if isinstance(node, list) and key:
        return sum(_delete(child, segs) for child in node)

    if not isinstance(node, dict):
        return 0

    if key and key not in node:
        return 0
    target = node[key] if key else node

    if not rest:
        if not indices:
            if key:
                node.pop(key, None)
                return 1
            return 0
        # `items[2]` as the LAST segment: remove that element, not the key.
        removed = 0
        if isinstance(target, list):
            for idx in sorted(
                    (int(i) for i in indices if i != "*"), reverse=True):
                if idx < len(target):
                    del target[idx]
                    removed += 1
            if "*" in indices and target:
                removed += len(target)
                target.clear()
        return removed

    return sum(_delete(child, rest) for child in _descend_indices(target, indices))


def strip_paths(data: dict, paths, section: str | None = None) -> tuple[list, list]:
    """Delete each path from `data` in place.

    Returns (stripped, unmatched): the paths this walker actually deleted
    something for, and the paths that named nothing. The second list is not
    a diagnostic nicety — an `internal_only` entry that matches nothing is a
    producer defect, and the only way anyone learns about it is that the
    serve layer says so.

    `section` names the section `data` is the body of. Producers write
    section-qualified paths (`starters.starters`) because that is how the
    payload reads to them, and `data` here is already inside the section, so
    the qualifier is dropped when it is present. Both spellings work; that
    is deliberate, because the contract has never said which one to use.
    """
    stripped, unmatched = [], []
    # Delete in DESCENDING index order. Producers list element paths in
    # ascending order (`cells[13].items[0]`, `[1]`, `[2]`); deleting them in
    # that order shifts the list under every later path, so a later path
    # deletes the WRONG element or nothing. Measured on SWBC 2026-10-02: of 64
    # marked internal drawer items, 12 paths matched nothing, 18 internal
    # items still served and 6 public items were removed instead.
    parsed = []
    for path in paths or ():
        if not isinstance(path, str) or not path:
            continue
        segs = _parse(path)
        if segs is None:
            unmatched.append(path)
            continue
        parsed.append((path, segs))
    parsed.sort(key=lambda ps: tuple(
        (name, tuple(-int(i) if i != "*" else 1 for i in idx))
        for name, idx in ps[1]))
    for path, segs in parsed:
        n = _delete(data, segs)
        if not n and section and segs[0][0] == section and len(segs) > 1:
            n = _delete(data, segs[1:])
        (stripped if n else unmatched).append(path)
    return stripped, unmatched


def _strip_keys(node, keys, path="", found=None) -> list:
    """Remove `keys` wherever they occur, returning the paths removed."""
    found = [] if found is None else found
    if isinstance(node, dict):
        for k in [k for k in node if k in keys]:
            found.append(f"{path}.{k}" if path else k)
            node.pop(k, None)
        for k, v in node.items():
            _strip_keys(v, keys, f"{path}.{k}" if path else k, found)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _strip_keys(v, keys, f"{path}[{i}]", found)
    return found


def _strip_vendor(node, path="", found=None, pattern=None) -> list:
    """Remove every string matching `pattern` (default: the vendor name).

    Two nets share this walk rather than each having their own: a second
    traversal is a second parser to disagree with the first, which is the
    class this file was rewritten for.

    Deleting in the same pass that finds it is deliberate: the alternative
    is a list of paths and a second walk to re-resolve them, which is a
    second parser to disagree with the first. That disagreement is exactly
    the class this file is being rewritten for.
    """
    found = [] if found is None else found
    rx = pattern if pattern is not None else _VENDOR_RE
    if rx is None:
        return found
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            here = f"{path}.{k}" if path else k
            if isinstance(v, str) and rx.search(v):
                node.pop(k, None)
                found.append(here)
            else:
                _strip_vendor(v, here, found, rx)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            here = f"{path}[{i}]"
            if isinstance(v, str) and rx.search(v):
                # An element, not a key: blanked rather than removed, because
                # dropping it would renumber a ranked list and order is
                # meaning (rule 10).
                node[i] = None
                found.append(here)
            else:
                _strip_vendor(v, here, found, rx)
    return found


# ── The customer serve allowlist — the fail-closed net ─────────────────
#
# Everything above this line is deny-based, and every rule in it was added
# after a measured leak. Deny-based means the NEXT internal-shaped key — the
# one nobody thought to deny — serves by default; measured on the Logix run
# 2026-08-19: 4,527 search-ladder strings across 705 cell drawers and tier
# codes on 97 drawer items reached the customer body with every deny rule
# green. For the CUSTOMER audience the default flips here: a key serves only
# if the generated allowlist names it. The list is derived from the contract
# minus packages/shared/serve_classes.json by scripts/gen_customer_allowlist.py,
# so a key the contract gains tomorrow is dropped until classified — and the
# drop is counted in the receipt, never silent.
#
# Missing file raises: the enrichment_register lesson — a loader that
# swallows FileNotFoundError into an empty dict ships the exact fail-open
# this net exists to end.
_ALLOWLIST = None


# `packages/shared` is resolved by the loader evidence.py already owns —
# reused rather than re-written, because its comments record two separate
# occasions when a fourth copy of these three lines shadowed the tracked file
# with a stale staged one.
from .evidence import _put_shared_on_path      # noqa: E402

_put_shared_on_path()

import internal_ids  # noqa: E402  packages/shared/internal_ids.py


def _customer_allowlist() -> dict:
    global _ALLOWLIST
    if _ALLOWLIST is None:
        path = Path(__file__).with_name("customer_allowlist.json")
        _ALLOWLIST = json.loads(path.read_text())
    return _ALLOWLIST


def _apply_allowlist(page: str, section: str, body: dict) -> tuple[dict | None, list]:
    """(body_or_None_if_unknown_section, dropped_key_paths)."""
    allow = _customer_allowlist()
    spec = allow["sections"].get(f"{page}.{section}")
    if spec is None:
        return None, [f"{section} (section not in the serve allowlist)"]
    dropped = []
    keep_top = set(spec["keys"])
    for key in list(body.keys()):
        if key not in keep_top:
            del body[key]
            dropped.append(key)
    es = body.get("empty_state")
    if isinstance(es, dict):
        keep_es = set(allow["empty_state_keys"])
        for key in list(es.keys()):
            if key not in keep_es:
                del es[key]
                dropped.append(f"empty_state.{key}")
    for field, item_allow in (spec.get("items") or {}).items():
        rows = body.get(field)
        keep = set(item_allow)
        # A DICT-valued field (`linking_stats`) is held to its allowlist too.
        # Only list-valued fields were, so heatmap.cell_evidence served all
        # seven reach counters while the allowlist names three. `empty_state`
        # has its own rule above (`empty_state_keys`) and is not re-filtered.
        if isinstance(rows, dict) and field != "empty_state":
            vals = list(rows.values())
            if vals and all(isinstance(v, dict) for v in vals):
                # An id-keyed MAP (`pillars`, `categories`): the allowlist
                # names each VALUE's keys, never the ids. Filtering the ids
                # emptied the customer grid.
                for k, v in rows.items():
                    for key in list(v.keys()):
                        if key not in keep:
                            del v[key]
                            dropped.append(f"{field}.{k}.{key}")
            elif all(not isinstance(v, (dict, list)) for v in vals):
                # A FLAT dict of counters (`linking_stats`).
                for key in list(rows.keys()):
                    if key not in keep:
                        del rows[key]
                        dropped.append(f"{field}.{key}")
            else:
                # A wrapper (`ladder` = {steps: [...], theme, ...}): the
                # allowlist names the row keys of its list-of-objects; its
                # own scalar keys are left as they were served before.
                for k, v in rows.items():
                    if isinstance(v, list):
                        for i, row in enumerate(v):
                            if isinstance(row, dict):
                                for key in list(row.keys()):
                                    if key not in keep:
                                        del row[key]
                                        dropped.append(f"{field}.{k}[{i}].{key}")
            continue
        if not isinstance(rows, list):
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for key in list(row.keys()):
                if key not in keep:
                    del row[key]
                    dropped.append(f"{field}[{i}].{key}")
    # The excluded CLASSES die at any depth: the contract's item grammar is
    # one level deep, but the drawer nests evidence items inside cells
    # (cells[].items[].tier on 97 Logix rows) — a structural walk alone
    # leaves the second level serving.
    excluded = set(allow["excluded_key_classes"])

    def _sweep(node, path):
        if isinstance(node, dict):
            for key in list(node.keys()):
                sub = f"{path}.{key}" if path else key
                if key in excluded:
                    del node[key]
                    dropped.append(sub)
                else:
                    _sweep(node[key], sub)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _sweep(item, f"{path}[{i}]")

    _sweep(body, "")
    return body, dropped


#: Keys whose whole job is to BE an identifier, so a machinery-shaped value in
#: one is the value and not a leak. `gate_id` is the measured case:
#: heatmap.safeguard_gates is a section invariant 12 DESIGNS to render to the
#: client, through `plain_label`, and the id is the resolver's key beside it.
#: `gate` is exempt with it because the one renderer reads `g.gate_id || g.gate`.
_MACHINERY_EXEMPT_KEYS = frozenset({"gate_id", "gate"})


def _strip_machinery(node, path: str = "", found=None) -> list:
    """Delete every non-exempt key whose string value names our machinery.

    Depth-first and in place, deleting the KEY that holds the string rather
    than any ancestor of it. Returns the paths removed, so the section's
    redaction receipt can count them.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        for key in list(node.keys()):
            value = node[key]
            if (isinstance(value, str) and key not in _MACHINERY_EXEMPT_KEYS
                    and internal_ids.names_machinery(value)):
                found.append(f"{path}.{key}".lstrip("."))
                del node[key]
                continue
            _strip_machinery(value, f"{path}.{key}".lstrip("."), found)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _strip_machinery(value, f"{path}[{i}]", found)
    return found


# ── Evidence ITEMS for the customer audience ───────────────────────────
#
# THE LEAK THIS CLOSES (CRITICAL), measured on SWBC 2026-10-02:
# `GET /v1/entities/swbc/evidence?audience=customer` served rows with
# origin='internal' — the assessing firm's own discovery write-up, its
# source name naming the person it was prepared for, excerpts about named
# people and a sales proposal — plus the tier `distribution` census. The
# route ran ONE redaction (`INTERNAL_FIELDS`, the grading) and none of the
# nets every page section runs: no excluded key classes, no vendor net, no
# seller-vocabulary net. The cell drawer resolves the same rows into
# `cells[].items[]`, so it had the same hole.
#
# An evidence item is a SOURCE, not a sentence: a verbatim excerpt cannot be
# rewritten, and an item with its excerpt or its source name cut out is a
# citation to nothing. So for the customer audience an item is served whole
# or not at all — default-deny:
#
#   · origin 'internal' never serves (our own documents about the client);
#   · an item ANY of whose strings names the vendor, speaks to the seller,
#     names our machinery or our pipeline's vocabulary is withheld whole;
#   · what survives loses the excluded key classes (tier, recency_band,
#     ers, link_basis, provenance, …), the grading, the contact routes and
#     `origin` itself.
EVIDENCE_WITHHELD_ORIGINS = frozenset({"internal"})
_EVIDENCE_ID_KEYS = frozenset({"e_id", "cited_as", "also_filed_as",
                               "linked_subcap_ids"})


def _evidence_item_hit(item: dict) -> str | None:
    """Why this item may not reach a customer, or None."""
    if str(item.get("origin") or "").strip().lower() in EVIDENCE_WITHHELD_ORIGINS:
        return "internal_origin"

    def strings(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in _EVIDENCE_ID_KEYS:
                    yield from strings(v, k)
        elif isinstance(node, list):
            for v in node:
                yield from strings(v, key)
        elif isinstance(node, str):
            yield key, node

    for key, text in strings(item):
        if _VENDOR_RE is not None and _VENDOR_RE.search(text):
            return "vendor_named"
        if SELLER_VOCABULARY.search(text):
            return "seller_voice"
        if internal_ids.names_machinery(text):
            return "machinery_named"
        if key not in _VOCAB_EXEMPT_KEYS and internal_vocabulary(text):
            return "internal_vocabulary"
    return None


def customer_evidence_items(items) -> tuple[list, dict]:
    """(items a customer may see, {reason: count withheld}). Never mutates
    the caller's rows — they are shared across readers."""
    from .evidence import INTERNAL_FIELDS
    excluded = set(_customer_allowlist()["excluded_key_classes"])
    strip = (tuple(INTERNAL_FIELDS) + CUSTOMER_STRIP_KEYS
             + CUSTOMER_STRIP_CONTACT_KEYS + NEVER_SERVED_KEYS
             + ("origin",))
    kept, withheld = [], {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        hit = _evidence_item_hit(item)
        if hit:
            withheld[hit] = withheld.get(hit, 0) + 1
            continue
        c = copy.deepcopy(item)
        _strip_keys(c, tuple(excluded) + strip)
        kept.append(c)
    return kept, withheld


def redact_evidence_response(res: dict, audience: str) -> dict:
    """The evidence route's whole body for `audience`. Default-deny: any
    audience that is not exactly `internal` gets the customer body."""
    if audience == "internal":
        return res
    out = dict(res)
    items, withheld = customer_evidence_items(res.get("items") or [])
    out["items"] = items
    served = {i.get("e_id") for i in items}
    # A withheld id is not reported as found — the reader is told how many
    # were withheld, never which, and never shown the row.
    out["found"] = [e for e in (res.get("found") or []) if e in served]
    out["withheld"] = sum(withheld.values())
    # The tier census and the merge receipt are how WE evidenced the run,
    # the same material O10 is withheld for on the overview page.
    out.pop("distribution", None)
    out.pop("merged", None)
    return out


def _customer_cell_items(data: dict) -> int:
    """Filter every cell's resolved `items[]` to what a customer may see,
    and drop the withheld items' ids from the cell's `e_ids` so the chips
    and the drawer agree. Returns how many items were withheld."""
    n = 0
    for cell in (data.get("cells") or []) if isinstance(data, dict) else []:
        if not isinstance(cell, dict) or not isinstance(cell.get("items"), list):
            continue
        before = cell["items"]
        kept, withheld = customer_evidence_items(before)
        if withheld:
            gone = ({i.get("e_id") for i in before if isinstance(i, dict)}
                    | {i.get("cited_as") for i in before if isinstance(i, dict)})
            gone -= {i.get("e_id") for i in kept} | {i.get("cited_as")
                                                     for i in kept}
            gone.discard(None)
            if isinstance(cell.get("e_ids"), list):
                cell["e_ids"] = [e for e in cell["e_ids"] if e not in gone]
            n += sum(withheld.values())
        cell["items"] = kept
    return n


def _recount_grounded_on(data: dict) -> None:
    """`grounded_on` = the number of items this body actually serves."""
    for cell in (data.get("cells") or []) if isinstance(data, dict) else []:
        if isinstance(cell, dict) and "grounded_on" in cell \
                and isinstance(cell.get("items"), list):
            cell["grounded_on"] = len(cell["items"])


def redact_empty_state(empty, audience: str) -> tuple[object, list]:
    """(empty_state_or_None, dropped) — the ONE part of a section that never
    went through the walker.

    MEM-0137, BLOCKER. `pages.py` redacts `built["data"]` and then attaches
    `env["empty_state"]` beside it, straight off the envelope. So every rule
    this module enforces — the internal_only paths, CUSTOMER_STRIP_KEYS, the
    vendor and seller-voice safety nets, the serve allowlist — applied to the
    section's content and to nothing in its empty state.

    Measured in production 2026-08-24 on three promoted clients:
    `platform.starters.empty_state.sources_searched` serves a customer
    `get_evidence('platform')`, `r_layer` and the literal string
    `CUSTOMER_WITHHELD`, and `heatmap.safeguard_gates.empty_state
    .sources_searched` serves SG-01 and SG-V4. Ten fields between them.

    An empty state is exactly where this hurts most. It is the surface a
    reader lands on when there is nothing else there — the one place they
    read every word — and it is the surface whose whole job is to say "here
    is what we looked for", which is a sentence about OUR machinery unless
    someone rewrites it for them.

    The internal audience keeps the ladder: `sources_searched` is the
    evidence that a search ran, and stripping it there would destroy the very
    distinction the ladder exists to make.
    """
    if not isinstance(empty, dict) or audience != "customer":
        return empty, []
    allow = _customer_allowlist()
    keep = set(allow["empty_state_keys"])
    out = copy.deepcopy(empty)
    dropped = [k for k in list(out) if k not in keep]
    for k in dropped:
        del out[k]
    # The kept keys are PROSE, and prose carries what a key filter cannot
    # see. CG-50's sibling CG-49 refuses a MEM id or a connector call inside
    # `reason` at submit — but only for content submitted after it existed,
    # and all three promoted clients predate it. So the same safety nets that
    # run over a section body run here too.
    dropped += [f"{k} (key)" for k in
                _strip_keys(out, CUSTOMER_STRIP_KEYS
                            + CUSTOMER_STRIP_CONTACT_KEYS)]
    # THE WHOLE KEY, NEVER HALF A SENTENCE. An allowed key with a MEM id in
    # its value is the case a key filter structurally cannot see, and the
    # owner-level decision already recorded on CG-49 is that surgery on prose
    # is the wrong repair: "stripping prose leaves a client reading half a
    # sentence, while refusing it makes the producer write the sentence a
    # client can read." At serve time there is no producer to ask, so the
    # sentence is withheld whole and the section's redaction receipt says one
    # was. The right fix stays upstream: CG-49 refuses it at submit.
    for key, hit in list(internal_ids.scan(out)):
        top = (key.split(".")[0].split("[")[0]) or key
        if top in out:
            del out[top]
            dropped.append(f"{top} (names {hit})")
    dropped += [f"{k} (vendor)" for k in _strip_vendor(out)]
    dropped += [f"{k} (seller voice)" for k in
                _strip_vendor(out, pattern=SELLER_VOCABULARY)]
    dropped += _strip_internal_vocabulary(out)
    return (out or None), dropped


def redact_section(page: str, section: str, data: dict, internal_only,
                   audience: str) -> tuple[dict | None, dict]:
    """Return (data_or_None_if_withheld, redaction_report). Never mutates
    the caller's object: the promoted payload is shared across readers."""
    out = copy.deepcopy(data) if isinstance(data, dict) else data
    report = {"withheld": False, "paths_stripped": [], "paths_unmatched": [],
              "keys_stripped": [], "vendor_named": [],
              "seller_voice": []}

    # The allowlist runs FIRST and for every audience, because a section
    # that reaches no reader has nothing further to decide about it.
    if (page, section) in NEVER_SERVED:
        return None, {"withheld": True, "never_served": True,
                      "paths_stripped": [], "paths_unmatched": [],
                      "keys_stripped": [], "vendor_named": [],
                      "seller_voice": []}

    always = ALWAYS_STRIP.get((page, section), ())
    if isinstance(out, dict) and always:
        did, missed = strip_paths(out, always, section)
        report["paths_stripped"] += did
        report["paths_unmatched"] += missed

    if isinstance(out, dict):
        report["keys_stripped"] += _strip_keys(out, NEVER_SERVED_KEYS)

    if audience == "customer":
        if (page, section) in CUSTOMER_WITHHELD:
            return None, {"withheld": True, "paths_stripped": [],
                          "paths_unmatched": [], "keys_stripped": [],
                          "vendor_named": [], "seller_voice": []}
        if isinstance(out, dict):
            did, missed = strip_paths(out, internal_only, section)
            report["paths_stripped"] += did
            report["paths_unmatched"] += missed

            did, missed = strip_paths(
                out, CUSTOMER_ALWAYS.get((page, section), ()), section)
            report["paths_stripped"] += did
            # An CUSTOMER_ALWAYS path that matches nothing is normal — the
            # field is optional and most runs will not carry it — so it is
            # not reported as a producer defect.
            del missed

            # `+=`, not `=`. The unconditional pass above already recorded
            # what it removed, and an assignment here silently discarded it —
            # so the receipt for a customer read reported fewer removals than
            # were actually made, which is the exact class of lying receipt
            # this module was rewritten to end.
            report["keys_stripped"] += _strip_keys(
                out, CUSTOMER_STRIP_KEYS + CUSTOMER_STRIP_CONTACT_KEYS)

            # The safety nets run LAST, over what survived every rule
            # above. Two of them: the vendor's name, and sentences addressed
            # to the seller's own account executive — the measured leak was
            # the second kind and named no vendor at all.
            # The cell drawer's evidence ITEMS are sources, not prose: an
            # item the customer may not see goes whole, before the nets
            # below take single fields out of it.
            if (page, section) == ("heatmap", "cell_evidence"):
                report["evidence_items_withheld"] = _customer_cell_items(out)
            report["vendor_named"] = _strip_vendor(out)
            report["seller_voice"] = _strip_vendor(out, pattern=SELLER_VOCABULARY)
            report["internal_vocabulary"] = _strip_internal_vocabulary(
                out, exempt=_VOCAB_SECTION_EXEMPT.get((page, section), ()))

            # The allowlist runs LAST for the customer audience: whatever
            # survived every deny rule above must also be NAMED to serve.
            out, dropped = _apply_allowlist(page, section, out)
            report["allowlist_dropped"] = dropped

            # …and then the one thing an allowlist structurally cannot see:
            # what the NAMED keys SAY. `narrative_thread` is allowed and its
            # VALUE is where a gate id sits, which is why ten fields reached
            # three clients' customer bodies while the allowlist was working
            # exactly as designed.
            #
            # DEFAULT-DENY WITH A MEASURED EXEMPTION, not a list of prose
            # keys: the customer bodies hold 93 distinct keys carrying a
            # sentence, so any such list is incomplete the day it is written.
            # Across the internal bodies of all five clients on all five
            # pages, only three keys ever hold a string matching the pattern —
            # sources_searched (the empty_state ladder, handled in
            # `redact_empty_state`), gate_id, and narrative_thread. So one key
            # is exempt and everything else is checked.
            #
            # THE KEY GOES, NOT ITS PARENT. `scan` returns
            # `gates[0].gate_id`; keying off the first path segment would
            # delete the whole `gates` array and empty
            # heatmap.safeguard_gates on every client.
            report["machinery_named"] = _strip_machinery(out)
            if out is None:
                return None, {**report, "withheld": True,
                              "unknown_section": True}
            # INVARIANT 8 at the very end, over what is actually served:
            # `grounded_on` is GENERATED as the length of the row's e_ids,
            # and the customer drawer may now serve fewer items than that.
            # A count that disagrees with the list printed beside it is a
            # stored total, which is what the invariant forbids.
            if (page, section) == ("heatmap", "cell_evidence"):
                _recount_grounded_on(out)

    return out, report


def page_forbidden(page: str, audience: str, role: str | None) -> str | None:
    """The reason a page may not be served at all, or None."""
    if audience == "customer" and page in CUSTOMER_WITHHELD_PAGES:
        return (f"the {page} dashboard is withheld from the customer audience "
                "and renders a locked state rather than a partial page")
    if role and page in ROLE_FORBIDDEN_PAGES.get(role.upper(), ()):
        return f"role {role.upper()} has no route to the {page} dashboard"
    return None


# Every audience this API knows. Anything else resolves to the LEAST
# privileged one rather than to the most: a typo, an omission or a value from
# a caller this build has not met must not open the internal body.
AUDIENCES = ("customer", "internal")


def normalise_audience(value: str | None) -> str:
    """Default-deny. `audience` defaulted to "internal" on every route, so a
    caller that omitted it — or misspelled it — was served the analyst body
    including every internal rung. The BFF has always sent it explicitly, so
    nothing legitimate depends on the old default."""
    v = (value or "").strip().lower()
    return v if v in AUDIENCES else "customer"
