/**
 * Maturity / freshness / peer-delta encoding — single source of truth.
 *
 * Lifted verbatim from the prototype's `data.proto.ts` helpers
 * (maturityClass, maturityHex, maturityLabel, freshnessOf) so every
 * surface in the live app renders the same colors the wireframe
 * promises. Keeping these in one module means any future tweak (e.g.
 * shifting the band breakpoints) lands in exactly one place.
 *
 * Canonical thresholds (from the UI/UX Brief + tokens.css comments):
 *   score < 2.0  → Activating (M1-M2)  · #FFCB99 (--m-act)
 *   score < 3.0  → Building   (M2-M3)  · #62D7B8 (--m-bld)
 *   score < 4.0  → Competing  (M3-M4)  · #27BBAF (--m-cmp)
 *   score >= 4.0 → Differentiating (M4-M5) · #139F94 (--m-dif)
 *   score null   → unset                · #E5E7EB (--z-sep)
 *
 * Peer-delta arrow convention (from client-overview-insights.proto.tsx):
 *   delta >= 0  → `▲` in `var(--z-mid)`   (teal, at/above peer)
 *   delta < 0   → `▼` in `var(--z-below)` (#C25008 orange, below peer)
 *
 * Freshness convention — MUST match `backend/app/services/evidence_staleness.py`
 * AND `backend/alembic/versions/018_intelligence_layer.py`. The
 * 4-band ladder (current/aging/dated/stale) + undated sentinel is
 * the SQL trigger's contract; the earlier 3-band Python helper
 * (>12 stale / >6 aging / else current) silently disagreed with the
 * DB-side `freshness_band` STORED column, so the chip on a row
 * could disagree with the bundle %.
 *
 * Canonical bands (months since published OR captured):
 *   age <= 12      → current  (tone "ok",    green)
 *   12 < age <= 24 → aging    (tone "warn",  amber)
 *   24 < age <= 36 → dated    (tone "below", orange)
 *   age > 36       → stale    (tone "below", red — the 3y mandate)
 *   no date        → undated  (tone "muted", grey)
 */

export type MaturityLabel = "Activating" | "Building" | "Competing" | "Differentiating" | "Unset";
export type MaturityClass = "b-act" | "b-bld" | "b-cmp" | "b-dif" | "muted";

export interface MaturityVisual {
  hex: string;
  label: MaturityLabel;
  cls: MaturityClass;
}

const HEX_ACT = "#FFCB99";  // --m-act
const HEX_BLD = "#62D7B8";  // --m-bld
const HEX_CMP = "#27BBAF";  // --m-cmp
const HEX_DIF = "#139F94";  // --m-dif
const HEX_UNSET = "#E5E7EB"; // --z-sep

export function maturityHex(score: number | null | undefined): string {
  if (score == null) return HEX_UNSET;
  if (score < 2) return HEX_ACT;
  if (score < 3) return HEX_BLD;
  if (score < 4) return HEX_CMP;
  return HEX_DIF;
}

export function maturityLabel(score: number | null | undefined): MaturityLabel {
  if (score == null) return "Unset";
  if (score < 2) return "Activating";
  if (score < 3) return "Building";
  if (score < 4) return "Competing";
  return "Differentiating";
}

export function maturityClass(score: number | null | undefined): MaturityClass {
  if (score == null) return "muted";
  if (score < 2) return "b-act";
  if (score < 3) return "b-bld";
  if (score < 4) return "b-cmp";
  return "b-dif";
}

export function maturityVisual(score: number | null | undefined): MaturityVisual {
  return {
    hex: maturityHex(score),
    label: maturityLabel(score),
    cls: maturityClass(score),
  };
}

/** Encode a peer-delta arrow per the prototype's overview convention. */
export interface PeerDelta {
  glyph: "▲" | "▼" | "·";
  color: string;       // CSS var token, not hex (so theme switches work)
  magnitude: number;   // |entity - peer|
  direction: "above" | "below" | "equal";
}

export function peerDeltaArrow(
  entityScore: number | null | undefined,
  peerMedian: number | null | undefined,
): PeerDelta | null {
  if (entityScore == null || peerMedian == null) return null;
  const delta = entityScore - peerMedian;
  if (Math.abs(delta) < 0.05) {
    return { glyph: "·", color: "var(--z-muted)", magnitude: 0, direction: "equal" };
  }
  if (delta >= 0) {
    return {
      glyph: "▲",
      color: "var(--z-mid)",
      magnitude: Math.abs(delta),
      direction: "above",
    };
  }
  return {
    glyph: "▼",
    color: "var(--z-below)",
    magnitude: Math.abs(delta),
    direction: "below",
  };
}

/** Freshness encoding for "last refreshed" chips. MUST match the SQL
 * trigger `compute_evidence_freshness_band` (migration 018) and the
 * Python helper `evidence_staleness.compute_band` byte-for-byte —
 * a row's per-chip color must equal the bundle %'s rollup color.
 */
export type FreshnessTone = "ok" | "warn" | "below" | "muted";
export type FreshnessLabel = "Current" | "Aging" | "Dated" | "Stale" | "Undated";
export type FreshnessBand = "current" | "aging" | "dated" | "stale" | "undated";

export interface Freshness {
  tone: FreshnessTone;
  label: FreshnessLabel;
  band: FreshnessBand;
  months: number | null;
}

export function freshnessOf(at: string | Date | null | undefined): Freshness | null {
  if (!at) {
    // Caller passed nothing — distinguish "no signal" from "undated"
    // by returning null. Use `freshnessOfBand` below when the SQL
    // trigger already produced a band.
    return null;
  }
  const d = typeof at === "string" ? new Date(at) : at;
  if (Number.isNaN(d.getTime())) return null;
  const months = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 30.4);
  const m = Math.round(months);
  if (months <= 12) return { tone: "ok",    label: "Current", band: "current", months: m };
  if (months <= 24) return { tone: "warn",  label: "Aging",   band: "aging",   months: m };
  if (months <= 36) return { tone: "below", label: "Dated",   band: "dated",   months: m };
  return { tone: "below", label: "Stale", band: "stale", months: m };
}

/** When the backend already produced a band (via SQL trigger or
 * `compute_band`), translate it directly to UI shape — no client-side
 * arithmetic, no drift. */
export function freshnessOfBand(band: FreshnessBand | string | null | undefined): Freshness | null {
  switch (band) {
    case "current": return { tone: "ok",    label: "Current", band: "current", months: null };
    case "aging":   return { tone: "warn",  label: "Aging",   band: "aging",   months: null };
    case "dated":   return { tone: "below", label: "Dated",   band: "dated",   months: null };
    case "stale":   return { tone: "below", label: "Stale",   band: "stale",   months: null };
    case "undated": return { tone: "muted", label: "Undated", band: "undated", months: null };
    default: return null;
  }
}
