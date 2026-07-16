/**
 * Evidence freshness helpers — mirror of the SQL GENERATED column /
 * Python evidence_staleness service.
 *
 * The 3-year staleness window for the current commit starts at
 * 2026-05-23 minus 3y = 2023-05-23 (the user mandate).
 */
import type { FreshnessBand } from "./queries";

export interface FreshnessBadgeStyle {
  label: string;
  className: string;
  tooltip: string;
}

const BADGE_STYLES: Record<FreshnessBand, FreshnessBadgeStyle> = {
  current: {
    label: "current",
    className: "freshness-badge freshness-current",
    tooltip: "Published within the last 12 months",
  },
  aging: {
    label: "aging",
    className: "freshness-badge freshness-aging",
    tooltip: "Published 12-24 months ago",
  },
  dated: {
    label: "dated",
    className: "freshness-badge freshness-dated",
    tooltip: "Published 24-36 months ago",
  },
  stale: {
    label: "⚠ >3y",
    className: "freshness-badge freshness-stale",
    tooltip: "Published more than 3 years ago — read with caution",
  },
  undated: {
    label: "undated",
    className: "freshness-badge freshness-undated",
    tooltip: "No publication date recorded",
  },
};

const MS_PER_MONTH = (1000 * 60 * 60 * 24 * 365.25) / 12;

export function computeBand(
  publishedDate: string | null,
  recencyMonths: number | null,
  today: Date = new Date(),
): FreshnessBand {
  if (!publishedDate && recencyMonths == null) return "undated";
  let ageMonths: number | null = null;
  if (publishedDate) {
    const p = new Date(publishedDate);
    if (!isNaN(p.valueOf())) {
      ageMonths = (today.valueOf() - p.valueOf()) / MS_PER_MONTH;
    }
  }
  if (ageMonths == null && recencyMonths != null) {
    ageMonths = recencyMonths;
  }
  if (ageMonths == null) return "undated";
  if (ageMonths <= 12) return "current";
  if (ageMonths <= 24) return "aging";
  if (ageMonths <= 36) return "dated";
  return "stale";
}

export function getBadgeStyle(band: FreshnessBand): FreshnessBadgeStyle {
  return BADGE_STYLES[band] ?? BADGE_STYLES.undated;
}
