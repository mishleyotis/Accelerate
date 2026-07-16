/**
 * EntityDirectoryPage — ported 1:1 from prototype
 * (standalone-src/src/pages-auth-dashboard-directory.jsx · EntityDirectoryPage).
 *
 * Page head with grid/table view toggle + Export + New run; filter bar
 * with search + subvertical + source + sort; .g3 grid of EntityCards OR
 * .card.flush table view. Search/filter/sort mirror the prototype state.
 */
import { useMemo, useState } from "react";
import { useRoute } from "@/lib/hash-router";
import { useEntities, useDashboard } from "@/lib/queries";
import { maturityHex } from "@/lib/maturity";
import { useUiStore } from "@/store/ui";
import { Icon, FreshnessDot, Pill, Spinner } from "@/components/utils";
import { downloadCsv } from "@/lib/export";
import { healHq, healName, healSubvertical, healText } from "@/lib/heal";

const PILLARS = [{ id: "P1" }, { id: "P2" }, { id: "P3" }, { id: "P4" }];

interface UIEntity {
  id: string;
  display_id: string;
  name: string;
  domain: string | null;
  subvertical: string | null;
  hq: string | null;
  overall: number | null;
  assessment_date: string | null;
  data_source: string | null;
  open_alerts: number;
  in_progress: boolean;
  pillar_scores: Record<string, number> | null;
  oss: Record<string, number> | null;
  current_batch: number;
}

export function DirectoryPage(): JSX.Element {
  const { navigate } = useRoute();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const pushToast = useUiStore((s) => s.pushToast);

  const [q, setQ] = useState("");
  const [subvFilter, setSubvFilter] = useState<string>("ALL");
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<"date" | "oss" | "alerts">("date");
  const [view, setView] = useState<"grid" | "table">("grid");

  const entitiesQ = useEntities({ owner: "all" });
  useDashboard("all"); // pre-warm

  const all: UIEntity[] = useMemo(() => {
    // Map backend EntitySummary to the prototype's UI shape. The cast-
    // away-the-type pattern that lived here pre-2026-06-05 silently
    // mapped `last_run_completed_at` (doesn't exist) to assessment_date
    // so every card date rendered `—`. Now that the frontend
    // EntitySummary type is synced to backend, the contract is checked.
    // `hq` / `oss` / `current_batch` aren't on backend; explicit
    // sentinels until the corresponding columns ship.
    const items = entitiesQ.data?.items ?? [];
    // 2026-06-15: backend now emits hq + top_platform + current_batch (platform
    // fit is computed for all 94), so the directory reads the real fields
    // through the render-heal layer instead of the old null sentinels.
    return items.map((e) => ({
      id: e.display_id,
      display_id: e.display_id,
      name: healName(e.name),
      domain: e.domain,
      subvertical: e.subvertical,
      hq: healHq(e.hq),
      overall: e.overall_score,
      assessment_date: e.last_run_at,
      data_source: e.data_source,
      // 2026-06-06 QA-M4: backend now emits open_alerts per entity.
      open_alerts: e.open_alerts,
      in_progress: e.in_progress,
      pillar_scores: e.pillar_scores,
      oss: e.top_platform ? { [e.top_platform.short]: e.top_platform.fit_score } : null,
      current_batch: e.current_batch ?? 1,
    }));
  }, [entitiesQ.data]);

  const subverticals = useMemo(() => {
    return Array.from(new Set(all.map((e) => e.subvertical).filter(Boolean) as string[])).sort();
  }, [all]);

  const filtered: UIEntity[] = useMemo(() => {
    const ql = q.toLowerCase().trim();
    let xs = all.filter((e) => {
      if (subvFilter !== "ALL" && e.subvertical !== subvFilter) return false;
      if (sourceFilter !== "ALL" && e.data_source !== sourceFilter) return false;
      if (ql) {
        const hay = `${e.name} ${e.domain ?? ""}`.toLowerCase();
        if (!hay.includes(ql)) return false;
      }
      return true;
    });
    if (sortBy === "date") {
      xs = xs.slice().sort((a, b) => {
        const at = a.assessment_date ? Date.parse(a.assessment_date) : 0;
        const bt = b.assessment_date ? Date.parse(b.assessment_date) : 0;
        return bt - at;
      });
    } else if (sortBy === "oss") {
      xs = xs.slice().sort((a, b) => {
        const am = a.oss ? Math.max(...Object.values(a.oss)) : 0;
        const bm = b.oss ? Math.max(...Object.values(b.oss)) : 0;
        return bm - am;
      });
    } else if (sortBy === "alerts") {
      xs = xs.slice().sort((a, b) => b.open_alerts - a.open_alerts);
    }
    return xs;
  }, [all, q, subvFilter, sourceFilter, sortBy]);

  return (
    <div className="page" data-page="directory" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Entity directory</div>
          <h1>Clients</h1>
          <div className="sub">
            {filtered.length} of {all.length} entities · sorted by {sortBy}
          </div>
        </div>
        <div className="actions">
          <div className="toggle-row" role="group" aria-label="View">
            <button
              type="button"
              className={view === "grid" ? "on" : ""}
              onClick={() => setView("grid")}
              aria-pressed={view === "grid"}
              title="Grid view"
            ><Icon name="grid" size={13} /></button>
            <button
              type="button"
              className={view === "table" ? "on" : ""}
              onClick={() => setView("table")}
              aria-pressed={view === "table"}
              title="Table view"
            ><Icon name="menu" size={13} /></button>
          </div>
          <button type="button" className="btn btn-secondary"
                  onClick={() => {
                    downloadCsv(
                      "dma-clients.csv",
                      ["display_id", "name", "domain", "subvertical", "hq", "overall", "assessment_date", "data_source", "open_alerts"],
                      filtered.map((e) => [
                        e.display_id, e.name, e.domain, e.subvertical, e.hq,
                        e.overall, e.assessment_date, e.data_source, e.open_alerts,
                      ]),
                    );
                    pushToast(`Exported ${filtered.length} clients to CSV`, "success");
                  }}>
            <Icon name="download" size={13} /> Export
          </button>
          <button type="button" className="btn btn-primary"
                  onClick={() => openDrawer("newRun")}>
            <Icon name="plus" size={13} /> New run
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="grow" style={{ position: "relative", flex: 1 }}>
          <span style={{ position: "absolute", top: 10, left: 10, color: "var(--z-muted)" }}><Icon name="search" size={14} /></span>
          <input
            className="inp"
            style={{ paddingLeft: 32, width: "100%" }}
            placeholder="Search by name or domain…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select
          className="inp"
          style={{ maxWidth: 200 }}
          value={subvFilter}
          onChange={(e) => setSubvFilter(e.target.value)}
          aria-label="Filter by subvertical"
        >
          <option value="ALL">All subverticals</option>
          {subverticals.map((sv) => (
            <option key={sv} value={sv}>{healSubvertical(sv)}</option>
          ))}
        </select>
        <select
          className="inp"
          style={{ maxWidth: 200 }}
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          aria-label="Filter by source"
        >
          <option value="ALL">All sources</option>
          <option value="PROJECT_API">Project API</option>
          <option value="DRIVE_PARSE">Drive parse</option>
        </select>
        <select
          className="inp"
          style={{ maxWidth: 200 }}
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "date" | "oss" | "alerts")}
          aria-label="Sort by"
        >
          <option value="date">Sort: Run date</option>
          <option value="oss">Sort: Top OSS</option>
          <option value="alerts">Sort: Open alerts</option>
        </select>
        {(q || subvFilter !== "ALL" || sourceFilter !== "ALL") ? (
          <button type="button" className="btn btn-tertiary btn-sm"
                  onClick={() => { setQ(""); setSubvFilter("ALL"); setSourceFilter("ALL"); }}>
            Clear filters
          </button>
        ) : null}
      </div>

      {entitiesQ.isLoading ? (
        <div className="page-loading"><Spinner /> Loading clients…</div>
      ) : filtered.length === 0 ? (
        <div className="empty">
          <div className="icon" style={{ fontSize: 22 }}><Icon name="search" size={22} /></div>
          <h3>No clients match your search</h3>
          <p>Try clearing filters or broaden the search term.</p>
        </div>
      ) : view === "grid" ? (
        <div className="g3">
          {filtered.map((e) => (
            <EntityCard key={e.id} e={e} onOpen={() => navigate(`/clients/${e.display_id}/overview`)} />
          ))}
        </div>
      ) : (
        <div className="card flush">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Subvertical</th>
                <th>Date</th>
                <th>Source</th>
                <th>Open alerts</th>
                <th>Top OSS</th>
                <th style={{ textAlign: "right" }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.id} onClick={() => navigate(`/clients/${e.display_id}/overview`)}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--z-dark)" }}>{e.name}</div>
                    <div className="f-mono" style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      {e.domain ?? e.display_id}
                    </div>
                  </td>
                  <td>{healSubvertical(e.subvertical)}</td>
                  <td>{e.assessment_date ? new Date(e.assessment_date).toLocaleDateString() : "—"}</td>
                  <td>
                    <span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>
                      {e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}
                    </span>
                  </td>
                  <td>
                    {e.open_alerts > 0 ? (
                      <span className="b b-org">{e.open_alerts}</span>
                    ) : (
                      <span className="muted">0</span>
                    )}
                  </td>
                  <td>{topOssDisplay(e.oss)}</td>
                  <td style={{ textAlign: "right" }}>
                    <Pill tone="teal">
                      {e.overall != null ? e.overall.toFixed(1) : "—"}
                    </Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function topOssDisplay(oss: Record<string, number> | null): JSX.Element {
  if (!oss) return <span className="muted">—</span>;
  const sorted = Object.entries(oss).sort((a, b) => b[1] - a[1]);
  if (sorted.length === 0) return <span className="muted">—</span>;
  const top = sorted[0];
  return (
    <>
      <span style={{ fontWeight: 600 }}>{top[1]}</span>{" "}
      <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
        {top[0].slice(0, 3).toUpperCase()}
      </span>
    </>
  );
}

function EntityCard({ e, onOpen }: { e: UIEntity; onOpen: () => void }): JSX.Element {
  const top = e.oss
    ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0]
    : null;
  return (
    <div className="card-tile clickable" onClick={onOpen}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--z-dark)", marginBottom: 2,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
               title={e.name}>{healText(e.name, 42)}</div>
          <div style={{ fontSize: 11, color: "var(--z-muted)", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {healSubvertical(e.subvertical)}{e.hq ? ` · ${e.hq}` : ""}
          </div>
        </div>
        {e.in_progress ? (
          <span className="b b-org" style={{ display: "inline-flex", gap: 4 }}>● IN PROGRESS</span>
        ) : (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 26, fontWeight: 200, color: "var(--z-teal)", lineHeight: 1, letterSpacing: "-.02em" }}>
              {e.overall != null ? e.overall.toFixed(1) : "—"}
            </div>
            <div style={{ fontSize: 9, color: "var(--z-muted)", marginTop: 2 }}>maturity</div>
          </div>
        )}
      </div>
      {e.pillar_scores ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 4, marginBottom: 10 }}>
          {PILLARS.map((p) => {
            const s = e.pillar_scores?.[p.id];
            const w = s != null ? (s / 5) * 100 : 0;
            return (
              <div key={p.id}>
                <div style={{ fontSize: 9, color: "var(--z-muted)", marginBottom: 3 }}>{p.id}</div>
                <div style={{ height: 6, background: "var(--z-sep)", borderRadius: 3, overflow: "hidden" }}>
                  {s != null ? (
                    <div style={{ width: `${w}%`, height: "100%", background: maturityHex(s) }} />
                  ) : null}
                </div>
                <div style={{ fontSize: 10, color: "var(--z-dark)", marginTop: 2 }}>
                  {s != null ? s.toFixed(1) : "—"}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ marginBottom: 10 }}>
          <div className="prog">
            <div className="prog-fill" style={{ width: `${(e.current_batch / 6) * 100}%`, background: "var(--z-org)" }} />
          </div>
          <div style={{ fontSize: 10, color: "var(--z-muted)", marginTop: 4 }}>
            Batch {e.current_batch} of 6
          </div>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 10, borderTop: "1px solid var(--z-sep)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span className={`b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`}>
            {e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"}
          </span>
          {e.assessment_date ? <FreshnessDot at={e.assessment_date} /> : null}
          {e.open_alerts > 0 ? <span className="b b-org" style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Icon name="bell" size={9} /> {e.open_alerts}</span> : null}
        </div>
        {top ? (
          <div style={{ fontSize: 11, color: "var(--z-mid)" }}>
            Top OSS · {top[0].slice(0, 3).toUpperCase()} <strong style={{ marginLeft: 4 }}>{top[1]}</strong>
          </div>
        ) : null}
      </div>
    </div>
  );
}
