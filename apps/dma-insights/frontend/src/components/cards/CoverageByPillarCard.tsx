/**
 * CoverageByPillarCard — D1 "Evidence & benchmarks" (proto df85cc41).
 * Renders `runs.coverage_stats` (derive_evidence_surfaces): per-pillar scored
 * share vs the 80% hard gate, with the thin-evidence count as the "why it
 * matters" hint (Part D: which pillars are thin and why that matters).
 */
import { Icon } from "@/components/utils";

export interface CoverageStatsData {
  overall_pct?: number;
  gate_pct?: number;
  by_pillar?: Array<{ pillar: string; pct: number; subcaps: number; scored: number; thin?: number }>;
}

const PILLAR_SHORT: Record<string, string> = {
  P1: "Strategy", P2: "Customer", P3: "Operations", P4: "Data & Tech",
};

export function CoverageByPillarCard({ data }: { data: CoverageStatsData | null }): JSX.Element {
  const rows = data?.by_pillar ?? [];
  if (!data || rows.length === 0) {
    return (
      <div className="card flush" data-source="api-empty">
        <div className="card-head"><h3>Evidence coverage</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }}>
          Coverage populates once the scoring workbook ingests.
        </div>
      </div>
    );
  }
  const gate = data.gate_pct ?? 80;
  const thinTotal = rows.reduce((a, p) => a + (p.thin ?? 0), 0);
  return (
    <div className="card flush" data-source="runs.coverage_stats">
      <div className="card-head">
        <div className="row"><Icon name="check" size={14} /><h3>Evidence coverage</h3></div>
        <span className={`b ${(data.overall_pct ?? 0) >= gate ? "b-above" : "b-org"}`}>
          {data.overall_pct ?? 0}% overall
        </span>
      </div>
      <div className="card-body">
        {rows.map((p) => {
          const pass = p.pct >= gate;
          return (
            <div key={p.pillar}
                 style={{ display: "grid", gridTemplateColumns: "90px 1fr 38px", gap: 8, alignItems: "center", padding: "5px 0" }}
                 title={`${p.scored}/${p.subcaps} subcaps scored${p.thin ? ` · ${p.thin} thin-evidence` : ""}`}>
              <div style={{ fontSize: 11, color: "var(--z-body)" }}>{PILLAR_SHORT[p.pillar] ?? p.pillar}</div>
              <div style={{ height: 7, background: "var(--z-sep)", borderRadius: 4, overflow: "hidden", position: "relative" }}>
                <div style={{ position: "absolute", left: `${gate}%`, top: -2, bottom: -2, width: 1, background: "var(--z-org)" }} />
                <div style={{ width: `${Math.min(100, p.pct)}%`, height: "100%", background: pass ? "var(--z-teal)" : "var(--z-org)", borderRadius: 4 }} />
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: pass ? "var(--z-teal)" : "var(--z-org)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{p.pct}%</div>
            </div>
          );
        })}
        <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6 }}>
          Orange line = {gate}% hard gate
          {thinTotal > 0 ? ` · ${thinTotal} subcaps on thin evidence — treat their scores as provisional` : ""}
        </div>
      </div>
    </div>
  );
}
