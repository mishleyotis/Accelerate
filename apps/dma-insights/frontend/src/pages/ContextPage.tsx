/**
 * D5 Context — AE-level (Part 8.1 access fix: the audit found AEs hitting
 * a dead-end 403 on a visible tab; the backend gate is now `require_ae`
 * and the frontend role gate is deleted). The customer-audience strip is
 * KEPT — Context is internal-only and server-side stripped.
 *
 * 2026-07-02 (plan Part 8): NLP-grade data consumption on the wireframe
 * ClientContext layout (proto 28883abf):
 *
 *   1. Digital evolution timeline — `signal` now comes NATIVE from the
 *      payload (polarity-classified per claim by the backend pipeline;
 *      `signalForKind` retained only as a legacy-row fallback), dots are
 *      precision-aware (`date_precision`: publish_fallback dates render
 *      as "≈ YYYY-MM" and same-date pile-ups get deterministic jitter so
 *      fallback clusters stop reading as real same-day bursts), and the
 *      EventDetail card shows cap-impact chips from `subcap_ids[]` plus
 *      one evidence chip per `evidence_e_ids[]` entry — each passing
 *      `eId` in the drawer payload.
 *   2. Issue register · Gantt — unchanged (bars toggle IssueDetail).
 *   3. 1.4fr/1fr grid — Financial trajectory consumes the LABELED series
 *      (`series_labeled: {metric, unit, fy[], values[]}`; metric picker
 *      when several exist; unit-aware value formatting; hover-year
 *      footer per proto) with honest single-year / metrics-KV fallbacks +
 *      Regulatory standing (license_type / jurisdictions now extracted
 *      server-side; clean-standing callout when the corpus records a
 *      verified regulatory absence and no OPEN regulatory issue exists).
 *   4. g2 — Sentiment overview: expandable tiles per proto :386-402
 *      (kind eyebrow · value/max · n · chevron → drilldown prose +
 *      themes + evidence chip w/ eId) + Acquisition history: structured
 *      frame rows (target/acquirer/amount/status + dates + details).
 *   5. NEW leadership panel (proto renders it; production omitted) —
 *      tenure / NEW-hire / KEY-SEAT / GAP badges from the view-time
 *      enriched `firmographics.leadership` rows.
 *   6. Kept: INTERNAL ONLY badge, real counts, CrossPillarStoriesPanel,
 *      trend callout (now also derivable server-side from real
 *      financials) and the AboutCard (`narrative_md`).
 *
 * State branches:
 *   1. audience='customer'       → hidden ("internal only")
 *   2. isLoading                 → spinner
 *   3. error.status === 403      → server-gate empty state
 *   4. error (other)             → couldn't load
 *   5. data.run_request_id null  → no active run
 *   6. all sections empty        → context still building
 *   7. happy path                → full interactive Context panel
 */
import { useMemo, useState } from "react";
import { humanizeEnum } from "@/lib/labels";
import { ApiError } from "@/lib/api";
import { mineFinancialSeries } from "@/lib/financialSeries";
import { scalarFirmographicEntries } from "@/lib/firmographics";
import { useRoute } from "@/lib/hash-router";
import { maturityClass, maturityHex } from "@/lib/maturity";
import {
  useCrossPillarStories,
  useEntityContext,
  useEntityOverview,
  type AcquisitionOut,
  type FinancialsView,
  type IssueRegisterOut,
  type PeerComparison,
  type TimelineEventOut,
} from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { Icon, EmptyState, Pill, Spinner } from "@/components/utils";

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/context$/);
  return m ? m[1] : null;
}

// ── Signal derivation ─────────────────────────────────────────────────────────
//
// The wireframe filters/colors timeline events by `signal`
// (positive/neutral/negative); the real payload carries `kind`
// (corpus enum: acquisition / leadership / milestone / regulatory).
// Derive deterministically — never fabricated per-event.

type Signal = "positive" | "neutral" | "negative";

const TONE: Record<Signal, string> = {
  positive: "var(--z-mid)",
  negative: "var(--z-below)",
  neutral: "var(--z-purple)",
};

// box-shadow can't alpha-suffix a var(); hex twins of the tokens above.
const TONE_GLOW: Record<Signal, string> = {
  positive: "#139F9440",
  negative: "#C2500840",
  neutral: "#8094C040",
};

const SIGNAL_EXPLAINER: Record<Signal, string> = {
  positive: "Positive signal - increases the maturity ceiling on the affected capability.",
  negative: "Negative signal - caps the maturity score on the affected capability.",
  neutral: "Neutral signal - context for understanding the entity's trajectory, no direct score effect.",
};

export function signalForKind(kind: string | null | undefined): Signal {
  const k = (kind ?? "").trim().toLowerCase();
  if (["acquisition", "funding", "hiring", "expansion", "launch"].includes(k)) return "positive";
  if (["regulatory", "enforcement", "breach", "litigation"].includes(k)) return "negative";
  return "neutral";
}

/**
 * Part 8.2 step 6: the backend now ships a NATIVE polarity-classified
 * `signal` per event (from the claim itself — a positive acquisition and a
 * botched one no longer share a colour). `signalForKind` remains only as
 * the fallback for legacy rows persisted before the re-derivation.
 */
export function eventSignal(ev: TimelineEventOut): Signal {
  const s = (ev.signal ?? "").trim().toLowerCase();
  if (s === "positive" || s === "negative" || s === "neutral") return s;
  return signalForKind(ev.kind);
}

/** Precision-aware date label — publish_fallback dates are approximate. */
export function eventDateLabel(ev: TimelineEventOut): string {
  const p = (ev.date_precision ?? "").toLowerCase();
  if (p === "publish_fallback") return `≈ ${ev.event_date.slice(0, 7)}`;
  if (p === "year") return ev.event_date.slice(0, 4);
  if (p === "quarter") {
    const m = parseInt(ev.event_date.slice(5, 7), 10);
    return `Q${Math.ceil(m / 3)} ${ev.event_date.slice(0, 4)}`;
  }
  if (p === "day") return ev.event_date;
  return ev.event_date.slice(0, 7);
}

function eventYear(ev: TimelineEventOut): number {
  // slice-parse (not Date.getFullYear) so local TZ can't shift Jan-01 dates.
  return parseInt(ev.event_date.slice(0, 4), 10);
}

const truncate = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// ── Range slider (wireframe lines 167-184) ────────────────────────────────────

function RangeSlider({
  min,
  max,
  value,
  onChange,
}: {
  min: number;
  max: number;
  value: [number, number];
  onChange: (next: [number, number]) => void;
}) {
  const [v1, v2] = value;
  const span = Math.max(1, max - min);
  const tickCount = max - min + 1;
  return (
    <div style={{ position: "relative", height: 26, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 4, background: "var(--z-sep)", borderRadius: 2 }} />
      <div style={{ position: "absolute", left: `${((v1 - min) / span) * 100}%`, right: `${100 - ((v2 - min) / span) * 100}%`, height: 4, background: "var(--z-teal)", borderRadius: 2 }} />
      <input
        type="range" min={min} max={max} value={v1} aria-label="Time range start year"
        onChange={(e) => onChange([Math.min(parseInt(e.target.value, 10), v2), v2])}
        style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }}
      />
      <input
        type="range" min={min} max={max} value={v2} aria-label="Time range end year"
        onChange={(e) => onChange([v1, Math.max(parseInt(e.target.value, 10), v1)])}
        style={{ position: "absolute", inset: 0, opacity: 0.001, cursor: "pointer", margin: 0 }}
      />
      {/* Knobs */}
      <div style={{ position: "absolute", left: `calc(${((v1 - min) / span) * 100}% - 8px)`, width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
      <div style={{ position: "absolute", left: `calc(${((v2 - min) / span) * 100}% - 8px)`, width: 16, height: 16, background: "#fff", border: "2px solid var(--z-teal)", borderRadius: 8, top: 5, pointerEvents: "none", boxShadow: "0 1px 3px rgba(0,0,0,.15)" }} />
      {/* Tick marks (min+max only when a long corpus span would overlap) */}
      <div style={{ position: "absolute", bottom: -16, left: 0, right: 0, display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--z-muted)" }}>
        {tickCount <= 20
          ? Array.from({ length: tickCount }).map((_, i) => <span key={i}>{min + i}</span>)
          : [<span key="min">{min}</span>, <span key="max">{max}</span>]}
      </div>
    </div>
  );
}

// ── InteractiveTimeline (horizontal axis, wireframe lines 186-221) ────────────

function InteractiveTimeline({
  events,
  hoverEvent,
  setHoverEvent,
  selectedEvent,
  setSelectedEvent,
}: {
  events: TimelineEventOut[];
  hoverEvent: number | null;
  setHoverEvent: (i: number | null) => void;
  selectedEvent: number | null;
  setSelectedEvent: (i: number | null) => void;
}) {
  if (events.length === 0) {
    return (
      <div className="empty" style={{ padding: 30 }}>
        <div className="icon"><Icon name="calendar" size={20} /></div>
        <h3>No events in range</h3>
        <p>Expand the time range or change the signal filter.</p>
      </div>
    );
  }
  const minT = new Date(events[0].event_date).getTime();
  const maxT = new Date(events[events.length - 1].event_date).getTime();
  const span = Math.max(1, maxT - minT);

  // Part 8.2 precision-aware clustering: events sharing one date (the
  // publish-fallback pile-up class) get a deterministic per-index jitter
  // so 26 dots on one fallback date stop rendering as a single stack.
  const dupIndex = new Map<string, number>();
  const jitterFor = (e: TimelineEventOut): number => {
    const n = dupIndex.get(e.event_date) ?? 0;
    dupIndex.set(e.event_date, n + 1);
    return n === 0 ? 0 : (n % 2 === 1 ? 1 : -1) * Math.ceil(n / 2) * 1.4;
  };
  const jitters = events.map(jitterFor);

  return (
    <div style={{ position: "relative", padding: "20px 8px 10px" }}>
      <div style={{ position: "relative", height: 2, background: "var(--z-sep)", margin: "30px 16px" }}>
        {events.map((e, i) => {
          const pct = Math.min(100, Math.max(0,
            ((new Date(e.event_date).getTime() - minT) / span) * 100 + jitters[i]));
          const active = selectedEvent === i || hoverEvent === i;
          const signal = eventSignal(e);
          const approx = (e.date_precision ?? "") === "publish_fallback";
          return (
            <button
              key={e.id}
              type="button"
              data-testid="timeline-dot"
              data-precision={e.date_precision ?? undefined}
              aria-label={`${eventDateLabel(e)} · ${e.title}`}
              aria-pressed={selectedEvent === i}
              style={{
                position: "absolute",
                left: `${pct}%`,
                top: active ? -10 : -7,
                width: active ? 22 : 16,
                height: active ? 22 : 16,
                borderRadius: 11,
                background: TONE[signal],
                transform: "translateX(-50%)",
                border: "2px solid #fff",
                cursor: "pointer",
                // Fallback-dated dots render softer — the position is the
                // publish date, not a verified event date.
                opacity: approx ? 0.55 : 1,
                boxShadow: active ? `0 0 0 4px ${TONE_GLOW[signal]}` : "var(--sh-sm)",
                transition: "all 160ms var(--ease)",
                padding: 0,
              }}
              onClick={() => setSelectedEvent(i === selectedEvent ? null : i)}
              onMouseEnter={() => setHoverEvent(i)}
              onMouseLeave={() => setHoverEvent(null)}
            />
          );
        })}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${events.length}, 1fr)`, gap: 6, fontSize: 9.5, color: "var(--z-muted)", padding: "0 8px" }}>
        {events.map((e, i) => {
          const active = hoverEvent === i || selectedEvent === i;
          const signal = eventSignal(e);
          return (
            <div key={e.id} style={{ textAlign: "center", lineHeight: 1.4 }}>
              <div className="f-mono" style={{ color: active ? TONE[signal] : "var(--z-muted)" }}>{eventDateLabel(e)}</div>
              <div className="txt-fit-2" style={{ fontSize: 9.5, color: active ? "var(--z-dark)" : "var(--z-muted)", fontWeight: hoverEvent === i ? 600 : 400 }}>{e.title}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── EventDetail (wireframe lines 223-252) ─────────────────────────────────────

export function EventDetail({
  event,
  onClose,
  onOpenEvidence,
}: {
  event: TimelineEventOut;
  onClose: () => void;
  /** Part 8.6 / 11.1: receives the clicked E-ID — the payload carries
   *  `eId` through DrawerHost (which may not consume it until the spine
   *  work lands; passing it is forward-compatible either way). */
  onOpenEvidence: (eId: string) => void;
}) {
  const signal = eventSignal(event);
  const evidenceIds =
    (event.evidence_e_ids?.length ? event.evidence_e_ids : null)
    ?? (event.e_id ? [event.e_id] : []);
  const subcapIds = event.subcap_ids ?? [];
  const approx = (event.date_precision ?? "") === "publish_fallback";
  const hasFooter = Boolean(event.body) || evidenceIds.length > 0 || subcapIds.length > 0;
  return (
    <div data-testid="event-detail" style={{ marginTop: 16, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${TONE[signal]}` }}>
      <div className="row" style={{ marginBottom: 8, flexWrap: "wrap" }}>
        <span className="f-mono" style={{ fontSize: 11, color: "var(--z-muted)" }} title={approx ? "Approximate — dated from the source's publish date" : undefined}>
          {eventDateLabel(event)}
        </span>
        <strong style={{ fontSize: 14, flex: 1, minWidth: 180 }}>
          {event.source_url ? (
            <a href={event.source_url} target="_blank" rel="noopener noreferrer">{event.title}</a>
          ) : event.title}
        </strong>
        {/* Wireframe cap_impact chips — real `subcap_ids[]` when the pipeline
            linked capabilities; the kind chip stays as classification. */}
        {subcapIds.slice(0, 3).map((sid) => (
          <span key={sid} className="chip purple" data-testid="cap-impact-chip">{sid}</span>
        ))}
        <span className="b b-purple">{humanizeEnum(event.kind)}</span>
        <span className="b b-muted">{signal.toUpperCase()}</span>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close event detail">
          <Icon name="x" size={14} />
        </button>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6, marginBottom: hasFooter ? 10 : 0 }}>
        {SIGNAL_EXPLAINER[signal]}
        {approx ? " Date is approximate (source publish date)." : ""}
      </div>
      {event.body ? (
        <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, marginBottom: evidenceIds.length > 0 ? 10 : 0 }}>{event.body}</div>
      ) : null}
      {evidenceIds.length > 0 ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Evidence:</span>
          {evidenceIds.slice(0, 6).map((eid) => (
            <button key={eid} type="button" className="chip" style={{ cursor: "pointer", border: 0 }} onClick={() => onOpenEvidence(eid)}>
              {eid}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ── InteractiveGantt ──────────────────────────────────────────────────────────

// Corpus severities are lowercase critical/high/medium/low; legacy package
// values (MATERIAL/MAJOR/MINOR) keep their prior colors. Uppercased lookup.
const GANTT_SEVERITY_COLOR: Record<string, string> = {
  MATERIAL: "var(--z-below)",
  CRITICAL: "var(--z-below)",
  HIGH: "var(--z-below)",
  MAJOR: "var(--m-bld)",
  MEDIUM: "var(--m-bld)",
  MINOR: "var(--z-teal)",
  LOW: "var(--z-muted)",
};

function severityColor(severity: string): string {
  return GANTT_SEVERITY_COLOR[severity.toUpperCase()] ?? "var(--z-mid)";
}

function severityBadgeClass(severity: string): string {
  const s = severity.toUpperCase();
  if (s === "CRITICAL" || s === "HIGH" || s === "MATERIAL") return "b-below";
  if (s === "MAJOR" || s === "MEDIUM" || s === "MODERATE") return "b-org";
  return "b-muted";
}

function InteractiveGantt({
  issues,
  issueOpen,
  setIssueOpen,
}: {
  issues: IssueRegisterOut[];
  issueOpen: string | null;
  setIssueOpen: (id: string | null) => void;
}) {
  const dates = issues.flatMap((i) => [
    i.opened_on ? new Date(i.opened_on).getTime() : Date.now(),
    i.resolved_on ? new Date(i.resolved_on).getTime() : Date.now(),
  ]);
  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const totalMs = Math.max(maxDate - minDate, 1);
  return (
    <div data-source="api" aria-label="Issue register Gantt">
      {issues.map((issue) => {
        const opened = issue.opened_on ? new Date(issue.opened_on).getTime() : minDate;
        const closed = issue.resolved_on ? new Date(issue.resolved_on).getTime() : Date.now();
        const startPct = ((opened - minDate) / totalMs) * 100;
        const endPct = ((closed - minDate) / totalMs) * 100;
        const widthPct = Math.max(2, endPct - startPct);
        const color = severityColor(issue.severity);
        const open = issueOpen === issue.id;
        return (
          <button
            key={issue.id}
            type="button"
            className="gantt-row"
            data-testid="gantt-row"
            aria-expanded={open}
            onClick={() => setIssueOpen(open ? null : issue.id)}
            style={{ width: "100%", textAlign: "left", cursor: "pointer", border: 0, borderBottom: "1px solid var(--z-sep)", borderRadius: 6, background: open ? "var(--z-lav)" : "transparent" }}
          >
            <div className="gantt-label">
              <code className="chip">{issue.issue_id}</code>
              <Pill tone={issue.status === "RESOLVED" ? "teal" : "amber"}>
                {humanizeEnum(issue.status)}
              </Pill>
              <span className="gantt-title">{issue.title}</span>
            </div>
            <div className="gantt-track">
              <div
                className="gantt-bar"
                style={{
                  left: `${startPct}%`,
                  width: `${widthPct}%`,
                  background: color,
                  opacity: issue.resolved_on ? 0.65 : 1,
                }}
                title={`${issue.opened_on ?? "?"} → ${issue.resolved_on ?? "open"} · ${issue.severity}`}
              />
            </div>
          </button>
        );
      })}
      <div className="gantt-axis">
        <span>{new Date(minDate).toLocaleDateString()}</span>
        <span>{new Date(maxDate).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

// ── IssueDetail (wireframe lines 299-339, mapped to IssueRegisterOut) ─────────

function IssueDetail({
  issue,
  displayId,
  onClose,
}: {
  issue: IssueRegisterOut;
  displayId: string | null;
  onClose: () => void;
}) {
  const hasFooter = Boolean(issue.rationale) || issue.linked_subcap_ids.length > 0;
  return (
    <div data-testid="issue-detail" style={{ marginTop: 14, padding: 14, background: "var(--z-lav)", borderRadius: 8, borderLeft: `4px solid ${severityColor(issue.severity)}` }}>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="chip">{issue.issue_id}</span>
        <span className={`b ${severityBadgeClass(issue.severity)}`}>{issue.severity.toUpperCase()}</span>
        <span className="b b-muted">{issue.status}</span>
        {issue.opened_on ? (
          <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
            {issue.opened_on} → {issue.resolved_on ?? "open"}
          </span>
        ) : null}
        <span className="spacer" />
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close issue detail">
          <Icon name="x" size={14} />
        </button>
      </div>
      <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6, marginBottom: hasFooter ? 10 : 0 }}>{issue.title}</div>
      {issue.dma_impact ? (
        <div data-testid="issue-dma-impact" style={{ fontSize: 12, lineHeight: 1.55, color: "var(--z-dark)", fontWeight: 600, marginBottom: 8 }}>
          <Icon name="lock" size={11} style={{ marginRight: 4, color: "var(--z-org)" }} />
          {issue.dma_impact}
        </div>
      ) : null}
      {issue.rationale ? (
        <div className="muted" style={{ fontSize: 12, lineHeight: 1.55, marginBottom: issue.linked_subcap_ids.length > 0 ? 10 : 0 }}>{issue.rationale}</div>
      ) : null}
      {issue.linked_subcap_ids.length > 0 ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Linked subcaps:</span>
          {issue.linked_subcap_ids.map((s) => {
            const cap = issue.caps?.[s];
            return (
              <span key={s} className="chip purple">
                {s}{cap != null ? ` @ M${cap}` : ""}
              </span>
            );
          })}
          {displayId ? (
            <a className="btn btn-tertiary btn-sm" href={`#/clients/${displayId}/heatmap`}>
              View in heatmap <Icon name="arrow-r" size={11} />
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ── Financial trajectory (B-3 multi-year view → wireframe FinChartInteractive) ─

const TREND_RE = /\b(accelerating|improving|recovering|stable|declining|decelerating)\b/i;

/** First trend classification found in the parsed lines/metrics — never fabricated. */
function deriveTrend(financials: FinancialsView | null): string | null {
  if (!financials) return null;
  const hay = [
    ...(financials.lines ?? []),
    ...Object.entries(financials.metrics ?? {}).map(([k, v]) => `${k} ${String(v)}`),
  ].join(" ");
  const m = TREND_RE.exec(hay);
  return m ? m[1].toUpperCase() : null;
}

function deriveCagr(years: number[], vals: number[]): number | null {
  if (years.length < 2 || vals.length < years.length) return null;
  const first = vals[0];
  const last = vals[years.length - 1];
  const span = years[years.length - 1] - years[0];
  if (!(first > 0) || !(last > 0) || span <= 0) return null;
  return Math.pow(last / first, 1 / span) - 1;
}

/** Labelled per-metric series (Part 8.4) — the backend's explicit shape. */
export type LabeledSeries = {
  metric: string;
  unit: string;
  fy: number[];
  values: number[];
};

/** The normalized, guarded trajectory blob — the SAME object the D1
 *  overview FinancialTrajectoryCard consumes (firmographics.financial_
 *  highlights.trajectory), passed straight through into the Context payload
 *  as `financials.trajectory`. Consuming it here keeps D1 and D5 on ONE
 *  view instead of D5 re-deriving a divergent axis from `series_labeled`
 *  (Zions charted raw `net_income: 824000000` on D5 while D1 showed a
 *  formatted highlight; Guaranteed Rate's guarded/dropped points must agree
 *  across both surfaces — 2026-07-06 deploy review). */
type NormalizedTrajectory = {
  unit?: string | null;
  fy?: Array<string | number> | null;
  series?: {
    total_assets?: Array<number | null> | null;
    net_income_m?: Array<number | null> | null;
  } | null;
  headline?: string | null;
  cagr?: string | null;
  trend?: string | null;
  highlights?: Array<{ label: string; value: number; unit?: string | null; year?: number | null }>;
  events?: Array<{ fy: string; label: string }>;
};

type FinancialsViewLabeled = FinancialsView & {
  series_labeled?: LabeledSeries[];
  trajectory?: NormalizedTrajectory | null;
};

/** Reshape the normalized trajectory into the same LabeledSeries[] the D5
 *  chart already renders — total_assets preferred, net income second (the
 *  exact metric precedence the D1 card uses), each aligned to the non-null
 *  fiscal years so the two surfaces plot identical points. */
export function trajectoryToLabeled(tj: NormalizedTrajectory | null | undefined): LabeledSeries[] {
  if (!tj || !Array.isArray(tj.fy) || !tj.series) return [];
  const fyNums = tj.fy.map((f) => parseInt(String(f).replace(/[^\d]/g, ""), 10));
  const specs: Array<[keyof NonNullable<NormalizedTrajectory["series"]>, string, string]> = [
    ["total_assets", "total_assets", "usd_b"],
    ["net_income_m", "net_income", "usd_m"],
  ];
  const out: LabeledSeries[] = [];
  for (const [key, metric, unit] of specs) {
    const arr = tj.series[key];
    if (!Array.isArray(arr)) continue;
    const fy: number[] = [];
    const values: number[] = [];
    fyNums.forEach((y, i) => {
      const v = arr[i];
      if (typeof v === "number" && Number.isFinite(y)) { fy.push(y); values.push(v); }
    });
    if (values.length >= 1) out.push({ metric, unit, fy, values });
  }
  return out;
}

/** Unit-AWARE compact label; falls back to magnitude heuristics when the
 *  series carries no unit metadata (legacy rows). */
export function fmtFinUnit(v: number, unit?: string): string {
  if (unit === "usd_b") return `$${v.toFixed(1)}B`;
  if (unit === "usd_m") return `$${v.toFixed(1)}M`;
  if (unit === "usd_k") return `$${v.toFixed(1)}K`;
  if (unit === "pct") return `${v.toFixed(1)}%`;
  if (unit === "usd") {
    const a = Math.abs(v);
    if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    return `$${v.toLocaleString()}`;
  }
  const a = Math.abs(v);
  if (a >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

const prettyMetric = (m: string): string =>
  m === "value" ? "Series" : m.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const PCT_METRIC_RE = /(_pct$|ratio|\bnim\b|\broa\b|\broe\b|tier[_ ]?1|margin)/i;

/** Format a scalar firmographic-financial metric so the D5 KV fallback reads
 *  like D1's formatted highlights instead of a raw integer (Zions charted
 *  `net_income: 824000000`; 2026-07-06 parity fix). Percent-style metrics
 *  keep their point value; money-scale numbers compact to $B/$M. */
export function fmtMetricValue(key: string, v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return String(v);
  if (PCT_METRIC_RE.test(key)) return `${v % 1 === 0 ? v : v.toFixed(1)}%`;
  return Math.abs(v) >= 1e6 ? fmtFinUnit(v, "usd") : v.toLocaleString();
}

export function FinancialTrajectoryCard({ financials }: { financials: FinancialsView | null }) {
  const [hoveredYear, setHoveredYear] = useState<number | null>(null);
  const [metricIdx, setMetricIdx] = useState(0);
  const fin = financials as FinancialsViewLabeled | null;

  // Parity (2026-07-06): the guarded, normalized trajectory — D1's EXACT
  // source — wins so both surfaces plot one identical view. The labelled
  // series / legacy axis stay as the fallback for legacy rows that predate
  // the trajectory derive.
  const trajLabeled = trajectoryToLabeled(fin?.trajectory);
  // Part 8.4: prefer the labelled series; legacy {years, series} fallback;
  // finally mine the year→$ pairs the payload carries as TEXT
  // (metrics/lines prose) so the wireframe's FinChartInteractive bar chart
  // renders whenever a series is derivable at all — production fell into
  // the KV-grid text state for entities whose series only shipped as
  // prose (2026-07-06). Points are verbatim payload pairs, never invented.
  const labeledShipped: LabeledSeries[] =
    trajLabeled.length > 0 ? trajLabeled : (fin?.series_labeled ?? []);
  // Highlights-only depth (latest-year metrics + CAGR) — the SAME variant the
  // D1 card renders when no >=2yr chart exists (Zions: net income $824M).
  const trajHighlights = fin?.trajectory?.highlights ?? [];
  const trajCagr = fin?.trajectory?.cagr ?? null;
  const legacySeries =
    (fin?.series && (fin.series.value ?? Object.values(fin.series)[0])) ?? null;
  const mined = useMemo(
    () => (labeledShipped.length === 0 && !(fin?.years && legacySeries)
      ? mineFinancialSeries(fin)
      : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fin],
  );
  const labeled: LabeledSeries[] = labeledShipped.length > 0 ? labeledShipped : mined;
  const seriesSource: "api" | "derived" | "api-empty" =
    labeledShipped.length > 0 || (fin?.years && legacySeries) ? "api"
    : mined.length > 0 ? "derived"
    : "api-empty";
  const active: LabeledSeries | null =
    labeled[Math.min(metricIdx, Math.max(0, labeled.length - 1))]
    ?? (fin?.years && legacySeries
      ? { metric: "value", unit: "unknown", fy: fin.years, values: legacySeries }
      : null);
  const years = active?.fy ?? [];
  const valueSeries = active?.values ?? null;
  const unit = active?.unit;
  const trend = deriveTrend(financials);
  const multiYear = years.length >= 2 && !!valueSeries && valueSeries.length >= years.length;
  const maxVal = valueSeries ? Math.max(...valueSeries.map(Math.abs), 0) : 0;

  const metrics = financials?.metrics
    ? Object.entries(financials.metrics).filter(([, v]) => v != null && v !== "")
    : [];

  return (
    <section className="card" data-source={financials ? seriesSource : "api-empty"} aria-label="Financial trajectory">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="money" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Financial trajectory</div>
        <span className="spacer" />
        {labeled.length > 1 ? (
          <div className="toggle-row" role="group" aria-label="Financial metric picker">
            {labeled.map((s, i) => (
              <button key={s.metric} type="button" className={metricIdx === i ? "on" : ""}
                      onClick={() => { setMetricIdx(i); setHoveredYear(null); }}>
                {prettyMetric(s.metric)}
              </button>
            ))}
          </div>
        ) : null}
        {trend ? (
          <span className={`b ${trend === "DECLINING" || trend === "DECELERATING" || trend === "STABLE" ? "b-muted" : "b-above"}`}>{trend}</span>
        ) : null}
      </div>
      {!financials ? (
        <EmptyState title="No financials on record" body="No financial highlights were parsed for this entity." />
      ) : multiYear && valueSeries ? (
        <div>
          {active && active.metric !== "value" ? (
            <div className="muted" style={{ fontSize: 10.5, marginBottom: 4, textTransform: "uppercase", letterSpacing: ".06em" }}>
              {prettyMetric(active.metric)}{unit && unit !== "unknown" ? ` · ${unit}` : ""}
            </div>
          ) : null}
          <div className="fin-chart" aria-label="Multi-year financial series">
            {years.map((y, i) => {
              const v = valueSeries[i] ?? 0;
              const hovered = hoveredYear === y;
              const h = maxVal > 0 ? Math.max(2, (Math.abs(v) / maxVal) * 110) : 2;
              return (
                <div
                  key={y}
                  className="fin-bar"
                  data-testid="fin-bar"
                  style={{ cursor: "pointer", gap: 4 }}
                  onMouseEnter={() => setHoveredYear(y)}
                  onMouseLeave={() => setHoveredYear(null)}
                >
                  <div style={{ fontSize: 10, color: hovered ? "var(--z-teal)" : "var(--z-muted)", fontWeight: hovered ? 700 : 400 }}>{fmtFinUnit(v, unit)}</div>
                  <div
                    className="fin-bar-fill"
                    data-testid="fin-bar-fill"
                    style={{
                      height: h,
                      background: hovered
                        ? "linear-gradient(180deg, var(--z-mid), var(--z-dark2))"
                        : "linear-gradient(180deg, var(--z-teal), var(--z-mid))",
                      transition: "background 160ms",
                    }}
                    title={`${y}: ${v.toLocaleString()}`}
                  />
                  <div className="fin-bar-label">{y}</div>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 10, padding: 8, background: "var(--z-lav)", borderRadius: 6, fontSize: 11, color: "var(--z-body)" }}>
            {(() => {
              const cagr = deriveCagr(years, valueSeries);
              return cagr != null ? (
                <>Series CAGR <strong style={{ color: "var(--z-mid)" }}>{(cagr * 100).toFixed(1)}%</strong> · {years[0]}–{years[years.length - 1]}</>
              ) : (
                <>{years[0]}–{years[years.length - 1]} series</>
              );
            })()}
            {trend ? <> · trend classified <strong>{trend}</strong></> : null}
            {hoveredYear != null ? (
              <span style={{ marginLeft: 8, color: "var(--z-teal)", fontWeight: 600 }}>
                · {hoveredYear}: {fmtFinUnit(valueSeries[years.indexOf(hoveredYear)] ?? 0, unit)}
              </span>
            ) : null}
          </div>
        </div>
      ) : trajHighlights.length > 0 ? (
        <div>
          {/* Highlights variant — one view with the D1 card: latest-year
              metrics + CAGR when no >=2yr chart is derivable. */}
          {trajCagr ? (
            <div className="muted" style={{ fontSize: 10.5, marginBottom: 8, textTransform: "uppercase", letterSpacing: ".06em" }}>
              {trajCagr} CAGR{trend ? ` · trend ${trend.toLowerCase()}` : ""}
            </div>
          ) : null}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {trajHighlights.map((h, i) => (
              <div key={i} style={{ flex: "1 1 40%", minWidth: 120, padding: "8px 10px", background: "var(--z-lav)", borderRadius: 8 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--z-dark)" }}>
                  {h.unit === "%" ? `${h.value}%` : h.unit ? `$${h.value}${h.unit}` : h.value.toLocaleString()}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                  {h.label}{h.year ? ` · ${h.year}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div>
          {/* Honest non-chart states: a single parsed year, or no year series at all. */}
          {years.length === 1 && valueSeries ? (
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
              Single-year series only — {years[0]}: {fmtFinUnit(valueSeries[0] ?? 0, unit)}. Multi-year trajectory unavailable for this entity.
            </div>
          ) : (
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
              No multi-year financial series parsed for this entity.
            </div>
          )}
          {metrics.length > 0 ? (
            <dl className="kv-grid">
              {metrics.map(([k, v]) => (
                <div className="kv" key={k}>
                  <dt>{k.replace(/_/g, " ")}</dt>
                  <dd>{fmtMetricValue(k, v)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {financials.lines && financials.lines.length > 0 ? (
            <ul className="muted small">
              {financials.lines.slice(0, 6).map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </section>
  );
}

// ── Regulatory standing (wireframe lines 106-126) ─────────────────────────────

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11.5, gap: 8 }}>
      <span style={{ color: "var(--z-muted)" }}>{k}</span>
      <span style={{ color: "var(--z-dark)", fontWeight: 500, textAlign: "right" }}>{v}</span>
    </div>
  );
}

const REGULATOR_KEYS = ["primary_regulator", "regulator"];
const LICENSE_KEYS = ["license_type", "license", "charter_type", "charter"];
const JURISDICTION_KEYS = ["jurisdictions", "jurisdiction", "footprint", "operating_states"];

function firmString(firm: Record<string, unknown> | null, keys: string[]): string | null {
  if (!firm) return null;
  for (const k of keys) {
    const v = firm[k];
    if (typeof v === "string" && v.trim()) return v;
    if (typeof v === "number") return String(v);
    if (Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === "string")) {
      return (v as string[]).join(" · ");
    }
  }
  return null;
}

const REG_ISSUE_RE = /(regulat|complian|enforc|consent|licen[cs]|bsa|aml|cfpb|sanction)/i;

export function RegulatoryStandingCard({
  firmographics,
  issues,
  onOpenIssue,
  onOpenEvidence,
}: {
  firmographics: Record<string, unknown> | null;
  issues: IssueRegisterOut[];
  onOpenIssue: (id: string) => void;
  onOpenEvidence?: (eId: string) => void;
}) {
  const regulator = firmString(firmographics, REGULATOR_KEYS);
  const license = firmString(firmographics, LICENSE_KEYS);
  const jurisdictions = firmString(firmographics, JURISDICTION_KEYS);
  const consumed = new Set([...REGULATOR_KEYS, ...LICENSE_KEYS, ...JURISDICTION_KEYS]);
  const extras = scalarFirmographicEntries(firmographics).filter(([k]) => !consumed.has(k));
  const regIssue =
    issues.find((i) => i.status === "OPEN" && REG_ISSUE_RE.test(`${i.issue_id} ${i.title}`)) ?? null;
  // Part 8.2 step 3: the timeline suppresses "NEGATIVE SEARCH: no formal
  // enforcement…" rows; the backend converts the strongest one into this
  // explicit clean-standing signal (absent whenever an OPEN reg issue exists).
  const standing = ((): { label?: string; note?: string; e_id?: string | null } | null => {
    const raw = firmographics?.["regulatory_standing"];
    return raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as { label?: string; note?: string; e_id?: string | null })
      : null;
  })();

  return (
    <section className="card" data-source={firmographics || regIssue ? "api" : "api-empty"} aria-label="Regulatory standing">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="shield" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Regulatory standing</div>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.65 }}>
        <Row k="Primary regulator" v={regulator ?? "—"} />
        <Row k="License type" v={license ?? "—"} />
        <Row k="Jurisdictions" v={jurisdictions ?? "—"} />
        {extras.map(([k, v]) => (
          <Row key={k} k={humanizeEnum(k).replace(/^\w/, (c) => c.toUpperCase())} v={String(v)} />
        ))}
        <div className="sep" />
        {regIssue ? (
          <button
            type="button"
            className="co co-org"
            data-testid="open-enforcement-callout"
            style={{ cursor: "pointer", width: "100%", textAlign: "left", border: "none", borderLeft: "3px solid var(--z-org)", font: "inherit" }}
            onClick={() => onOpenIssue(regIssue.id)}
          >
            <Icon name="warn" size={14} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="co-title">Open enforcement · {regIssue.issue_id}</div>
              <div className="co-body">{truncate(regIssue.title, 140)} · click to view detail</div>
            </div>
            <Icon name="arrow-r" size={12} />
          </button>
        ) : standing ? (
          <div className="co co-teal" data-testid="clean-standing-callout" style={{ borderLeft: "3px solid var(--z-teal)" }}>
            <Icon name="check" size={14} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="co-title">{standing.label ?? "Clean regulatory standing"}</div>
              <div className="co-body">{standing.note}</div>
              {standing.e_id && onOpenEvidence ? (
                <button type="button" className="chip" style={{ cursor: "pointer", border: 0, marginTop: 6 }}
                        onClick={() => onOpenEvidence(standing.e_id as string)}>
                  {standing.e_id}
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 11.5 }}>
            No open regulatory or compliance issue in the register
            {issues.length > 0 ? ` — ${issues.length} other issue${issues.length === 1 ? "" : "s"} tracked in the Gantt above` : ""}.
          </div>
        )}
      </div>
    </section>
  );
}

// ── Acquisitions (B-4 / Part 8.3) — structured frame rows per proto ──────────

const ACQ_STATUS_LABEL: Record<string, string> = {
  announced: "Announced",
  closed: "Complete",
  integrating: "Integrating",
};

export function AcquisitionsCard({
  acquisitions,
  onOpenEvidence,
}: {
  acquisitions: AcquisitionOut[];
  onOpenEvidence?: (eId: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <section className="card" data-source={acquisitions.length > 0 ? "api" : "api-empty"} aria-label="Acquisition history">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="stack" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Acquisition history</div>
        <span className="spacer" />
        {acquisitions.length > 0 ? <span className="muted" style={{ fontSize: 11 }}>{acquisitions.length}</span> : null}
      </div>
      {acquisitions.length === 0 ? (
        <EmptyState
          title="No acquisitions on record"
          body="Only frame-verified M&A events surface here — strategy intent and peer deals are excluded."
        />
      ) : (
        <ul className="acq-list">
          {acquisitions.map((a) => {
            const open = openId === a.id;
            const statusKey = (a.status ?? "").toLowerCase();
            return (
              <li key={a.id} className={`acq-item ${open ? "open" : ""}`}>
                <button
                  type="button"
                  className="acq-row"
                  data-testid="acq-row"
                  onClick={() => setOpenId(open ? null : a.id)}
                  aria-expanded={open}
                >
                  <span className="acq-date">{a.event_date.slice(0, 7)}</span>
                  <span className="acq-title">{a.target ?? a.title}</span>
                  {a.amount ? <span className="b b-teal">{a.amount}</span> : null}
                  {statusKey && ACQ_STATUS_LABEL[statusKey] ? (
                    <span className="b b-muted">{ACQ_STATUS_LABEL[statusKey]}</span>
                  ) : null}
                  <Icon name={open ? "chevron-u" : "chevron-d"} size={12} style={{ color: "var(--z-muted)" }} />
                </button>
                {open ? (
                  <div className="acq-detail">
                    {(a.acquirer || a.target) ? (
                      <div style={{ fontSize: 11.5, marginBottom: 6 }}>
                        {a.acquirer ? <><span className="muted">Acquirer</span> <strong>{a.acquirer}</strong></> : null}
                        {a.acquirer && a.target ? <span className="muted"> → </span> : null}
                        {a.target ? <><span className="muted">Target</span> <strong>{a.target}</strong></> : null}
                      </div>
                    ) : null}
                    {(a.announced_on || a.closed_on) ? (
                      <div className="muted" style={{ fontSize: 10.5, marginBottom: 6 }}>
                        {a.announced_on ? `Announced ${a.announced_on}` : ""}
                        {a.announced_on && a.closed_on ? " · " : ""}
                        {a.closed_on ? `Closed ${a.closed_on}` : ""}
                      </div>
                    ) : null}
                    {a.details || a.body ? <p>{a.details ?? a.body}</p> : <p className="muted">No additional detail.</p>}
                    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                      {a.e_id ? (
                        <button type="button" className="chip" style={{ cursor: "pointer", border: 0 }}
                                onClick={() => onOpenEvidence?.(a.e_id as string)}>
                          {a.e_id}
                        </button>
                      ) : null}
                      {a.source_url ? (
                        <a href={a.source_url} target="_blank" rel="noopener noreferrer">
                          Source <Icon name="external" size={11} />
                        </a>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ── Leadership (Part 8.6) — proto renders it on Context; production omitted.
// Light local panel (the Overview LeadershipPanel is module-private there):
// tenure / NEW-hire / KEY-SEAT / GAP badges from the view-time enriched
// `firmographics.leadership` rows.

export type ContextLeaderRow = {
  name?: string | null;
  title?: string | null;
  tenure_months?: number | null;
  background?: string | null;
  note?: string | null;
  critical_role?: boolean;
  recent_hire?: boolean;
  gap_flag?: boolean;
};

export function ContextLeadershipPanel({ leadership }: { leadership: ContextLeaderRow[] }) {
  if (leadership.length === 0) return null;
  return (
    <section className="card" data-source="api" aria-label="Leadership panel" data-testid="context-leadership-panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="users" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Leadership</div>
        <span className="spacer" />
        {(() => {
          const gaps = leadership.filter((l) => l.gap_flag).length;
          return gaps > 0 ? (
            <span className="b b-below">{gaps} critical seat{gaps === 1 ? "" : "s"} unconfirmed</span>
          ) : null;
        })()}
      </div>
      <div>
        {leadership.map((ex, i) => (
          <div key={`${ex.name ?? "gap"}-${ex.title ?? i}`} data-testid="context-leader-row"
               style={{ display: "flex", gap: 10, padding: "10px 0", borderBottom: "1px solid var(--z-sep)" }}>
            <div style={{
              width: 32, height: 32, borderRadius: 16, flexShrink: 0,
              background: ex.gap_flag ? "var(--z-sep)" : "linear-gradient(135deg, var(--z-teal), var(--z-mid))",
              color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 600,
            }}>
              {ex.gap_flag ? "?" : (ex.name ?? "").split(" ").map((n) => n[0]).join("").slice(0, 2)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontWeight: 600, fontSize: 12.5, color: "var(--z-dark)" }}>
                  {ex.gap_flag ? "—" : (ex.name ?? "—")}
                </span>
                <span style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>{ex.title ?? ""}</span>
                {ex.gap_flag ? <span className="b b-below">GAP</span>
                : ex.recent_hire ? <span className="b b-org">NEW · {ex.tenure_months ?? 0} mo</span>
                : ex.tenure_months != null ? (
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    · {ex.tenure_months >= 12 ? `${Math.round(ex.tenure_months / 12)} yr` : `${ex.tenure_months} mo`}
                  </span>
                ) : null}
                {ex.critical_role && !ex.gap_flag ? (
                  <span className="b b-purple" title="Security / data / technology leadership seat">KEY SEAT</span>
                ) : null}
              </div>
              {ex.background ? (
                <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 3, lineHeight: 1.5 }}>{ex.background}</div>
              ) : null}
              {ex.note ? (
                <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>{ex.note}</div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Peer comparison — named comparators + overall maturity vs the client ──────

function PeerComparisonCard({
  peers,
  clientOverall,
}: {
  peers: PeerComparison[];
  clientOverall: number | null;
}) {
  const max = 5;
  return (
    <section
      className="card"
      data-source={peers.length > 0 ? "api" : "api-empty"}
      aria-label="Peer comparison"
    >
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="users" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Peer comparison</div>
        <span className="spacer" />
        {peers.length > 0 ? (
          <span className="b b-muted">{peers.length} comparators</span>
        ) : null}
      </div>
      {peers.length === 0 ? (
        <EmptyState
          title="No peer scores on record"
          body="This assessment package shipped no individually-scored comparators."
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {clientOverall != null ? (
            <PeerBar
              label="This client"
              score={clientOverall}
              max={max}
              highlight
            />
          ) : null}
          {peers.map((p) => (
            <PeerBar
              key={p.peer_name}
              label={p.peer_name}
              role={p.role}
              score={p.overall_score}
              max={max}
              delta={clientOverall != null && p.overall_score != null
                ? Math.round((p.overall_score - clientOverall) * 10) / 10
                : null}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function PeerBar({
  label,
  role,
  score,
  max,
  highlight,
  delta,
}: {
  label: string;
  role?: string | null;
  score: number | null;
  max: number;
  highlight?: boolean;
  delta?: number | null;
}) {
  const pct = score != null ? Math.max(2, (score / max) * 100) : 0;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 6, alignItems: "center" }}>
      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 6 }}>
          <span
            className="txt-fit-1"
            style={{ fontSize: 12, fontWeight: highlight ? 700 : 500, color: highlight ? "var(--z-dark)" : "var(--z-body)" }}
            title={label}
          >
            {label}
          </span>
          {role ? <span className="b b-muted" style={{ fontSize: 9.5 }}>{role}</span> : null}
        </div>
        <div style={{ height: 6, borderRadius: 4, background: "var(--z-lav)", marginTop: 3 }}>
          <div
            className={maturityClass(score)}
            style={{ width: `${pct}%`, height: "100%", borderRadius: 4, background: maturityHex(score) }}
          />
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
        <strong style={{ color: maturityHex(score) }}>{score != null ? score.toFixed(2) : "—"}</strong>
        {delta != null ? (
          // peer-relative: ▲ = this peer scores ABOVE the client, ▼ = below.
          <span className="b b-muted" style={{ fontSize: 9.5 }} title="peer vs this client">
            {delta > 0 ? "▲" : delta < 0 ? "▼" : "•"} {Math.abs(delta).toFixed(1)}
          </span>
        ) : null}
      </div>
    </div>
  );
}

// ── Sentiment (Part 8.5) — structured, drillable tiles per proto :386-402 ─

/** One structured sentiment row from the backend's `sentiment_view`. */
export type SentimentSource = {
  source: string;
  kind?: string;
  value?: number | null;
  max?: number | null;
  n?: number | null;
  polarity?: string | null;
  trend?: string | null;
  themes?: string[];
  drilldown?: string | null;
  evidence_e_id?: string | null;
};

const SENTIMENT_TONE: Record<string, string> = {
  positive: "var(--z-mid)",
  negative: "var(--z-below)",
  neutral: "var(--z-muted)",
};

export function SentimentCard({
  sentiment,
  onOpenEvidence,
}: {
  sentiment: Record<string, unknown> | null;
  onOpenEvidence?: (eId: string) => void;
}) {
  const [sentOpen, setSentOpen] = useState<string | null>(null);
  const sources = Array.isArray((sentiment as { sources?: unknown })?.sources)
    ? ((sentiment as { sources: SentimentSource[] }).sources)
    : null;
  return (
    <section className="card" data-source={sentiment ? "api" : "api-empty"} aria-label="Sentiment overview">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="users" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Sentiment overview</div>
        <span className="spacer" />
        {sources && sources.length > 0 ? (
          <span style={{ fontSize: 10, color: "var(--z-muted)" }}>Click any card for detail</span>
        ) : null}
      </div>
      {sources && sources.length > 0 ? (
        <div className="g3" style={{ gap: 10 }}>
          {sources.map((s, i) => {
            const id = `${s.source}-${i}`;
            const isOpen = sentOpen === id;
            const tone = SENTIMENT_TONE[(s.polarity ?? "neutral").toLowerCase()] ?? "var(--z-muted)";
            const hasDrill = Boolean(s.drilldown || (s.themes && s.themes.length > 0) || s.evidence_e_id);
            return (
              <div key={id}>
                <button
                  type="button"
                  data-testid="sentiment-tile"
                  aria-expanded={isOpen}
                  onClick={() => setSentOpen(isOpen ? null : id)}
                  className="card-tile clickable"
                  style={{ padding: 10, width: "100%", textAlign: "left", border: isOpen ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)" }}
                >
                  <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                    {s.kind ?? "source"}
                  </div>
                  <div className="row" style={{ marginTop: 4 }}>
                    {s.value != null ? (
                      <span style={{ fontSize: 18, fontWeight: 600 }}>
                        {s.value}
                        {s.max ? <span style={{ fontSize: 11, color: "var(--z-muted)", fontWeight: 400 }}>/{s.max}</span> : null}
                      </span>
                    ) : (
                      <span style={{ fontSize: 13, fontWeight: 600, color: tone }}>
                        {(s.polarity ?? "—").toUpperCase()}
                      </span>
                    )}
                    <span className="spacer" />
                    <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={11} style={{ color: "var(--z-muted)" }} />
                  </div>
                  <div style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    {s.source}
                    {s.n != null ? ` · n=${s.n.toLocaleString()}` : ""}
                    {s.trend ? ` · ${s.trend}` : ""}
                  </div>
                </button>
                {isOpen ? (
                  <div data-testid="sentiment-drilldown" style={{ marginTop: 6, padding: "10px 12px", background: "var(--z-lav)", borderRadius: 6, fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55 }}>
                    {s.drilldown ? <div>{s.drilldown}</div> : null}
                    {s.themes && s.themes.length > 0 ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: s.drilldown ? 8 : 0 }}>
                        {s.themes.map((t) => <span key={t} className="chip" style={{ fontSize: 10 }}>{t}</span>)}
                      </div>
                    ) : null}
                    {!hasDrill ? <div className="muted">No additional detail parsed for this source.</div> : null}
                    {s.evidence_e_id ? (
                      <div style={{ marginTop: 8 }}>
                        <button type="button" className="chip" style={{ cursor: "pointer", border: 0 }}
                                onClick={(ev) => { ev.stopPropagation(); onOpenEvidence?.(s.evidence_e_id as string); }}>
                          {s.evidence_e_id}
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : sentiment && Object.keys(sentiment).length > 0 ? (
        <pre className="muted small">{JSON.stringify(sentiment, null, 2)}</pre>
      ) : (
        <EmptyState
          title="No public sentiment parsed"
          body="Glassdoor / App Store / CFPB sentiment appears here once the research corpus carries it."
        />
      )}
    </section>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

// 2026-06-06 QA-5: split into guard + data component to keep React's
// hook count stable across role/audience flips. See HealthPage's
// matching comment for full rationale.
// ── Cross-pillar stories (D5) — standalone port. Fetches the catalogue's
// cross-pillar mappings scoped to this entity's scored subcaps; fail-closed
// (render nothing) on error so it never blocks the Context page. Honest
// contextual-empty when the catalogue mappings don't intersect this entity.
export function CrossPillarStoriesPanel({ displayId }: { displayId: string | null }): JSX.Element | null {
  const [pillarFilter, setPillarFilter] = useState<"ALL" | "P1" | "P2" | "P3" | "P4">("ALL");
  const q = useCrossPillarStories(displayId, pillarFilter === "ALL" ? null : pillarFilter);
  const stories = q.data?.stories ?? [];
  if (q.isError && stories.length === 0) return null;
  // Fail-closed on an unfiltered empty too (ADR-documented contract:
  // "Empty/404 → panel renders nothing") — an empty card in the page's
  // prime slot pushes the real timeline below the fold (all-94 parity
  // capture). The contextual empty stays ONLY for a user-chosen pillar
  // filter, which is interactive state worth explaining.
  if (!q.isLoading && stories.length === 0 && pillarFilter === "ALL") return null;
  return (
    <div className="card" style={{ marginBottom: 14 }} data-source="api" aria-label="Cross-pillar stories">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="sparkle" size={16} />
        <div style={{ fontWeight: 600, fontSize: 13 }}>Cross-pillar stories</div>
        <span className="spacer" />
        <div className="toggle-row" role="group" aria-label="Filter by origin pillar">
          {(["ALL", "P1", "P2", "P3", "P4"] as const).map((p) => (
            <button key={p} type="button" data-pillar-filter={p}
                    className={pillarFilter === p ? "on" : ""}
                    onClick={() => setPillarFilter(p)}>{p === "ALL" ? "All" : p}</button>
          ))}
        </div>
      </div>
      {q.isLoading ? (
        <div style={{ fontSize: 11, color: "var(--z-muted)", padding: 12 }}>Loading cross-pillar stories…</div>
      ) : stories.length === 0 ? (
        <EmptyState
          title="No cross-pillar stories"
          body={pillarFilter === "ALL"
            ? "Stories appear once the catalogue's cross-pillar mappings land for this entity's subcaps."
            : `No stories originate from ${pillarFilter}. Try another pillar filter.`}
        />
      ) : (
        stories.map((s) => {
          const subcaps = s.sample_subcap_names.length > 0 ? s.sample_subcap_names : s.subcaps_touched;
          return (
            <div key={s.story_key} data-story-key={s.story_key}
                 style={{ padding: "10px 0", borderBottom: "1px solid var(--z-sep)" }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <span className="b b-purple">{s.origin_pillar}</span>
                <strong style={{ fontSize: 12.5 }}>{s.origin_capability ?? s.themes[0] ?? s.story_key}</strong>
                <span className="spacer" />
                {s.target_pillar ? <span className="b b-teal">→ {s.target_pillar}</span> : null}
              </div>
              {s.why_this_matters ? (
                <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55, marginBottom: 6 }}>
                  {s.why_this_matters}
                </div>
              ) : null}
              {subcaps.length > 0 ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {subcaps.slice(0, 6).map((sid, i) => (
                    <span key={i} className="chip" style={{ fontSize: 10 }}>{sid}</span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })
      )}
    </div>
  );
}

export function ContextPage(): JSX.Element {
  // Part 8.1: no frontend role gate — Context is AE-level (backend
  // `require_ae` still enforces server-side). The customer-audience
  // strip is KEPT: this dashboard is internal-only.
  const audience = useUiStore((s) => s.audience);

  if (audience === "customer") {
    return (
      <EmptyState
        title="Hidden in customer view"
        body="Context is internal-only and is server-side-stripped from customer responses."
      />
    );
  }
  return <ContextPageData />;
}

function ContextPageData(): JSX.Element {
  const { path, query } = useRoute();
  const displayId = getDisplayId(path);
  // 2026-06-06 QA-1: propagate `?run=<request_id>`.
  const selectedRun = typeof query.run === "string" ? query.run : null;

  const { data, isLoading, error } = useEntityContext(displayId, selectedRun);
  // Client's own overall maturity for the peer-comparison reference bar
  // (from the ClientShell-cached overview query — no extra request).
  const overviewData = useEntityOverview(displayId, selectedRun).data;
  const clientOverall = ((): number | null => {
    const o = (overviewData?.entity as { overall_score?: number | null } | undefined)?.overall_score;
    if (typeof o === "number") return o;
    const ps = (overviewData?.pillar_scores ?? [])
      .map((p) => p.score)
      .filter((s): s is number => typeof s === "number");
    return ps.length ? Math.round((ps.reduce((a, b) => a + b, 0) / ps.length) * 100) / 100 : null;
  })();
  const openDrawer = useUiStore((s) => s.openDrawer);

  // Timeline interaction state (wireframe ClientContext lines 8-15).
  // `yearRange === null` means "auto full range" until the user drags.
  const [signalFilter, setSignalFilterRaw] = useState<"ALL" | Signal>("ALL");
  const [yearRange, setYearRangeRaw] = useState<[number, number] | null>(null);
  const [hoverEvent, setHoverEvent] = useState<number | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [issueOpen, setIssueOpen] = useState<string | null>(null);

  // Every terminal branch keeps the standard `.page`/data-page shell so
  // the chrome stays consistent and the e2e harnesses (routes.ts waits
  // on [data-page]) can tell "honest empty" from "never mounted".
  const shell = (inner: JSX.Element) => (
    <div className="page" data-page="context" data-source="context-pending">{inner}</div>
  );
  if (isLoading) return <div className="page-loading"><Spinner /> Loading context…</div>;
  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return shell(<EmptyState title="Forbidden" body="Server-side role gate denied this request." />);
    }
    return shell(<EmptyState title="Couldn't load context" body={(error as Error).message} />);
  }
  if (!data) return shell(<EmptyState title="No context yet" body="Try again in a moment." />);
  if (!data.run_request_id) {
    return shell(<EmptyState title="No active run yet" body="Context populates once a DMA ingests." />);
  }
  const empty =
    data.timeline_events.length === 0
    && data.issue_register.length === 0
    && data.acquisitions.length === 0
    && !data.firmographics
    && !data.financials
    && !data.sentiment;
  if (empty) {
    return shell(<EmptyState title="Context still building" body="The pipeline ran but no context data has landed yet." />);
  }

  const allEvents = [...data.timeline_events].sort((a, b) =>
    a.event_date.localeCompare(b.event_date),
  );
  const issues = data.issue_register;

  // Year axis bounds come from the real corpus (never a hardcoded range).
  const eventYears = allEvents.map(eventYear);
  const minYear = eventYears.length > 0 ? Math.min(...eventYears) : new Date().getFullYear();
  const maxYear = eventYears.length > 0 ? Math.max(...eventYears) : new Date().getFullYear();
  const range: [number, number] = yearRange
    ? [Math.max(minYear, Math.min(yearRange[0], maxYear)), Math.min(maxYear, Math.max(yearRange[1], minYear))]
    : [minYear, maxYear];

  // Selection indexes into the FILTERED list — reset it on filter moves.
  const setSignalFilter = (f: "ALL" | Signal): void => {
    setSignalFilterRaw(f);
    setSelectedEvent(null);
    setHoverEvent(null);
  };
  const setYearRange = (r: [number, number]): void => {
    setYearRangeRaw(r);
    setSelectedEvent(null);
    setHoverEvent(null);
  };

  const events = allEvents.filter((e) => {
    const y = eventYear(e);
    if (y < range[0] || y > range[1]) return false;
    if (signalFilter !== "ALL" && eventSignal(e) !== signalFilter) return false;
    return true;
  });

  const openCount = issues.filter((i) => i.status === "OPEN").length;
  const resolvedCount = issues.filter((i) => i.status === "RESOLVED").length;
  const finYears = data.financials?.years ?? [];
  const openIssue = issueOpen ? issues.find((i) => i.id === issueOpen) ?? null : null;

  return (
    <div className="page" data-page="context" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Context & timeline</div>
          <h1>Historical intelligence</h1>
          <div className="sub">
            Internal-only · {events.length} of {allEvents.length} events · {issues.length} issue{issues.length === 1 ? "" : "s"}
            {finYears.length > 0 ? ` · ${finYears.length}-year financials` : ""}
          </div>
        </div>
        <div className="actions">
          <span className="b b-org" style={{ alignSelf: "center" }}><Icon name="lock" size={10} /> INTERNAL ONLY</span>
        </div>
      </div>

      {/* Standalone 5 template contract: Context = timeline, issue gantt,
          financial trajectory, regulatory standing, sentiment, acquisitions
          ONLY. Cross-pillar stories / leadership / peer comparison are NOT
          on this page (leadership renders on Overview; peer deployment on
          the tech-stack drilldown). Components stay exported for reuse. */}

      {/* Timeline (wireframe lines 52-81) */}
      <div className="card" style={{ marginBottom: 14 }} data-source={allEvents.length > 0 ? "api" : "api-empty"} aria-label="Timeline of digital evolution events">
        <div className="row" style={{ marginBottom: 14 }}>
          <Icon name="timeline" size={16} />
          <div style={{ fontWeight: 600, fontSize: 13 }}>Digital evolution timeline</div>
          <span className="spacer" />
          {allEvents.length > 0 ? (
            <div className="toggle-row" role="group" aria-label="Filter timeline by signal">
              <button type="button" className={signalFilter === "ALL" ? "on" : ""} onClick={() => setSignalFilter("ALL")}>All</button>
              <button type="button" className={signalFilter === "positive" ? "on" : ""} onClick={() => setSignalFilter("positive")} style={{ color: signalFilter === "positive" ? "var(--z-mid)" : "var(--z-muted)" }}>Positive</button>
              <button type="button" className={signalFilter === "neutral" ? "on" : ""} onClick={() => setSignalFilter("neutral")}>Neutral</button>
              <button type="button" className={signalFilter === "negative" ? "on" : ""} onClick={() => setSignalFilter("negative")} style={{ color: signalFilter === "negative" ? "var(--z-below)" : "var(--z-muted)" }}>Negative</button>
            </div>
          ) : null}
        </div>

        {allEvents.length === 0 ? (
          <EmptyState title="No timeline events on record" body="Timeline events populate from the research corpus on ingest." />
        ) : (
          <>
            {/* Range slider */}
            <div style={{ background: "var(--z-lav)", padding: "12px 16px", borderRadius: 8, marginBottom: 14 }}>
              <div className="row" style={{ marginBottom: 8, fontSize: 11, color: "var(--z-muted)" }}>
                <Icon name="calendar" size={12} />
                <span>Time range</span>
                <span className="spacer" />
                <strong style={{ color: "var(--z-dark)" }}>{range[0]} – {range[1]}</strong>
              </div>
              {maxYear > minYear ? (
                <RangeSlider min={minYear} max={maxYear} value={range} onChange={setYearRange} />
              ) : null}
            </div>

            <InteractiveTimeline
              events={events}
              hoverEvent={hoverEvent}
              setHoverEvent={setHoverEvent}
              selectedEvent={selectedEvent}
              setSelectedEvent={setSelectedEvent}
            />

            {selectedEvent !== null && events[selectedEvent] ? (
              <EventDetail
                event={events[selectedEvent]}
                onClose={() => setSelectedEvent(null)}
                onOpenEvidence={(eId) => openDrawer("evidence", { displayId, eId, origin: "context-timeline" })}
              />
            ) : null}
          </>
        )}
      </div>

      {/* Issue register Gantt (wireframe lines 84-93) */}
      <div className="card flush" style={{ marginBottom: 14 }} data-source={issues.length > 0 ? "api" : "api-empty"} aria-label="Issue register">
        <div className="card-head">
          <h3>Issue register · Gantt</h3>
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {openCount} OPEN · {resolvedCount} RESOLVED{issues.length > 0 ? " · click any bar for detail" : ""}
          </span>
        </div>
        <div className="card-body">
          {issues.length === 0 ? (
            <EmptyState title="No issues on record" body="The issue register is empty for this run." />
          ) : (
            <InteractiveGantt issues={issues} issueOpen={issueOpen} setIssueOpen={setIssueOpen} />
          )}
          {openIssue ? (
            <IssueDetail issue={openIssue} displayId={displayId} onClose={() => setIssueOpen(null)} />
          ) : null}
        </div>
      </div>

      {/* Financial trajectory + Regulatory standing (wireframe lines 96-127) */}
      <div className="ctx-split" style={{ gap: 14, marginBottom: 14 }}>
        <FinancialTrajectoryCard financials={data.financials} />
        <RegulatoryStandingCard
          firmographics={data.firmographics}
          issues={issues}
          onOpenIssue={(id) => setIssueOpen(id)}
          onOpenEvidence={(eId) => openDrawer("evidence", { displayId, eId, origin: "context-regulatory" })}
        />
      </div>

      {/* Sentiment + acquisitions (wireframe lines 130-161) */}
      <div className="g2" style={{ marginBottom: 14 }}>
        <SentimentCard
          sentiment={data.sentiment}
          onOpenEvidence={(eId) => openDrawer("evidence", { displayId, eId, origin: "context-sentiment" })}
        />
        <AcquisitionsCard
          acquisitions={data.acquisitions}
          onOpenEvidence={(eId) => openDrawer("evidence", { displayId, eId, origin: "context-acquisitions" })}
        />
      </div>

      {data.narrative?.trend_md ? (
        <section
          className="co co-teal"
          data-source={data.narrative?.trend_md_source === "derived_financials" ? "derived" : "narrative"}
          style={{ marginTop: 14 }}
        >
          <header className="co-head">
            {data.narrative?.trend_md_source === "derived_financials"
              ? "Trend analysis · derived from the parsed financial series"
              : "Trend analysis · from the assessment report"}
          </header>
          <p className="co-body" style={{ whiteSpace: "pre-wrap" }}>
            {String(data.narrative.trend_md)}
          </p>
        </section>
      ) : null}

      <AboutCard firmographics={data.firmographics} />
    </div>
  );
}

// F5c (2026-06-07 follow-up): "About" card renders the analyst-prose
// `narrative_md` paragraph (200-1600 chars per the real fixtures)
// extracted from the Client Profile DOCX. Returns null when no
// narrative was sourced (preserves the older layout for packages
// without a Client Profile DOCX).
function AboutCard({
  firmographics,
}: {
  firmographics: Record<string, unknown> | null;
}): JSX.Element | null {
  const narrativeRaw = firmographics?.["narrative_md"];
  if (typeof narrativeRaw !== "string" || !narrativeRaw.trim()) {
    return null;
  }
  return (
    <section
      className="card"
      data-source="api"
      data-testid="about-narrative-card"
      style={{ marginTop: 14 }}
    >
      <div className="card-head">
        <h3 className="card-title">About</h3>
      </div>
      <div className="card-body">
        <p
          style={{
            whiteSpace: "pre-wrap",
            margin: 0,
            lineHeight: 1.55,
            fontSize: 14,
          }}
        >
          {narrativeRaw}
        </p>
      </div>
    </section>
  );
}
