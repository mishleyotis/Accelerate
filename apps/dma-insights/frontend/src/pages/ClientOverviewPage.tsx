/**
 * D1 ClientOverview — ported 1:1 from prototype
 * (standalone-src/src/pages-d1-overview.jsx · ClientOverview).
 *
 * Section order, class vocabulary, layout grid, and copy match the
 * prototype exactly. Mock-data reads (DMA.PILLARS / DMA.LEADERSHIP /
 * DMA.THOUGHT_LEADERSHIP / DMA.getEvidence) are replaced with the
 * `useEntityOverview` and `useEntityPlatforms` hooks; fields without a
 * backend producer yet render an honest empty state instead of
 * fabricated values.
 */
import { useEffect, useMemo, useState } from "react";
import { useRoute } from "@/lib/hash-router";
import {
  useEntityOverview,
  useEntityPlatforms,
  useExportScorecard,
  useRequestNewRun,
} from "@/lib/queries";
import type { EntityOverviewResponse } from "@/lib/queries";
import { maturityClass, maturityHex, maturityLabel } from "@/lib/maturity";
import { healHq, healSubvertical } from "@/lib/heal";
import { stripMd } from "@/lib/text";
import { useUiStore } from "@/store/ui";
import { EmptyState, FreshnessDot, Icon, Spinner } from "@/components/utils";
import { EvidenceTierCard } from "@/components/cards/EvidenceTierCard";
import type { EvidenceSummaryData } from "@/components/cards/EvidenceTierCard";
import { CoverageByPillarCard } from "@/components/cards/CoverageByPillarCard";
import type { CoverageStatsData } from "@/components/cards/CoverageByPillarCard";
import { FinancialTrajectoryCard } from "@/components/cards/FinancialTrajectoryCard";
import type { TrajectoryData } from "@/components/cards/FinancialTrajectoryCard";
import { CeilingEstimateCard } from "@/components/cards/CeilingEstimateCard";
import type { CeilingBand } from "@/components/cards/CeilingEstimateCard";
import { SentimentCard } from "@/components/cards/SentimentCard";
import type { SentimentData } from "@/components/cards/SentimentCard";

const PILLARS = [
  { id: "P1", short: "Strategy" },
  { id: "P2", short: "Customer" },
  { id: "P3", short: "Operations" },
  { id: "P4", short: "Data & Tech" },
];

const PLATFORM_META: Record<string, { name: string; features: string }> = {
  salesforce: { name: "Salesforce", features: "Agentforce · Data Cloud · FSC · Marketing" },
  databricks: { name: "Databricks", features: "Mosaic AI · Lakehouse · Delta" },
  tableau:    { name: "Tableau",    features: "Cloud · Pulse · Lineage" },
  twilio:     { name: "Twilio",     features: "Engage · Flex · Verify" },
  ncino:      { name: "nCino",      features: "Origination · Servicing · Banking AI" },
};

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)(\/.*)?$/);
  return m ? m[1] : null;
}

export function ClientOverviewPage(): JSX.Element {
  const { path, query } = useRoute();
  const displayId = getDisplayId(path);
  // 2026-06-06 QA-1: propagate `?run=<request_id>` to data hooks so the
  // page renders THE selected run, not always the latest ACTIVE run.
  // Before: ClientBar selected an old run, URL got `?run=REQ-OLD`,
  // hooks ignored it, page rendered current data while the bar showed
  // the old run -- a serious audit-trust violation.
  const selectedRun = typeof query.run === "string" ? query.run : null;
  const setIpSurface = useUiStore((s) => s.setIpSurface);
  const setIpOpen = useUiStore((s) => s.setIpOpen);
  const pushToast = useUiStore((s) => s.pushToast);
  const audience = useUiStore((s) => s.audience);

  const overviewQ = useEntityOverview(displayId, selectedRun);
  const platformsQ = useEntityPlatforms(displayId, selectedRun);
  const [findingOpen, setFindingOpen] = useState<string | null>(null);
  const [scqaExp, setScqaExp] = useState(false);

  useEffect(() => {
    if (overviewQ.data?.entity?.display_id) {
      setIpSurface("why_now", { ref: overviewQ.data.entity.display_id });
    }
  }, [overviewQ.data?.entity?.display_id, setIpSurface]);

  if (overviewQ.isLoading) {
    return <div className="page-loading"><Spinner /> Loading overview…</div>;
  }
  if (overviewQ.error || !overviewQ.data) {
    return <EmptyState title="Couldn't load overview" body={(overviewQ.error as Error)?.message} />;
  }
  const { entity, run, firmographics } = overviewQ.data;
  // Defensive: a partial/empty payload (no `entity`) must degrade to an
  // honest empty state, never crash the page on `entity.name`.
  if (!entity) {
    return <EmptyState title="Couldn't load overview" body="This entity has no overview data yet." />;
  }
  // Run-state-aware empty messaging — distinguish "never assessed" from
  // "ingested but waiting on catalogue" from "in progress". The prior
  // single "no completed DMA yet" copy lied to operators who had JUST
  // ingested a real package and saw the same screen as an empty entity.
  if (!run) {
    return (
      <EmptyState
        title={`${entity.name} has no completed DMA yet`}
        body="The bot will populate this view once the next assessment ingests."
      />
    );
  }
  const runStatus = (run.status || "").toUpperCase();
  if (runStatus === "PENDING_REVIEW") {
    const cv = run.ccg_catalog_version || "";
    return (
      <EmptyState
        title={`${entity.name} assessment awaiting catalogue load`}
        body={cv
          ? `The run was ingested but references catalogue ${cv}. Run ccg_loader --version ${cv} (Admin → Catalogue), then refresh — the scores will flip ACTIVE automatically.`
          : "The run was ingested but the catalogue it references hasn't been loaded yet. Load it via Admin → Catalogue, then refresh."}
      />
    );
  }
  if (runStatus === "IN_PROGRESS") {
    return (
      <EmptyState
        title={`${entity.name} assessment in progress`}
        body="Scores + insights populate as the batch completes. This view auto-refreshes every 30s."
      />
    );
  }

  // overall_score is now server-computed (top-level of the overview
  // response). Fall back to entity/run/firmographics shapes only for
  // older payloads, then to mean(pillar_scores) when nothing is set.
  const overviewData = overviewQ.data as {
    overall_score?: number | null;
    pillar_scores?: Array<{ pillar_id: string; score: number }>;
  };
  const fallbackOverall = (() => {
    const ps = overviewData.pillar_scores ?? [];
    if (!ps.length) return null;
    const nums = ps.map((p) => p.score).filter((n) => typeof n === "number");
    if (!nums.length) return null;
    return Number((nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(2));
  })();
  const overall = overviewData.overall_score
    ?? (entity as { overall_score?: number | null }).overall_score
    ?? (run as { overall_score?: number | null }).overall_score
    ?? fallbackOverall;
  // 2026-06-06 QA-M1: backend EntityOverviewResponse.pillar_scores is
  // now typed (Batch 9) so we drop the unsafe cast and read directly.
  // Each row carries score + peer_median + subcaps_scored + peer_benchmarked.
  const rawPillarScores: Array<{
    pillar_id: string;
    score: number | null;
    peer_median: number | null;
  }> = overviewQ.data?.pillar_scores
    ?? Object.entries(
      (firmographics as { pillar_scores?: Record<string, number> } | null)?.pillar_scores ?? {},
    ).map(([k, v]) => ({ pillar_id: k, score: v as number, peer_median: null }));
  const pillarScoreMap: Record<string, number> = Object.fromEntries(
    rawPillarScores
      .filter((p): p is { pillar_id: string; score: number; peer_median: number | null } => p.score != null)
      .map((p) => [p.pillar_id, p.score]),
  );
  // QA-M1: real peer median lookup. `null` per pillar means no peer
  // data for that pillar -- the bar renders without the peer marker
  // rather than showing the pre-fix `score + 0.3` synthetic value.
  const peerMedianMap: Record<string, number | null> = Object.fromEntries(
    rawPillarScores.map((p) => [p.pillar_id, p.peer_median]),
  );

  const subv = (entity as { subvertical?: string | null }).subvertical;
  const hq = healHq((entity as { hq_region?: string | null; hq?: string | null }).hq_region
                    ?? (entity as { hq?: string | null }).hq);
  // Prototype subtitle: "Farm Credit · Enfield, CT · $11.3B assets ·
  // Assessment Jun 1, 2026" — the subvertical renders as its human label
  // (never the raw "RB"/"AM" code), and segments the data doesn't carry are
  // DROPPED, never rendered as "— · —" placeholder noise (2026-06-10
  // parity click-through found the junk dashes on every entity whose
  // enrich jobs hadn't run yet).
  const subvLabel = subv ? healSubvertical(subv) : null;
  const subParts = [subvLabel, hq].filter(
    (v): v is string => !!v && v.trim() !== "" && v.trim() !== "—",
  );

  type LeaderRow = {
    id?: string; name?: string; title?: string;
    tenure_months?: number; tenure?: number | null;
    recent_hire?: boolean; gap_flag?: boolean; critical_role?: boolean;
    background?: string;
    clay?: { email?: string; linkedin?: string };
  };
  type TLRow = {
    id?: string; type?: string; date?: string; title?: string;
    excerpt?: string; author?: string; url?: string;
  };
  const leadership: LeaderRow[] = (firmographics as { leadership?: LeaderRow[] } | null)?.leadership ?? [];
  const thoughtLeadership: TLRow[] = (firmographics as { thought_leadership?: TLRow[] } | null)?.thought_leadership ?? [];

  const ossEntries: OssEntry[] = useMemo(() => {
    const cards = platformsQ.data?.cards ?? [];
    return cards
      .map((c) => ({
        pid: c.platform_id,
        score: Math.round(c.fit_score),
        opportunity: (c as { opportunity_md?: string }).opportunity_md ?? null,
        evidence: (c as { evidence_ids?: string[] }).evidence_ids ?? [],
      }))
      .sort((a, b) => b.score - a.score);
  }, [platformsQ.data]);

  const whyNow = overviewQ.data.why_now_signals ?? [];
  const findings = (overviewQ.data.top_findings ?? []).map((f, i) => {
    // deepen_narrative emits the full W/W/SW shape {name, what, why, so_what,
    // theme, magnitude, score, peer_median, subcap_id, platforms, evidence};
    // older shapes carried only {title|name, body}. Read all of them.
    const ff = f as {
      name?: string; title?: string; body?: string; score?: number;
      peer_median?: number; subcap_id?: string; platforms?: string[]; evidence?: string[];
      what?: string; why?: string; so_what?: string; theme?: string; magnitude?: string;
    };
    const score = typeof ff.score === "number" && ff.score > 0 ? ff.score : null;
    const peer = typeof ff.peer_median === "number" && ff.peer_median > 0 ? ff.peer_median : null;
    const body = ff.body
      ?? (score != null
        ? `Scores ${score.toFixed(1)}/5${peer != null ? ` vs peer median ${peer.toFixed(1)}` : ""}.`
        : "Priority capability gap — open the heatmap for the subcap-level detail.");
    return {
      id: `F-${String(i + 1).padStart(2, "0")}`,
      title: ff.name ?? ff.title ?? ff.subcap_id ?? "—",
      body,
      what: ff.what ?? null,
      why: ff.why ?? null,
      soWhat: ff.so_what ?? null,
      theme: ff.theme ?? null,
      magnitude: ff.magnitude ?? null,
      score, peer,
      subcapId: ff.subcap_id ?? null,
      platforms: ff.platforms ?? [],
      evidence: ff.evidence ?? (ff.subcap_id ? [ff.subcap_id] : []),
    };
  });
  // "Evidence & benchmarks" payload slices (plan 4.6; server-derived).
  const fh = (firmographics as { financial_highlights?: { trajectory?: TrajectoryData } } | null)
    ?.financial_highlights ?? null;
  const trajectory: TrajectoryData | null = fh?.trajectory ?? null;
  const evidenceSummary = (overviewQ.data.evidence_summary ?? null) as EvidenceSummaryData | null;
  const coverageStats = (overviewQ.data.coverage_stats ?? null) as CoverageStatsData | null;
  const uncertaintyBands = (overviewQ.data.uncertainty_bands ?? null) as Record<string, CeilingBand> | null;
  // Read the TOP-LEVEL card-ready projection the backend exposes (normalized
  // {employee[], customer[], nps[], qualitative[]}), not the nested raw
  // firmographics.sentiment blob — the raw {sources:[…]} shape lacks the
  // scorecard arrays the card renders, which blanked most cards (2026-07-09 QA).
  // Fall back to the nested blob for older payloads.
  const sentiment = ((overviewQ.data.sentiment as SentimentData | null)
    ?? (firmographics as { sentiment?: SentimentData } | null)?.sentiment ?? null);

  return (
    <div className="page" data-page="overview" data-source="api">
      <div className="page-head" style={{ marginBottom: 18 }}>
        <div>
          <div className="eyebrow">Entity intelligence</div>
          <h1 style={{ marginBottom: 4 }}>{entity.name}</h1>
          <div className="sub">
            {subParts.map((v) => `${v} · `).join("")}Assessment{" "}
            {run.completed_at ? new Date(run.completed_at).toLocaleDateString() : "pending"}
          </div>
        </div>
        <div className="actions">
          {/* 2026-06-06 QA-M2: wire to real backend mutations. Pre-fix
              these buttons pushed "success" toasts without any backend
              call -- the AE believed the scorecard generated / rerun
              queued when nothing happened server-side. */}
          <ScorecardButton displayId={displayId} entityName={entity.name} pushToast={pushToast} />
          <RerunButton displayId={displayId} entityName={entity.name}
                       parentRequestId={run.request_id} pushToast={pushToast} />
          <button type="button" className="btn btn-secondary"
                  onClick={() => { setIpSurface("why_now", { ref: displayId ?? "" }); setIpOpen(true); }}>
            <Icon name="sparkle" size={13} /> Meeting prep
          </button>
        </div>
      </div>

      {/* Source-data quality banner (2026-06-25 contamination remediation): an
          honest unverified-source notice so an AE never reads a different
          institution's findings under this client's name. Null on clean entities. */}
      <SourceQualityBanner entityName={entity.name} dataQuality={overviewQ.data.data_quality} />

      <div className="card" style={{ marginBottom: 18, padding: "20px 22px" }}>
        <div className="sidebar-split" style={{ gap: 28, alignItems: "stretch" }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
              <ScoreRing score={overall} />
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span className={`b ${maturityClass(overall)}`}>
                    {(maturityLabel(overall) ?? "—").toUpperCase()}
                  </span>
                  {run.evidence_mode ? (
                    <span className="b b-ph1">EVIDENCE · {run.evidence_mode}</span>
                  ) : null}
                  {run.completed_at ? (
                    <FreshnessDot at={run.completed_at} withLabel />
                  ) : null}
                  {run.data_source === "DRIVE_PARSE" ? (
                    <span className="b b-ph0">DRIVE PARSE</span>
                  ) : null}
                </div>
                <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.5 }}>
                  Overall maturity {overall != null ? overall.toFixed(1) : "—"} / 5
                  {Object.keys(pillarScoreMap).length === 4 ? (
                    <> · gap concentrated in {(() => {
                      const sorted = Object.entries(pillarScoreMap).sort((a, b) => a[1] - b[1]);
                      return `${sorted[0][0]} ${sorted[0][1].toFixed(1)}`;
                    })()}</>
                  ) : null}.
                </div>
              </div>
            </div>

            <PillarBars pillars={PILLARS} scoreMap={pillarScoreMap}
                        peerMedianMap={peerMedianMap} displayId={displayId} run={selectedRun} />
          </div>

          <div style={{ background: "var(--z-lav)", borderRadius: 12, padding: 16 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Firmographics</div>
            <FirmographicsRows firm={firmographics ?? null} />
          </div>
        </div>
      </div>

      <WhyNowStrip displayId={displayId} signals={whyNow} audience={audience} />


      <SCQACard
        entity={{ name: entity.name, subvertical: subv ?? "", overall }}
        narrative={overviewQ.data.narrative as { scqa_md?: string } | null}
        expanded={scqaExp}
        onToggle={() => setScqaExp((v) => !v)}
      />

      <OpportunitySurfaceStrip displayId={displayId} ossEntries={ossEntries} />

      <div className="lead-split" style={{ marginBottom: 18 }}>
        <TopFindingsCard findings={findings} openFinding={findingOpen} setOpenFinding={setFindingOpen} displayId={displayId} />
        <LeadershipPanel audience={audience} leadership={leadership} />
      </div>

      {/* Evidence & benchmarks — the five deep cards (proto df85cc41 /
          a34d5122), fed by derive_evidence_surfaces + derive_financials +
          derive_sentiment. Sentiment + ceilings are internal-only. */}
      <div className="section-label" style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "4px 0 12px" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--z-dark)", textTransform: "uppercase", letterSpacing: ".06em" }}>Evidence &amp; benchmarks</span>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>derived from scoring workbook · evidence index · uncertainty register</span>
      </div>
      <div className="cards-grid-3" style={{ marginBottom: 16 }}>
        <FinancialTrajectoryCard data={trajectory} />
        <CoverageByPillarCard data={coverageStats} />
        <EvidenceTierCard data={evidenceSummary} />
      </div>
      {audience !== "customer" ? (
        <div className="cards-grid-2" style={{ marginBottom: 18 }}>
          <CeilingEstimateCard data={uncertaintyBands} audience={audience} displayId={displayId} />
          <SentimentCard data={sentiment} audience={audience} />
        </div>
      ) : null}

      {audience !== "customer" ? (
        <ThoughtLeadershipPanel rows={thoughtLeadership} />
      ) : null}

    </div>
  );
}


function ScoreRing({ score, size = 110 }: { score: number | null; size?: number }): JSX.Element | null {
  if (score == null) return null;
  const r = size * 0.34;
  const c = 2 * Math.PI * r;
  const pct = score / 5;
  return (
    <div className="score-ring" style={{ width: size, height: size, flexShrink: 0, position: "relative" }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--z-sep)" strokeWidth={6} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r}
                stroke={maturityHex(score)} strokeWidth={6} fill="none"
                strokeDasharray={c} strokeDashoffset={c * (1 - pct)} strokeLinecap="round"
                transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div style={{
        position: "absolute", textAlign: "center", inset: 0,
        display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center",
      }}>
        <div style={{ color: maturityHex(score), fontSize: size * 0.32, fontWeight: 300, lineHeight: 1 }}>
          {score.toFixed(1)}
        </div>
      </div>
    </div>
  );
}

/**
 * Pillar score bars. Each bar drills into the heatmap scoped to that pillar —
 * the prototype contract (06_pages_b.js: `pbar onClick → navigate(heatmap,
 * {pillar})`) that the 1:1 port had dropped, leaving the bars inert. The
 * production heatmap reads the pillar focus from `?zoom=pillar:{id}`
 * (HeatmapPage `drilledPillar`), so we deep-link there. Keyboard-operable for
 * a11y parity with the other D1 drill tiles (WhyNowStrip).
 */
export function PillarBars({
  pillars, scoreMap, peerMedianMap, displayId, run,
}: {
  pillars: Array<{ id: string; short: string }>;
  scoreMap: Record<string, number>;
  peerMedianMap: Record<string, number | null>;
  displayId: string | null;
  run?: string | null;
}): JSX.Element {
  const navigate = useRoute().navigate;
  const drill = (pid: string): void => {
    if (!displayId) return;
    const q = `zoom=pillar:${pid}${run ? `&run=${encodeURIComponent(run)}` : ""}`;
    navigate(`/clients/${displayId}/heatmap?${q}`);
  };
  return (
    <div>
      {pillars.map((p) => {
        const s = scoreMap[p.id];
        // 2026-06-06 QA-M1: peer is the REAL peer_median from subcap_scores
        // AVG via the overview endpoint, not the pre-fix synthetic `s + 0.3`.
        // `null` when no peer data exists for this pillar -- the marker + delta
        // render empty rather than fabricating a value.
        const peer = peerMedianMap[p.id];
        const w = s != null ? (s / 5) * 100 : 0;
        const peerL = peer != null ? (peer / 5) * 100 : 0;
        const delta = s != null && peer != null ? s - peer : null;
        return (
          <div className="pbar" key={p.id}
               role={displayId ? "button" : undefined}
               tabIndex={displayId ? 0 : undefined}
               style={{ cursor: displayId ? "pointer" : "default" }}
               title={displayId ? `Open ${p.id} in the heatmap` : undefined}
               onClick={() => drill(p.id)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drill(p.id); } }}>
            <div className="pbar-name">{p.id} · {p.short}</div>
            <div className="pbar-track">
              {s != null ? (
                <div className="pbar-fill" style={{ width: `${w}%`, background: maturityHex(s) }} />
              ) : null}
              {peer != null ? (
                <div className="pbar-peer" style={{ left: `calc(${peerL}% - 1px)` }} title={`Peer ${peer.toFixed(1)}`} />
              ) : null}
            </div>
            <div className="pbar-score">{s != null ? s.toFixed(1) : "—"}</div>
            {delta != null ? (
              <div className="pbar-delta" style={{ color: delta < 0 ? "var(--z-below)" : "var(--z-mid)" }}>
                {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}
              </div>
            ) : <div className="pbar-delta">—</div>}
          </div>
        );
      })}
      <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)", display: "flex", gap: 14, paddingLeft: 122 }}>
        <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 12, height: 4, background: "var(--z-teal)", borderRadius: 2 }} /> Entity</span>
        <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 2, height: 10, background: "var(--z-dpur)" }} /> Peer median</span>
      </div>
    </div>
  );
}

function FirmographicsRows({ firm }: { firm: Record<string, unknown> | null }): JSX.Element {
  // 2026-06-11 corpus QA ("this is dynamic"): the fixed 6-row template
  // showed em-dashes while the REPORTS' data sat unrendered in
  // financial_highlights prose (95/95 populated: "3-Year CAGR: ~10.4%",
  // "Trend Classification: ACCELERATING", asset lines) and in
  // parser-extracted facts beyond the whitelist. The card now:
  //   1. keeps the wireframe's canonical rows, additionally MINING
  //      financial_highlights lines/metrics for Assets/CAGR/Trend;
  //   2. appends a dynamic row for EVERY other scalar fact the
  //      backend returns (humanized label) — whatever a given report
  //      contains is what renders;
  //   3. only then shows "—" for canonical gaps (diagnostic on
  //      genuinely silent sources; Gemini gap-fill deepens post-deploy).
  const f = (firm ?? {}) as Record<string, unknown>;
  const fh = (f.financial_highlights ?? null) as
    { lines?: unknown[]; metrics?: Record<string, unknown> } | null;
  const fhText = [
    ...(Array.isArray(fh?.lines) ? fh!.lines!.map(String) : []),
    ...(fh?.metrics ? Object.entries(fh.metrics).map(([k, v]) => `${k}: ${String(v)}`) : []),
  ].join(" | ");
  const mine = (re: RegExp): string | null => {
    const m = fhText.match(re);
    return m ? m[1].trim() : null;
  };
  const fmt = (v: unknown): string => (v == null || v === "" ? "—" : String(v));
  const fmtNum = (v: unknown): string => {
    if (v == null || v === "") return "—";
    const n = typeof v === "number" ? v : Number(v);
    return Number.isFinite(n) ? n.toLocaleString() : String(v);
  };
  const fmtFootprint = (v: unknown): string =>
    !v ? "—" : Array.isArray(v) ? v.join(" · ") : String(v);
  // Compact USD: $10.2B / $529.0B / $3.0M — never a raw 13-digit number.
  const fmtUsd = (v: unknown): string | null => {
    const n = typeof v === "number" ? v : Number(v);
    if (!Number.isFinite(n) || n <= 0) return null;
    if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
    return `$${n.toLocaleString()}`;
  };

  const assets = (f.total_assets as string)
    ?? (f.aum_usd != null ? fmtUsd(f.aum_usd) : null)
    ?? mine(/(?:Total\s+)?Assets?[^|:]*:\s*([^|]+)/i);
  // The scale figure isn't always balance-sheet assets — the healer records
  // its basis (AUM, market cap, premium, servicing UPB…) so a broker's premium
  // or a REIT's market cap is labelled honestly instead of "Assets".
  const SCALE_LABEL: Record<string, string> = {
    total_assets: "Assets", aum: "AUM", aua: "AUA", earning_assets: "Earning Assets",
    market_cap: "Market Cap", premium_volume: "Premium", servicing_upb: "Servicing UPB",
    loan_portfolio: "Loan Portfolio", policyholder_surplus: "Surplus", size_tier: "Size",
  };
  const scaleLabel = SCALE_LABEL[(f.aum_basis as string) ?? ""] ?? "Assets";
  const cagr = (f.cagr as string) ?? mine(/CAGR[^:|]*:\s*([^|]+)/i);
  const trend = (f.trend as string) ?? mine(/Trend(?:\s+Classification)?\s*:\s*([A-Za-z ]+)/i);
  // Acquisitions renders as a COUNT (0 when none) — never a bare true/false
  // (2026-07-06 operator report). A list → its length; a number → itself; a
  // bare presence bool or null → 0.
  const acqCount = ((): number => {
    const a = f.acquisitions;
    if (Array.isArray(a)) return a.length;
    if (typeof a === "number" && Number.isFinite(a)) return a;
    return 0;
  })();
  const canonical: Array<[string, string]> = [
    [scaleLabel, fmt(assets)],
    ["Employees", fmtNum(f.employees_approx ?? f.headcount)],
    ["Branches", fmtNum(f.branches)],
    ["CAGR", fmt(cagr)],
    ["Trend", fmt(trend)],
    ["Regulator", fmt(f.primary_regulator ?? f.regulator)],
    ["Footprint", fmtFootprint(f.footprint ?? f.hq ?? f.hq_address)],
    ["Acquisitions", String(acqCount)],
  ];
  const SHOWN = new Set([
    "total_assets", "aum_usd", "employees_approx", "headcount", "branches",
    "cagr", "trend", "primary_regulator", "regulator", "footprint", "hq",
    "hq_address", "revenue_usd", "acquisitions",
  ]);
  const META = new Set([
    "leadership", "thought_leadership", "sentiment", "narrative_md",
    "financial_highlights", "parsed_facts", "clay_synced_at", "tl_synced_at",
    "sentiment_synced_at", "pillar_scores",
  ]);
  const dynamic: Array<[string, string]> = Object.entries(f)
    .filter(([k, v]) =>
      !SHOWN.has(k) && !META.has(k)
      // any *_basis / *_src key is labelling/provenance metadata (tokens like
      // "report_prose", "trajectory_prose", fin_src) — never an AE-facing row
      // (2026-07-06 operator report: "remove fin src / report_prose").
      && !k.endsWith("_basis") && !k.endsWith("_src")
      && v != null && v !== ""
      // booleans are not meaningful firmographic rows (they render as
      // "true/false"); only real strings/numbers surface.
      && (typeof v === "string" || typeof v === "number")
      && String(v).trim().toLowerCase() !== "report_prose")
    .slice(0, 10)
    .map(([k, v]) => [
      k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      String(v),
    ]);
  const rows = [...canonical, ...dynamic];
  return (
    <div data-testid="firmographics-rows">
      {rows.map(([k, v]) => (
        <div key={k} className="row" style={{
          justifyContent: "space-between", padding: "5px 0",
          borderBottom: "1px solid rgba(229,231,235,.6)", fontSize: 12,
        }}>
          <span style={{ color: "var(--z-muted)" }}>{k}</span>
          <span style={{ color: "var(--z-dark)", fontWeight: 500, textAlign: "right",
                         maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis",
                         whiteSpace: "nowrap" }} title={v}>{v}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Source-data quality banner (2026-06-25 contamination remediation). When the
 * assessment's analytical content could not be confirmed as belonging to this
 * entity — the audit's beacon-bank case, whose identity is correct but whose
 * ticker / run-id / prose are a different institution (BB&T/Berkshire) — surface
 * an honest unverified-source notice so an AE never reads another company's
 * findings under this client's name. Renders nothing on clean entities, so it is
 * safe to mount unconditionally.
 */
export function SourceQualityBanner({
  entityName, dataQuality,
}: {
  entityName: string;
  dataQuality: EntityOverviewResponse["data_quality"];
}): JSX.Element | null {
  const dq = dataQuality?.source_misattribution;
  if (!dq) return null;
  const mk = dataQuality?.misattribution_markers;
  const foreign = [...(mk?.foreign_entities ?? []), ...(mk?.foreign_tickers ?? [])]
    .filter(Boolean);
  return (
    <div className="card" data-source-misattribution={dq}
         style={{ marginBottom: 18, padding: "13px 18px",
                  borderLeft: "3px solid #c0392b", background: "#fdecea" }}>
      <strong>⚠ Source data unverified.</strong>{" "}
      {dq === "A"
        ? `This assessment's analytical content could not be confirmed as ${entityName}'s${
            foreign.length ? ` — it references ${foreign.join(", ")}` : ""
          }. Treat the findings as provisional pending re-ingest of the correct source package.`
        : "A foreign-looking identifier was detected and is pending review; firmographics may reflect a holding company."}
    </div>
  );
}

const WN_CAT: Record<string, { icon: string; color: string }> = {
  core_migration: { icon: "refresh", color: "var(--z-teal)" },
  leadership: { icon: "users", color: "var(--z-dpur)" },
  hiring: { icon: "users", color: "var(--z-mid)" },
  regulatory: { icon: "shield", color: "var(--z-org)" },
  market: { icon: "stack", color: "var(--z-mid)" },
};
const WN_STRENGTH: Record<string, string> = {
  STRONG: "b-teal", LEADING: "b-purple", SUPPORTING: "b-muted",
};
const WN_CLAIM: Record<string, string> = {
  FACT: "b-teal", INFERENCE: "b-purple", HYPOTHESIS: "b-org",
};

export function WhyNowStrip({
  displayId, signals, audience,
}: {
  displayId: string | null;
  signals: Array<Record<string, unknown>>;
  audience?: string;
}): JSX.Element {
  const navigate = useRoute().navigate;
  const openDrawer = useUiStore((s) => s.openDrawer);
  // First signal expanded by default (prototype v4 · Standalone 4).
  const [openIdx, setOpenIdx] = useState<number>(0);
  if (signals.length === 0) {
    return (
      <div className="card" style={{ marginBottom: 18, padding: 16, color: "var(--z-muted)", fontSize: 12.5 }} data-source="api-empty">
        Why-now signals will populate once the timeline + issue register ingest.
      </div>
    );
  }
  const isCust = audience === "customer";
  const str = (v: unknown): string | null => (typeof v === "string" && v.trim() !== "" ? v : null);
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: "var(--ph0-lt)", color: "var(--ph0)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="sparkle" size={14} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>Why now signals</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {signals.length} trigger{signals.length === 1 ? "" : "s"} · click any signal to drill into the evidence
          </div>
        </div>
        <button type="button" className="btn btn-tertiary btn-sm"
                onClick={() => displayId && navigate(`/clients/${displayId}/context`)}>
          View timeline <Icon name="arrow-r" size={11} />
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {signals.map((sig, i) => {
          // 14-field deep shape (deepen_narrative): label/category/strength/
          // window/confidence/claim/detail/metric/peer_context/play/risk/
          // evidence/timeline/impact — every field renders defensively.
          const s = sig as Record<string, unknown>;
          const eids = (Array.isArray(s.evidence) ? s.evidence : [])
            .filter((e): e is string => typeof e === "string");
          const category = str(s.category) ?? "market";
          const cat = WN_CAT[category] ?? WN_CAT.market;
          const strength = str(s.strength);
          const window_ = str(s.window);
          const label = stripMd(str(s.label) ?? "Signal");
          const impact = stripMd(String(str(s.impact) ?? str(s.detail) ?? str(s.text) ?? "")
            .replace(/(?:\.\s*)?\bWindow:\s[^.]*\.?\s*$/, ".").replace(/^\.$/, "").trim());
          // Customer view keeps positive framing (impact), never the internal
          // detail/metric/peer/risk/claim rationale.
          const body = stripMd(isCust ? impact : (String(str(s.detail) ?? impact) || impact));
          const isOpen = openIdx === i;
          const timeline = (typeof s.timeline === "object" && s.timeline !== null
            ? s.timeline : null) as Record<string, unknown> | null;
          return (
            <div key={str(s.id) ?? i} style={{
              border: `1px solid ${isOpen ? "var(--ph0-bd)" : "var(--z-sep)"}`,
              borderRadius: 10, overflow: "hidden",
              background: isOpen ? "var(--ph0-lt)" : "#fff",
              transition: "background 140ms var(--ease), border-color 140ms var(--ease)",
            }}>
              {/* clickable header */}
              <button type="button" aria-expanded={isOpen}
                      onClick={() => setOpenIdx((o) => (o === i ? -1 : i))}
                      style={{ width: "100%", display: "flex", alignItems: "center", gap: 11, padding: "12px 14px", background: "none", border: 0, cursor: "pointer", textAlign: "left" }}>
                <span style={{ width: 30, height: 30, borderRadius: 8, background: cat.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon name={cat.icon} size={15} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row" style={{ gap: 7, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>{label}</span>
                    {!isCust && strength ? <span className={`b ${WN_STRENGTH[strength] ?? "b-muted"}`}>{strength}</span> : null}
                  </div>
                  {!isOpen && impact ? (
                    <div className="txt-fit-1" style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 3, lineHeight: 1.4 }}>{impact}</div>
                  ) : null}
                </div>
                {window_ ? (
                  <span className="b" style={{ background: "rgba(115,91,161,.14)", color: "var(--z-dpur)", flexShrink: 0 }} title="Urgency window">{window_}</span>
                ) : null}
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={15} style={{ color: "var(--z-muted)", flexShrink: 0 }} />
              </button>
              {/* expanded drilldown */}
              {isOpen ? (
                <div style={{ padding: "0 14px 14px 55px" }}>
                  {body ? <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6, marginBottom: 10 }}>{body}</div> : null}
                  {!isCust && str(s.metric) ? (
                    <div className="f-mono" style={{ fontSize: 11.5, color: "var(--z-dark)", background: "#fff", border: "1px solid var(--z-sep)", borderRadius: 6, padding: "7px 10px", marginBottom: 10, display: "inline-block" }}>{str(s.metric)}</div>
                  ) : null}
                  {timeline && (str(timeline.date) || str(timeline.event)) ? (
                    <button type="button"
                            onClick={() => displayId && navigate(`/clients/${displayId}/context`)}
                            style={{ display: "flex", alignItems: "center", gap: 7, background: "none", border: 0, padding: 0, cursor: "pointer", marginBottom: 12 }}>
                      <Icon name="timeline" size={12} style={{ color: "var(--ph0)" }} />
                      {str(timeline.date) ? <span className="f-mono" style={{ fontSize: 11, color: "var(--z-mid)" }}>{String(timeline.date).slice(0, 10)}</span> : null}
                      {str(timeline.event) ? <span style={{ fontSize: 11.5, color: "var(--z-body)" }}>{str(timeline.event)}</span> : null}
                      <Icon name="arrow-r" size={10} style={{ color: "var(--z-muted)" }} />
                    </button>
                  ) : null}
                  {str(s.play) ? (
                    <div style={{ background: "rgba(39,187,175,.1)", borderLeft: "3px solid var(--z-teal)", borderRadius: "0 6px 6px 0", padding: "8px 12px", marginBottom: 8 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-teal)", textTransform: "uppercase", marginBottom: 2 }}>The play</div>
                      <div style={{ fontSize: 12, color: "var(--z-dark)", lineHeight: 1.55, fontWeight: 500 }}>{str(s.play)}</div>
                    </div>
                  ) : null}
                  {!isCust && str(s.peer_context) ? (
                    <div style={{ fontSize: 11.5, color: "var(--z-muted)", lineHeight: 1.5, margin: "6px 0" }}>
                      <strong style={{ color: "var(--z-body)" }}>Peer context · </strong>{str(s.peer_context)}
                    </div>
                  ) : null}
                  {!isCust && str(s.risk) ? (
                    <div style={{ background: "rgba(214,109,42,.08)", borderLeft: "3px solid var(--z-org)", borderRadius: "0 6px 6px 0", padding: "8px 12px", marginBottom: 10 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-org)", textTransform: "uppercase", marginBottom: 2 }}>If ignored</div>
                      <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.55 }}>{str(s.risk)}</div>
                    </div>
                  ) : null}
                  {/* footer: evidence + claim/confidence */}
                  <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                    {eids.length > 0 ? (
                      <>
                        <span style={{ fontSize: 9.5, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Evidence</span>
                        {eids.slice(0, 6).map((e) => (
                          <button key={e} type="button" className="chip purple"
                                  onClick={(ev) => { ev.stopPropagation(); openDrawer("evidence", { eId: e, eIds: eids, displayId, origin: "why-now" }); }}>
                            {e}
                          </button>
                        ))}
                      </>
                    ) : (
                      <span style={{ fontSize: 11, color: "var(--z-muted)", fontStyle: "italic" }}>No direct evidence yet — confirm in first meeting</span>
                    )}
                    <span style={{ flex: 1 }} />
                    {!isCust && str(s.claim) ? <span className={`b ${WN_CLAIM[str(s.claim) as string] ?? "b-muted"}`}>{str(s.claim)}</span> : null}
                    {!isCust && str(s.confidence) ? <span className="b b-muted">{str(s.confidence)} confidence</span> : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Human-readable subvertical label for narrative copy. Codes like "CL"
// or "RB" are operational shorthand — they read as gibberish ("a cl
// institution") when interpolated into prose. Mirrors the prototype's
// SUBVERTICAL_LABEL dict + falls back to a generic label so we never
// leak an opaque code into AE-facing text.
const SUBVERTICAL_LABELS: Record<string, string> = {
  CL: "commercial lender",
  RB: "regional bank",
  CU: "credit union",
  FC: "farm credit institution",
  REIT: "REIT",
  REGIONAL_BANK: "regional bank",
  FARM_CREDIT: "farm credit institution",
  INSURANCE_CARRIER: "insurance carrier",
  INSURANCE_BROKER: "insurance broker",
  WEALTH_RIA: "wealth / RIA firm",
  ASSET_MANAGER: "asset manager",
  FINTECH_SAAS: "fintech / SaaS company",
};
function subverticalLabel(code: string | null | undefined): string {
  if (!code) return "mid-tier financial institution";
  return SUBVERTICAL_LABELS[code.toUpperCase()] ?? "mid-tier financial institution";
}

function SCQACard({
  entity, narrative, expanded, onToggle,
}: {
  entity: { name: string; subvertical: string; overall: number | null };
  narrative: { scqa_md?: string } | null;
  expanded: boolean;
  onToggle: () => void;
}): JSX.Element {
  // narrative.scqa_md is the Assessment_Report.docx-derived prose. When it
  // is absent (workbook-only / prose-light DMA — see DMA_RENDER_VERIFICATION
  // Tier B), we synthesize an intro from the persisted scores. Flagging that
  // synthesis explicitly (badge + data-source) keeps the page honest: it
  // reads as "scores shown, full narrative pending" rather than passing a
  // generated sentence off as the real executive narrative.
  const narrativePending = !narrative?.scqa_md;
  // Wireframe SCQACard contract: COLLAPSED shows only the lead (the
  // situation sentence-or-two); "Read full ↓" expands the rest. The
  // prior render put the ENTIRE scqa_md in the collapsed intro AND
  // appended it again when expanded — the D1 "text wall" from the
  // 2026-06-11 QA audit (page height 3757px vs the wireframe's 2465).
  // HARD length guard (plan 4.3): the derive layer clamps at 4,000 chars,
  // but an older snapshot may still carry a 31K report dump — never render
  // more than the contract allows.
  const scqaMd = useMemo(() => {
    const raw = narrative?.scqa_md ?? "";
    if (raw.length <= 4000) return raw;
    const cut = raw.slice(0, 4000);
    const idx = cut.lastIndexOf(". ");
    return idx > 2000 ? cut.slice(0, idx + 1) : cut;
  }, [narrative?.scqa_md]);
  const paragraphs = useMemo(
    () => splitNarrativeParagraphs(scqaMd),
    [scqaMd],
  );
  // Wireframe parity (proto SCQACard): the COLLAPSED view shows the full
  // opening Situation paragraph running the full card width — not a 320-char
  // snippet (the 2026-07-06 "text doesn't fill the card" report). Only when
  // the whole SCQA is a single un-split paragraph do we clamp the lead so it
  // does not become a text wall, keeping the remainder behind "Read full".
  const fallbackLead = `${entity.name} is a ${subverticalLabel(entity.subvertical)} mid-way through a multi-year digital transformation. Current overall maturity (${entity.overall != null ? entity.overall.toFixed(1) : "—"} / 5).`;
  const lead = paragraphs.length > 1
    ? paragraphs[0]
    : paragraphs.length === 1
      ? clampLead(paragraphs[0])
      : fallbackLead;
  const rest = paragraphs.length > 1
    ? paragraphs.slice(1)
    : paragraphs.length === 1 && paragraphs[0].length > lead.length
      ? [paragraphs[0].slice(lead.length).trim()].filter(Boolean)
      : [];
  return (
    <div className="card" style={{ marginBottom: 18 }}
         data-source={narrativePending ? "narrative-pending" : "api"}>
      <div className="row" style={{ marginBottom: 12 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: "var(--z-ice)", color: "var(--z-mid)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="doc" size={14} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Executive narrative</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {narrativePending
              ? "Scores shown from workbook · full narrative pending"
              : "SCQA · Assessment Report · stored verbatim"}
          </div>
        </div>
        {narrativePending || rest.length === 0 ? null : (
          <button type="button" className="btn btn-tertiary btn-sm" onClick={onToggle}>
            {expanded ? "Collapse ↑" : "Read full ↓"}
          </button>
        )}
      </div>
      <div style={{ fontSize: 14, color: "var(--z-dark)", lineHeight: 1.7 }}>
        <p style={{ margin: 0 }}>
          <span style={{ fontWeight: 600 }}>{entity.name}</span> — <NarrativeText text={lead} />
          {!expanded && rest.length > 0 ? "…" : null}
        </p>
        {expanded
          ? rest.map((para, i) => (
              <p key={i} style={{ margin: "10px 0 0" }}><NarrativeText text={para} /></p>
            ))
          : null}
      </div>
    </div>
  );
}

/** Split DOCX-derived markdown into display paragraphs, stripping
 *  heading markers / list bullets / emphasis tokens that otherwise
 *  render as raw characters. */
function splitNarrativeParagraphs(md: string): string[] {
  return md
    .split(/\n{2,}|\r\n{2,}/)
    .map((p) =>
      p
        .replace(/^#{1,6}\s*/gm, "")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/^[-*•]\s+/gm, "")
        .replace(/\s*\n\s*/g, " ")
        .trim(),
    )
    .filter(Boolean);
}

/** Lead clamp: the first 2 sentences, capped near 320 chars at a
 *  sentence boundary (wireframe collapsed-SCQA scale). */
function clampLead(paragraph: string): string {
  const sentences = paragraph.match(/[^.!?]+[.!?]+(\s|$)/g);
  if (!sentences) return paragraph.slice(0, 320);
  let out = "";
  for (const sent of sentences) {
    if (out && out.length + sent.length > 320) break;
    out += sent;
    if (out.split(/[.!?]+\s/).length > 2) break;
  }
  return (out || paragraph.slice(0, 320)).trim();
}

/** Renders narrative text with E-ID tokens as evidence chips (the
 *  wireframe makes every E-ID a click-through; the URL-param fallback
 *  matches IntelligencePanel's deep-link contract). */
function NarrativeText({ text }: { text: string }): JSX.Element {
  // Canonical E-047 plus the corpus's real id variants ("E0001" dash-less,
  // "E-INT-0002"/"E-B1-001" segmented, "EV-12") — same recognizer as the
  // backend's startup_enrich/_E_ID_RE.
  const parts = text.split(/((?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}|E\d{3,4})/g);
  return (
    <>
      {parts.map((part, i) =>
        /^(?:(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}|E\d{3,4})$/.test(part) ? (
          <button
            key={i}
            type="button"
            className="chip"
            onClick={() => {
              const hash = window.location.hash || "#/";
              const [path, qs = ""] = hash.replace(/^#/, "").split("?");
              const params = new URLSearchParams(qs);
              params.set("drawer", "evidence");
              params.set("e", part);
              window.location.hash = `${path}?${params.toString()}`;
            }}
          >
            {part}
          </button>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

type OssEntry = { pid: string; score: number; opportunity: string | null; evidence: string[] };

function OpportunitySurfaceStrip({
  displayId, ossEntries,
}: {
  displayId: string | null;
  ossEntries: OssEntry[];
}): JSX.Element {
  const navigate = useRoute().navigate;
  if (ossEntries.length === 0) {
    return (
      <div className="card" style={{ marginBottom: 18, padding: 16, color: "var(--z-muted)", fontSize: 12.5 }} data-source="api-empty">
        Per-platform opportunity scores populate once the platforms fit run completes.
      </div>
    );
  }
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: "var(--z-ice)", color: "var(--z-mid)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="platform" size={14} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Opportunity Surface · per platform</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>Composite fit score 0–100</div>
        </div>
        <button type="button" className="btn btn-tertiary btn-sm"
                onClick={() => displayId && navigate(`/clients/${displayId}/platform`)}>
          Open matrix <Icon name="arrow-r" size={11} />
        </button>
      </div>
      <div className="g5">
        {ossEntries.map(({ pid, score, opportunity, evidence }) => {
          const p = PLATFORM_META[pid] ?? { name: pid, features: "" };
          return (
            <div key={pid} className="card-tile clickable"
                 onClick={() => displayId && navigate(`/clients/${displayId}/platform?platform=${encodeURIComponent(pid)}`)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
                    {p.features.split(" · ").slice(0, 2).join(" · ")}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1 }}>{score}</div>
                  <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)" }}>fit score</div>
                </div>
              </div>
              <div className="prog" style={{ height: 5 }}>
                <div className="prog-fill" style={{
                  width: `${score}%`,
                  background: score >= 60 ? "var(--z-teal)" : score >= 35 ? "var(--m-bld)" : "var(--m-act)",
                }} />
              </div>
              {opportunity ? (
                <div style={{ fontSize: 10.5, color: "var(--z-body)", lineHeight: 1.45, marginTop: 8 }}>
                  {opportunity.replace(/\*\*/g, "").slice(0, 160)}
                  {evidence.length ? (
                    <span style={{ color: "var(--z-muted)" }}> · {evidence.length} evidence</span>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface Finding {
  id: string;
  title: string;
  body: string;
  what?: string | null;
  why?: string | null;
  soWhat?: string | null;
  theme?: string | null;
  magnitude?: string | null;
  score?: number | null;
  peer?: number | null;
  subcapId?: string | null;
  platforms: string[];
  evidence: string[];
}

export function TopFindingsCard({
  findings, openFinding, setOpenFinding, displayId,
}: {
  findings: Finding[];
  openFinding: string | null;
  setOpenFinding: (f: string | null) => void;
  displayId: string | null;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  if (findings.length === 0) {
    return (
      <div className="card flush">
        <div className="card-head"><h3>Top findings</h3><span className="b b-muted">0</span></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }} data-source="api-empty">
          Findings populate once the Assessment Report ingests.
        </div>
      </div>
    );
  }
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Top findings</h3>
        <span className="b b-muted">{findings.length}</span>
      </div>
      <div>
        {findings.map((f) => {
          const isOpen = openFinding === f.id;
          const wwsw: Array<[string, string | null | undefined, string]> = [
            ["What", f.what, "var(--z-dark)"],
            ["Why", f.why, "var(--z-body)"],
          ];
          return (
            <div key={f.id} style={{ padding: "12px 16px", borderTop: "1px solid var(--z-sep)" }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}
                   onClick={() => setOpenFinding(isOpen ? null : f.id)}>
                <span className="chip" style={{ marginTop: 1 }}>{f.id}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.35 }}>{f.title}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                    {f.theme ? (
                      <span style={{ fontSize: 10, color: "var(--z-mid)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em" }}>{f.theme}</span>
                    ) : null}
                    {f.magnitude ? (
                      <><span style={{ color: "var(--z-sep)" }}>·</span>
                        <span style={{ fontSize: 11, color: "var(--z-body)" }}>{f.magnitude}</span></>
                    ) : null}
                    {f.score != null ? (
                      <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>
                        {f.score.toFixed(1)}/5{f.peer != null ? ` vs peer ${f.peer.toFixed(1)}` : ""}
                      </span>
                    ) : null}
                  </div>
                </div>
                {f.platforms.map((p) => (
                  <span key={p} className="b b-teal" style={{ marginTop: 1 }}>{p}</span>
                ))}
                {f.evidence.length > 0 ? (
                  <span className="b b-muted">{f.evidence.length} ev</span>
                ) : null}
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={14} style={{ color: "var(--z-muted)", marginTop: 3, flexShrink: 0 }} />
              </div>
              {isOpen ? (
                <div style={{ marginTop: 10, padding: 14, background: "var(--z-bg)", borderRadius: 8 }}>
                  {f.what || f.why ? (
                    wwsw.filter(([, v]) => v).map(([k, v, c]) => (
                      <div key={k} style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 3 }}>{k}</div>
                        <div style={{ fontSize: 12.5, color: c, lineHeight: 1.6 }}>{v}</div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.6 }}>
                      {f.body || <span className="muted">No body text provided.</span>}
                    </div>
                  )}
                  {f.soWhat ? (
                    <div style={{ background: "rgba(39,187,175,.1)", borderLeft: "3px solid var(--z-teal)", borderRadius: "0 6px 6px 0", padding: "9px 12px", marginBottom: f.evidence.length ? 12 : 0 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-teal)", textTransform: "uppercase", marginBottom: 3 }}>So what</div>
                      <div style={{ fontSize: 12.5, color: "var(--z-dark)", lineHeight: 1.6, fontWeight: 500 }}>{f.soWhat}</div>
                    </div>
                  ) : null}
                  {f.evidence.length > 0 ? (
                    <div style={{ display: "flex", gap: 4, marginTop: 8, flexWrap: "wrap" }}>
                      {f.evidence.map((token) => {
                        const eidRe = /^(?:EV|INT|E)(?:-[A-Za-z0-9]{1,6})*-\d{1,4}$|^E\d{3,4}$/i;
                        const isEid = eidRe.test(token);
                        // The finding's full E-ID citation list (subcap
                        // tokens excluded) scopes the drawer to exactly
                        // the rows this finding cites.
                        const eidTokens = f.evidence.filter((t) => eidRe.test(t));
                        return (
                          <button key={token} type="button" className="chip"
                                  title="View evidence"
                                  onClick={() => openDrawer("evidence",
                                    isEid
                                      ? { eId: token, eIds: eidTokens, displayId, origin: "top-finding" }
                                      : { subcapId: token, displayId, origin: "top-finding" })}>
                            {token}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

type LeaderRow = {
  id?: string; name?: string; title?: string;
  tenure_months?: number; tenure?: number | null;
  recent_hire?: boolean; gap_flag?: boolean; critical_role?: boolean;
  background?: string;
  clay?: { email?: string; linkedin?: string };
};

function LeadershipPanel({
  audience, leadership,
}: {
  audience: string;
  leadership: LeaderRow[];
}): JSX.Element {
  const [enriched, setEnriched] = useState<Record<string, "loading" | "done">>({});
  const [enrichingAll, setEnrichingAll] = useState(false);

  function enrich(id: string): void {
    setEnriched((e) => ({ ...e, [id]: "loading" }));
    window.setTimeout(() => {
      setEnriched((e) => ({ ...e, [id]: "done" }));
    }, 900);
  }
  function enrichAll(): void {
    setEnrichingAll(true);
    leadership.forEach((ex, i) => window.setTimeout(() => {
      if (ex.gap_flag || !ex.id) return;
      enrich(ex.id);
      if (i === leadership.length - 1) {
        window.setTimeout(() => setEnrichingAll(false), 1000);
      }
    }, i * 240));
  }

  if (leadership.length === 0) {
    return (
      <div className="card flush">
        <div className="card-head"><h3>Leadership panel</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }} data-source="api-empty">
          No public leadership roster on file for this client yet.
        </div>
      </div>
    );
  }

  const gapRows = leadership.filter((x) => x.gap_flag);
  const enrichedCount = Object.values(enriched).filter((v) => v === "done").length;
  const enrichable = leadership.filter((x) => !x.gap_flag).length;
  return (
    <div className="card flush">
      <div className="card-head">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}><Icon name="users" size={15} /> Leadership panel</h3>
        <button type="button" className="btn btn-secondary btn-sm"
                onClick={enrichAll} disabled={enrichingAll}>
          {enrichingAll ? "Enriching…" : <><Icon name="sparkle" size={13} /> Enrich all via Clay</>}
        </button>
      </div>
      <div style={{ padding: "8px 16px 14px" }}>
        {leadership.map((ex) => {
          const state = ex.id ? enriched[ex.id] : undefined;
          const hasClay = ex.clay && !ex.gap_flag;
          const isEnriched = state === "done" && hasClay;
          return (
            <div key={ex.id ?? `${ex.title}-${ex.name}`}
                 style={{ display: "flex", gap: 10, padding: "12px 0", borderBottom: "1px solid var(--z-sep)" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 18,
                background: ex.gap_flag
                  ? "var(--z-sep)"
                  : "linear-gradient(135deg, var(--z-teal), var(--z-mid))",
                color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, fontWeight: 600, flexShrink: 0,
              }}>
                {ex.gap_flag ? "?" : (ex.name ?? "").split(" ").map((n) => n[0]).join("").slice(0, 2)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  {ex.gap_flag ? (
                    <span style={{ fontWeight: 600, fontSize: 13 }}>—</span>
                  ) : (
                    <span style={{ fontWeight: 600, fontSize: 13, color: "var(--z-dark)" }}>
                      {ex.name ?? "—"}
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: "var(--z-mid)", fontWeight: 600 }}>{ex.title ?? ""}</span>
                  {ex.gap_flag ? <span className="b b-below">GAP</span>
                  : ex.recent_hire ? <span className="b b-org">NEW · {ex.tenure_months ?? ex.tenure ?? 0} mo</span>
                  : (ex.tenure_months ?? ex.tenure) ? <span style={{ fontSize: 10, color: "var(--z-muted)" }}>· {Math.round(((ex.tenure_months ?? ex.tenure) ?? 0) / 12)} yr</span> : null}
                  {ex.critical_role && !ex.gap_flag ? <span className="b b-purple" title="Security / data / technology leadership seat">KEY SEAT</span> : null}
                </div>
                {ex.background ? (
                  <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 4, lineHeight: 1.5 }}>
                    {ex.background}
                  </div>
                ) : null}
                {hasClay && audience !== "customer" ? (
                  <div style={{
                    marginTop: 8, padding: "8px 10px",
                    background: isEnriched ? "var(--z-ice)" : state === "loading" ? "var(--z-lav)" : "var(--z-bg)",
                    border: `1px solid ${isEnriched ? "rgba(39,187,175,.35)" : "var(--z-sep)"}`,
                    borderRadius: 6,
                  }}>
                    {!state ? (
                      <div className="row" style={{ fontSize: 11 }}>
                        <span style={{ color: "var(--z-muted)", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="lock" size={11} /> Email · LinkedIn hidden until enriched</span>
                        <span className="spacer" />
                        <button type="button" className="btn btn-tertiary btn-sm"
                                style={{ padding: "3px 8px" }}
                                onClick={() => ex.id && enrich(ex.id)}>
                          <Icon name="sparkle" size={13} /> Enrich via Clay
                        </button>
                      </div>
                    ) : state === "loading" ? (
                      <div className="row" style={{ fontSize: 11, color: "var(--z-dpur)" }}>
                        Querying Clay enrichment…
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <div className="row" style={{ fontSize: 11, color: "var(--z-mid)" }}>
                          <Icon name="check" size={11} /> <strong style={{ color: "var(--z-mid)" }}>Enriched</strong>
                          <span className="spacer" />
                          <span style={{ fontSize: 10, color: "var(--z-muted)" }}>via Clay · just now</span>
                        </div>
                        {ex.clay?.email ? (
                          <a href={`mailto:${ex.clay.email}`}
                             style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="envelope" size={11} /> {ex.clay.email}</a>
                        ) : null}
                        {ex.clay?.linkedin ? (
                          <a href={`https://${ex.clay.linkedin}`} target="_blank" rel="noreferrer"
                             style={{ fontSize: 11, color: "var(--z-mid)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="linkedin" size={11} /> {ex.clay.linkedin}</a>
                        ) : null}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ padding: "10px 16px", background: "var(--z-lav)", fontSize: 11, color: "var(--z-muted)", display: "flex", alignItems: "center", gap: 6 }}
           data-testid="leadership-footer">
        <Icon name="info" size={11} />
        {gapRows.length > 0 ? (
          <span>Critical roles flagged: <strong style={{ color: "var(--z-below)" }}>
            {gapRows.map((g) => g.title).filter(Boolean).join(", ")} absent
          </strong> from evidence</span>
        ) : (
          <span>No critical-seat gaps flagged</span>
        )}
        <span className="spacer" />
        {enrichedCount > 0 ? (
          <span style={{ color: "var(--z-mid)", fontWeight: 600 }}>✓ {enrichedCount} of {enrichable} enriched</span>
        ) : null}
      </div>
    </div>
  );
}

function ThoughtLeadershipPanel({
  rows,
}: {
  rows: Array<{ id?: string; type?: string; date?: string; title?: string;
                excerpt?: string; author?: string; url?: string }>;
}): JSX.Element {
  if (rows.length === 0) {
    return (
      <div className="card flush" style={{ marginBottom: 18 }}>
        <div className="card-head"><h3>Thought leadership signal</h3></div>
        <div style={{ padding: 16, color: "var(--z-muted)", fontSize: 12.5 }} data-source="api-empty">
          Recent executive press / posts populate here.
        </div>
      </div>
    );
  }
  return (
    <div className="card flush" style={{ marginBottom: 18 }}>
      <div className="card-head">
        <h3><Icon name="lightbulb" size={15} /> Thought leadership signal</h3>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>From executives · recent 6 months</span>
      </div>
      <div style={{ padding: 16 }}>
        <div className="g3">
          {rows.map((tl) => (
            <div key={tl.id ?? tl.title ?? Math.random()} className="card-tile" style={{ padding: 14 }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <span className="b b-purple">{(tl.type ?? "").toUpperCase()}</span>
                {tl.date ? (
                  <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    {new Date(tl.date).toLocaleDateString()}
                  </span>
                ) : null}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4, marginBottom: 6 }}>{tl.title}</div>
              {tl.excerpt ? (
                <div style={{ fontSize: 11, color: "var(--z-body)", lineHeight: 1.55, fontStyle: "italic" }}>
                  "{tl.excerpt}"
                </div>
              ) : null}
              <div className="sep" style={{ margin: "8px 0", height: 1, background: "var(--z-sep)" }} />
              <div className="row" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                <span>{tl.author ?? "—"}</span>
                <span className="spacer" />
                {tl.url && tl.url !== "#" ? (
                  <a href={tl.url.startsWith("http") ? tl.url : `https://${tl.url}`}
                     target="_blank" rel="noreferrer"
                     style={{ color: "var(--z-mid)", display: "inline-flex", alignItems: "center", gap: 3 }}>Open <Icon name="external" size={10} /></a>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


/**
 * 2026-06-06 QA-M2: real Scorecard export. Replaces a pre-fix toast-
 * only "success" stub. Uses the shared `useExportScorecard` mutation
 * (which now goes through the shared `apiBlob` helper per QA-M7 so
 * the same 401 auth-expired hook fires here as everywhere else).
 */
function ScorecardButton({
  displayId, entityName, pushToast,
}: {
  displayId: string | null;
  entityName: string;
  pushToast: (msg: string, level?: "success" | "warn" | "error") => void;
}): JSX.Element {
  const exportMutation = useExportScorecard();
  async function go() {
    if (!displayId) return;
    try {
      const out = await exportMutation.mutateAsync({ displayId, format: "html" });
      const a = document.createElement("a");
      a.href = out.url;
      a.download = out.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      pushToast(`Customer-safe scorecard for ${entityName} downloaded`, "success");
    } catch (err) {
      pushToast((err as Error).message || "Scorecard export failed", "error");
    }
  }
  return (
    <button
      type="button"
      className="btn btn-tertiary"
      onClick={go}
      disabled={exportMutation.isPending || !displayId}
    >
      {exportMutation.isPending ? "Exporting…" : <><Icon name="download" size={13} /> Scorecard</>}
    </button>
  );
}


/**
 * 2026-06-06 QA-M2: real Rerun request. Replaces a pre-fix toast-only
 * "Rerun queued" stub. Calls `POST /api/v1/runs/new` with
 * `is_rerun: true` + `parent_request_id` so the bot pipeline threads
 * the rerun back to the existing assessment.
 */
function RerunButton({
  displayId, entityName, parentRequestId, pushToast,
}: {
  displayId: string | null;
  entityName: string;
  parentRequestId: string | null;
  pushToast: (msg: string, level?: "success" | "warn" | "error") => void;
}): JSX.Element {
  const mutation = useRequestNewRun();
  async function go() {
    if (!displayId || !parentRequestId) {
      pushToast("Rerun requires a parent run", "warn");
      return;
    }
    try {
      const out = await mutation.mutateAsync({
        entity_name: entityName,
        is_rerun: true,
        parent_request_id: parentRequestId,
      });
      pushToast(
        out.eta_minutes != null
          ? `Rerun ${out.request_id} queued — ETA ${out.eta_minutes} min`
          : `Rerun ${out.request_id} queued`,
        "success",
      );
    } catch (err) {
      pushToast((err as Error).message || "Rerun request failed", "error");
    }
  }
  return (
    <button
      type="button"
      className="btn btn-tertiary"
      onClick={go}
      disabled={mutation.isPending || !displayId || !parentRequestId}
    >
      {mutation.isPending ? "Requesting…" : <><Icon name="refresh" size={13} /> Request rerun</>}
    </button>
  );
}
