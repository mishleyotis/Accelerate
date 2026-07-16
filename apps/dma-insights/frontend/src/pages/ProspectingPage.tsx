/**
 * ProspectingPage — ported 1:1 from prototype
 * (standalone-src/src/pages-f.jsx · ProspectingPage).
 *
 * CUSTOMER-SAFE eyebrow + lock badge in page-head. Search .card with
 * typeahead .inp + recent-searches hint. On pick, renders the
 * ScorecardPreview card (ScoreRing + pillar .g4 + top-3 platforms .g3)
 * and Export PDF / Download HTML actions. Export resolves via the B-6
 * useExportScorecard hook; success shows a co.co-teal "ready" callout.
 */
import { useMemo, useState } from "react";
import { Icon, Spinner } from "@/components/utils";
import {
  useEntities, useEntityOverviewAsCustomer, useEntityPlatformsAsCustomer,
  useExportScorecard,
} from "@/lib/queries";
import { ScoreRing } from "@/components/utils";
import { maturityHex } from "@/lib/maturity";
import { healName, healSubvertical } from "@/lib/heal";
import { useUiStore, type ToastKind } from "@/store/ui";

const PILLARS = [
  { id: "P1", short: "Strategy" },
  { id: "P2", short: "Customer" },
  { id: "P3", short: "Operations" },
  { id: "P4", short: "Data & Tech" },
];

export function ProspectingPage(): JSX.Element {
  const [q, setQ] = useState("");
  const [pickedId, setPickedId] = useState<string | null>(null);
  const pushToast = useUiStore((s) => s.pushToast);

  const entitiesQ = useEntities({ owner: "all" });
  const allEntities = entitiesQ.data?.items ?? [];

  const matches = useMemo(() => {
    if (!q) return [];
    const needle = q.toLowerCase();
    return allEntities.filter((e) => e.name.toLowerCase().includes(needle)).slice(0, 5);
  }, [q, allEntities]);

  const picked = pickedId ? allEntities.find((e) => e.display_id === pickedId) ?? null : null;

  return (
    <div className="page" data-page="prospecting" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Customer-safe export</div>
          <h1>Prospecting</h1>
          <div className="sub">Search → one-page scorecard → export PDF or HTML</div>
        </div>
        <span className="b b-org" style={{ alignSelf: "center" }}>
          <Icon name="lock" size={10} /> CUSTOMER-SAFE MODE
        </span>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ position: "relative", maxWidth: 600 }}>
          <input className="inp" style={{ paddingLeft: 32, fontSize: 14, padding: "11px 14px 11px 32px" }}
                 placeholder="Search by institution name…"
                 value={q}
                 onChange={(e) => setQ(e.target.value)} />
          <span style={{ position: "absolute", top: 10, left: 10, color: "var(--z-muted)" }}><Icon name="search" size={14} /></span>
          {matches.length > 0 ? (
            <div style={{
              position: "absolute", top: 46, left: 0, right: 0, background: "#fff",
              border: "1px solid var(--z-sep)", borderRadius: 8,
              boxShadow: "var(--sh-lg)", zIndex: 5,
            }}>
              {matches.map((e) => (
                <button key={e.id} type="button"
                        style={{
                          display: "flex", width: "100%", padding: "10px 14px",
                          borderBottom: "1px solid var(--z-sep)", background: "transparent",
                          textAlign: "left", gap: 12, alignItems: "center", cursor: "pointer",
                        }}
                        onClick={() => { setPickedId(e.display_id); setQ(""); }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{healName(e.name)}</div>
                    <div style={{ fontSize: 11, color: "var(--z-muted)" }}>
                      {healSubvertical(e.subvertical)}{e.domain ? ` · ${e.domain}` : ""}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: "var(--z-muted)" }}>
          {entitiesQ.isLoading ? "Loading clients…" : `${allEntities.length} clients indexed`}
        </div>
      </div>

      {picked ? (
        <ScorecardCard displayId={picked.display_id} name={picked.name} pushToast={pushToast} />
      ) : (
        <div className="empty">
          <h3>Search to begin</h3>
          <p>Search the institution name to load a one-page scorecard. The export is always Customer-safe — internal fields are stripped.</p>
        </div>
      )}
    </div>
  );
}

function ScorecardCard({
  displayId, name, pushToast,
}: {
  displayId: string;
  name: string;
  pushToast: (msg: string, level?: ToastKind) => void;
}): JSX.Element {
  // 2026-06-06 QA-6: the preview copy says "always Customer-safe --
  // internal fields are stripped" but until this batch, the hooks
  // honoured the GLOBAL audience and an internal AE saw the preview
  // render with internal-only fields (NPS notes, internal SCQA, etc.).
  // The *AsCustomer variants force `view=customer` server-side so the
  // audience_strip middleware removes internal fields before they hit
  // the wire -- the UI claim now matches the data shape.
  const overviewQ = useEntityOverviewAsCustomer(displayId);
  const platformsQ = useEntityPlatformsAsCustomer(displayId);
  const exportMutation = useExportScorecard();
  const [downloadReady, setDownloadReady] = useState<{ url: string; filename: string } | null>(null);

  async function go(format: "html" | "pdf"): Promise<void> {
    try {
      const out = await exportMutation.mutateAsync({ displayId, format });
      const a = document.createElement("a");
      a.href = out.url;
      a.download = out.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setDownloadReady(out);
      pushToast(`${format.toUpperCase()} ready — link valid 24h`, "success");
    } catch (err) {
      pushToast((err as Error).message, format === "pdf" ? "warn" : "error");
    }
  }

  const overview = overviewQ.data;
  const platforms = platformsQ.data?.cards ?? [];
  const top3 = platforms.slice().sort((a, b) => b.fit_score - a.fit_score).slice(0, 3);
  const pillarScores = (overview as { pillar_scores?: Array<{ pillar_id: string; score: number }> } | undefined)?.pillar_scores ?? [];
  const overall = pillarScores.length
    ? pillarScores.reduce((a, p) => a + p.score, 0) / pillarScores.length
    : 0;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>Scorecard preview · always Customer View</span>
        <span className="spacer" />
        <button type="button" className="btn btn-tertiary"
                disabled={exportMutation.isPending}
                onClick={() => void go("pdf")}>
          {exportMutation.isPending ? <Spinner /> : <><Icon name="download" size={13} /> Export PDF</>}
        </button>
        <button type="button" className="btn btn-secondary"
                disabled={exportMutation.isPending}
                onClick={() => void go("html")}>
          <Icon name="download" size={13} /> Download HTML
        </button>
      </div>

      {downloadReady ? (
        <div className="co co-teal" style={{ marginBottom: 14 }}>
          <div className="co-body">
            <strong>Ready</strong> — Your file ({downloadReady.filename}) is ready · link valid 24h.
          </div>
        </div>
      ) : null}

      {overviewQ.isLoading ? (
        <div className="page-loading"><Spinner /> Loading scorecard…</div>
      ) : (
        <div style={{ background: "var(--z-bg)", border: "1px solid var(--z-sep)", borderRadius: 12, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".1em" }}>
                Zennify · DMA Scorecard
              </div>
              <div style={{ fontSize: 24, fontWeight: 600, marginTop: 4 }}>{name}</div>
              <div style={{ fontSize: 12, color: "var(--z-muted)" }}>
                {healSubvertical(overview?.entity.subvertical)}
                {overview?.entity.domain ? ` · ${overview.entity.domain}` : ""}
              </div>
            </div>
            <ScoreRing score={overall} />
          </div>

          <div className="g4">
            {PILLARS.map((p) => {
              const ps = pillarScores.find((x) => x.pillar_id === p.id);
              const score = ps?.score ?? 0;
              return (
                <div key={p.id} className="card-tile">
                  <div style={{ fontSize: 10, color: "var(--z-muted)" }}>{p.id}</div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.short}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                    <span className="b" style={{ background: maturityHex(score), color: "#fff" }}>
                      {score.toFixed(1)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="sep" />

          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Top 3 platform opportunities</div>
          {top3.length === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>Platform recommendations appear after the assessment completes.</p>
          ) : (
            <div className="g3">
              {top3.map((p) => (
                <div key={p.platform_id} className="card-tile">
                  <strong>{p.display_name}</strong>
                  <div style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", marginTop: 4 }}>
                    {Math.round(p.fit_score)}
                    <span style={{ fontSize: 11, color: "var(--z-muted)" }}>/100</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{p.pillar}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
