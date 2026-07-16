/**
 * D4 ClientPlatform — ported 1:1 from prototype
 * (standalone-src/src/pages-d3-d4.jsx · ClientPlatform), rebuilt per
 * remediation plan Part 7 (fit engine v2 traceability surfaces):
 *
 *   - .page-head ("Platform Fit Score") with Roadmap-export + Platform-story
 *     actions.
 *   - .g5 5 platform fit tiles w/ OSS score (click score → fit-breakdown
 *     drilldown), gap count, "N absent" badge, readiness pill and the
 *     prototype's "Top: {2 subcap names}" line.
 *   - 2-col grid: 6-column gap table (Subcap name+id | Pillar | Score |
 *     Peer | Gap | Evidence tier-chip/feature) — rows clickable →
 *     EvidenceDrawer; Readiness card with EXPANDABLE prereq accordions
 *     (backing subcap chips + evidence chips + progress bar).
 *   - 2-col grid: rich Recommendations cards (root-cause E-ID chips,
 *     outcomes grid, phase pill) + Conversation starters.
 *   - StairstepCurve + TransformationRoadmap (real per-phase fields).
 */
import { useEffect, useMemo, useState } from "react";
import { useRoute } from "@/lib/hash-router";
import { mapRoadmapPhases, useEntityPlatformRoadmap, useEntityPlatforms,
         useEntityRecommendationsList,
         type FitBreakdown, type FitSubcapRow, type PlatformCard,
         type RecListItem } from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { Icon, EmptyState, Spinner } from "@/components/utils";
import { maturityClass } from "@/lib/maturity";
import { TransformationRoadmap } from "@/components/TransformationRoadmap";
import { StairstepCurve } from "@/components/StairstepCurve";
import { printView } from "@/lib/export";
import { stripMd } from "@/lib/text";

const PLATFORM_LIST: Array<{ id: string; name: string; features: string }> = [
  { id: "salesforce", name: "Salesforce", features: "Agentforce · Data Cloud · FSC · Marketing" },
  { id: "databricks", name: "Databricks", features: "Mosaic AI · Lakehouse · Delta" },
  { id: "tableau",    name: "Tableau",    features: "Cloud · Pulse · Lineage" },
  { id: "twilio",     name: "Twilio",     features: "Engage · Flex · Verify" },
  { id: "ncino",      name: "nCino",      features: "Origination · Servicing · Banking AI" },
];

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/platform$/);
  return m ? m[1] : null;
}

function ScoreChip({ score }: { score: number | null | undefined }): JSX.Element {
  if (score === null || score === undefined) return <span className="b muted">—</span>;
  return (
    <span className={`b ${maturityClass(score)}`} style={{ minWidth: 30, justifyContent: "center" }}>
      {score.toFixed(1)}
    </span>
  );
}

export function PlatformPage(): JSX.Element {
  const { path, query, setQuery } = useRoute();
  const displayId = getDisplayId(path);
  // 2026-06-06 QA-1: propagate `?run=<request_id>` so platform tiles
  // reflect the selected run.
  const selectedRun = typeof query.run === "string" ? query.run : null;
  const setIpSurface = useUiStore((s) => s.setIpSurface);
  const setIpOpen = useUiStore((s) => s.setIpOpen);
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [breakdownFor, setBreakdownFor] = useState<string | null>(null);

  const platformsQ = useEntityPlatforms(displayId, selectedRun);
  const recsQ = useEntityRecommendationsList(displayId);
  const roadmapQ = useEntityPlatformRoadmap(displayId, selectedRun);

  const selected = (query.platform as string) || "salesforce";
  function selectPlatform(pid: string): void {
    setQuery({ platform: pid });
  }

  useEffect(() => {
    if (displayId) {
      setIpSurface("platform_story", { ref: `${displayId}:${selected}` });
    }
  }, [displayId, selected, setIpSurface]);

  // Per-rec metadata from the roadmap payload: platform + feature (the
  // Part-7.3 per-step platform note) + phase duration feed the
  // StairstepCurve band tiles; titles feed the roadmap rec chips.
  const { recMeta, recTitles } = useMemo(() => {
    const recMeta: Record<string, { platform: string; duration: string }> = {};
    const recTitles: Record<string, string> = {};
    for (const phase of roadmapQ.data?.phases ?? []) {
      for (const r of phase.recommendations) {
        const parts = [...new Set([r.platform_name, r.feature]
          .filter((x): x is string => !!x))];
        if (parts.length > 0) {
          recMeta[r.rec_id] = {
            platform: parts.join(" · "),
            duration: `${phase.duration_months} mo`,
          };
        }
        if (r.title) recTitles[r.rec_id] = r.title;
      }
    }
    return { recMeta, recTitles };
  }, [roadmapQ.data]);

  if (platformsQ.isLoading) {
    return <div className="page-loading"><Spinner /> Loading platforms…</div>;
  }
  if (platformsQ.error || !platformsQ.data) {
    return <EmptyState title="Couldn't load platforms" body={(platformsQ.error as Error)?.message} />;
  }

  const cards = platformsQ.data.cards ?? [];
  const cardByPid: Record<string, PlatformCard | undefined> = {};
  cards.forEach((c) => { cardByPid[c.platform_id] = c; });
  const selectedCard = cardByPid[selected] ?? cards[0] ?? null;
  const selectedMeta = PLATFORM_LIST.find((p) => p.id === selected) ?? PLATFORM_LIST[0];
  const breakdownCard = breakdownFor ? cardByPid[breakdownFor] ?? null : null;

  return (
    <div className="page" data-page="platform" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Platform opportunity</div>
          <h1>Platform Fit Score</h1>
          <div className="sub">Which platform conversation should lead with this client?</div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-tertiary"
                  onClick={() => printView()}>
            <Icon name="download" size={13} /> Roadmap export
          </button>
          <button type="button" className="btn btn-secondary"
                  onClick={() => { setIpSurface("platform_story", { ref: `${displayId}:${selected}` }); setIpOpen(true); }}>
            <Icon name="sparkle" size={13} /> Platform story
          </button>
        </div>
      </div>

      {/* 5 platform fit tiles (prototype badges restored: N absent +
          Top-2 subcap names; score click opens the fit breakdown). */}
      <div className="g5" style={{ marginBottom: 16 }}>
        {PLATFORM_LIST.map((p) => {
          const c = cardByPid[p.id];
          const isSel = p.id === selected;
          const fit = c ? Math.round(c.fit_score) : 0;
          const gaps = c?.addressable_subcap_ids.length ?? 0;
          const topNames = (c?.top_subcap_names ?? []).filter(Boolean);
          return (
            <div
              key={p.id}
              className="card-tile clickable"
              data-testid={`fit-tile-${p.id}`}
              onClick={() => selectPlatform(p.id)}
              style={{
                border: isSel ? "1px solid var(--z-teal)" : "1px solid var(--z-sep)",
                background: isSel ? "var(--z-ice)" : "#fff",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontSize: 9.5, color: "var(--z-muted)" }}>
                    {p.features.split(" · ").slice(0, 3).join(" · ")}
                  </div>
                </div>
                <button
                  type="button"
                  data-testid={`fit-score-${p.id}`}
                  title="Why this score? Open the fit breakdown"
                  aria-label={`Open fit breakdown for ${p.name}`}
                  onClick={(e) => { e.stopPropagation(); if (c?.fit_breakdown) setBreakdownFor(p.id); }}
                  style={{ textAlign: "right", background: "none", border: 0,
                           cursor: c?.fit_breakdown ? "pointer" : "default", padding: 0 }}
                >
                  <div style={{ fontSize: 26, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1 }}>{fit}</div>
                  <div className="f-mono" style={{ fontSize: 9, color: "var(--z-muted)" }}>/100 OSS</div>
                </button>
              </div>
              <div style={{ marginTop: 10, fontSize: 11, color: "var(--z-body)" }}>
                <span className="b b-org" style={{ marginRight: 4 }}>{gaps} gaps</span>
                {typeof c?.absent_count === "number" && c.absent_count > 0 ? (
                  <span className="b b-below" style={{ marginRight: 4 }}>{c.absent_count} absent</span>
                ) : null}
                {c?.state === "INSUFFICIENT_EVIDENCE" ? (
                  <span className="b b-muted">INSUFFICIENT EVIDENCE</span>
                ) : (
                  <span className={`b b-${c?.readiness_index === "green" ? "above" : c?.readiness_index === "amber" ? "org" : "below"}`}>
                    {(c?.readiness_index ?? "—").toUpperCase()}
                  </span>
                )}
              </div>
              {topNames.length > 0 ? (
                <div className="txt-fit-1" style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 6 }}>
                  Top: {topNames.slice(0, 2).join(" · ")}
                </div>
              ) : null}
              {(() => {
                // Current-stack strip (platform v3): named confirmed systems
                // the entity already runs in this pillar — the mandate's
                // "current organizational capabilities". Guarded on dossier.
                const stack = c?.dossier?.readiness_now?.confirmed_systems ?? [];
                if (stack.length === 0) return null;
                const names = stack.map((s) => s.name).filter(Boolean).slice(0, 2).join(", ");
                return (
                  <div className="txt-fit-1" style={{ fontSize: 10, color: "var(--z-mid)", marginTop: 3 }}
                       title={`${stack.length} confirmed current systems in ${p.name}'s pillar`}>
                    Stack: {names}{stack.length > 2 ? ` +${stack.length - 2}` : ""}
                  </div>
                );
              })()}
            </div>
          );
        })}
      </div>

      {selectedCard ? (
        <>
          {/* 2-col: 6-column gap table + readiness accordions */}
          <div className="sidebar-split w-380" style={{ gap: 16, marginBottom: 16 }}>
            <GapTable
              card={selectedCard}
              platformName={selectedMeta.name}
              featureFallback={selectedMeta.features.split(" · ")[0]}
              displayId={displayId}
            />
            <ReadinessCard card={selectedCard} platformName={selectedMeta.name} displayId={displayId} />
          </div>

          {/* Platform v3 dossier — the evidence-rich narrative sections with
              provenance E-ID chips (guarded on presence; cold packs skip). */}
          {selectedCard.dossier ? (
            <DossierCard
              card={selectedCard}
              platformName={selectedMeta.name}
              displayId={displayId}
            />
          ) : null}

          {/* 2-col: Recommendations + Conversation starters */}
          <div className="g2" style={{ gap: 16, marginBottom: 16 }}>
            <RecommendationsCard
              platformName={selectedMeta.name}
              platformId={selectedCard.platform_id}
              recs={recsQ.data ?? []}
              displayId={displayId}
              onOpen={(recId) =>
                openDrawer("recommendation", { recommendationId: recId, displayId })}
            />

            <ConversationStartersCard
              platformName={selectedMeta.name}
              starters={selectedCard.conversation_starters ?? []}
              text={selectedCard.conversation_starter}
              storyMd={selectedCard.story_md}
              storySource={selectedCard.story_source}
            />
          </div>

          {/* Prototype D4 surfaces the stairstep milestone curve alongside
              the transformation roadmap (08_pages_d.js). Rec steps open the
              RecommendationModal scoped to that rec. recMeta/recTitles bind
              the staircase bands + chevron chips to the roadmap payload. */}
          <StairstepCurve
            displayId={displayId}
            focusPillar={selectedCard.pillar}
            recMeta={recMeta}
            onRecClick={(recId) =>
              openDrawer("recommendation", { recommendationId: recId, displayId })}
          />

          <TransformationRoadmap
            phases={(() => {
              const backend = mapRoadmapPhases(roadmapQ.data);
              return backend.length > 0 ? backend : platformsQ.data.narrative?.roadmap_phases;
            })()}
            roadmapMd={platformsQ.data.narrative?.roadmap_md}
            displayId={displayId}
            recTitles={recTitles}
          />
        </>
      ) : (
        <EmptyState title="No platform fit data yet" body="Re-run the assessment once subcap_scores ingest." />
      )}

      <FitBreakdownModal
        card={breakdownCard}
        displayId={displayId}
        onClose={() => setBreakdownFor(null)}
      />
    </div>
  );
}

/** E-ID chip that opens the EvidenceDrawer (the existing app-wide opener
 *  contract — passes eId + eIds + origin, same as GapTable). */
function EidChip({ eid, eids, subcapId, displayId }: {
  eid: string;
  eids?: string[];
  subcapId?: string | null;
  displayId: string | null;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  return (
    <button
      type="button"
      className="chip"
      style={{ cursor: "pointer", border: 0, marginRight: 4 }}
      title={`Open evidence ${eid}`}
      onClick={() =>
        openDrawer("evidence", {
          displayId,
          subcapId: subcapId ?? null,
          eId: eid,
          eIds: eids && eids.length > 0 ? eids : [eid],
          origin: "platform-dossier",
        })}
    >
      {eid}
    </button>
  );
}

/** Platform v3 dossier panel: three evidence-rich sections (Where they are
 *  today · Why {platform} · Path to ready) with provenance E-ID chips that
 *  open the EvidenceDrawer, plus the audit chain. Guarded on card.dossier. */
function DossierCard({ card, platformName, displayId }: {
  card: PlatformCard;
  platformName: string;
  displayId: string | null;
}): JSX.Element | null {
  const d = card.dossier;
  if (!d) return null;
  const rn = d.readiness_now;
  const opp = d.opportunity;
  const seq = d.why_sequence;
  const prov = card.narrative_provenance ?? [];
  const lead = opp.lead_subcap;
  const fmt = (v: number | null | undefined): string =>
    v === null || v === undefined ? "—" : v.toFixed(1);
  return (
    <div className="card" data-testid="platform-dossier" style={{ marginBottom: 16 }}>
      <div className="row" style={{ marginBottom: 10 }}>
        <Icon name="sparkle" size={15} />
        <div style={{ fontSize: 13, fontWeight: 600 }}>Platform dossier · {platformName}</div>
        <span className="spacer" />
        <span className="b b-muted">deterministic · evidence-cited</span>
      </div>

      {card.story_md ? (
        <p style={{ fontSize: 12.5, color: "var(--z-body)", lineHeight: 1.65, margin: "0 0 12px" }}>
          {stripMd(card.story_md)}
        </p>
      ) : null}

      <div className="g3" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {/* 1 — Where they are today */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
            Where they are today
          </div>
          {rn.confirmed_systems.length > 0 ? (
            rn.confirmed_systems.map((s, i) => (
              <div key={i} className="row" style={{ gap: 6, padding: "3px 0", flexWrap: "wrap" }}>
                <span className="b b-above">{s.status}</span>
                <span style={{ fontSize: 12, flex: 1, minWidth: 0 }}>{s.name}</span>
                {typeof s.peer_coverage === "number" && s.peer_coverage > 0 ? (
                  <span className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>
                    {Math.round(s.peer_coverage * 100)}% peers
                  </span>
                ) : null}
                {s.e_ids.map((eid) => (
                  <EidChip key={eid} eid={eid} eids={s.e_ids} displayId={displayId} />
                ))}
              </div>
            ))
          ) : (
            <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
              No confirmed systems mapped to this pillar for this run.
            </div>
          )}
          {rn.lens === "integrate" && rn.category_incumbents?.length ? (
            <div className="b b-org" style={{ marginTop: 6 }}>
              integration · {rn.category_incumbents[0]}
            </div>
          ) : rn.greenfield ? (
            <div className="b b-below" style={{ marginTop: 6 }}>
              greenfield{rn.absent_families.length ? ` · ${rn.absent_families.join(", ")}` : ""}
            </div>
          ) : rn.family_present.length > 0 ? (
            <div className="b b-teal" style={{ marginTop: 6 }}>
              expansion · {rn.family_present[0].name}
            </div>
          ) : null}
        </div>

        {/* 2 — Why this platform */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
            Why {platformName}
          </div>
          {lead ? (
            <div style={{ fontSize: 12, marginBottom: 6 }}>
              <div style={{ fontWeight: 600 }}>{lead.name}</div>
              <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)", margin: "2px 0" }}>
                {fmt(lead.score)}/5 vs {fmt(lead.peer_median)} peer median
              </div>
              {lead.e_ids.map((eid) => (
                <EidChip key={eid} eid={eid} eids={lead.e_ids} subcapId={null} displayId={displayId} />
              ))}
            </div>
          ) : null}
          <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
            {opp.gap_count} addressable gap{opp.gap_count === 1 ? "" : "s"}
            {typeof opp.opportunity_points === "number" ? ` · ${opp.opportunity_points.toFixed(0)} fit pts` : ""}
          </div>
          {opp.next_subcaps.length > 0 ? (
            <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4 }}>
              Next: {opp.next_subcaps.map((s) => s.name).filter(Boolean).slice(0, 2).join(" · ")}
            </div>
          ) : null}
        </div>

        {/* 3 — Path to ready */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
            Path to ready
          </div>
          <div className="row" style={{ gap: 6, marginBottom: 6 }}>
            <span className={`b b-${rn.light === "green" ? "above" : rn.light === "amber" ? "org" : "below"}`}>
              {(rn.light ?? "—").toUpperCase()}
            </span>
            <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
              {rn.open_prereqs.length} of {rn.total_prereqs} prereqs open
            </span>
          </div>
          {rn.open_prereqs.slice(0, 3).map((p, i) => (
            <div key={i} style={{ fontSize: 11.5, color: "var(--z-body)", padding: "2px 0" }}>
              {p.name}
              {typeof p.current === "number" && typeof p.threshold === "number" ? (
                <span className="f-mono" style={{ fontSize: 10, color: "var(--z-below)", marginLeft: 4 }}>
                  {p.current.toFixed(1)} / {p.threshold.toFixed(1)}
                </span>
              ) : null}
            </div>
          ))}
          {seq.after.length > 0 ? (
            <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 6 }}>
              Sequence after {seq.after.slice(0, 2).join(", ")}
            </div>
          ) : seq.rank === 1 ? (
            <div style={{ fontSize: 11, color: "var(--z-mid)", marginTop: 6 }}>Leads the sequence</div>
          ) : null}
        </div>
      </div>

      {prov.length > 0 ? (
        <details style={{ marginTop: 12 }}>
          <summary style={{ fontSize: 11, color: "var(--z-muted)", cursor: "pointer" }}>
            Audit chain · {prov.length} claim{prov.length === 1 ? "" : "s"}
          </summary>
          <div style={{ marginTop: 6 }}>
            {prov.map((pv, i) => (
              <div key={i} style={{ fontSize: 11, color: "var(--z-body)", padding: "4px 0", borderTop: "1px solid var(--z-sep)" }}>
                <span className="b b-muted" style={{ marginRight: 6 }}>{pv.source_kind}</span>
                {pv.claim}
                {pv.e_ids.length > 0 ? (
                  <span style={{ marginLeft: 4 }}>
                    {pv.e_ids.map((eid) => (
                      <EidChip key={eid} eid={eid} eids={pv.e_ids} displayId={displayId} />
                    ))}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

/** 6-column gap table (prototype parity): Subcap name+id | Pillar |
 *  Score chip | Peer chip | Gap | Evidence tier-chip (else feature).
 *  Rows are clickable → EvidenceDrawer scoped to the subcap. */
function GapTable({ card, platformName, featureFallback, displayId }: {
  card: PlatformCard;
  platformName: string;
  featureFallback: string;
  displayId: string | null;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const rows: FitSubcapRow[] = card.fit_breakdown?.top_subcaps ?? [];
  const openEvidence = (row: FitSubcapRow): void => {
    // Pass the row's top E-ID so the drawer scrolls-to + highlights THAT
    // item (plan Part 11.1: ALL openers pass eId; DrawerHost forwards it)
    // plus the row's full citation list so the drawer scopes to exactly
    // the rows this gap is grounded in (2026-07-06 remediation).
    openDrawer("evidence", {
      displayId,
      subcapId: row.subcap_id,
      eId: row.e_ids[0] ?? null,
      eIds: row.e_ids.length > 0 ? row.e_ids : null,
      origin: "platform-gap-table",
    });
  };
  return (
    <div className="card flush">
      <div className="card-head">
        <h3>Gap-to-platform mapping · {platformName}</h3>
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
          {card.addressable_subcap_ids.length} addressable subcaps
        </span>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="tbl" data-testid="gap-table">
          <thead>
            <tr>
              <th>Subcap</th>
              <th>Pillar</th>
              <th>Score</th>
              <th>Peer</th>
              <th>Gap</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((s) => (
              <tr key={s.subcap_id} className="tbl-click" style={{ cursor: "pointer" }}
                  data-testid={`gap-row-${s.subcap_id}`}
                  title={s.e_ids.length ? `Open evidence ${s.e_ids[0]}` : "Open evidence for this subcap"}
                  onClick={() => openEvidence(s)}>
                <td data-label="Subcap">
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{s.name ?? s.subcap_id}</div>
                  <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>{s.subcap_id}</div>
                </td>
                <td data-label="Pillar"><span className="b b-purple">{s.pillar}</span></td>
                <td data-label="Score"><ScoreChip score={s.score} /></td>
                <td data-label="Peer"><ScoreChip score={s.peer_median} /></td>
                <td data-label="Gap">
                  {s.peer_median !== null && s.score !== null && s.peer_median > s.score ? (
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--z-below)" }}>
                      −{(s.peer_median - s.score).toFixed(1)}
                    </span>
                  ) : s.gap !== null && s.gap !== undefined ? (
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--z-below)" }}>
                      −{s.gap.toFixed(1)}
                    </span>
                  ) : "—"}
                </td>
                <td data-label="Evidence">
                  {s.e_ids.length > 0 ? (
                    <span className={`tier-chip tier-T${s.tier ?? 5}`}>{s.e_ids[0]}</span>
                  ) : (
                    <span style={{ fontSize: 11, color: "var(--z-body)" }}>{featureFallback}</span>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              // Legacy snapshots without fit_breakdown: id-only fallback.
              card.addressable_subcap_ids.slice(0, 10).map((sid) => (
                <tr key={sid}>
                  <td data-label="Subcap"><div className="f-mono" style={{ fontSize: 11 }}>{sid}</div></td>
                  <td data-label="Pillar" colSpan={5}><span className="b b-purple">{sid.slice(0, 2)}</span></td>
                </tr>
              ))
            ) : null}
            {rows.length === 0 && card.addressable_subcap_ids.length === 0 ? (
              <tr><td colSpan={6} className="tbl-empty">No addressable subcaps for this platform.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Readiness card with EXPANDABLE prereq accordions (prototype parity):
 *  header row (category chip + name + status pill + chevron), meta line
 *  (min · current · N subcaps · N evidence), progress bar; expanded body
 *  lists backing subcap chips + clickable evidence chips. */
function ReadinessCard({ card, platformName, displayId }: {
  card: PlatformCard;
  platformName: string;
  displayId: string | null;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [openPrereq, setOpenPrereq] = useState<string | null>(null);
  const topSubcaps: FitSubcapRow[] = card.fit_breakdown?.top_subcaps ?? [];

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <Icon name="shield" size={16} />
        <div style={{ fontSize: 13, fontWeight: 600 }}>Readiness · {platformName}</div>
        <span className="spacer" />
        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>click a row to drill in</span>
      </div>
      {card.prereq_checks.map((p) => {
        const met = p.status === "MET";
        const cur = p.current_score ?? 0;
        const pct = Math.min(100, (cur / p.threshold) * 100);
        const isOpen = openPrereq === p.required_subcap_id;
        const catPrefix = p.required_subcap_id.slice(0, 4);
        const prefixBacking = topSubcaps.filter((s) => s.subcap_id.startsWith(catPrefix));
        // When the platform's top-opportunity subcaps don't fall in the
        // prereq's gated category, fall back to the server-resolved related
        // subcaps (gate subcap + category siblings + nlp matches) so an issue
        // never renders with zero related subcaps (2026-07 operator report).
        const related = card.dossier?.readiness_now?.open_prereqs?.find(
          (op) => op.required_subcap_id === p.required_subcap_id,
        )?.related_subcaps ?? [];
        const backing = prefixBacking.length > 0
          ? prefixBacking
          : related.map((r) => ({
              subcap_id: r.subcap_id, name: r.name, score: r.score,
              pillar: r.subcap_id.slice(0, 2), peer_median: null,
              gap: null, opportunity: null, e_ids: r.e_ids,
            }));
        const evidence = [...new Set(backing.flatMap((s) => s.e_ids))].slice(0, 8);
        return (
          <div key={p.name} style={{ borderBottom: "1px solid var(--z-sep)" }}>
            <button
              type="button"
              data-testid={`prereq-toggle-${p.required_subcap_id}`}
              aria-expanded={isOpen}
              onClick={() => setOpenPrereq((o) => o === p.required_subcap_id ? null : p.required_subcap_id)}
              style={{ width: "100%", background: "none", border: 0, cursor: "pointer",
                       textAlign: "left", padding: "10px 0" }}
            >
              <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                <span className="b b-purple">{catPrefix}</span>
                <span style={{ fontSize: 12, flex: 1 }}>{p.name}</span>
                <span className={`b b-${met ? "above" : "org"}`}>{met ? "MET" : p.status}</span>
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} style={{ color: "var(--z-muted)" }} />
              </div>
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
                Min {p.threshold.toFixed(1)} · Current {cur.toFixed(1)}
                {backing.length ? ` · ${backing.length} subcaps` : ""}
                {evidence.length ? ` · ${evidence.length} evidence` : ""}
              </div>
              <div className="prog" style={{ marginTop: 4, height: 4 }}>
                <div className="prog-fill" style={{
                  width: `${pct}%`,
                  background: met ? "var(--z-mid)" : "var(--z-org)",
                }} />
              </div>
            </button>
            {isOpen ? (
              <div data-testid={`prereq-body-${p.required_subcap_id}`} style={{ padding: "2px 0 12px" }}>
                <div className="row" style={{ gap: 6, padding: "3px 0" }}>
                  <span className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                    Gate: {p.required_subcap_id} ≥ {p.threshold.toFixed(1)}
                  </span>
                </div>
                {backing.length > 0 ? (
                  <>
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", margin: "6px 0 4px" }}>
                      Backing subcaps
                    </div>
                    {backing.slice(0, 6).map((s) => (
                      <div key={s.subcap_id} className="row" style={{ gap: 6, padding: "3px 0" }}>
                        <ScoreChip score={s.score} />
                        <span className="txt-fit-1" style={{ fontSize: 11.5, color: "var(--z-dark)", flex: 1, minWidth: 0 }}>
                          {s.name ?? s.subcap_id}
                        </span>
                        <span className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{s.subcap_id}</span>
                      </div>
                    ))}
                  </>
                ) : (
                  <div style={{ fontSize: 11, color: "var(--z-muted)", padding: "4px 0" }}>
                    No addressable gap subcaps under {catPrefix} for this platform.
                  </div>
                )}
                {evidence.length > 0 ? (
                  <>
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", margin: "8px 0 4px" }}>
                      Evidence · click to open
                    </div>
                    <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                      {evidence.map((eid) => (
                        <button key={eid} type="button" className="chip"
                                style={{ cursor: "pointer", border: 0 }}
                                onClick={() =>
                                  openDrawer("evidence", {
                                    displayId,
                                    subcapId: p.required_subcap_id,
                                    eId: eid,
                                    origin: "prereq-gate",
                                  })}>
                          {eid}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
      {card.prereq_checks.some((p) => p.status !== "MET") ? (
        <div className="co co-org" style={{ marginTop: 10, padding: 10, borderRadius: 6, background: "var(--ph0-lt)" }}>
          <div className="co-title" style={{ fontWeight: 600, fontSize: 12 }}>Advisory</div>
          <div className="co-body" style={{ fontSize: 11.5, marginTop: 4 }}>
            Lead with the foundation prerequisite conversation before introducing {platformName}.
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Fit-breakdown drilldown (Part 7.1 traceability): factor bars +
 *  readiness penalty + contributing subcaps with E-ID chips + sequence. */
function FitBreakdownModal({ card, displayId, onClose }: {
  card: PlatformCard | null;
  displayId: string | null;
  onClose: () => void;
}): JSX.Element | null {
  const openDrawer = useUiStore((s) => s.openDrawer);
  if (!card?.fit_breakdown) return null;
  const bd: FitBreakdown = card.fit_breakdown;
  const factors = bd.factors ?? {};
  const bars: Array<{ label: string; points: number; note?: string }> = [
    { label: "Opportunity (gap × severity × evidence)", points: factors.opportunity?.points ?? 0 },
    { label: "Interconnect (catalogue adjacency)", points: factors.interconnect?.points ?? 0,
      note: factors.interconnect?.dependent_subcaps
        ? `${factors.interconnect.dependent_subcaps} dependent subcaps` : undefined },
    { label: factors.absent_boost?.stack_lens?.lens === "integrate"
        ? "Absent boost (integration lens)"
        : "Absent boost (greenfield)",
      points: factors.absent_boost?.points ?? 0,
      note: factors.absent_boost?.stack_lens?.lens === "integrate"
        ? `incumbent: ${(factors.absent_boost.stack_lens.category_incumbents ?? []).join(", ")}`
        : (bd.absent_families ?? []).join(", ") || undefined },
  ];
  const readiness = factors.readiness;
  const maxPts = Math.max(60, ...bars.map((b) => b.points));
  const top = (bd.top_subcaps ?? []).slice(0, 6);
  return (
    <div className="modal-mask" data-testid="fit-breakdown-modal" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 640 }}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div className="row" style={{ gap: 6, marginBottom: 4 }}>
              <span className="chip">{card.platform_id}</span>
              <span className="b b-teal">fit {Math.round(card.fit_score)}/100</span>
              {bd.sequence?.rank ? <span className="b b-purple">sequence #{bd.sequence.rank}</span> : null}
              <span className="b b-muted">{bd.engine ?? "v2"} · target {bd.target_band ?? "M4"}</span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>Why this score · {card.display_name}</div>
          </div>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="modal-body">
          {bars.map((b) => (
            <div key={b.label} style={{ marginBottom: 10 }}>
              <div className="row" style={{ fontSize: 12, marginBottom: 3 }}>
                <span style={{ flex: 1 }}>{b.label}</span>
                <strong>+{b.points.toFixed(1)} pts</strong>
              </div>
              <div className="prog" style={{ height: 6 }}>
                <div className="prog-fill" style={{ width: `${Math.min(100, (b.points / maxPts) * 100)}%`, background: "var(--z-teal)" }} />
              </div>
              {b.note ? <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2 }}>{b.note}</div> : null}
            </div>
          ))}
          {readiness ? (
            <div style={{ marginBottom: 12, padding: "8px 10px", borderRadius: 6,
                          background: readiness.light === "red" ? "rgba(213,77,73,.08)" : "var(--z-bg)" }}>
              <div className="row" style={{ fontSize: 12 }}>
                <span style={{ flex: 1 }}>
                  Readiness gate ({readiness.light.toUpperCase()}) · ×{readiness.multiplier}
                </span>
                <strong style={{ color: readiness.penalty_points < 0 ? "var(--z-below)" : "var(--z-mid)" }}>
                  {readiness.penalty_points.toFixed(1)} pts
                </strong>
              </div>
              <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 2 }}>
                Red readiness caps a platform below the hot threshold — prerequisites first.
              </div>
            </div>
          ) : null}
          <div className="row" style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 12 }}>
            Evidence strength {(bd.evidence_strength ?? 0).toFixed(2)} · {bd.n_addressable ?? 0} addressable subcaps
            {bd.sequence?.after?.length ? ` · lands after ${bd.sequence.after.join(", ")}` : ""}
          </div>
          {top.length > 0 ? (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 6 }}>
                Top contributing subcaps
              </div>
              {top.map((s) => (
                <div key={s.subcap_id} className="row" style={{ gap: 6, padding: "5px 0", borderTop: "1px solid var(--z-sep)" }}>
                  <ScoreChip score={s.score} />
                  <span className="txt-fit-1" style={{ fontSize: 12, flex: 1, minWidth: 0 }}>{s.name ?? s.subcap_id}</span>
                  <span className="f-mono" style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{s.subcap_id}</span>
                  {s.e_ids.slice(0, 2).map((eid) => (
                    <button key={eid} type="button" className="chip"
                            style={{ cursor: "pointer", border: 0 }}
                            onClick={() => {
                              onClose();
                              openDrawer("evidence", {
                                displayId,
                                subcapId: s.subcap_id,
                                eId: eid,
                                origin: "fit-breakdown",
                              });
                            }}>
                      {eid}
                    </button>
                  ))}
                </div>
              ))}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Rich recommendation cards (prototype parity, Part 7.2): rec chip +
 *  title + phase pill, feature line, root-cause E-ID chips, outcomes
 *  grid (Time | Effort | Metric). */
function RecommendationsCard({
  platformName, platformId, recs, displayId, onOpen,
}: {
  platformName: string;
  platformId: string;
  recs: RecListItem[];
  displayId: string | null;
  onOpen: (recId: string) => void;
}): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  // Platform-scoped recs first (prototype filters by platform); recs the
  // package didn't tag to a platform stay visible under "all platforms"
  // so analyst content is never hidden.
  const scoped = recs.filter((r) => (r.platform_id ?? "").toLowerCase() === platformId.toLowerCase());
  const shown = scoped.length > 0 ? scoped : recs;
  return (
    <div className="card flush">
      <div className="card-head"><h3>Recommendations · {platformName}</h3>
        {scoped.length === 0 && recs.length > 0 ? (
          <span className="b b-muted">all platforms</span>
        ) : null}
      </div>
      <div>
        {shown.map((r) => {
          const outcomes = r.outcomes ?? null;
          const rce = r.root_cause_e_ids ?? [];
          return (
            <div key={r.id} data-testid={`rec-card-${r.rec_id}`}
                 style={{ padding: "12px 18px", borderBottom: "1px solid var(--z-sep)" }}>
              <button type="button" className="row"
                      style={{ width: "100%", textAlign: "left", background: "none",
                               border: 0, cursor: "pointer", gap: 8, padding: 0 }}
                      onClick={() => onOpen(r.id)}>
                <span className="chip">{r.rec_id}</span>
                <span style={{ fontWeight: 600, fontSize: 13, flex: 1, minWidth: 0 }}>{r.title}</span>
                {r.phase ? <span className="b b-teal">Phase {r.phase}</span> : null}
                <Icon name="chevron-r" size={12} />
              </button>
              {r.feature ? (
                <div style={{ fontSize: 10.5, color: "var(--z-mid)", marginTop: 3 }}>{r.feature}</div>
              ) : null}
              {rce.length > 0 ? (
                <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.55, margin: "6px 0 0" }}>
                  Root cause:{" "}
                  {rce.slice(0, 4).map((eid) => (
                    <button key={eid} type="button" className="chip" style={{ marginRight: 4, cursor: "pointer", border: 0 }}
                            onClick={() =>
                              openDrawer("evidence", { displayId, eId: eid, origin: "rec-card" })}>
                      {eid}
                    </button>
                  ))}
                </div>
              ) : null}
              {outcomes && (outcomes.time || outcomes.effort || outcomes.metric || outcomes.peer) ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginTop: 8, fontSize: 11 }}>
                  <div><div className="muted" style={{ fontSize: 10 }}>Time</div><strong>{outcomes.time ?? "—"}</strong></div>
                  <div><div className="muted" style={{ fontSize: 10 }}>Effort</div><strong>{outcomes.effort ?? "—"}</strong></div>
                  <div style={{ gridColumn: "span 2" }}>
                    <div className="muted" style={{ fontSize: 10 }}>Metric</div>
                    <strong>{outcomes.metric ?? outcomes.peer ?? "—"}</strong>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
        {shown.length === 0 ? (
          <div className="empty" style={{ padding: 24, color: "var(--z-muted)", fontSize: 12 }}>
            No recommendations in this run — the package shipped none.
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** One chat-bubble starter row — wireframe contract: --z-lav bubble with
 *  a teal left accent, 13px/1.6 body, #N badge + the honest
 *  "Template-fill · evidence-cited" provenance microcopy (B-1 producer),
 *  and a small per-bubble copy icon-button. */
function StarterBubble({ index, text, onCopy }: {
  index: number;
  text: string;
  onCopy: (s: string) => void;
}): JSX.Element {
  return (
    <div style={{ padding: "10px 12px", marginBottom: 8, background: "var(--z-lav)",
                  borderLeft: "3px solid var(--z-teal)", borderRadius: 8 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <span className="b b-purple">#{index + 1}</span>
        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>Template-fill · evidence-cited</span>
        <span className="spacer" />
        <button type="button" className="icon-btn" aria-label={`Copy conversation starter ${index + 1}`}
                onClick={() => onCopy(text)}>
          <Icon name="copy" size={12} />
        </button>
      </div>
      <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6 }}>{stripMd(text)}</div>
    </div>
  );
}

function ConversationStartersCard({
  platformName, starters, text, storyMd, storySource,
}: {
  platformName: string;
  starters: string[];
  text: string | null;
  storyMd?: string | null;
  storySource?: string | null;
}): JSX.Element {
  const pushToast = useUiStore((s) => s.pushToast);
  function copy(s: string): void {
    void navigator.clipboard?.writeText(s).catch(() => undefined);
    pushToast("Copied to clipboard", "success");
  }
  // Prototype (08_pages_d.js:200-222): a white card whose head carries the
  // title + Copy-all action, and one chat-bubble row per starter with its
  // own copy button. The structured list is the primary contract; the
  // legacy single string degrades to the same bubbles (never a prose wall).
  const storyBlock = storyMd ? (
    <div style={{ padding: "12px 14px 0" }}>
      <div className="row" style={{ gap: 6, marginBottom: 4 }}>
        <span className="chip" title="Validated Gemini synthesis, persisted at deploy">
          {storySource === "vertex" ? "✦ AI story" : "story"}
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--z-body)", whiteSpace: "pre-wrap" }}>
        {stripMd(storyMd)}
      </div>
    </div>
  ) : null;
  if (starters.length > 0) {
    return (
      <div className="card flush conv-starters">
        <div className="card-head">
          <h3>Conversation starters</h3>
          <button type="button" className="btn btn-tertiary btn-sm"
                  onClick={() => copy(starters.map((cs, i) => `#${i + 1} — ${cs}`).join("\n\n"))}>
            <Icon name="copy" size={12} /> Copy all
          </button>
        </div>
        {storyBlock}
        <div style={{ padding: 14 }}>
          {starters.map((cs, i) => (
            <StarterBubble key={i} index={i} text={cs} onCopy={copy} />
          ))}
        </div>
      </div>
    );
  }
  if (!text) {
    return (
      <div className="card flush">
        <div className="card-head"><h3>Conversation starters · {platformName}</h3></div>
        <div className="empty" style={{ padding: 24, color: "var(--z-muted)", fontSize: 12 }}>
          Conversation starters populate when the platform has addressable subcaps.
        </div>
      </div>
    );
  }
  const lines = text.split("\n").map((s) => s.trim()).filter(Boolean);
  const steps = lines.filter((l) => /^\d+\./.test(l)).map((l) => l.replace(/^\d+\.\s*/, ""));
  const next = lines.find((l) => /^Next step:/i.test(l));
  const opening = lines[0] && !/^\d+\./.test(lines[0]) ? lines[0] : null;
  // No parseable steps → the whole string becomes a single bubble, so the
  // legacy payload still renders as chat bubbles, never an amber wall.
  const bubbles = steps.length > 0 ? steps : [text.trim()];
  return (
    <div className="card flush conv-starters">
      <div className="card-head">
        <h3>Conversation starters · {platformName}</h3>
        <button type="button" className="btn btn-tertiary btn-sm" onClick={() => copy(text)}>
          <Icon name="copy" size={12} /> Copy all
        </button>
      </div>
      <div style={{ padding: 14 }}>
        {opening && steps.length > 0 ? (
          <p style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.6, margin: "0 0 10px" }}>
            {opening}
          </p>
        ) : null}
        {bubbles.map((s, i) => (
          <StarterBubble key={i} index={i} text={s} onCopy={copy} />
        ))}
        {next ? (
          <p style={{ marginTop: 10, padding: 10, background: "var(--z-ice)", borderRadius: 6, fontSize: 12.5, fontWeight: 500, lineHeight: 1.6 }}>
            {next}
          </p>
        ) : null}
      </div>
    </div>
  );
}
