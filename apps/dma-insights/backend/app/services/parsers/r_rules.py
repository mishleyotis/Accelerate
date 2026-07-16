"""F6 — PRD §6 R-rules detection (ingestion-time intelligence).

Each rule fires deterministically against parser inputs (file path,
metadata, payload) and emits a typed RRuleHit. Rules are pure
functions; the caller decides how to act (warn / skip / route to
admin queue).

State-branch contract (returned via RRuleHit.action):
  - allow         → rule did not match; ingest as normal
  - warn          → rule matched but is informational only
                    (e.g. T2 sub-vertical without subvertical pin)
  - quarantine    → file should be routed to admin queue with the
                    rule's reason in `import_files.parser_warnings`
                    (e.g. client-provided document needs SME review)
  - skip          → file should NOT be ingested (e.g. Nyumba Zetu
                    test case; can be operator-overridden via the
                    admin queue)
  - downgrade     → ingest but mark as legacy (pre-v5.5 framework)

The rule registry is data; new rules land by appending to RULES.
Tests assert: each rule has at least one positive + one negative
sample, the registry is sorted by rule_id, and every rule_id is
unique.

Rules:
  R05 — Client-provided document detection
  R06 — Pre-v5.5 framework detection
  R07 — Test-case / sample-data quarantine (Nyumba Zetu, "*test*",
        "*sample*", "*demo*")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# ── Public API ─────────────────────────────────────────────────────────


RRuleAction = Literal["allow", "warn", "quarantine", "skip", "downgrade"]


@dataclass(frozen=True)
class RRuleHit:
    rule_id: str           # 'R05' / 'R06' / 'R07'
    action: RRuleAction    # see module docstring
    reason: str            # short human-readable, lands in JSONB
    confidence: float      # 0.0 to 1.0
    evidence: dict         # rule-specific payload (matched substring etc.)


# ── R05 — Client-provided document detection ──────────────────────────


_ZENNIFY_DOMAINS = ("@zennify.com",)
_ZENNIFY_BOT_AUTHORS = (
    "dma@zennify.com", "dmabot", "n8n", "claude project",
)


def detect_r05_client_provided(
    *,
    file_owner_email: str | None,
    last_modified_by_email: str | None,
    filename: str = "",
) -> RRuleHit | None:
    """R05 — file owner / modifier is not a Zennify analyst.

    Caller passes the Drive file's `owners[0].emailAddress` and
    `lastModifyingUser.emailAddress` from the Drive metadata. If
    BOTH are outside the Zennify domain (and not the bot SA), the
    file is treated as client-provided and routed to admin queue.

    The bot SA + dma@zennify.com counts as Zennify-internal so
    auto-uploaded analysis artifacts don't trigger.
    """
    def _is_zennify(addr: str | None) -> bool:
        if not addr:
            return False
        a = addr.strip().lower()
        if any(a.endswith(d) for d in _ZENNIFY_DOMAINS):
            return True
        return any(b in a for b in _ZENNIFY_BOT_AUTHORS)

    owner_is_z = _is_zennify(file_owner_email)
    mod_is_z = _is_zennify(last_modified_by_email)

    # If we have NEITHER signal we can't decide — return None so the
    # parser defaults to "allow" (don't quarantine on missing metadata).
    if file_owner_email is None and last_modified_by_email is None:
        return None
    if owner_is_z or mod_is_z:
        return None
    return RRuleHit(
        rule_id="R05",
        action="quarantine",
        reason=(
            "client-provided document: neither owner "
            f"({file_owner_email or '?'}) nor last-modifier "
            f"({last_modified_by_email or '?'}) is a Zennify analyst"
        ),
        confidence=1.0,
        evidence={
            "owner": file_owner_email,
            "last_modifier": last_modified_by_email,
            "filename": filename,
        },
    )


# ── R06 — Pre-v5.5 framework detection ────────────────────────────────


# Liberal match — DOCX cover pages render the version differently across
# AlmaBank ("Framework v4.0"), WSFS ("DMA Framework v5.1 — March 2025"),
# Regions ("Capability Mapping v5.0 (R3)"), early AmeriCU ("v4.8-beta").
_PRE_55_FRAMEWORK_RE = re.compile(
    r"\b(?:framework|capability\s+mapping|dma\s+framework)\s+v(?:[0-4]\.\d+|5\.[0-4])\b",
    re.IGNORECASE,
)
_V55_PLUS_RE = re.compile(
    r"\b(?:framework|capability\s+mapping|dma\s+framework)\s+v(?:5\.[5-9]|[6-9]\.\d+|\d{2,}\.\d+)\b",
    re.IGNORECASE,
)


def detect_r06_pre_v55_framework(
    *,
    docx_first_page_text: str,
    filename: str = "",
) -> RRuleHit | None:
    """R06 — assessment report cover-page references a pre-v5.5
    framework.

    These reports were scored against the v5.0 / v5.4 catalogue which
    used a slightly different sub-cap shape (ID prefix `P{n}.{cat}.X`
    instead of v7's `P{n}C{cat}.X.Y`). The catalogue alias bridge
    (`ccg_subcap_aliases`) handles the ID translation but the
    parser also needs to know to expect the legacy shape so it
    doesn't mis-classify rows.

    Returns:
      None             → no v5.x version stamp on cover page
      action=downgrade → matched pre-v5.5 (parser uses legacy branch)
      action=allow     → matched v5.5+ explicitly (informational)
    """
    text = docx_first_page_text or ""
    # Prefer the more-specific v5.5+ match first — defensive.
    if _V55_PLUS_RE.search(text):
        return None
    m = _PRE_55_FRAMEWORK_RE.search(text)
    if not m:
        return None
    matched = m.group(0)
    return RRuleHit(
        rule_id="R06",
        action="downgrade",
        reason=f"pre-v5.5 framework detected on cover page: '{matched}'",
        confidence=0.95,
        evidence={"matched_phrase": matched, "filename": filename},
    )


# ── R07 — Test-case / sample-data quarantine ──────────────────────────


# Real entity names we've seen used as test cases. The substring is
# case-insensitive. Operators can override per-file via the admin
# "Allow as real" toggle (which writes `import_files.allow_override`).
_TEST_CASE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("nyumba zetu", "Nyumba Zetu test case (used by historical demos)"),
    ("nyumba_zetu", "Nyumba Zetu test case"),
    ("__test__", "explicit __test__ marker"),
    ("sample-bank", "sample-bank placeholder"),
    ("acme-bank", "Acme Bank placeholder"),
    ("foo-bank", "foo-bank placeholder"),
)


# Generic name-pattern filters — broader, lower confidence so the
# operator can override more easily.
_GENERIC_TEST_RE = re.compile(
    r"(?<![a-z])(?:test|sample|demo|qa[-_]|fixture)(?![a-z])",
    re.IGNORECASE,
)


def detect_r07_test_case(
    *,
    folder_name: str,
    entity_name: str | None = None,
) -> RRuleHit | None:
    """R07 — folder / entity name matches a known test-case pattern.

    Two-tier confidence:
      - Known test case (Nyumba Zetu etc.) → confidence=1.0, skip
      - Generic test/sample/demo token     → confidence=0.65, warn
        (operator decides via admin queue)
    """
    composite = " ".join(filter(None, (folder_name, entity_name))).lower()
    for needle, why in _TEST_CASE_PATTERNS:
        if needle in composite:
            return RRuleHit(
                rule_id="R07",
                action="skip",
                reason=f"test case: {why}",
                confidence=1.0,
                evidence={"matched": needle, "folder_name": folder_name,
                          "entity_name": entity_name},
            )
    m = _GENERIC_TEST_RE.search(composite)
    if m:
        return RRuleHit(
            rule_id="R07",
            action="warn",
            reason=(
                f"name contains generic test-marker token: '{m.group(0)}'"
            ),
            confidence=0.65,
            evidence={"matched": m.group(0), "folder_name": folder_name,
                      "entity_name": entity_name},
        )
    return None


# ── Orchestrator ───────────────────────────────────────────────────────


def evaluate_all_rules(
    *,
    folder_name: str,
    entity_name: str | None = None,
    file_owner_email: str | None = None,
    last_modified_by_email: str | None = None,
    docx_first_page_text: str = "",
    filename: str = "",
) -> list[RRuleHit]:
    """Apply every R-rule to one ingest-time input bundle.

    Returns the list of hits ordered by rule_id so downstream
    persistence + audit output is deterministic.

    Caller (drive_crawler / historical_backfill / parse_package)
    decides what to do with each hit per the action field. The
    typical chain is:

        hits = evaluate_all_rules(...)
        # Highest-severity action wins for routing:
        if any(h.action == 'skip' for h in hits):
            return SKIP_with_audit(hits)
        if any(h.action == 'quarantine' for h in hits):
            return QUARANTINE_with_audit(hits)
        # Otherwise ingest, attaching hits to parser_warnings.
        warnings.extend(h.reason for h in hits if h.action in ('warn', 'downgrade'))
    """
    hits: list[RRuleHit] = []
    h = detect_r05_client_provided(
        file_owner_email=file_owner_email,
        last_modified_by_email=last_modified_by_email,
        filename=filename,
    )
    if h:
        hits.append(h)
    h = detect_r06_pre_v55_framework(
        docx_first_page_text=docx_first_page_text, filename=filename,
    )
    if h:
        hits.append(h)
    h = detect_r07_test_case(
        folder_name=folder_name, entity_name=entity_name,
    )
    if h:
        hits.append(h)
    return sorted(hits, key=lambda x: x.rule_id)


# ── Severity helpers (caller-facing) ───────────────────────────────────


_ACTION_PRIORITY: dict[RRuleAction, int] = {
    "skip": 5,
    "quarantine": 4,
    "downgrade": 3,
    "warn": 2,
    "allow": 1,
}


def highest_severity(hits: list[RRuleHit]) -> RRuleAction:
    """Pick the highest-severity action across a hit set so the
    orchestrator has a single routing decision."""
    if not hits:
        return "allow"
    return max(hits, key=lambda h: _ACTION_PRIORITY[h.action]).action


def hits_to_audit_payload(hits: list[RRuleHit]) -> dict:
    """JSON-safe dict for `import_files.parser_warnings`."""
    return {
        "r_rules": [
            {
                "rule_id": h.rule_id,
                "action": h.action,
                "reason": h.reason,
                "confidence": h.confidence,
                "evidence": h.evidence,
            }
            for h in hits
        ],
        "highest_severity": highest_severity(hits),
    }


# Re-export for downstream
__all__ = [
    "RRuleAction", "RRuleHit",
    "detect_r05_client_provided",
    "detect_r06_pre_v55_framework",
    "detect_r07_test_case",
    "evaluate_all_rules",
    "highest_severity",
    "hits_to_audit_payload",
]
