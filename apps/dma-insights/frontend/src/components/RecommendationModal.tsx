/**
 * RecommendationModal — opens for a single rec_id; prototype parity
 * (374f91c6 · RecommendationModal) restored per plan Part 7.2: three
 * prototype tabs + the internal-only AE-notes tab —
 *
 *   1. "DMA impact"           — customer-impact tiles (outcomes
 *      time/effort/metric/peer), ABSOLUTE before→after pillar uplift
 *      bars (before = the run's current pillar score, after = +uplift;
 *      delta-only rendering survives as the fallback when the run's
 *      pillar scores aren't loadable), description, targets, platform,
 *      cited references.
 *   2. "Root-cause evidence"  — the restored evidence tab: E-ID chips
 *      grounding the rec's root cause → EvidenceDrawer.
 *   3. "Sequencing"           — DependencyMap (prerequisites / this /
 *      unlocks), fed by the now-populated prerequisite_rec_ids.
 *   4. "AE notes"             — NotesPanel (migration 057): multi-note
 *      field intelligence with author/status/recalibrate + Gemini
 *      impact assessment. Hidden for the customer audience.
 *
 * Render-state matrix:
 *   1. closed                       → null (modal not open)
 *   2. open + no recommendationId   → modal body shows "no rec selected"
 *   3. isLoading                    → spinner
 *   4. error / 404                  → "Couldn't load recommendation"
 *   5. unresolved_count > 0         → amber "Pending review" banner +
 *                                     unresolved citations marked
 *                                     visually distinct
 *   6. happy path                   → full body + clickable references
 */
import { useEffect, useState } from "react";
import { Modal } from "@/components/Modal";
import { stripLabelPrefix } from "@/lib/sanitize";
import { EmptyState, Pill, Spinner } from "@/components/utils";
import {
  useRecommendationDetail,
  type CitedReference,
  type RecommendationDetail,
} from "@/lib/recommendations";
import { maturityHex } from "@/lib/maturity";
import { useEntityOverview } from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { lookupRecUuid, useEntityRecommendations } from "@/lib/entityRecommendations";
import { NotesPanel } from "@/components/NotesPanel";

interface RecommendationModalProps {
  open: boolean;
  onClose: () => void;
  recommendationId: string | null;
  /** Entity scope for REC-NN display-code lookups (stairstep / roadmap
   *  openers hold only the code — see recommendationDetailPath) AND the
   *  pack-first snapshot fallback (2026-07-06: platform-page rec
   *  drilldown failed to load). */
  displayId?: string | null;
}

type Tab = "impact" | "evidence" | "dependencies" | "notes";

const TAB_LABEL: Record<Tab, string> = {
  impact: "DMA impact",
  evidence: "Root-cause evidence",
  dependencies: "Sequencing",
  notes: "AE notes",
};

export function RecommendationModal({
  open,
  onClose,
  recommendationId,
  displayId = null,
}: RecommendationModalProps) {
  const { data, isLoading, error } = useRecommendationDetail(
    open ? recommendationId : null,
    displayId,
  );
  // AE notes are internal field intelligence — never rendered to the
  // customer audience (mirrors the IntelligencePanel gate).
  const audience = useUiStore((s) => s.audience);
  const tabs = (Object.keys(TAB_LABEL) as Tab[]).filter(
    (t) => t !== "notes" || audience !== "customer",
  );
  const [tab, setTab] = useState<Tab>("impact");
  // Reset to DMA impact whenever a different rec opens (e.g. via a
  // DependencyMap chip), so the modal doesn't land on a stale tab.
  useEffect(() => { setTab("impact"); }, [recommendationId]);

  // Current pillar scores for the ABSOLUTE before→after uplift bars.
  const overviewQ = useEntityOverview(open ? data?.entity_display_id ?? null : null);
  const pillarScores: Record<string, number> = {};
  for (const p of overviewQ?.data?.pillar_scores ?? []) {
    if (p.score !== null && p.score !== undefined) pillarScores[p.pillar_id] = p.score;
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={data ? `${data.rec_id} · ${stripLabelPrefix(data.title)}` : "Recommendation"}
      size="wide"
    >
      {!recommendationId ? (
        <EmptyState
          title="No recommendation selected"
          body="Click a step on the stairstep curve to open its details."
        />
      ) : isLoading ? (
        <div className="page-loading">
          <Spinner /> Loading recommendation…
        </div>
      ) : error || !data ? (
        <EmptyState
          title="Couldn't load recommendation"
          body={error?.message ?? "Try again in a moment."}
        />
      ) : (
        <div className="rec-modal-body">
          {/* Prototype header chips: platform · feature · phase · effort/time */}
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
            {data.platform_id ? (
              <span className="b b-teal">
                {data.platform_id}{data.feature ? ` · ${data.feature}` : ""}
              </span>
            ) : data.feature ? (
              <span className="b b-teal">{data.feature}</span>
            ) : null}
            {data.phase ? <span className="b b-purple">Phase {data.phase}</span> : null}
            {(data.outcomes?.effort || data.outcomes?.time) ? (
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                {data.outcomes?.effort ? `Effort ${data.outcomes.effort}` : null}
                {data.outcomes?.effort && data.outcomes?.time ? " · " : null}
                {data.outcomes?.time ?? null}
              </span>
            ) : null}
          </div>

          {data.unresolved_count > 0 ? (
            <div className="rec-modal-warning" role="alert">
              <strong>Pending review.</strong>{" "}
              {data.unresolved_count} cited reference
              {data.unresolved_count === 1 ? "" : "s"} did not resolve in
              catalogue {data.catalogue_version}. The Analyst should
              verify before sharing externally.
            </div>
          ) : null}

          <div role="tablist" aria-label="Recommendation detail"
               style={{ display: "flex", borderBottom: "1px solid var(--z-sep)", marginBottom: 14 }}>
            {tabs.map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t}
                      className="client-tab"
                      style={{
                        background: "transparent",
                        color: tab === t ? "var(--z-teal)" : "var(--z-muted)",
                        borderBottom: tab === t ? "2px solid var(--z-teal)" : "2px solid transparent",
                      }}
                      onClick={() => setTab(t)}>
                {TAB_LABEL[t]}
              </button>
            ))}
          </div>

          {tab === "impact" ? (
            <ImpactTab data={data} pillarScores={pillarScores} />
          ) : tab === "evidence" ? (
            <RootCauseEvidenceTab data={data} />
          ) : tab === "dependencies" ? (
            <DependencyMap data={data} />
          ) : (
            <NotesPanel
              displayId={displayId ?? data.entity_display_id}
              targetKind="recommendation"
              targetId={data.rec_id}
            />
          )}
        </div>
      )}
    </Modal>
  );
}

// AE-notes adjudication (2026-07-10 merge): the deploy branch shipped a
// single shared-note textarea here (AENotes, backed by the live
// recommendation_notes table + /recommendation-notes endpoints). The
// redeploy branch shipped the richer multi-note NotesPanel (per-note
// author/status/recalibrate + Gemini impact assessment) as the "AE notes"
// TAB. One notes surface only: the tab wins; the shared-note textarea UI
// was dropped, while its backend endpoints and lib/recNotes.ts client
// remain live so any data captured server-side is preserved.

/** Tab 1 — DMA impact: customer-impact tiles + absolute uplift bars +
 *  description/targets/platform/citations. */
function ImpactTab({ data, pillarScores }: {
  data: RecommendationDetail;
  pillarScores: Record<string, number>;
}): JSX.Element {
  const outcomes = data.outcomes ?? null;
  const tiles: Array<[string, string]> = [];
  if (outcomes?.time) tiles.push(["Time", outcomes.time]);
  if (outcomes?.effort) tiles.push(["Effort", outcomes.effort]);
  if (outcomes?.metric) tiles.push(["Success metric", outcomes.metric]);
  if (outcomes?.peer) tiles.push(["Peer proof", outcomes.peer]);
  return (
    <>
      {tiles.length > 0 ? (
        <div className="g3" style={{ marginBottom: 14 }} data-testid="rec-impact-tiles">
          {tiles.map(([k, v]) => (
            <div key={k} className="card-tile" style={{ background: "var(--z-ice)", padding: 14 }}>
              <div style={{ fontSize: 10, color: "var(--z-mid)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>{k}</div>
              <div style={{ fontSize: k === "Success metric" || k === "Peer proof" ? 13 : 18, fontWeight: 700, color: "var(--z-dark)" }}>{v}</div>
            </div>
          ))}
        </div>
      ) : null}

      <section>
        <h4>Description</h4>
        <p>{data.description}</p>
      </section>

      {data.uplift_per_pillar ? (
        <section>
          <h4>Projected pillar uplift</h4>
          {/* .pbar family — mirrors the prototype Impact view. ABSOLUTE
              before→after when the run's pillar scores are available
              (before = current score at 45% opacity on top, after =
              before + uplift underneath, trailing absolute + delta
              columns); delta-only fallback otherwise. */}
          <div data-testid="rec-uplift-pbars">
            {Object.entries(data.uplift_per_pillar).map(([pillar, uplift]) => {
              const before = pillarScores[pillar];
              if (before !== undefined) {
                const after = Math.min(5, before + uplift);
                return (
                  <div key={pillar} className="pbar" data-testid={`pbar-abs-${pillar}`}>
                    <span className="pbar-name">{pillar}</span>
                    <div
                      className="pbar-track"
                      role="progressbar"
                      aria-valuenow={after}
                      aria-valuemin={0}
                      aria-valuemax={5}
                      aria-label={`${pillar}: ${before.toFixed(1)} today, ${after.toFixed(1)} projected`}
                      style={{ position: "relative" }}
                    >
                      <div
                        style={{
                          position: "absolute", left: 0, top: 0, height: "100%",
                          width: `${Math.min(100, (after / 5) * 100)}%`,
                          background: maturityHex(after), borderRadius: 4,
                        }}
                      />
                      <div
                        className="pbar-fill"
                        style={{
                          position: "absolute", left: 0, top: 0, height: "100%",
                          width: `${Math.min(100, (before / 5) * 100)}%`,
                          background: maturityHex(before), opacity: 0.45,
                        }}
                      />
                    </div>
                    <span className="pbar-score">{after.toFixed(1)}</span>
                    <span className="pbar-delta" style={{ color: "var(--z-mid)" }}>
                      +{(after - before).toFixed(2)}
                    </span>
                  </div>
                );
              }
              return (
                <div key={pillar} className="pbar">
                  <span className="pbar-name">{pillar}</span>
                  <div
                    className="pbar-track"
                    role="progressbar"
                    aria-valuenow={uplift}
                    aria-valuemin={0}
                    aria-valuemax={5}
                    aria-label={`Uplift on ${pillar}: +${uplift.toFixed(2)} of 5`}
                  >
                    <div
                      className="pbar-fill"
                      style={{
                        width: `${Math.min(100, (uplift / 5) * 100)}%`,
                        background: maturityHex(uplift),
                      }}
                    />
                  </div>
                  <span className="pbar-delta" style={{ color: "var(--z-mid)" }}>
                    +{uplift.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {data.target_subcap_ids.length > 0 ? (
        <section>
          <h4>Targets {data.target_subcap_ids.length} sub-capabilit
            {data.target_subcap_ids.length === 1 ? "y" : "ies"}
          </h4>
          <div className="rec-targets">
            {data.target_subcap_ids.map((sid) => (
              <code key={sid} className="rec-subcap-chip">{sid}</code>
            ))}
          </div>
        </section>
      ) : null}

      {data.platform_id ? (
        <section>
          <h4>Platform</h4>
          <Pill tone="teal">{data.platform_id}</Pill>
          {data.effort_band ? (
            <Pill tone="amber">{data.effort_band} effort</Pill>
          ) : null}
        </section>
      ) : null}

      <CitedSection
        heading="Cited features"
        items={data.cited_features}
        emptyText="No features cited."
      />
      <CitedSection
        heading="Cited platform constructs"
        items={data.cited_constructs}
        emptyText="No platform constructs cited."
      />
      <CitedSection
        heading="Cited agents"
        items={data.cited_agents}
        emptyText="No agents cited."
      />
    </>
  );
}

/** Tab 2 — the restored Root-cause evidence tab (prototype 374f91c6):
 *  E-ID chips grounding the rec's root cause → EvidenceDrawer. */
function RootCauseEvidenceTab({ data }: { data: RecommendationDetail }): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const eIds = data.root_cause_e_ids ?? [];
  if (eIds.length === 0) {
    return (
      <EmptyState
        title="No root-cause evidence recorded"
        body="This recommendation's source did not cite E-IDs for its root cause."
      />
    );
  }
  return (
    <div data-testid="root-cause-evidence">
      <p style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 12 }}>
        The root cause is grounded in the following evidence. Click any chip
        to open the full source.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {eIds.map((eid) => (
          <button key={eid} type="button" className="chip"
                  style={{ cursor: "pointer", border: 0 }}
                  onClick={() =>
                    // Part 11.1 spine: pass the clicked eId (scroll-to +
                    // highlight) AND the rec's full root-cause citation
                    // list so the drawer scopes to exactly these rows.
                    openDrawer("evidence", {
                      displayId: data.entity_display_id,
                      subcapId: data.target_subcap_ids[0] ?? null,
                      eId: eid,
                      eIds,
                      origin: "rec-root-cause",
                    })}>
            {eid}
          </button>
        ))}
      </div>
      {data.target_subcap_ids.length > 0 ? (
        <p style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 12 }}>
          Evidence opens scoped to {data.target_subcap_ids[0]} — the rec's
          primary target subcap.
        </p>
      ) : null}
    </div>
  );
}

function CitedSection({
  heading,
  items,
  emptyText,
}: {
  heading: string;
  items: CitedReference[];
  emptyText: string;
}) {
  if (items.length === 0) {
    return (
      <section>
        <h4>{heading}</h4>
        <p className="muted">{emptyText}</p>
      </section>
    );
  }
  return (
    <section>
      <h4>{heading}</h4>
      <ul className="rec-cited-list">
        {items.map((item) => (
          <li
            key={item.id}
            className={`rec-cited ${item.resolved ? "resolved" : "unresolved"}`}
          >
            <code style={item.resolved ? undefined : { textDecoration: "line-through" }}>
              {item.id}
            </code>
            {item.resolved ? (
              <Pill tone="green">resolved</Pill>
            ) : (
              <Pill tone="red">not in catalogue</Pill>
            )}
            {item.name && item.name !== item.id ? (
              <span className="muted"> — {item.name}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

// D4 DependencyMap — Prerequisites / This initiative / Unlocks (prototype
// drawers.jsx DependencyMap 1:1): PHASE header row, then three card
// columns — prerequisite tiles (ice), the highlighted current-initiative
// card (lavender + teal border), and downstream-unlock tiles (ph0-lt).
// Tiles resolve rec_id→UUID and open that rec; the prototype's honest
// column empties ("No prerequisites · can land first" / "No downstream
// initiatives") replace the old all-or-nothing empty state.
// Fed by the Part-7.2 dependency mining (prerequisite_rec_ids populated).
const DEP_HEAD: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, letterSpacing: ".1em",
  color: "var(--z-muted)", textTransform: "uppercase", marginBottom: 8,
};

function DependencyMap({ data }: { data: RecommendationDetail }): JSX.Element {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const recRows = useEntityRecommendations(data.entity_display_id).data;
  const { prerequisites, unlocks } = data.dependencies;
  const openRec = (recId: string): void => {
    const uuid = lookupRecUuid(recRows, recId);
    if (uuid) {
      openDrawer("recommendation", {
        recommendationId: uuid, displayId: data.entity_display_id,
      });
    }
  };
  const titleFor = (recId: string): string | null =>
    recRows?.find((r) => r.rec_id === recId)?.title ?? null;
  return (
    <div data-testid="dependency-map">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="b b-muted">PHASE {data.phase ?? "-"}</span>
        <span style={{ fontSize: 12 }}>Sequencing position in the transformation roadmap</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, alignItems: "stretch" }}>
        <DepColumn title="Prerequisites" ids={prerequisites} tileBg="var(--z-ice)"
                   emptyText="No prerequisites · can land first"
                   titleFor={titleFor} onOpenRec={openRec} />
        <div className="card" style={{ padding: 12, background: "var(--z-lav)", border: "2px solid var(--z-teal)" }}>
          <div style={{ ...DEP_HEAD, color: "var(--z-mid)" }}>This initiative</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{data.rec_id}</div>
          <div style={{ fontSize: 11, color: "var(--z-body)", marginTop: 4 }}>{stripLabelPrefix(data.title)}</div>
          <div className="sep" />
          <div style={{ fontSize: 11 }}>
            Phase {data.phase ?? "-"}{data.outcomes?.time ? ` · ${data.outcomes.time}` : ""}
          </div>
        </div>
        <DepColumn title="Unlocks" ids={unlocks} tileBg="var(--ph0-lt)"
                   emptyText="No downstream initiatives"
                   titleFor={titleFor} onOpenRec={openRec} />
      </div>
    </div>
  );
}

function DepColumn({ title, ids, tileBg, emptyText, titleFor, onOpenRec }: {
  title: string;
  ids: string[];
  tileBg: string;
  emptyText: string;
  titleFor: (recId: string) => string | null;
  onOpenRec: (recId: string) => void;
}): JSX.Element {
  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={DEP_HEAD}>{title}</div>
      {ids.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>{emptyText}</div>
      ) : (
        ids.map((rid) => {
          const t = titleFor(rid);
          return (
            <button key={rid} type="button"
                    style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px",
                             background: tileBg, border: 0, borderRadius: 6, marginBottom: 6, cursor: "pointer" }}
                    onClick={() => onOpenRec(rid)}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{rid}</div>
              {t ? <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{stripLabelPrefix(t)}</div> : null}
            </button>
          );
        })
      )}
    </div>
  );
}
