"""Run-ID normalization.

The DMA pipeline emits two distinct run-ID conventions:

1. Bot-originated: `REQ-{8 uppercase hex}` — the canonical id when the
   request flowed through the DMA Bot + Ops Sheet (plan §④).
2. Direct delivery: `DMA-ASM-{ENTITY}-{YYYYMMDD}-{NNNN}` — what Claude
   project assessment runs and out-of-band deliveries produce. Always
   paired with a sibling `DMA-RES-{ENTITY}-{YYYYMMDD}-{NNNN}` research
   run (the L0/L1 split — see `07_governance/run_manifest.json`).

`runs.request_id` must be unique, so we store the canonical form (REQ-…)
when present, otherwise the DMA-ASM-… string verbatim. Both forms parse
cleanly through `parse_run_id`.

State-branch contract for this module:
  - REQ-{hex}     → kind=REQ,   entity_token=None,  date_iso=None
  - DMA-ASM-…    → kind=ASM,   entity_token=str,   date_iso=YYYY-MM-DD
  - DMA-RES-…    → kind=RES,   entity_token=str,   date_iso=YYYY-MM-DD
  - anything else → ValueError (callers handle ad-hoc IDs explicitly)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

REQ_PATTERN = re.compile(r"^REQ-[0-9A-F]{8}$")
DMA_ASM_PATTERN = re.compile(
    r"^DMA-(?P<phase>ASM|RES)-(?P<entity>[A-Z][A-Z0-9]+)-"
    r"(?P<date>\d{8})-(?P<seq>\d{4})$"
)


RunIdKind = Literal["REQ", "ASM", "RES"]


@dataclass(frozen=True)
class RunIdInfo:
    raw: str
    kind: RunIdKind
    entity_token: str | None
    date_iso: str | None
    seq: int | None

    @property
    def is_canonical(self) -> bool:
        """REQ-… IDs are canonical (bot-originated); others are derived."""
        return self.kind == "REQ"


def parse_run_id(value: str) -> RunIdInfo:
    raw = value.strip()
    if REQ_PATTERN.match(raw):
        return RunIdInfo(raw=raw, kind="REQ", entity_token=None,
                         date_iso=None, seq=None)
    m = DMA_ASM_PATTERN.match(raw)
    if m is None:
        raise ValueError(f"unrecognized run_id format: {raw!r}")
    d = m.group("date")
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    # Validate date components (a parse here catches 20261332 style typos).
    date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    return RunIdInfo(
        raw=raw,
        kind=m.group("phase"),  # type: ignore[arg-type]
        entity_token=m.group("entity"),
        date_iso=iso,
        seq=int(m.group("seq")),
    )


def is_valid_run_id(value: str) -> bool:
    try:
        parse_run_id(value)
    except ValueError:
        return False
    return True


def compute_assessment_date(
    manifest_date: date | None,
    run_id: str,
    package_date: date | None,
) -> tuple[date | None, str | None]:
    """Resolve the run's official assessment date (migration 039).

    Fallback chain, mirroring the provenance the UI may surface:
      1. run_manifest.json `assessment_date`      → ("run_manifest")
      2. the DMA-ASM-{ENTITY}-{YYYYMMDD} segment  → ("run_id")
      3. MANIFEST.json `package_date`             → ("package_manifest")
      4. nothing                                  → (None, None) — the
         read-side falls back to `started_at` (ingest day) and flags it.

    Pure + import-light so `app.scripts.backfill_run_dates` can repair
    already-ingested rows from `request_id` alone without re-ingest.
    """
    if manifest_date:
        return manifest_date, "run_manifest"
    try:
        info = parse_run_id(run_id)
    except ValueError:
        info = None
    if info is not None and info.date_iso:
        return date.fromisoformat(info.date_iso), "run_id"
    if package_date:
        return package_date, "package_manifest"
    return None, None
