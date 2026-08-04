"""The four-signal entity cascade (stage 1.2 / PRD §"four-signal cascade").

Signals in strict order — the first that yields an identity stops the
cascade:
  1 run manifest        explicit identity in the package; highest confidence
  2 request identifier  carries the entity token in its own structure
  3 document header     legal name from the report cover, resolved against
                        known suffixes and trading names
  4 folder name         lowest confidence; produces a PENDING_REVIEW
                        entity, NEVER an active one

Low confidence is a status decision, not a float threshold: the policy is
per-signal, encoded structurally below. inference_confidence is recorded
on the entity row for the audit either way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REQ_ID = re.compile(r"^REQ-[0-9A-F]{8}$")
DMA_ASM = re.compile(r"^DMA-ASM-(?P<entity>[A-Z0-9]+)-(?P<date>\d{8})-(?P<seq>\d{4})$")

# Legal-form suffixes stripped before name comparison.
_SUFFIXES = re.compile(
    r",?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|llp|"
    r"n\.?a\.?|fsb|ssb|plc|bancorp|bancshares|holdings?|group|association|aca|fcu|cu)\.?$",
    re.I,
)


def normalise_name(name: str) -> str:
    n = name.strip().lower()
    prev = None
    while prev != n:
        prev = n
        n = _SUFFIXES.sub("", n).strip()
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


@dataclass(frozen=True)
class Resolution:
    entity_token: str        # normalised name or explicit identifier
    signal: str              # manifest · request_id · document_header · folder_name
    confidence: float        # recorded on entities.inference_confidence
    status: str              # ACTIVE | PENDING_REVIEW


def resolve(
    manifest_identity: str | None,
    request_id: str | None,
    document_header: str | None,
    folder_name: str | None,
    known_names: dict[str, str] | None = None,
) -> Resolution | None:
    """known_names maps normalised legal/trading names -> canonical token,
    used by signal 3 to resolve a header against known entities."""
    if manifest_identity:
        return Resolution(manifest_identity.strip(), "manifest", 0.98, "ACTIVE")

    if request_id:
        rid = request_id.strip().upper()
        m = DMA_ASM.match(rid)
        if m:
            return Resolution(m.group("entity"), "request_id", 0.90, "ACTIVE")
        if REQ_ID.match(rid):
            # The bot-originated format carries no entity token in its own
            # structure — it identifies the run, not the entity. Fall through.
            pass

    if document_header:
        norm = normalise_name(document_header)
        if norm:
            if known_names and norm in known_names:
                return Resolution(known_names[norm], "document_header", 0.75, "ACTIVE")
            # An unrecognised legal name is still an identity claim, but an
            # unverified one — never auto-activated.
            return Resolution(norm, "document_header", 0.60, "PENDING_REVIEW")

    if folder_name:
        norm = normalise_name(folder_name)
        if norm:
            # Lowest confidence: pending review, never active (PRD).
            return Resolution(norm, "folder_name", 0.40, "PENDING_REVIEW")

    return None
