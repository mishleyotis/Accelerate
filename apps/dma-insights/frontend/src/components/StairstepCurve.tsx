/**
 * StairstepCurve — D4 "Stairstepped maturity curve" (signature DMA viz),
 * ported 1:1 from the 2026-06 prototype (08_pages_d.js · StairstepCurve).
 *
 * Layout (prototype): .card with icon-tile head ("Stairstepped maturity
 * curve · {focus}" + sub + pillar toggle), then a 2-col grid:
 *   - left:  SVG staircase — 4 step bands M2 Building → M3 Competing →
 *            M4 Differentiating → M5 Leading (m-act → m-bld → m-cmp →
 *            m-dif fills, first band 0.6 opacity), M-level node circles,
 *            dashed connectors, baseline Today→Leading arrow, and a
 *            dashed orange CURRENT marker pinned to the band the
 *            entity's real pillar score falls in.
 *   - right: per-band meta tiles — maturity chip (b-act/b-bld/b-cmp/
 *            b-dif), enabling platform(s) + roadmap-phase duration
 *            (from the roadmap payload via recMeta), and the rec steps
 *            that land in that band (clickable → RecommendationModal).
 *
 * Honest-data contract (no wireframe mock content):
 *   - current marker + band annotations come from GET
 *     /entities/{id}/stairstep (corpus-recomputed scores);
 *   - platform/duration labels come from the roadmap payload the page
 *     passes down (recMeta) — never hardcoded;
 *   - bands with no mapped rec render a branded "No mapped
 *     recommendation in this run." note.
 *
 * Render-state matrix:
 *   1. displayId null                    → null
 *   2. isLoading                         → card + spinner row
 *   3. error                             → card + "Couldn't load stairstep."
 *   4. empty_state="no-gaps" OR no run
 *      yet (no pillar has a score)       → card + branded EmptyState
 *   5. otherwise (incl. "no-recs" /
 *      "no-applicable-uplift")           → staircase renders; meta tiles
 *                                          carry honest empty notes
 */
import { useState } from "react";
import { EmptyState, Icon, Spinner } from "@/components/utils";
import { useStairstep, type StairStepOut } from "@/lib/stairstep";

const PILLAR_LABEL: Record<string, string> = {
  P1: "Strategy",
  P2: "Engagement",
  P3: "Operations",
  P4: "Data & AI",
};
const PILLARS = ["P1", "P2", "P3", "P4"];

/** The 4 maturity step bands of the prototype staircase. Chip/fill
 *  pairing intentionally mirrors 08_pages_d.js (color index shifted by
 *  one vs. the band scale: Building renders in --m-act, etc.). */
const BANDS = [
  { m: 2, label: "Building", chip: "b-act", fill: "var(--m-act)", tileBg: "var(--m-act)" },
  { m: 3, label: "Competing", chip: "b-bld", fill: "var(--m-bld)", tileBg: "rgba(98,215,184,.15)" },
  { m: 4, label: "Differentiating", chip: "b-cmp", fill: "var(--m-cmp)", tileBg: "var(--z-ice)" },
  { m: 5, label: "Leading", chip: "b-dif", fill: "var(--m-dif)", tileBg: "rgba(19,159,148,.10)" },
] as const;

/** Map a 1–5 maturity score to the staircase band index (0..3).
 *  Scores below M2 clamp into the Building band — the verbatim score is
 *  always displayed next to the marker, so nothing is overstated. */
function bandIndexFor(score: number): number {
  return Math.min(3, Math.max(0, Math.floor(score) - 2));
}

/** Per-rec metadata the page derives from the roadmap payload. */
export interface StairRecMeta {
  platform: string;
  duration: string;
}

interface StairstepCurveProps {
  displayId: string | null;
  /** Pillar of the platform selected on the page (P1..P4) — initial
   *  focus for the staircase; the AE can re-focus via the toggle. */
  focusPillar?: string | null;
  /** rec_id → {platform, duration} from /platforms/roadmap. */
  recMeta?: Record<string, StairRecMeta>;
  /** Opens the RecommendationModal scoped to that rec (page-wired). */
  onRecClick?: (recId: string) => void;
}

export function StairstepCurve({
  displayId,
  focusPillar,
  recMeta,
  onRecClick,
}: StairstepCurveProps): JSX.Element | null {
  const { data, isLoading, error } = useStairstep(displayId);
  const [pillarSel, setPillarSel] = useState<string | null>(null);

  if (!displayId) return null;

  // Focus pillar: explicit AE toggle wins, else the selected platform's
  // pillar, else the first pillar the run scored.
  const currents = data?.current_by_pillar ?? {};
  const scored = PILLARS.filter((p) => p in currents);
  const pillar =
    (pillarSel && scored.includes(pillarSel) ? pillarSel : null) ??
    (focusPillar && scored.includes(focusPillar) ? focusPillar : null) ??
    scored[0] ??
    null;

  const head = (body: JSX.Element, toggle?: JSX.Element): JSX.Element => (
    <div className="card stairstep-curve" style={{ marginBottom: 16 }} data-component="stairstep-curve">
      <div className="row" style={{ marginBottom: 14, gap: 10 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--z-ice)", color: "var(--z-mid)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="stairs" size={14} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            Stairstepped maturity curve{pillar ? ` · ${PILLAR_LABEL[pillar] ?? pillar}` : ""}
          </div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            Where this client is today → M3 → M4 → M5 · with the platform that enables each step-up
          </div>
        </div>
        {toggle ?? null}
      </div>
      {body}
    </div>
  );

  if (isLoading) {
    return head(
      <div className="muted" style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <Spinner size={14} /> Loading stairstep…
      </div>,
    );
  }
  if (error || !data) {
    return head(
      <div className="muted" style={{ fontSize: 12 }}>Couldn't load stairstep.</div>,
    );
  }

  const hasAnyScore = scored.some((p) => (currents[p] ?? 0) > 0);
  if (data.empty_state === "no-gaps" || !hasAnyScore || !pillar) {
    return head(
      <EmptyState
        title="No scored subcaps yet"
        body="The stairstep populates once the DMA ingests."
      />,
    );
  }

  const current = currents[pillar] ?? 0;
  const curIdx = bandIndexFor(current);
  const steps = data.steps_by_pillar?.[pillar] ?? [];

  // Bucket the cumulative rec steps into the band their score_after reaches.
  const buckets: StairStepOut[][] = BANDS.map(() => []);
  steps.forEach((s) => buckets[bandIndexFor(s.score_after)].push(s));
  const platformsFor = (bucket: StairStepOut[]): string[] =>
    [...new Set(bucket.map((s) => recMeta?.[s.rec_id]?.platform).filter((x): x is string => !!x))];
  const durationFor = (bucket: StairStepOut[]): string | null =>
    bucket.map((s) => recMeta?.[s.rec_id]?.duration).find((x): x is string => !!x) ?? null;

  // ── SVG geometry (verbatim from the prototype) ────────────────────
  const W = 880, H = 280, padL = 60, padR = 40, padT = 30, padB = 60;
  const stepW = (W - padL - padR) / 4;
  const stepY = (i: number): number => H - padB - ((i + 1) * (H - padT - padB)) / 5;

  const toggle = (
    <div className="toggle-row" role="group" aria-label="Stairstep focus pillar">
      {scored.map((p) => (
        <button key={p} type="button" className={p === pillar ? "on" : ""} onClick={() => setPillarSel(p)}>
          {PILLAR_LABEL[p] ?? p}
        </button>
      ))}
    </div>
  );

  return head(
    <div className="sidebar-split" style={{ gap: 18, alignItems: "stretch" }}>
      <div style={{ background: "linear-gradient(180deg, var(--z-bg), #fff)", borderRadius: 10, padding: "16px 14px 12px", border: "1px solid var(--z-sep)", position: "relative", overflow: "hidden" }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", position: "relative" }} role="img"
          aria-label={`Stairstepped maturity curve for ${PILLAR_LABEL[pillar] ?? pillar}: current ${current.toFixed(1)}`}>
          <defs>
            <marker id="stairstep-arrow-h" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--z-purple)" />
            </marker>
          </defs>
          <line x1={padL} y1={H - padB + 18} x2={W - padR} y2={H - padB + 18} stroke="var(--z-purple)" strokeWidth="1.5" markerEnd="url(#stairstep-arrow-h)" />
          <text x={padL} y={H - padB + 38} fontSize="10" fill="var(--z-muted)">Today</text>
          <text x={W - padR - 36} y={H - padB + 38} fontSize="10" fill="var(--z-mid)" fontWeight="600">Leading</text>

          {BANDS.map((b, i) => {
            const x = padL + i * stepW;
            const y = stepY(i);
            const w = stepW - 8;
            const h = H - padB - y;
            const plats = platformsFor(buckets[i]);
            return (
              <g key={b.m}>
                <rect x={x} y={y} width={w} height={h} fill={b.fill} rx="6" ry="6" opacity={i === 0 ? 0.6 : 1} />
                <circle cx={x + 16} cy={y - 14} r="14" fill="#fff" stroke={b.fill} strokeWidth="2.5" />
                <text x={x + 16} y={y - 9} fontSize="13" fontWeight="700" fill={b.fill} textAnchor="middle">M{b.m}</text>
                <text x={x + w / 2} y={y + 18} fontSize="12" fontWeight="600" fill={i >= 2 ? "#fff" : "var(--z-dark)"} textAnchor="middle">{b.label}</text>
                {plats.length > 0 ? (
                  <text x={x + w / 2} y={y + 35} fontSize="9.5" fill={i >= 2 ? "rgba(255,255,255,.85)" : "var(--z-body)"} textAnchor="middle" style={{ fontFamily: "var(--font-mono)" }}>
                    via {plats.join(" + ")}
                  </text>
                ) : null}
              </g>
            );
          })}

          {BANDS.slice(0, -1).map((b, i) => (
            <line key={b.m}
              x1={padL + (i + 1) * stepW - 8} y1={stepY(i)}
              x2={padL + (i + 1) * stepW} y2={stepY(i + 1) + (H - padB - stepY(i + 1))}
              stroke="var(--z-dpur)" strokeWidth="2" strokeDasharray="3 3" opacity="0.5" />
          ))}

          <g>
            <circle cx={padL + curIdx * stepW + 16} cy={stepY(curIdx) - 14} r="20" fill="none" stroke="var(--z-org)" strokeWidth="2" strokeDasharray="4 3" />
            <text x={padL + curIdx * stepW - 6} y={stepY(curIdx) - 30} fontSize="9.5" fill="var(--z-org)" fontWeight="700" textAnchor="end">CURRENT</text>
            <text x={padL + curIdx * stepW - 6} y={stepY(curIdx) - 17} fontSize="11" fill="var(--z-dark)" fontWeight="700" textAnchor="end">{current.toFixed(1)}</text>
          </g>
        </svg>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {BANDS.map((b, i) => {
          const bucket = buckets[i];
          const plats = platformsFor(bucket);
          const duration = durationFor(bucket);
          return (
            <div key={b.m} style={{ padding: "10px 12px", background: b.tileBg, borderRadius: 8, border: "1px solid var(--z-sep)" }}>
              <div className="row" style={{ marginBottom: 4 }}>
                <span className={`b ${b.chip}`}>M{b.m} {b.label}</span>
                {plats.length > 0 ? (
                  <span style={{ fontSize: 10, color: "var(--z-mid)" }}>
                    {plats.join(" + ")}{duration ? ` · ${duration}` : ""}
                  </span>
                ) : null}
              </div>
              {i === curIdx ? (
                <div style={{ fontSize: 11.5, color: "var(--z-dark)", lineHeight: 1.55 }}>
                  Today — current {current.toFixed(1)} in {PILLAR_LABEL[pillar] ?? pillar}
                </div>
              ) : null}
              {bucket.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: i === curIdx ? 6 : 0 }}>
                  {bucket.map((s) => {
                    const body = (
                      <>
                        <span className="stair-rec-id"><code>{s.rec_id}</code></span>
                        <span className="stair-rec-title txt-trunc" style={{ flex: 1, minWidth: 0 }}>{s.title}</span>
                        <span className="stair-jump">{s.score_before.toFixed(1)} → {s.score_after.toFixed(1)}</span>
                      </>
                    );
                    return onRecClick ? (
                      <button key={s.rec_id} type="button" className="stair-step-button"
                        onClick={() => onRecClick(s.rec_id)}
                        aria-label={`Open recommendation ${s.rec_id}: ${s.title}`}>
                        {body}
                      </button>
                    ) : (
                      <div key={s.rec_id} className="stair-step">{body}</div>
                    );
                  })}
                </div>
              ) : i > curIdx ? (
                <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5 }}>
                  No mapped recommendation in this run.
                </div>
              ) : i < curIdx ? (
                <div style={{ fontSize: 11, color: "var(--z-muted)", lineHeight: 1.5 }}>
                  Already at or above this step today.
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>,
    toggle,
  );
}
