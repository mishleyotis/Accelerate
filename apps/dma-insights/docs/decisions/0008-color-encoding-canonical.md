# ADR 0008 — Maturity color / freshness / peer-delta encoding canonical

**Status**: Accepted (2026-05-20)

## Context

The UI/UX Brief specifies four named maturity bands (Activating, Building,
Competing, Differentiating) plus a "Defining" label that overlaps with M5.
`tokens.css` ships four `--m-*` CSS vars that the prototype's
`data.js` helpers (`maturityHex`, `maturityLabel`, `maturityClass`) map
from raw score → color. The prototype also defines a peer-delta arrow
convention (▲ at/above peer in `--z-mid`, ▼ below peer in `--z-below`)
and a freshness ladder (Current ≤ 6 mo, Aging 6-12 mo, Stale > 12 mo).

The first cut of the heatmap page introduced its own
`BAND_COLOR = {M1: #C8102E, …}` palette that *did not* match the
prototype tokens. This ADR locks down the canonical encoding and
mandates that every visible surface read from one place.

## Decision

Create `frontend/src/lib/maturity.ts` as the single source of truth for:

1. **maturityHex(score)** — score→hex, exactly mirroring the prototype's
   data.js (`s < 2 → #FFCB99`, `s < 3 → #62D7B8`, `s < 4 → #27BBAF`,
   `s ≥ 4 → #139F94`, `null → #E5E7EB`). Uses score breakpoints, not
   M-band strings, because the UI/UX brief is score-driven.

2. **maturityLabel(score)** — `Activating | Building | Competing |
   Differentiating | Unset`.

3. **maturityClass(score)** — emits the `b-act | b-bld | b-cmp | b-dif |
   muted` class tokens that `app.css` already styles.

4. **peerDeltaArrow(entity, peer)** — returns `{ glyph: ▲|▼|·, color,
   magnitude, direction }`. `▲` uses `var(--z-mid)`, `▼` uses
   `var(--z-below)`. Near-zero deltas collapse to `·` (within 0.05) so
   the AE isn't visually noised by indistinguishable peer matches.

5. **freshnessOf(at)** — returns `{ tone: ok|warn|below, label:
   Current|Aging|Stale, months }`, matching the prototype's `freshnessOf`.

## Consequences

- **HeatmapPage**: cell background uses `maturityHex(cell.score)`; the
  peer overlay uses the new `peerDeltaArrow` so the AE sees the canonical
  ▲/▼ arrows + color-coded text instead of the previous amber "below" pill.
- **ScoreRing**: ring stroke + number color both use
  `maturityHex(score)`, so a 4.6 score renders dark teal (--m-dif) and a
  1.8 renders peach (--m-act). The score "tone" matches the wireframe.
- **DriftBadge / StairstepCurve / PatternBadge**: future score-rendering
  can pull from the same helpers; no per-page palette duplication.
- **All cross-pillar surfaces** (Dashboard tiles, Directory rows,
  Client Overview) get a consistent palette without each page
  re-deriving thresholds.

## Locked numbers

| Threshold | Label | Hex | CSS var |
|---|---|---|---|
| `s == null` | Unset | `#E5E7EB` | `--z-sep` |
| `s < 2.0`  | Activating | `#FFCB99` | `--m-act` |
| `s < 3.0`  | Building | `#62D7B8` | `--m-bld` |
| `s < 4.0`  | Competing | `#27BBAF` | `--m-cmp` |
| `s >= 4.0` | Differentiating | `#139F94` | `--m-dif` |

Peer-delta arrows:

| Condition | Glyph | Color |
|---|---|---|
| `|delta| < 0.05` | `·` | `var(--z-muted)` |
| `delta >= 0`     | `▲` | `var(--z-mid)` |
| `delta < 0`      | `▼` | `var(--z-below)` |

Freshness thresholds:

| Age | Label | Tone |
|---|---|---|
| > 12 months | Stale | `below` |
| 6-12 months | Aging | `warn` |
| ≤ 6 months  | Current | `ok` |

## Tests

`frontend/src/lib/__tests__/maturity.test.ts` locks every threshold.
Visual-regression tests in stage 12 lock pixel diffs against the
prototype's `Standalone.html`.
