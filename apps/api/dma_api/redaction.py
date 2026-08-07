"""Audience redaction — one enforcement point, server-side, default-deny.

The frontend never decides what is internal, because it never receives the
internal fields (TRD §11). Three mechanisms, in order of authority:

1. `internal_only` — JSON paths the producer marked, deleted for the
   customer audience. This is the primary mechanism and the reason the
   marking is a payload field: an unmarked rung is invisible here, so the
   contract, the walker and the tests all push the marking upstream.
2. ALWAYS_STRIP — paths stripped for EVERY audience, whatever the payload
   said. Cross-entity pattern entity ids are audit-only and never leave
   the audit trail (charter invariant 5), so they do not depend on a
   producer remembering to mark them.
3. CUSTOMER_WITHHELD — sections withheld whole rather than redacted: a
   page that renders half its cards invites the question of what the other
   half said (TRD §11).

Open adjudication recorded rather than resolved silently: the TRD's rung
table lists all five D7 Health surfaces as analyst-only, while charter
invariant 12 says a safeguard gate's result "renders to client with
plain_label" and the H5 prompt says the same in its own words. This module
follows the invariant — safeguard_gates stays visible, the operational
health surfaces (thin-evidence alerts, evidence age, cohort patterns) do
not — and the tension is flagged for the user.
"""
from __future__ import annotations

import copy

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


def _walk_delete(node, segs: list[str]) -> None:
    """Delete the leaf named by segs, following `[*]` across lists."""
    if not segs or node is None:
        return
    seg, rest = segs[0], segs[1:]
    wildcard = seg.endswith("[*]")
    key = seg[:-3] if wildcard else seg

    if wildcard:
        children = node.get(key) if isinstance(node, dict) else None
        if isinstance(children, list):
            for child in children:
                if rest:
                    _walk_delete(child, rest)
        return

    if isinstance(node, list):
        for child in node:
            _walk_delete(child, segs)
        return

    if not isinstance(node, dict):
        return

    if not rest:
        node.pop(key, None)
        return
    _walk_delete(node.get(key), rest)


def strip_paths(data: dict, paths) -> list[str]:
    """Delete each path from data in place; return the paths applied."""
    applied = []
    for path in paths or ():
        if not isinstance(path, str) or not path:
            continue
        _walk_delete(data, path.split("."))
        applied.append(path)
    return applied


def redact_section(page: str, section: str, data: dict, internal_only,
                   audience: str) -> tuple[dict | None, dict]:
    """Return (data_or_None_if_withheld, redaction_report). Never mutates
    the caller's object: the promoted payload is shared across readers."""
    out = copy.deepcopy(data) if isinstance(data, dict) else data
    report = {"withheld": False, "paths_stripped": []}

    always = ALWAYS_STRIP.get((page, section), ())
    if isinstance(out, dict) and always:
        report["paths_stripped"] += strip_paths(out, always)

    if audience == "customer":
        if (page, section) in CUSTOMER_WITHHELD:
            return None, {"withheld": True, "paths_stripped": []}
        if isinstance(out, dict):
            report["paths_stripped"] += strip_paths(out, internal_only)

    return out, report


def page_forbidden(page: str, audience: str, role: str | None) -> str | None:
    """The reason a page may not be served at all, or None."""
    if audience == "customer" and page in CUSTOMER_WITHHELD_PAGES:
        return (f"the {page} dashboard is withheld from the customer audience "
                "and renders a locked state rather than a partial page")
    if role and page in ROLE_FORBIDDEN_PAGES.get(role.upper(), ()):
        return f"role {role.upper()} has no route to the {page} dashboard"
    return None
