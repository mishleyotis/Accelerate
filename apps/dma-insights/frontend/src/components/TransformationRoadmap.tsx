/**
 * TransformationRoadmap (D4) — ported from the 2026-06 prototype
 * (08_pages_d.js · TransformationRoadmap). Three views via a toggle,
 * chevrons being the DEFAULT (wireframe contract):
 *   - chevrons:  dark chevron header strip + dark phase content columns
 *   - curve:     composite-maturity step curve (SVG) + click-to-drilldown
 *   - impact:    per-phase customer-facing impact KVs
 * Recommendation chips open the RecommendationModal (openDrawer).
 *
 * Production-ready + cascade-safe: driven by structured
 * `PlatformNarrative.roadmap_phases` when present; degrades to rendering the
 * `roadmap_md` prose so the surface is never blank with the current backend.
 *
 * Honest-data notes:
 *   - Phase colors follow the prototype's DARK teal ramp (01_data.js
 *     ROADMAP: --z-dark2 → --z-mid → --z-teal) — NOT the amber maturity
 *     band ramp.
 *   - The "Sequencing rationale" footnote renders the roadmap prose that
 *     ships in the payload (`narrative.roadmap_md`); the /platforms/roadmap
 *     endpoint carries no rationale field, so when no prose ships the
 *     footnote is omitted rather than fabricated.
 */
import { useState } from "react";
import type { RoadmapPhase } from "@/lib/queries";
import { Icon } from "@/components/utils";
import { useUiStore } from "@/store/ui";
import { printView } from "@/lib/export";

// Prototype ROADMAP palette (01_data.js): dark→mid→teal; --z-dark caps a
// 4th phase when the backend emits one (effort-band grouping yields 1–4).
const PHASE_COLORS = ["var(--z-dark2)", "var(--z-mid)", "var(--z-teal)", "var(--z-dark)"];
const colorFor = (p: RoadmapPhase, i: number): string => p.color || PHASE_COLORS[i % PHASE_COLORS.length];

/** Parse "M2 → M3" / "M3" → {start,end} composite maturity (1–5). */
function parseTarget(s: string): { start: number; end: number } {
  const nums = (s.match(/(\d(?:\.\d)?)/g) ?? []).map(Number).filter((n) => n >= 1 && n <= 5);
  const start = nums[0] ?? 2;
  return { start, end: nums[nums.length - 1] ?? start };
}

interface Props {
  phases?: RoadmapPhase[] | null;
  /** Roadmap prose from the payload (narrative.roadmap_md) — renders as
   *  the "Sequencing rationale" footnote (and as the whole card when no
   *  structured phases shipped). */
  roadmapMd?: string | null;
  displayId?: string | null;
  /** rec_id → title (from the roadmap payload) so chevron rec chips can
   *  show the wireframe's `REC-NN · title →` row, not just the id. */
  recTitles?: Record<string, string>;
}

export function TransformationRoadmap({ phases, roadmapMd, displayId, recTitles }: Props): JSX.Element | null {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [view, setView] = useState<"chevrons" | "curve" | "impact">("chevrons");
  const ph = Array.isArray(phases) ? phases : [];
  const openRec = (rid: string): void => openDrawer("recommendation", { recommendationId: rid, displayId });
  const titles = recTitles ?? {};

  if (ph.length === 0) {
    if (!roadmapMd) return null;
    return (
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card-head"><h3>Transformation roadmap</h3></div>
        <div style={{ padding: "14px 18px", fontSize: 13, lineHeight: 1.6, color: "var(--z-body)", whiteSpace: "pre-wrap" }}>{roadmapMd}</div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginBottom: 16, padding: "18px 20px" }} data-component="transformation-roadmap">
      <div className="row" style={{ marginBottom: 16, gap: 10 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="route" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Transformation roadmap</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{ph.length}-phase sequencing aligned to the maturity curve above</div>
        </div>
        <div className="toggle-row" role="group" aria-label="Roadmap view">
          <button type="button" className={view === "chevrons" ? "on" : ""} onClick={() => setView("chevrons")}><Icon name="route" size={11} /> Chevrons</button>
          <button type="button" className={view === "curve" ? "on" : ""} onClick={() => setView("curve")}><Icon name="stairs" size={11} /> Step curve</button>
          <button type="button" className={view === "impact" ? "on" : ""} onClick={() => setView("impact")}><Icon name="users" size={11} /> Customer impact</button>
        </div>
        <button type="button" className="btn btn-tertiary btn-sm" onClick={() => printView()}><Icon name="download" size={11} /> Export</button>
      </div>

      {view === "chevrons" ? <ChevronView ph={ph} openRec={openRec} titles={titles} />
        : view === "curve" ? <StepCurveView ph={ph} openRec={openRec} titles={titles} />
          : <CustomerImpactView ph={ph} openRec={openRec} titles={titles} />}

      {roadmapMd ? (
        <div className="co co-teal" style={{ marginTop: 14 }}>
          <Icon name="info" size={14} />
          <div>
            <div className="co-title">Sequencing rationale</div>
            <div className="co-body">{roadmapMd}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const FIELD_LABEL: React.CSSProperties = { fontSize: 10, color: "rgba(255,255,255,.7)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 };

function RecChip({ rid, title, onOpen }: { rid: string; title?: string; onOpen: (r: string) => void }): JSX.Element {
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(rid); }}
      style={{ padding: "6px 8px", background: "rgba(255,255,255,.14)", borderRadius: 5, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, border: 0, color: "#fff", textAlign: "left", cursor: "pointer", width: "100%" }}>
      <span style={{ fontSize: 10.5, fontWeight: 600, flexShrink: 0 }}>{rid}</span>
      {title ? (
        <span className="txt-trunc" style={{ fontSize: 10.5, color: "rgba(255,255,255,.85)", flex: 1, minWidth: 0 }}>{title}</span>
      ) : <span className="spacer" />}
      <Icon name="arrow-r" size={11} />
    </button>
  );
}

type Titles = Record<string, string>;

function ChevronView({ ph, openRec, titles }: { ph: RoadmapPhase[]; openRec: (r: string) => void; titles: Titles }): JSX.Element {
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${ph.length}, 1fr)`, gap: 12, marginBottom: 12 }}>
        {ph.map((p, i) => (
          <div key={p.phase} style={{
            background: colorFor(p, i),
            // Wireframe chevron notch/arrow (08_pages_d.js uses 4%/96% on
            // third-width columns ≈ 18px) — fixed px keeps the shape when
            // the backend emits fewer/wider phases.
            clipPath: i === ph.length - 1
              ? "polygon(0 0, 100% 0, 100% 100%, 0 100%, 18px 50%)"
              : "polygon(0 0, calc(100% - 18px) 0, 100% 50%, calc(100% - 18px) 100%, 0 100%, 18px 50%)",
            color: "#fff", padding: "10px 22px 10px 34px", fontSize: 12.5, fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 10, opacity: 0.8, letterSpacing: ".08em", textTransform: "uppercase" }}>Phase {p.phase}</div>
              <div>{p.label}</div>
            </div>
            <div style={{ fontSize: 10, opacity: 0.85, textAlign: "right" }}>{p.duration}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${ph.length}, 1fr)`, gap: 12 }}>
        {ph.map((p, i) => (
          <div key={p.phase} style={{ background: colorFor(p, i), borderRadius: 8, padding: 14, color: "#fff" }}>
            <div style={FIELD_LABEL}>Platform</div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>{p.platform}</div>
            <div style={FIELD_LABEL}>Target maturity</div>
            <div style={{ fontSize: 12.5, marginBottom: 10, color: "var(--z-mint-lt)" }}>{p.target}</div>
            <div style={FIELD_LABEL}>Success metric</div>
            <div style={{ fontSize: 12, marginBottom: 10, lineHeight: 1.5 }}>{p.metric}</div>
            {p.rec_ids && p.rec_ids.length > 0 ? (
              <>
                <div style={FIELD_LABEL}>Recommendations</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {p.rec_ids.map((rid) => <RecChip key={rid} rid={rid} title={titles[rid]} onOpen={openRec} />)}
                </div>
              </>
            ) : null}
            {p.dependencies && p.dependencies.length > 0 ? (
              <div style={{ fontSize: 10, color: "rgba(255,255,255,.75)", marginTop: 8 }}>
                Depends on {p.dependencies.join(", ")}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </>
  );
}

function StepCurveView({ ph, openRec, titles }: { ph: RoadmapPhase[]; openRec: (r: string) => void; titles: Titles }): JSX.Element {
  const [sel, setSel] = useState<number | null>(null);
  const start = parseTarget(ph[0]?.target ?? "M2").start;
  const points = [
    { t: 0, m: start, label: "Today", phase: null as number | null },
    ...ph.map((p, i) => ({ t: Math.round(((i + 1) / ph.length) * 18), m: parseTarget(p.target).end, label: `End ${p.label}`, phase: p.phase })),
  ];
  const W = 880, H = 280, padL = 50, padR = 30, padT = 30, padB = 50;
  const xFor = (t: number): number => padL + (t / 18) * (W - padL - padR);
  const yFor = (m: number): number => H - padB - ((m - 1) / 4) * (H - padT - padB);
  const bandW = (W - padL - padR) / ph.length;
  const selPhase = sel != null ? ph.find((r) => r.phase === points[sel].phase) ?? null : null;
  const selPoint = sel != null ? points[sel] : null;

  return (
    <div>
      <div style={{ background: "linear-gradient(180deg, var(--z-bg), #fff)", borderRadius: 10, padding: 14, border: "1px solid var(--z-sep)" }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
          {[1, 2, 3, 4, 5].map((m) => (
            <g key={m}>
              <line x1={padL} y1={yFor(m)} x2={W - padR} y2={yFor(m)} stroke="var(--z-sep)" strokeDasharray="3 3" />
              <text x={padL - 8} y={yFor(m) + 3} fontSize="10" fill="var(--z-muted)" textAnchor="end">M{m}</text>
            </g>
          ))}
          {ph.map((p, i) => (
            <rect key={p.phase} x={padL + i * bandW} y={padT} width={bandW} height={H - padT - padB} fill={colorFor(p, i)} opacity="0.06" />
          ))}
          {ph.map((p, i) => (
            <text key={`l${p.phase}`} x={padL + (i + 0.5) * bandW} y={padT - 8} fontSize="11" fontWeight="700" fill={colorFor(p, i)} textAnchor="middle">{p.label.toUpperCase()}</text>
          ))}
          <path d={`M ${xFor(0)} ${yFor(points[0].m)} ${points.slice(1).map((p) => `L ${xFor(p.t)} ${yFor(p.m)}`).join(" ")}`} fill="none" stroke="var(--z-teal)" strokeWidth="2.5" />
          {points.map((p, i) => (
            <g key={i} style={{ cursor: "pointer" }} onClick={() => setSel(i === sel ? null : i)}>
              <circle cx={xFor(p.t)} cy={yFor(p.m)} r="14" fill="transparent" />
              <circle cx={xFor(p.t)} cy={yFor(p.m)} r={sel === i ? "10" : "7"} fill="#fff" stroke={sel === i ? "var(--z-mid)" : "var(--z-teal)"} strokeWidth="3" />
              <text x={xFor(p.t)} y={yFor(p.m) - 16} fontSize="11" fontWeight="700" fill="var(--z-dark)" textAnchor="middle">{p.m.toFixed(1)}</text>
              <text x={xFor(p.t)} y={H - padB + 18} fontSize="10" fill={sel === i ? "var(--z-mid)" : "var(--z-muted)"} fontWeight={sel === i ? 700 : 400} textAnchor="middle">{p.label}</text>
              <text x={xFor(p.t)} y={H - padB + 32} fontSize="9" fill="var(--z-muted)" textAnchor="middle">{p.t === 0 ? "0 mo" : `${p.t} mo`}</text>
            </g>
          ))}
        </svg>
        <div style={{ fontSize: 10, color: "var(--z-muted)", textAlign: "center", marginTop: 6 }}>Click any milestone for the phase plan</div>
      </div>
      {selPhase && selPoint ? (
        <div style={{ marginTop: 12, padding: 16, background: colorFor(selPhase, selPhase.phase - 1), borderRadius: 10, color: "#fff", position: "relative" }}>
          <button type="button" onClick={() => setSel(null)} className="icon-btn" style={{ position: "absolute", top: 10, right: 10, color: "rgba(255,255,255,.7)" }} aria-label="Close"><Icon name="x" size={14} /></button>
          <div className="row" style={{ marginBottom: 10 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,.8)", letterSpacing: ".08em", textTransform: "uppercase" }}>Phase {selPhase.phase}</span>
            <strong style={{ fontSize: 16 }}>{selPhase.label}</strong>
            <span className="spacer" />
            <span style={{ fontSize: 11, color: "var(--z-mint-lt)" }}>{selPhase.duration} · target {selPhase.target}</span>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--z-mint-lt)", marginBottom: 10, lineHeight: 1.55 }}>
            Reaches <strong style={{ color: "#fff" }}>{selPoint.m.toFixed(1)}</strong> composite maturity. Success metric: {selPhase.metric}.
          </div>
          {selPhase.rec_ids && selPhase.rec_ids.length > 0 ? (
            <div className="g2" style={{ gap: 8 }}>
              {selPhase.rec_ids.map((rid) => <RecChip key={rid} rid={rid} title={titles[rid]} onOpen={openRec} />)}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function CustomerImpactView({ ph, openRec, titles }: { ph: RoadmapPhase[]; openRec: (r: string) => void; titles: Titles }): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${ph.length}, 1fr)`, gap: 12 }}>
      {ph.map((p, i) => {
        const impact = p.customer_impact ?? { "Success metric": p.metric };
        return (
          <div key={p.phase} className="card-tile" style={{ padding: 14, borderTop: `3px solid ${colorFor(p, i)}` }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: colorFor(p, i), letterSpacing: ".08em", textTransform: "uppercase" }}>Phase {p.phase}</span>
              <strong style={{ fontSize: 13 }}>{p.label}</strong>
            </div>
            <div style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Customer-facing impact</div>
            {Object.entries(impact).map(([k, v]) => (
              <div key={k} className="row" style={{ padding: "6px 0", borderTop: "1px solid var(--z-sep)" }}>
                <span style={{ fontSize: 11.5, color: "var(--z-body)", flex: 1 }}>{k.replace(/_/g, " ")}</span>
                <strong style={{ fontSize: 12, color: "var(--z-mid)" }}>{v}</strong>
              </div>
            ))}
            {p.rec_ids && p.rec_ids.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 10 }}>
                {p.rec_ids.map((rid) => (
                  <button key={rid} type="button" onClick={() => openRec(rid)}
                    style={{ padding: "6px 8px", background: "var(--z-lav)", border: 0, borderRadius: 5, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, textAlign: "left", cursor: "pointer", fontSize: 10.5 }}>
                    <strong style={{ color: "var(--z-dark)", flexShrink: 0 }}>{rid}</strong>
                    {titles[rid] ? (
                      <span className="txt-trunc" style={{ color: "var(--z-muted)", flex: 1, minWidth: 0 }}>{titles[rid]}</span>
                    ) : null}
                    <Icon name="arrow-r" size={11} style={{ color: "var(--z-muted)" }} />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
