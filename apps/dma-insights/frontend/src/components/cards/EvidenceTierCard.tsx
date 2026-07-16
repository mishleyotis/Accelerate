/**
 * EvidenceTierCard — D1 "Evidence & benchmarks" (proto df85cc41).
 * Renders `runs.evidence_summary` (derive_evidence_surfaces): tier histogram
 * + claim/signal mix. Honest-empty when the run has no evidence index.
 */
import { Icon } from "@/components/utils";

export interface EvidenceSummaryData {
  total_items?: number;
  total_facts?: number;
  tiers?: Record<string, number>;
  claims?: Record<string, number>;
  signals?: Record<string, number>;
  connectors?: Record<string, number>;
}

const TIER_COLOR: Record<string, string> = {
  T1: "var(--z-teal)", T2: "var(--z-teal)", T3: "var(--z-mid)",
  T4: "var(--z-org)", T5: "var(--z-org)", T6: "var(--z-below)",
  T7: "var(--z-below)", T8: "var(--z-below)",
};

/** Canonicalize a tier key to "T{n}" so "Tier 1" / "t1" / "1" all collapse
 *  onto one bucket — the histogram reads identically regardless of how the
 *  upstream evidence_summary spelled the tier (2026-07-06: one view). */
function canonTier(t: string): string {
  const m = String(t).match(/(\d+)/);
  return m ? `T${m[1]}` : String(t).toUpperCase();
}

export function EvidenceTierCard({ data }: { data: EvidenceSummaryData | null }): JSX.Element {
  const tierMap = new Map<string, number>();
  for (const [k, v] of Object.entries(data?.tiers ?? {})) {
    const key = canonTier(k);
    tierMap.set(key, (tierMap.get(key) ?? 0) + (typeof v === "number" ? v : 0));
  }
  const tiers = [...tierMap.entries()].sort(([a], [b]) => {
    const na = parseInt(a.slice(1), 10);
    const nb = parseInt(b.slice(1), 10);
    return (Number.isNaN(na) ? 99 : na) - (Number.isNaN(nb) ? 99 : nb);
  });
  if (!data || tiers.length === 0) {
    return (
      <div className="card flush" data-source="api-empty">
        <div className="card-head"><h3>Evidence tier distribution</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }}>
          No evidence index for this run — tiers populate on the next ingest.
        </div>
      </div>
    );
  }
  const max = Math.max(...tiers.map(([, v]) => v), 1);
  return (
    <div className="card flush" data-source="runs.evidence_summary">
      <div className="card-head">
        <div className="row"><Icon name="evidence" size={14} /><h3>Evidence tier distribution</h3></div>
        <span className="b b-muted">
          {data.total_items ?? 0} items · {data.total_facts ?? 0} facts
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 120, padding: "4px 0 0" }}>
          {tiers.map(([t, v]) => (
            <div key={t} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}
                 title={`${t}: ${v} items`}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", fontVariantNumeric: "tabular-nums" }}>{v}</div>
              <div style={{
                width: "100%", height: `${(v / max) * 84}px`, minHeight: 3,
                background: TIER_COLOR[t] ?? "var(--z-mid)", borderRadius: "4px 4px 0 0",
              }} />
              <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{t}</div>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12, gap: 6, flexWrap: "wrap" }}>
          {Object.entries(data.claims ?? {}).filter(([, v]) => v > 0).map(([k, v]) => (
            <span key={k} className="chip" title="claim distribution">
              {k.replace(/_/g, " ").toLowerCase()} · {v}
            </span>
          ))}
          {Object.entries(data.signals ?? {})
            .filter(([k, v]) => v > 0 && k !== "NEUTRAL")
            .map(([k, v]) => (
              <span key={k} className="chip muted" title="polarity signal">
                {k.toLowerCase()} · {v}
              </span>
            ))}
        </div>
      </div>
    </div>
  );
}
