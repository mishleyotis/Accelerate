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
internal one on both platform pages (132,711 against 132,462 for Baxter;
33,165 against 33,126 for Odlum) — the receipt naming the removals was the
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
import os
import re

# (page, section) withheld entirely from the customer audience.
CUSTOMER_WITHHELD = frozenset((
    ("overview", "ceilings"),            # O1b — TRD §11 rung table
    ("overview", "sentiment"),            # O9  — TRD §11 rung table
    ("overview", "thought_leadership"),   # O12 — TRD §11 rung table
    ("heatmap", "alerts"),                # D7 Health, operational
    ("heatmap", "evidence_age"),          # D7 Health, operational
    ("heatmap", "cohort_patterns"),       # D7 Health + cross-entity
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
CUSTOMER_STRIP_KEYS = ("r_layer", "storyline_challenge",
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
    ("techstack", "items"): ("items[*].dma_impact",),
}

# The assessing firm's own name. A customer-audience string that names it is
# sell copy on the client's dashboard, whatever field it arrived in. This is a
# SAFETY NET under the two rules above, not a substitute for them: it fires on
# the shape nobody marked and nobody predicted, and it records every path it
# fires on so the content defect is visible rather than merely absent.
VENDOR_NAME = os.environ.get("ASSESSING_VENDOR_NAME", "Zennify")
_VENDOR_RE = re.compile(re.escape(VENDOR_NAME), re.I) if VENDOR_NAME else None

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
    for path in paths or ():
        if not isinstance(path, str) or not path:
            continue
        segs = _parse(path)
        if segs is None:
            unmatched.append(path)
            continue
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


def _strip_vendor(node, path="", found=None) -> list:
    """Remove every string that names the assessing vendor, in one walk.

    Deleting in the same pass that finds it is deliberate: the alternative
    is a list of paths and a second walk to re-resolve them, which is a
    second parser to disagree with the first. That disagreement is exactly
    the class this file is being rewritten for.
    """
    found = [] if found is None else found
    if _VENDOR_RE is None:
        return found
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            here = f"{path}.{k}" if path else k
            if isinstance(v, str) and _VENDOR_RE.search(v):
                node.pop(k, None)
                found.append(here)
            else:
                _strip_vendor(v, here, found)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            here = f"{path}[{i}]"
            if isinstance(v, str) and _VENDOR_RE.search(v):
                # An element, not a key: blanked rather than removed, because
                # dropping it would renumber a ranked list and order is
                # meaning (rule 10).
                node[i] = None
                found.append(here)
            else:
                _strip_vendor(v, here, found)
    return found


def redact_section(page: str, section: str, data: dict, internal_only,
                   audience: str) -> tuple[dict | None, dict]:
    """Return (data_or_None_if_withheld, redaction_report). Never mutates
    the caller's object: the promoted payload is shared across readers."""
    out = copy.deepcopy(data) if isinstance(data, dict) else data
    report = {"withheld": False, "paths_stripped": [], "paths_unmatched": [],
              "keys_stripped": [], "vendor_named": []}

    always = ALWAYS_STRIP.get((page, section), ())
    if isinstance(out, dict) and always:
        did, missed = strip_paths(out, always, section)
        report["paths_stripped"] += did
        report["paths_unmatched"] += missed

    if audience == "customer":
        if (page, section) in CUSTOMER_WITHHELD:
            return None, {"withheld": True, "paths_stripped": [],
                          "paths_unmatched": [], "keys_stripped": [],
                          "vendor_named": []}
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

            report["keys_stripped"] = _strip_keys(
                out, CUSTOMER_STRIP_KEYS + CUSTOMER_STRIP_CONTACT_KEYS)

            # The safety net runs LAST, over what survived every rule above.
            report["vendor_named"] = _strip_vendor(out)

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
