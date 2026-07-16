/**
 * Evidence tier helpers — surfaced in the EvidenceDrawer tier filter,
 * tier chips and excerpt callouts.
 *
 * Mirrors the wireframe's EVIDENCE_TIERS table (01_data.js) verbatim:
 * T1 = primary disclosure (10-K / regulator filing) down to T8 =
 * social / hypothesis. Real ingested corpora use T1..T4; the DB check
 * constraint allows 1..8 (synthetic proxy tiers like T7-PROXY land as
 * 7), so the full table is kept and the drawer only offers the tiers
 * actually present in the fetched rows.
 */
export interface TierDef {
  label: string;
  /** Accent (text/border) color token — the wireframe's `color`. */
  color: string;
  /** Callout background token — the wireframe's `bg`. */
  bg: string;
}

export const EVIDENCE_TIERS: Record<number, TierDef> = {
  1: { label: "Primary disclosure", color: "var(--z-mid)", bg: "var(--z-ice)" },
  2: { label: "Earnings & investor", color: "var(--m-cmp)", bg: "var(--z-ice)" },
  3: { label: "Trade press · analyst", color: "var(--ph1)", bg: "var(--ph1-lt)" },
  4: { label: "Marketing claim", color: "var(--z-org)", bg: "rgba(254,151,50,.14)" },
  5: { label: "Analyst inference", color: "var(--z-dpur)", bg: "var(--ph0-lt)" },
  6: { label: "Sentiment / review", color: "var(--z-purple)", bg: "var(--z-lav)" },
  7: { label: "Job posting · proxy", color: "var(--z-blue)", bg: "var(--ph1-lt)" },
  8: { label: "Social / hypothesis", color: "var(--z-muted)", bg: "var(--z-lav)" },
};

export const TIER_LABELS: Record<number, string> = Object.fromEntries(
  Object.entries(EVIDENCE_TIERS).map(([t, d]) => [Number(t), d.label]),
);

export function tierLabel(tier: number): string {
  return EVIDENCE_TIERS[tier]?.label ?? `Tier ${tier}`;
}

/** Accent color for a tier (chip text / excerpt border). */
export function tierColor(tier: number): string {
  return EVIDENCE_TIERS[tier]?.color ?? "var(--z-muted)";
}

/** Callout background for a tier (excerpt quote block). */
export function tierBg(tier: number): string {
  return EVIDENCE_TIERS[tier]?.bg ?? "var(--z-bg)";
}
