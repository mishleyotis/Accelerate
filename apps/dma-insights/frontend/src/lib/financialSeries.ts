/**
 * Client-side financial year-series miner — the D5 Context chart fallback.
 *
 * The Context "Financial trajectory" card charts the backend's
 * `financials.series_labeled` (context_extras.financials_view). For many
 * live entities that field ships EMPTY while the same payload still
 * carries the multi-year series as text — `metrics` values / `lines`
 * prose like "grew from $2.286B in 2021 to $3.209B in 2025" — so
 * production rendered the KV-grid/lines fallback (text tiles) where the
 * wireframe shows the FinChartInteractive bar chart (2026-07-06
 * screenshots). This module mines those year→$ pairs with the same
 * two-orientation regexes as the backend miner
 * (app/services/overview_cards.financial_trajectory_card::_pairs) so the
 * chart renders whenever ANY series is derivable — never fabricated:
 * every point is a (year, value) pair present verbatim in the payload.
 *
 * Backend gap (reported, not hacked around): when this fallback fires,
 * /entities/{id}/context should have shipped `financials.series_labeled`
 * for the same prose — the server-side miner missed it.
 */

/** Matches ContextPage's LabeledSeries (Part 8.4 shape) structurally. */
export interface MinedSeries {
  metric: string;
  unit: string;
  fy: number[];
  values: number[];
}

interface FinancialsViewLike {
  years?: number[];
  series?: Record<string, number[]>;
  metrics?: Record<string, unknown>;
  lines?: string[];
}

/** "$2.286B" / "$592 M" / "$34,200k" → absolute dollars. */
function moneyToUsd(raw: string): number | null {
  const m = raw.match(/\$\s*([\d,]+(?:\.\d+)?)\s*([BbMmKk])/);
  if (!m) return null;
  const v = Number(m[1].replace(/,/g, ""));
  if (!Number.isFinite(v)) return null;
  const mult = { b: 1e9, m: 1e6, k: 1e3 }[m[2].toLowerCase() as "b" | "m" | "k"];
  return v * mult;
}

// Mirrors the backend's two orientations:
//   year→value  "2023 $34.2B" · "in 2021 to $3.2B"
//   value→year  "$592M in 2023" · "$153.7M (FY2022)"
const YEAR_VALUE_RE =
  /\b((?:19|20)\d{2})\b[^\d$]{0,14}?(\$\s*[\d,]+(?:\.\d+)?\s*[BbMmKk])\b/g;
const VALUE_YEAR_RE =
  /(\$\s*[\d,]+(?:\.\d+)?\s*[BbMmKk])\s*(?:(?:in|of|as of|by|during|for|through)\s+(?:\w+\s+)?((?:19|20)\d{2})|\(\s*(?:FY\s*)?((?:19|20)\d{2})[^)]*\))/gi;

/** Mirror of backend derive_financials._plausible_series (50x): a real balance
 *  sheet never moves 50x between years of one series, so a point that far from
 *  the median is a wrong-column / unit grab, not data. With exactly 2 disagreeing
 *  points there's no majority to vote, so the whole series drops rather than
 *  charting a fabricated cliff — this keeps the $0.48B-in-a-$30B-series outlier
 *  off Context. Backend guards always win; this only fires on the LAST-RESORT
 *  client mine (when the server shipped no series_labeled), never overriding
 *  backend values. */
const MAX_JUMP = 50;
function plausibleSeries(bucket: Map<number, number>): Map<number, number> {
  if (bucket.size < 2) return bucket;
  const vals = [...bucket.values()].filter((v) => v > 0).sort((a, b) => a - b);
  if (vals.length !== bucket.size) return bucket; // non-positive → stay conservative
  if (bucket.size === 2) {
    const [lo, hi] = vals;
    return hi / lo > MAX_JUMP ? new Map() : bucket;
  }
  const med = vals[Math.floor(vals.length / 2)];
  const out = new Map<number, number>();
  for (const [y, v] of bucket) {
    if (med / MAX_JUMP <= v && v <= med * MAX_JUMP) out.set(y, v);
  }
  return out;
}

const METRIC_KEYS: Array<[RegExp, string]> = [
  [/total\s+assets?|balance\s+sheet/i, "total_assets"],
  [/net\s+income|profit|earnings/i, "net_income"],
  [/revenue|sales|turnover/i, "revenue"],
  [/deposits?/i, "deposits"],
  [/loans?/i, "loans"],
  [/aum|assets\s+under\s+management/i, "aum"],
];

function metricFor(text: string): string {
  for (const [re, key] of METRIC_KEYS) {
    if (re.test(text)) return key;
  }
  return "value";
}

/** All (year, usd) pairs in one text segment, both orientations.
 *  value→year pairs come FIRST: their connective ("$2.3B in 2021") is
 *  explicit, so under first-wins dedup they beat the proximity-based
 *  year→value matches (in "from $2.3B in 2021 to $3.2B in 2025" the
 *  proximity scan would otherwise pair 2021 with the NEXT value). */
export function extractYearMoneyPairs(text: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (const m of text.matchAll(VALUE_YEAR_RE)) {
    const y = Number(m[2] ?? m[3]);
    const v = moneyToUsd(m[1]);
    if (v !== null && y >= 1990 && y <= 2035) out.push([y, v]);
  }
  for (const m of text.matchAll(YEAR_VALUE_RE)) {
    const y = Number(m[1]);
    const v = moneyToUsd(m[2]);
    if (v !== null && y >= 1990 && y <= 2035) out.push([y, v]);
  }
  return out;
}

/**
 * Mine `[{metric, unit, fy[], values[]}]` out of a financials view whose
 * structured series is missing. Sources scanned:
 *   1. `metrics` entries — the key labels the metric, a string value may
 *      carry the prose series ("grew from $2.29B in 2021 to $3.21B in 2025");
 *   2. `lines` prose fragments.
 * A series charts only with ≥2 DISTINCT years (first value wins per
 * year); values are scaled to the dominant magnitude (usd_b/usd_m/usd_k)
 * so fmtFinUnit renders compact labels. Series ordered most-points-first
 * (total_assets wins ties — the wireframe's primary axis).
 */
export function mineFinancialSeries(fin: FinancialsViewLike | null): MinedSeries[] {
  if (!fin) return [];
  const perMetric = new Map<string, Map<number, number>>();

  const harvest = (label: string, text: string): void => {
    const pairs = extractYearMoneyPairs(text);
    if (pairs.length === 0) return;
    const metric = metricFor(`${label} ${text}`);
    const bucket = perMetric.get(metric) ?? new Map<number, number>();
    for (const [y, v] of pairs) {
      if (!bucket.has(y)) bucket.set(y, v);
    }
    perMetric.set(metric, bucket);
  };

  for (const [k, v] of Object.entries(fin.metrics ?? {})) {
    if (typeof v === "string") harvest(k.replace(/_/g, " "), v);
  }
  for (const line of fin.lines ?? []) {
    if (typeof line === "string") harvest("", line);
  }

  const out: MinedSeries[] = [];
  for (const [metric, rawBucket] of perMetric) {
    const bucket = plausibleSeries(rawBucket);  // guard the last-resort mine
    if (bucket.size < 2) continue;
    const fy = [...bucket.keys()].sort((a, b) => a - b);
    const usd = fy.map((y) => bucket.get(y) as number);
    const max = Math.max(...usd.map(Math.abs));
    const [unit, div] =
      max >= 1e9 ? (["usd_b", 1e9] as const)
      : max >= 1e6 ? (["usd_m", 1e6] as const)
      : (["usd_k", 1e3] as const);
    out.push({
      metric,
      unit,
      fy,
      values: usd.map((v) => Math.round((v / div) * 100) / 100),
    });
  }
  return out.sort((a, b) =>
    b.fy.length - a.fy.length
    || Number(b.metric === "total_assets") - Number(a.metric === "total_assets"),
  );
}
