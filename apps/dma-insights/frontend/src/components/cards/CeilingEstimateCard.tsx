/**
 * CeilingEstimateCard — D1 "Evidence & benchmarks" (proto df85cc41).
 * Renders `runs.uncertainty_bands` (derive_evidence_surfaces): per-category
 * ceiling ± band with the REAL modifiers (caps, thin evidence, coverage) and
 * evidence chips that open the EvidenceDrawer scoped to the E-ID.
 * INTERNAL-ONLY: ceilings are analyst estimates — hidden for customer view
 * (the server additionally strips the payload via audience_strip).
 */
import { useState } from "react";
import { Icon } from "@/components/utils";
import { useUiStore } from "@/store/ui";

export interface CeilingBand {
  ceiling: number;
  band: number;
  modifiers?: string[];
  evidence?: string[];
  rationale?: string;
  derived_from?: string;
}

export function CeilingEstimateCard({
  data, audience, displayId,
}: {
  data: Record<string, CeilingBand> | null;
  audience: string;
  displayId: string | null;
}): JSX.Element | null {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [open, setOpen] = useState<string | null>(null);
  if (audience === "customer") return null;
  const rows = Object.entries(data ?? {})
    .filter(([k, v]) => /^P[1-4]C\d/.test(k) && v && typeof v.ceiling === "number")
    .sort(([a], [b]) => a.localeCompare(b));
  if (rows.length === 0) {
    return (
      <div className="card flush" data-source="api-empty">
        <div className="card-head"><h3>Capability ceiling &amp; uncertainty</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }}>
          Ceiling bands populate once the run&apos;s scores + uncertainty register ingest.
        </div>
      </div>
    );
  }
  const pct = (v: number): number => ((v - 1) / 4) * 100;
  return (
    <div className="card flush" data-source="runs.uncertainty_bands">
      <div className="card-head">
        <div className="row"><Icon name="stack" size={14} /><h3>Capability ceiling &amp; uncertainty</h3></div>
        <span className="b b-purple">{rows.length} categories · click to drill</span>
      </div>
      <div className="card-body" style={{ maxHeight: 340, overflowY: "auto" }}>
        {rows.map(([cat, d]) => {
          const lo = Math.max(1, d.ceiling - d.band);
          const hi = Math.min(5, d.ceiling + d.band);
          const tone = d.ceiling <= 2 ? "var(--z-below)" : d.ceiling < 3 ? "var(--z-org)" : "var(--z-teal)";
          const isOpen = open === cat;
          return (
            <div key={cat} style={{ borderBottom: "1px solid var(--z-sep)" }}>
              <button type="button" onClick={() => setOpen((o) => (o === cat ? null : cat))}
                      aria-label={`Ceiling detail ${cat}`}
                      style={{ width: "100%", display: "grid", gridTemplateColumns: "64px 1fr 72px 16px", gap: 8, alignItems: "center", padding: "8px 0", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
                <div className="f-mono" style={{ fontSize: 10.5, color: "var(--z-body)" }}>{cat}</div>
                <div style={{ position: "relative", height: 8, background: "var(--z-sep)", borderRadius: 4 }}
                     title={`Band ${lo.toFixed(1)}–${hi.toFixed(1)}`}>
                  <div style={{ position: "absolute", left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%`, top: 0, bottom: 0, background: "rgba(124,93,201,.25)", borderRadius: 4 }} />
                  <div style={{ position: "absolute", left: `calc(${pct(d.ceiling)}% - 4px)`, top: -1, width: 8, height: 10, borderRadius: 2, background: tone }} />
                </div>
                <div style={{ fontSize: 11, fontWeight: 600, color: tone, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {d.ceiling.toFixed(1)}<span style={{ color: "var(--z-muted)", fontWeight: 400 }}> ±{d.band}</span>
                </div>
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={12} style={{ color: "var(--z-muted)" }} />
              </button>
              {isOpen ? (
                <div style={{ padding: "2px 0 12px", paddingLeft: 4 }}>
                  {d.rationale ? (
                    <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, marginBottom: 8 }}>{d.rationale}</div>
                  ) : null}
                  {d.modifiers && d.modifiers.length ? (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 3 }}>Ceiling modifiers</div>
                      {d.modifiers.map((m, i) => (
                        <div key={i} style={{ fontSize: 11, color: "var(--z-org)", fontFamily: "var(--font-mono)" }}>{m}</div>
                      ))}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 4 }}>Evidence · click to open</div>
                  {d.evidence && d.evidence.length ? (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {d.evidence.map((eid) => (
                        <button key={eid} type="button" className="chip" title="Open evidence"
                                onClick={() => openDrawer("evidence", { eId: eid, eIds: d.evidence, displayId, origin: "ceiling-card" })}>
                          {eid}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: "var(--z-muted)" }}>No evidence linked — inferred ceiling.</div>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
