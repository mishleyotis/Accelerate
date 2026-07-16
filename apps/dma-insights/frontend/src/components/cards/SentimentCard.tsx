/**
 * SentimentCard — D1 "Evidence & benchmarks" (proto df85cc41).
 * Renders the normalized `firmographics.sentiment` scorecard
 * (derive_sentiment): per-source score/scale/n rows split employee vs
 * customer, NPS index rows (their own -100..+100 metric kind), score-less
 * qualitative rows (polarity + signal + themes), below-peer flags, B2B/B2C
 * gap badge. INTERNAL-ONLY (hidden for customer view; the server additionally
 * strips the nested field).
 *
 * 2026-07-06 depth fix (operator: "Sentiment card on the overview is mostly
 * blank. No enrichment on this?"): the card previously gated on
 * employee/customer SCORED rows only and dropped the empty state on 24 of 94
 * clients whose signal is NPS- or qualitative-only — and never rendered the
 * `nps[]` / `qualitative[]` / per-source `themes[]` the derive already
 * produces. It now renders every cohort and only shows the honest-empty state
 * when NO sentiment of any kind exists.
 */
import { Icon } from "@/components/utils";

export interface SentimentRow {
  source: string;
  metric?: string;
  score: number;
  scale?: number;
  n?: number;
  flag?: string;
  themes?: string[] | null;
}

/** NPS is its own metric kind — a signed -100..+100 index, never a /scale bar. */
export interface NpsRow {
  source: string;
  metric?: string;
  value: number;
  cohort?: string;
  benchmark?: number | null;
  n?: number;
  flag?: string;
}

/** A source that carries signal/themes but no parsable number — a polarity
 *  row instead of a scored bar (so the source is not silently dropped). */
export interface QualRow {
  source: string;
  metric?: string;
  cohort?: string;
  signal?: string | null;
  trend?: string | null;
  polarity?: string | null;
  themes?: string[] | null;
}

export interface SentimentData {
  employee?: SentimentRow[] | null;
  customer?: SentimentRow[] | null;
  nps?: NpsRow[] | null;
  qualitative?: QualRow[] | null;
  industry_avg?: number;
  b2b_b2c_gap?: boolean;
  sources?: Array<Record<string, unknown>>;
}

const POLARITY_TONE: Record<string, string> = {
  positive: "var(--z-teal)",
  negative: "var(--z-below)",
  neutral: "var(--z-muted)",
};

function Themes({ themes }: { themes?: string[] | null }): JSX.Element | null {
  if (!themes || themes.length === 0) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 3 }}>
      {themes.slice(0, 4).map((t) => (
        <span key={t} className="chip" style={{ fontSize: 9.5 }}>{t}</span>
      ))}
    </div>
  );
}

function Row({ r }: { r: SentimentRow }): JSX.Element {
  const scale = r.scale || 5;
  const pct = Math.min(100, (r.score / scale) * 100);
  const five = (r.score * 5) / scale;
  const tone = five >= 4 ? "var(--z-teal)" : five >= 3 ? "var(--z-org)" : "var(--z-below)";
  return (
    <div style={{ padding: "5px 0" }}>
      <div style={{ display: "grid", gridTemplateColumns: "150px 1fr 52px", gap: 8, alignItems: "center" }}>
        <div style={{ fontSize: 11, color: "var(--z-body)" }} className="txt-fit-1" title={`${r.source} · ${r.metric ?? "Overall"}${r.n ? ` · n=${r.n.toLocaleString()}` : ""}`}>
          {r.source}
          <span style={{ color: "var(--z-muted)" }}> · {r.metric ?? "Overall"}</span>
          {r.flag === "below_peer" ? <span className="b b-below" style={{ marginLeft: 4 }}>BELOW PEER</span> : null}
        </div>
        <div style={{ height: 7, background: "var(--z-sep)", borderRadius: 4, overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: tone, borderRadius: 4 }} />
        </div>
        <div style={{ fontSize: 12, fontWeight: 600, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
          {r.score.toFixed(1)}<span style={{ color: "var(--z-muted)", fontWeight: 400, fontSize: 10 }}>/{scale}</span>
        </div>
      </div>
      <Themes themes={r.themes} />
    </div>
  );
}

function NpsRowEl({ r }: { r: NpsRow }): JSX.Element {
  const below = r.flag === "below_peer";
  const tone = below ? "var(--z-below)" : r.value >= 0 ? "var(--z-teal)" : "var(--z-below)";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "150px 1fr auto", gap: 8, alignItems: "center", padding: "5px 0" }}>
      <div style={{ fontSize: 11, color: "var(--z-body)" }} className="txt-fit-1" title={`${r.source} · ${r.metric ?? "NPS"}${r.n ? ` · n=${r.n.toLocaleString()}` : ""}`}>
        {r.source}
        <span style={{ color: "var(--z-muted)" }}> · {r.metric ?? "NPS"}</span>
        {below ? <span className="b b-below" style={{ marginLeft: 4 }}>BELOW PEER</span> : null}
      </div>
      <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
        {r.benchmark != null ? `FSI norm ${r.benchmark > 0 ? "+" : ""}${r.benchmark}` : "index"}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {r.value > 0 ? "+" : ""}{r.value}
      </div>
    </div>
  );
}

function QualRowEl({ r }: { r: QualRow }): JSX.Element {
  const tone = POLARITY_TONE[(r.polarity ?? "neutral").toLowerCase()] ?? "var(--z-muted)";
  return (
    <div style={{ padding: "5px 0" }}>
      <div className="row" style={{ gap: 6, alignItems: "center" }}>
        <span style={{ width: 7, height: 7, borderRadius: 4, background: tone, flexShrink: 0 }} />
        <span style={{ fontSize: 11, color: "var(--z-body)", fontWeight: 500 }}>{r.source}</span>
        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>· {(r.polarity ?? "neutral").toUpperCase()}</span>
        {r.trend ? <span className="b b-muted" style={{ fontSize: 9 }}>{r.trend}</span> : null}
      </div>
      {r.signal ? (
        <div className="txt-fit-2" style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2, lineHeight: 1.45 }} title={r.signal}>
          {r.signal}
        </div>
      ) : null}
      <Themes themes={r.themes} />
    </div>
  );
}

function CohortLabel({ children }: { children: string }): JSX.Element {
  return (
    <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", margin: "10px 0 2px" }}>
      {children}
    </div>
  );
}

export function SentimentCard({
  data, audience,
}: {
  data: SentimentData | null;
  audience: string;
}): JSX.Element | null {
  if (audience === "customer") return null;
  const employee = data?.employee ?? [];
  const customer = data?.customer ?? [];
  const nps = data?.nps ?? [];
  const qualitative = data?.qualitative ?? [];
  // Honest-empty ONLY when no signal of any kind exists (score, NPS or
  // qualitative) — not merely when the two SCORED cohorts are missing.
  if (!data || (employee.length === 0 && customer.length === 0
      && nps.length === 0 && qualitative.length === 0)) {
    return (
      <div className="card flush" data-source="api-empty">
        <div className="card-head"><h3>Sentiment</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }}>
          No public review signal (Glassdoor / app stores / BBB) found for this client.
        </div>
      </div>
    );
  }
  const empNps = nps.filter((r) => (r.cohort ?? "").toLowerCase() === "employee");
  const custNps = nps.filter((r) => (r.cohort ?? "").toLowerCase() !== "employee");
  const empQual = qualitative.filter((r) => (r.cohort ?? "").toLowerCase() === "employee");
  const custQual = qualitative.filter((r) => (r.cohort ?? "").toLowerCase() !== "employee");
  const hasEmp = employee.length > 0 || empNps.length > 0 || empQual.length > 0;
  const hasCust = customer.length > 0 || custNps.length > 0 || custQual.length > 0;
  return (
    <div className="card flush" data-source="firmographics.sentiment">
      <div className="card-head">
        <div className="row">
          <Icon name="users" size={14} /><h3>Sentiment</h3>
          {data.b2b_b2c_gap ? <span className="b b-org">B2B/B2C gap</span> : null}
        </div>
        {data.industry_avg != null ? (
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Industry avg {data.industry_avg.toFixed(1)}</span>
        ) : null}
      </div>
      <div className="card-body">
        {hasEmp ? (
          <>
            <CohortLabel>Employee</CohortLabel>
            {employee.map((r, i) => <Row key={`e${i}`} r={r} />)}
            {empNps.map((r, i) => <NpsRowEl key={`en${i}`} r={r} />)}
            {empQual.map((r, i) => <QualRowEl key={`eq${i}`} r={r} />)}
          </>
        ) : null}
        {hasCust ? (
          <>
            <CohortLabel>Customer</CohortLabel>
            {customer.map((r, i) => <Row key={`c${i}`} r={r} />)}
            {custNps.map((r, i) => <NpsRowEl key={`cn${i}`} r={r} />)}
            {custQual.map((r, i) => <QualRowEl key={`cq${i}`} r={r} />)}
          </>
        ) : null}
      </div>
    </div>
  );
}
