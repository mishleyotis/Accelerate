/**
 * D7 ClientTechStackDetail — structural port of the wireframe drilldown
 * (proto ClientTechStackDetail, 28883abf:895-1078) bound to the Part 9
 * TechStackDetailResponse.
 *
 * Wireframe anatomy kept:
 *   breadcrumb ("Tech stack overview" › {name})
 *   header card (layer chip · status chip · since/Detected chip · 22px
 *                title · right-side DMA-impact stat)
 *   2-col grid: Detection evidence card + DMA assessment impact card
 *   2-col grid: Gap zones (ABSENT rows) + Peer deployment card
 *   Zennify recommendation callout (ABSENT rows)
 *
 * Data honesty (Part 9):
 *   - status: real 4-state (CONFIRMED / INFERRED / CLAIMED / ABSENT +
 *     REMOVED); ABSENT rows are server-generated scored-family gap rows,
 *     so the gap-zone bullets + recommendation callout render on REAL
 *     data (addressable subcaps with run scores + cohort coverage) — no
 *     fabricated bullets.
 *   - DMA impact: avg gap-to-peer-median across addressed subcaps when
 *     the run scores make it computable; otherwise the honest linked
 *     sub-capability count.
 *   - Peer deployment: real cohort share (% bar) + named cohort peers
 *     with true adoption flags; falls back to the plain count when the
 *     payload predates Part 9.
 *   - Pack fallback: the API is primary; when it is cold the hook
 *     hydrates from the committed techstack LIST snapshot row (no
 *     per-tech snapshot exists) — cohort extras simply stay empty.
 *
 * Route: /clients/:id/techstack/:techId
 */
import { Icon, EmptyState, Spinner } from "@/components/utils";
import { techSourceLabel } from "@/lib/labels";
import { useRoute } from "@/lib/hash-router";
import { useTechStackDetail } from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { LAYER_INFO, layerCodeOf, mapStatus } from "@/pages/TechStackPage";
import type { MappedStatus } from "@/pages/TechStackPage";
import type { TechSubcapImpact } from "@/lib/queries";

function getIds(path: string): { displayId: string; techId: string } | null {
  const m = path.match(/^\/clients\/([^/]+)\/techstack\/([^/]+)$/);
  return m ? { displayId: m[1], techId: decodeURIComponent(m[2]) } : null;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/* Wireframe STATUS_STYLE — colors verbatim; labels grounded on the real
   4-state read model. */
const STATUS_CHIP: Record<MappedStatus, { bg: string; bd: string; color: string; label: (src: string) => string }> = {
  CONFIRMED: {
    bg: "var(--z-ice)", bd: "rgba(39,187,175,.4)", color: "var(--z-mid)",
    label: (src) => `Confirmed - ${src || "source-asserted"}`,
  },
  INFERRED: {
    bg: "var(--ph0-lt)", bd: "var(--ph0-bd)", color: "var(--z-dpur)",
    label: () => "Inferred - technographic · job posting · press",
  },
  CLAIMED: {
    bg: "rgba(254,151,50,.08)", bd: "rgba(254,151,50,.3)", color: "#7C3500",
    label: () => "Claimed - marketing-tier source only",
  },
  ABSENT: {
    bg: "rgba(194,80,8,.10)", bd: "rgba(194,80,8,.25)", color: "var(--z-below)",
    label: () => "Absent - not detected in the stack",
  },
  CONFIRMED_REMOVED: {
    bg: "rgba(194,80,8,.06)", bd: "rgba(194,80,8,.25)", color: "var(--z-below)",
    label: () => "Removed - decommissioned",
  },
};

/** Avg positive gap to peer median across addressed subcaps — the honest,
 *  computable "ceiling uplift"; null when the run scores don't allow it. */
export function avgPeerUplift(impacts: TechSubcapImpact[] | undefined): { value: number; n: number } | null {
  const deltas = (impacts ?? [])
    .filter((i) => i.score != null && i.peer_median != null)
    .map((i) => Math.max(0, (i.peer_median as number) - (i.score as number)));
  if (deltas.length === 0) return null;
  return {
    value: deltas.reduce((a, b) => a + b, 0) / deltas.length,
    n: deltas.length,
  };
}

export function TechStackDetailPage(): JSX.Element {
  const { path, navigate } = useRoute();
  const ids = getIds(path);
  const openDrawer = useUiStore((s) => s.openDrawer);

  const { data, isLoading, error } = useTechStackDetail(
    ids?.displayId ?? null, ids?.techId ?? null,
  );

  if (!ids) {
    return (
      <EmptyState
        title="Invalid tech stack URL"
        body="Expected /clients/:id/techstack/:techId"
      />
    );
  }
  if (isLoading) {
    return (
      <div className="page-loading">
        <Spinner /> Loading tech detail…
      </div>
    );
  }
  if (error || !data) {
    return (
      <EmptyState
        title="Technology not found"
        body={(error as Error | null)?.message}
      />
    );
  }

  const { entry, evidence_e_ids, linked_subcap_ids } = data;
  const status = mapStatus(entry);
  const S = STATUS_CHIP[status] ?? STATUS_CHIP.CONFIRMED;
  const isAbsent = status === "ABSENT";
  const layerName = entry.layer_full
    ?? LAYER_INFO[layerCodeOf(entry)]?.name ?? entry.layer;
  const productName = entry.product_name ?? entry.product;
  const title = productName && productName.toLowerCase() !== entry.vendor.toLowerCase()
    ? `${entry.vendor} · ${productName}` : entry.vendor;
  const note = entry.note
    ?? (productName && productName !== entry.vendor && productName.length <= 120 ? productName : null);

  const impacts = data.impacts ?? [];
  const uplift = avgPeerUplift(impacts);
  const peerCoverage = data.peer_coverage ?? entry.peer_coverage ?? null;
  const peerNames = data.peer_names ?? [];
  const gapZones = data.gap_zones ?? [];
  const cohortLabel = data.cohort_label ?? "cohort";

  return (
    <div className="page" data-page="techstack-detail" data-source="api">
      {/* Breadcrumb */}
      <div className="row" style={{ fontSize: 12, color: "var(--z-muted)", marginBottom: 14 }}>
        <a href={`#/clients/${ids.displayId}/techstack`} style={{ color: "var(--z-mid)", fontWeight: 500 }}>
          Tech stack overview
        </a>
        <Icon name="chevron-r" size={12} />
        <strong style={{ color: "var(--z-dark)" }}>{title}</strong>
      </div>

      {/* Header card */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ marginBottom: 8, flexWrap: "wrap" }}>
          <span className="b b-muted" style={{ textTransform: "uppercase" }}>{layerName}</span>
          <span className="b" data-testid="detail-status-chip"
                style={{ background: S.bg, color: S.color, border: `1px solid ${S.bd}` }}>
            {S.label(entry.source)}
          </span>
          {entry.primary_gap ? <span className="b b-ph1">PRIMARY GAP</span> : null}
          {/* Real `since` (evidence-mined) — else the ingest timestamp is
              honestly labelled "Detected", never "Since". */}
          {entry.since ? (
            <span style={{ fontSize: 11, color: "var(--z-muted)", background: "var(--z-lav)", padding: "2px 8px", borderRadius: 3 }}>
              Since {entry.since}
            </span>
          ) : entry.detected_at ? (
            <span style={{ fontSize: 11, color: "var(--z-muted)", background: "var(--z-lav)", padding: "2px 8px", borderRadius: 3 }}>
              Detected {fmtDate(entry.detected_at)}
            </span>
          ) : null}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: "var(--z-dark)", marginBottom: 6 }}>{title}</div>
            {note ? (
              <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.55, maxWidth: 720 }}>{note}</div>
            ) : null}
          </div>
          {/* DMA impact: peer-median uplift when computable, else the
              honest linked-subcap count. */}
          <div style={{ textAlign: "right", flexShrink: 0 }} data-testid="dma-impact-stat">
            <div style={{ fontSize: 10, color: "var(--z-muted)", marginBottom: 4 }}>DMA impact</div>
            {uplift ? (
              <>
                <div style={{ fontSize: 32, fontWeight: 200, color: isAbsent ? "var(--z-below)" : "var(--z-teal)", lineHeight: 1 }}>
                  {isAbsent ? "−" : "+"}{uplift.value.toFixed(1)}
                </div>
                <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
                  avg gap to peer median · {uplift.n} sub-cap{uplift.n === 1 ? "" : "s"}
                  {isAbsent ? " (ceiling blocked)" : ""}
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 32, fontWeight: 200, color: isAbsent ? "var(--z-below)" : "var(--z-teal)", lineHeight: 1 }}>
                  {linked_subcap_ids.length}
                </div>
                <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 2 }}>
                  linked sub-capabilit{linked_subcap_ids.length === 1 ? "y" : "ies"}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 2-col: Evidence + DMA assessment impact */}
      <div className="g2" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="evidence" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Detection evidence</div>
            <span className="spacer" />
            <span className="b b-muted">{evidence_e_ids.length} items</span>
          </div>
          {evidence_e_ids.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)", padding: "8px 12px", background: "var(--z-lav)", borderRadius: 6 }}>
              {isAbsent
                ? "No evidence items - this gap row derives from the absence of the family in the detected stack."
                : `No evidence items - detection recorded from ${entry.source || "the technographic feed"}.`}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* Source signal first (real detection trail) */}
              {entry.source ? (
                <div style={{ padding: "8px 10px", background: "var(--z-ice)", borderLeft: "3px solid var(--z-teal)", borderRadius: 4 }}>
                  <div className="row" style={{ marginBottom: 3, fontSize: 11 }}>
                    <span className="b b-teal" title={entry.source}>{techSourceLabel(entry.source)}</span>
                    <span style={{ fontSize: 10, color: "var(--z-muted)" }}>Detection source</span>
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--z-dark)" }}>
                    {entry.since ? `Deployed since ${entry.since}` : `Recorded ${fmtDate(entry.detected_at)}`}
                  </div>
                </div>
              ) : null}
              {/* E-ID chips → EvidenceDrawer (single source for source/url/excerpt) */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {evidence_e_ids.map((eid) => (
                  <button
                    key={eid}
                    type="button"
                    className="chip purple"
                    onClick={() => openDrawer("evidence", { eId: eid, eIds: evidence_e_ids, displayId: ids.displayId, origin: "techstack-detail" })}
                    style={{ cursor: "pointer" }}
                    title={`Open evidence ${eid}`}
                  >
                    {eid}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="heatmap" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>DMA assessment impact</div>
            <span className="spacer" />
            <button type="button" className="btn btn-tertiary btn-sm"
                    onClick={() => navigate(`/clients/${ids.displayId}/heatmap`)}>
              Open heatmap <Icon name="arrow-r" size={11} />
            </button>
          </div>
          {linked_subcap_ids.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--z-muted)" }}>No subcap impact mapped.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {(impacts.length > 0 ? impacts : linked_subcap_ids.map((sid) => ({ subcap_id: sid } as TechSubcapImpact))).map((i) => (
                <button
                  key={i.subcap_id}
                  type="button"
                  data-testid="impact-row"
                  onClick={() => navigate(`/clients/${ids.displayId}/heatmap?zoom=subcap&subcap=${encodeURIComponent(i.subcap_id)}`)}
                  style={{
                    padding: "8px 12px", borderRadius: 6, textAlign: "left", cursor: "pointer",
                    background: i.thin ? "rgba(254,151,50,.08)" : "var(--z-ice)",
                    border: i.thin ? "1px solid rgba(254,151,50,.3)" : "1px solid transparent",
                    display: "flex", alignItems: "center", gap: 8,
                  }}
                  title={`Open ${i.subcap_id} in heatmap`}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span className="f-mono" style={{ fontSize: 11, color: "var(--z-dark)" }}>{i.subcap_id}</span>
                    {i.name ? <span style={{ fontSize: 11, color: "var(--z-body)", marginLeft: 6 }}>{i.name}</span> : null}
                    {i.thin ? <div style={{ fontSize: 9.5, color: "var(--z-org)", marginTop: 1 }}>▲ Thin evidence</div> : null}
                  </div>
                  {i.score != null ? (
                    <span className="row" style={{ gap: 6, flexShrink: 0 }}>
                      <strong style={{ fontSize: 13, color: isAbsent ? "var(--z-below)" : "var(--z-mid)" }}>{i.score.toFixed(1)}</strong>
                      {i.peer_median != null ? (
                        <span style={{ fontSize: 10.5, color: "var(--z-muted)" }}>peer {i.peer_median.toFixed(1)}</span>
                      ) : null}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 2-col: Gap zones (ABSENT) + Peer deployment */}
      <div className="g2" style={{ marginBottom: isAbsent ? 14 : 0 }}>
        {isAbsent && gapZones.length > 0 ? (
          <div className="card" data-testid="gap-zones-card">
            <div className="row" style={{ marginBottom: 12 }}>
              <Icon name="warn" size={15} style={{ color: "var(--z-below)" }} />
              <div style={{ fontSize: 13, fontWeight: 600 }}>Gap zones - what {entry.vendor} would unlock</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {gapZones.map((g, i) => (
                <div key={i} style={{ padding: "8px 12px", background: "rgba(194,80,8,.05)", border: "1px solid rgba(194,80,8,.15)", borderRadius: 5, fontSize: 12, color: "var(--z-below)", lineHeight: 1.5 }}>{g}</div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="card" data-testid="peer-deployment-card">
          <div className="row" style={{ marginBottom: 12 }}>
            <Icon name="scale" size={15} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>Peer deployment</div>
            <span className="spacer" />
            {peerCoverage != null ? (
              <span className="b b-teal">{Math.round(peerCoverage * 100)}% adopted</span>
            ) : (
              <span className="b b-muted">{data.peer_adoption_count} peer{data.peer_adoption_count === 1 ? "" : "s"}</span>
            )}
          </div>
          {peerCoverage != null ? (
            <>
              <div className="prog" style={{ marginBottom: 10 }}>
                <div className="prog-fill" data-testid="peer-coverage-bar"
                     style={{ width: `${Math.round(peerCoverage * 100)}%`, background: "linear-gradient(90deg, var(--z-teal), var(--z-mid))" }} />
              </div>
              <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: peerNames.length ? 10 : 0 }}>
                {Math.round(peerCoverage * 100)}% of {cohortLabel}
                {data.cohort_size ? ` (${data.cohort_size} assessed)` : ""} carry this technology.
              </div>
              {peerNames.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {peerNames.map((p) => (
                    <div key={p.name} data-testid="peer-name-row"
                         style={{ padding: "6px 10px", background: p.has_tech ? "var(--z-ice)" : "var(--z-lav)", borderRadius: 5, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11.5 }}>
                      <span style={{ color: "var(--z-dark)", fontWeight: 500 }}>{p.name}</span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: p.has_tech ? "var(--z-mid)" : "var(--z-muted)" }}>
                        {p.has_tech ? `✓ ${entry.vendor.split(" ")[0]}` : "not detected"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.5 }}>
              {data.peer_adoption_count > 0
                ? `${data.peer_adoption_count} other assessed organisation${data.peer_adoption_count === 1 ? "" : "s"} in the corpus also carr${data.peer_adoption_count === 1 ? "ies" : "y"} this technology.`
                : "Cohort adoption data arrives once the live API warms."}
            </div>
          )}
        </div>
      </div>

      {/* Zennify recommendation callout (ABSENT rows only) — grounded copy */}
      {isAbsent ? (
        <div className="card" data-testid="zennify-recommendation"
             style={{ background: "var(--ph0-lt)", border: "1px solid var(--ph0-bd)" }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <Icon name="sparkle" size={15} style={{ color: "var(--z-dpur)" }} />
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dpur)" }}>Zennify recommendation</div>
            <span className="spacer" />
            <button type="button" className="btn btn-tertiary btn-sm"
                    onClick={() => navigate(`/clients/${ids.displayId}/platform`)}>
              See platform matrix <Icon name="arrow-r" size={11} />
            </button>
          </div>
          <div style={{ fontSize: 13, color: "#3B0764", lineHeight: 1.65 }}>
            {entry.vendor} is absent from the detected stack
            {peerCoverage != null ? ` while ${Math.round(peerCoverage * 100)}% of ${cohortLabel} deploy it` : ""}.
            The catalogue maps it to {linked_subcap_ids.length} scored sub-capabilit{linked_subcap_ids.length === 1 ? "y" : "ies"} —
            open the platform matrix for fit, sequencing and readiness prerequisites.
          </div>
        </div>
      ) : null}
    </div>
  );
}
