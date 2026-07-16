/**
 * FinancialTrajectoryCard — D1 "Evidence & benchmarks" (proto df85cc41).
 * Renders the normalized `firmographics.financial_highlights.trajectory`
 * (derive_financials): labeled multi-year assets series with unit, trend
 * headline, fy events, and the footer facts (regulator/geography/branches).
 */
import { Icon } from "@/components/utils";

export interface TrajectoryData {
  currency?: string;
  unit?: string;
  fy?: string[];
  /**
   * Metric-keyed series. Banks/CUs chart `total_assets`; insurance brokers /
   * asset managers chart `revenue` / `premium` / `aum`; some clients chart
   * `loans`. The card picks the first non-null series generically so any
   * line-of-business renders (audit bug 6) — the index signature admits the
   * LOB keys without breaking the two documented ones.
   */
  series?: ({
    total_assets?: Array<number | null> | null;
    net_income_m?: Array<number | null> | null;
  } & Record<string, Array<number | null> | null | undefined>) | null;
  branches?: number | null;
  regulator?: string | null;
  geography?: string | null;
  employees?: number | null;
  headline?: string | null;
  cagr?: string | null;
  trend?: string | null;
  /** latest-year headline metrics when no >=2yr series is derivable */
  highlights?: Array<{ label: string; value: number; unit?: string | null; year?: number | null }>;
  /** agency credit ratings, shown in the highlights variant ({Fitch: "BBB (Stable)"}) */
  ratings?: Record<string, string> | null;
  events?: Array<{ fy: string; label: string }>;
}

// Chartable series keys in render priority + their axis label / unit. Percent
// ratios (nim_pct, credit_quality_pct, …) are deliberately absent — they are
// not bar-chartable and surface only as highlight tiles.
const SERIES_META: Array<{ key: string; label: string; unit: "B" | "M" }> = [
  { key: "total_assets", label: "assets", unit: "B" },
  { key: "revenue", label: "revenue", unit: "B" },
  { key: "premium", label: "premium placed", unit: "B" },
  { key: "premium_placed", label: "premium placed", unit: "B" },
  { key: "aum", label: "AUM", unit: "B" },
  { key: "loans", label: "loans", unit: "B" },
  { key: "deposits", label: "deposits", unit: "B" },
  { key: "net_income_m", label: "net income", unit: "M" },
];

function pickPrimarySeries(
  series: TrajectoryData["series"],
  unit: string | undefined,
): { bars: Array<number | null>; barUnit: string; barLabel: string } | null {
  if (!series) return null;
  for (const meta of SERIES_META) {
    const arr = series[meta.key];
    if (Array.isArray(arr) && arr.some((v) => v != null)) {
      return {
        bars: arr,
        barUnit: meta.key === "total_assets" ? (unit ?? "B") : meta.unit,
        barLabel: meta.label,
      };
    }
  }
  return null;
}

function FooterFacts({ data }: { data: TrajectoryData }): JSX.Element {
  return (
    <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
      {data.regulator ? <span className="chip">{data.regulator}</span> : null}
      {data.geography ? <span>{data.geography}</span> : null}
      <span className="spacer" />
      <span>
        {[data.branches ? `${data.branches} branches` : null,
          data.employees ? `${data.employees.toLocaleString()} FTE` : null]
          .filter(Boolean).join(" · ")}
      </span>
    </div>
  );
}

export function FinancialTrajectoryCard({ data }: { data: TrajectoryData | null }): JSX.Element {
  const fy = data?.fy ?? [];
  const primary = pickPrimarySeries(data?.series, data?.unit);
  const bars = primary?.bars ?? null;
  const barUnit = primary?.barUnit ?? "B";
  const barLabel = primary?.barLabel ?? "";
  const ni = data?.series?.net_income_m ?? null;
  const hasChart = !!(data && fy.length >= 2 && bars);
  const highlights = data?.highlights ?? [];
  const ratings = data?.ratings ?? null;
  const ratingRows = ratings ? Object.entries(ratings) : [];
  const hlEvents = data?.events ?? [];
  const hasHighlights = !!(highlights.length || data?.cagr || ratingRows.length);
  // Highlights variant — real financial DEPTH (CAGR / latest-year metrics /
  // agency ratings) exists but no >=2yr chart series does. Beats the empty
  // state (audit bug 1: Capital Farm loans/patronage/credit-quality/ratings).
  if (data && !hasChart && hasHighlights) {
    return (
      <div className="card flush" data-source="financial_highlights.summary">
        <div className="card-head">
          <div className="row"><Icon name="money" size={14} /><h3>Financial highlights</h3></div>
          {data.cagr ? <span className="chip" title="Compound annual growth rate">{data.cagr} CAGR</span> : null}
        </div>
        <div className="card-body">
          {data.trend ? (
            <div style={{ fontSize: 11.5, color: "var(--z-body)", marginBottom: 8 }}>
              Trend: <strong>{data.trend.toLowerCase()}</strong>
            </div>
          ) : null}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {highlights.map((h, i) => (
              <div key={i} style={{ flex: "1 1 40%", minWidth: 110, padding: "8px 10px",
                background: "var(--z-surface-2, rgba(0,0,0,0.03))", borderRadius: 8 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--z-dark)" }}>
                  {h.unit === "%" ? `${h.value}%` : h.unit ? `$${h.value}${h.unit}` : h.value.toLocaleString()}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                  {h.label}{h.year ? ` · ${h.year}` : ""}
                </div>
              </div>
            ))}
          </div>
          {ratingRows.length > 0 ? (
            <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap" }}>
              {ratingRows.map(([agency, grade]) => (
                <span key={agency} className="chip" title={`${agency} credit rating`}
                      style={{ fontSize: 11 }}>{agency}: {grade}</span>
              ))}
            </div>
          ) : null}
          {hlEvents.length > 0 ? (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
              {hlEvents.slice(0, 3).map((e, i) => (
                <div key={i} style={{ fontSize: 10.5, color: "var(--z-body)" }}>
                  <span className="f-mono" style={{ color: "var(--z-muted)" }}>{e.fy}</span> · {e.label}
                </div>
              ))}
            </div>
          ) : null}
          {data.headline ? (
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--z-muted)" }}>{data.headline}</div>
          ) : null}
          <FooterFacts data={data} />
        </div>
      </div>
    );
  }
  if (!hasChart) {
    return (
      <div className="card flush" data-source="api-empty">
        <div className="card-head"><h3>Financial trajectory</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }}>
          No multi-year series is derivable from this client&apos;s public filings yet.
        </div>
      </div>
    );
  }
  const max = Math.max(...bars.map((v) => v ?? 0), 0.001);
  const events = data.events ?? [];
  return (
    <div className="card flush" data-source="financial_highlights.trajectory">
      <div className="card-head">
        <div className="row"><Icon name="money" size={14} /><h3>Financial trajectory</h3></div>
        {data.headline ? (
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{data.headline}</span>
        ) : null}
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120 }}>
          {fy.map((y, i) => {
            const v = bars[i];
            const niV = ni?.[i];
            return (
              <div key={y} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}
                   title={`${y} · ${v != null ? `$${v}${barUnit} ${barLabel}` : "no data"}${niV != null && bars !== ni ? ` · NI $${niV}M` : ""}`}>
                <div style={{ fontSize: 10.5, fontWeight: 600, color: v != null ? "var(--z-dark)" : "var(--z-muted)" }}>
                  {v != null ? `$${v}${barUnit}` : "—"}
                </div>
                <div style={{
                  width: "100%", height: `${((v ?? 0) / max) * 80}px`, minHeight: v != null ? 3 : 0,
                  background: "linear-gradient(180deg, var(--z-teal), var(--z-mid))",
                  borderRadius: "4px 4px 0 0",
                }} />
                <div className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{y.replace("FY", "'")}</div>
              </div>
            );
          })}
        </div>
        {events.length > 0 ? (
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
            {events.slice(0, 3).map((e, i) => (
              <div key={i} style={{ fontSize: 10.5, color: "var(--z-body)" }}>
                <span className="f-mono" style={{ color: "var(--z-muted)" }}>{e.fy}</span> · {e.label}
              </div>
            ))}
          </div>
        ) : null}
        <div className="row" style={{ marginTop: 10, gap: 6, flexWrap: "wrap", fontSize: 11, color: "var(--z-muted)" }}>
          {data.regulator ? <span className="chip">{data.regulator}</span> : null}
          {data.geography ? <span>{data.geography}</span> : null}
          <span className="spacer" />
          <span>
            {[data.branches ? `${data.branches} branches` : null,
              data.employees ? `${data.employees.toLocaleString()} FTE` : null]
              .filter(Boolean).join(" · ")}
          </span>
        </div>
      </div>
    </div>
  );
}
