/**
 * EvidenceDrawer — right-side panel showing evidence items for the active
 * client, structured per prototype 374f91c6 (drawers.jsx EvidenceDrawer):
 * header (EVIDENCE badge + scope chips + title + "N evidence items"
 * subline), internal-only Rationale callout, tier-DISTRIBUTION chips with
 * counts ("All · N", per-tier toggle), rows with E-ID chip + tier chip +
 * claim badge + recency + freshness badge + bold title line + italic
 * excerpt in a tier-colored blockquote + source link + clickable
 * "supports:" subcap chips, footer Copy citation + Close.
 *
 * Data path (pack-first, 2026-07-06 remediation): ONE fetch of the FULL
 * per-client evidence list (`min_tier=8&limit=500` — the loosest server
 * filter; per-run row counts max ~312). Default (active-run) view serves
 * the committed pack snapshot first (`snapshotOrApi`, page "evidence"),
 * exactly like every page query; a selected run isn't in the pack → live
 * API first (`apiOrSnapshot`), mirroring the other run-aware hooks. ALL
 * scoping/filtering is then client-side over that one list, so one baked
 * file serves every drawer scope. Pre-fix the drawer was the ONLY surface
 * bypassing pack-first (bare apiGet) → 404/empty for all 94 pack clients
 * on a cold backend.
 *
 * Scope resolution (proto three-mode contract):
 *   eIds[] (card citations)  → list = exactly those rows (membership can
 *                              never diverge from the chips on the card);
 *                              falls back to the subcap scope when zero
 *                              cited rows resolve (cited-but-pruned corpus)
 *   subcapId                 → HIERARCHICAL match (exact OR prefix in both
 *                              directions: scope P2C1 matches row tag
 *                              P2C1.1.6 and vice versa — the same rule the
 *                              backend + attach_evidence_ladder use; the
 *                              pre-fix exact match emptied 72% of insight
 *                              opens)
 *   neither                  → the full run list
 *
 * Per-E-ID reveal (plan Part 11.1, retained): when the opener passes
 * `eId`, the row is force-included in the scope, the sticky tier-chip
 * filter auto-relaxes to "All" if it hides the target, and the row is
 * scrolled into view + highlighted (`.evidence-row-hl`).
 *
 * The old server-side "Tier N or better" min-tier select is GONE — the
 * fetch is always the loosest window (min_tier=8) and the operator
 * filters with the prototype's exact-tier chip row, default "All"
 * (2026-07-06 production: E-037 drilldown → "No evidence at this tier"
 * at the loosest setting; the real cause was scope, not tier).
 *
 * State branches per evidence row:
 *   first_seen          → "First seen" chip in muted color
 *   seen_in_n_runs      → "Seen in N runs" chip; click → popover
 *   evidence_run_history_load_error
 *                       → no chip rendered (fail-closed; row still shown)
 *   eId present + row in list       → scroll-to + `.evidence-row-hl`
 *   eId present + row tier-filtered → tier chips relax to "All", then retry
 *   eId present + row absent        → honest: list renders, no highlight;
 *                                     an EMPTY corpus names the E-ID
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet } from "@/lib/api";
import { computeBand, getBadgeStyle } from "@/lib/freshness";
import { useRoute } from "@/lib/hash-router";
import { apiOrSnapshot, snapshotOrApi, USE_STARTUP_PACK } from "@/lib/startup-pages";
import { tierBg, tierColor, tierLabel } from "@/lib/tiers";
import { useUiStore } from "@/store/ui";
import { EmptyState, Icon, Spinner } from "@/components/utils";

interface RunHistoryEntry {
  run_id: string;
  request_id: string | null;
  completed_at: string | null;
  status: string | null;
  first_seen_in_run: boolean;
  surfaces_in_run: string[];
}
interface RunHistoryResponse {
  evidence_id: string;
  e_id: string;
  n_runs: number;
  is_first_seen: boolean;
  runs: RunHistoryEntry[];
}

function SeenInRunsChip({ evidenceId }: { evidenceId: string }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["evidence-run-history", evidenceId],
    queryFn: () => apiGet<RunHistoryResponse>(
      `/api/v1/evidence/${evidenceId}/run-history`,
    ),
    staleTime: 60 * 1000,
    retry: 0,
  });
  if (!data) return null;
  const n = data.n_runs;
  const label = data.is_first_seen ? "First seen" : `Seen in ${n} runs`;
  const tone = data.is_first_seen ? "muted" : "info";
  return (
    <>
      <button
        type="button"
        className={`chip chip-${tone}`}
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        data-history-n={n}
      >
        {label}
      </button>
      {open && !data.is_first_seen ? (
        <div className="popover" role="dialog" aria-label="Evidence run history">
          <header className="popover-head">Seen in {n} runs</header>
          <ul className="popover-body">
            {data.runs.map((r) => (
              <li key={r.run_id} className="popover-row">
                <div>
                  <span className="popover-rid">{r.request_id ?? r.run_id}</span>
                  {r.first_seen_in_run ? (
                    <span className="chip chip-muted">first seen</span>
                  ) : null}
                </div>
                <div className="popover-meta">
                  {r.completed_at ? new Date(r.completed_at).toLocaleDateString() : "—"}
                  {r.surfaces_in_run.length > 0
                    ? ` · ${r.surfaces_in_run.slice(0, 3).join(", ")}`
                    : ""}
                </div>
              </li>
            ))}
          </ul>
          <footer className="popover-foot">
            <button type="button" className="btn btn-tertiary" onClick={() => setOpen(false)}>
              Close
            </button>
          </footer>
        </div>
      ) : null}
    </>
  );
}

interface EvidenceItem {
  id: string;
  e_id: string;
  source_name: string;
  source_url: string | null;
  excerpt: string;
  claim_type: string;
  tier: number;
  /** Age in months at ingest (additive 2026-07-06; absent on older packs). */
  recency_months?: number | null;
  published_date: string | null;
  linked_subcap_ids: string[];
}

interface EvidenceResponse {
  entity_display_id: string;
  run_request_id: string | null;
  filter_subcap_id: string | null;
  filter_min_tier: number;
  filter_e_ids?: string[];
  items: EvidenceItem[];
}

/**
 * Hierarchical subcap match — frontend twin of the backend's
 * `subcap_matches` (routers/insights.py) and attach_evidence_ladder's
 * derive-time roll-up: exact tag OR prefix containment in either
 * direction, dot-boundary safe (P2C10 is NOT under P2C1). Exported for
 * the vitest contract.
 */
export function subcapMatches(scope: string, tags: readonly string[] | null | undefined): boolean {
  if (!scope) return false;
  return (tags ?? []).some(
    (t) => t === scope || t.startsWith(scope + ".") || scope.startsWith(t + "."),
  );
}

function sourceHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

interface EvidenceDrawerProps {
  open: boolean;
  onClose: () => void;
  displayId: string | null;
  subcapId?: string | null;
  /** Exact evidence row to reveal (e.g. "E-042"). See module docstring. */
  eId?: string | null;
  /** The opening card's cited E-ID list (proto `ic.evidence`) — when set,
   *  the drawer scopes to exactly these rows. */
  eIds?: string[] | null;
  /** Optional scope metadata for the header subline (proto
   *  "score X · confidence") — passed by openers that have it (heatmap
   *  synthesis cell). */
  score?: number | null;
  confidence?: string | null;
}

export function EvidenceDrawer({
  open, onClose, displayId, subcapId, eId, eIds, score, confidence,
}: EvidenceDrawerProps) {
  /** Client-side tier-distribution toggle ("ALL" or an exact tier), per
   *  proto. Sticky across opens — the reveal effect relaxes it when it
   *  would hide the clicked E-ID. */
  const [tierFilter, setTierFilter] = useState<number | "ALL">("ALL");
  const [copied, setCopied] = useState(false);
  /** The e_id currently highlighted (set once the row is confirmed in the
   *  scoped list; cleared on close so a later subcap-only open doesn't
   *  keep a stale highlight). */
  const [hlEid, setHlEid] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const navigate = useRoute().navigate;
  const audience = useUiStore((s) => s.audience);
  // Honour the operator's run selection (endpoint grew ?run= for the
  // drawer on 2026-06-05 but the drawer never sent it). ClientBar syncs
  // the page's ?run= param into the store, so URL deep-links work too.
  const selectedRunId = useUiStore((s) => s.selectedRunId);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // ONE full-list fetch per client+run+audience; every scope below is
  // client-side. Default view is pack-first (snapshotOrApi); a selected
  // run is not in the pack → API-first with snapshot fallback (the same
  // split every run-aware hook in lib/queries.ts uses).
  const { data, isLoading, error } = useQuery({
    queryKey: ["evidence", displayId, selectedRunId ?? "active", audience],
    queryFn: () =>
      (selectedRunId || !USE_STARTUP_PACK ? apiOrSnapshot : snapshotOrApi)(() =>
        apiGet<EvidenceResponse>(
          `/api/v1/entities/${displayId}/evidence`,
          { min_tier: 8, limit: 500, run: selectedRunId ?? undefined },
        ), displayId, "evidence"),
    enabled: open && displayId !== null,
    staleTime: 60 * 1000,
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  // Scope resolution — see module docstring. The clicked eId is always
  // force-included so the reveal contract can't be broken by scoping.
  const scoped = useMemo(() => {
    const citedSet = new Set(eIds ?? []);
    if (citedSet.size > 0) {
      const cited = items.filter(
        (it) => citedSet.has(it.e_id) || (eId != null && it.e_id === eId),
      );
      if (cited.length > 0) return cited;
      // Cited-but-pruned corpus → fall back to the subcap scope rather
      // than render an empty drawer.
    }
    if (subcapId) {
      return items.filter(
        (it) => subcapMatches(subcapId, it.linked_subcap_ids)
          || (eId != null && it.e_id === eId),
      );
    }
    return items;
  }, [items, eIds, subcapId, eId]);

  // Tier distribution over the SCOPED list (proto dist), then the chip
  // filter narrows the rendered rows.
  const dist = useMemo(() => {
    const d = new Map<number, number>();
    for (const it of scoped) d.set(it.tier, (d.get(it.tier) ?? 0) + 1);
    return [...d.entries()].sort((a, b) => a[0] - b[0]);
  }, [scoped]);
  const filtered = useMemo(
    () => (tierFilter === "ALL" ? scoped : scoped.filter((it) => it.tier === tierFilter)),
    [scoped, tierFilter],
  );

  // Part 11.1 — reveal the clicked E-ID: relax the sticky tier-chip filter
  // when it hides the target, otherwise mark + scroll the row into view.
  useEffect(() => {
    if (!open || !eId) {
      setHlEid(null);
      return;
    }
    if (!data) return;
    if (!scoped.some((it) => it.e_id === eId)) {
      // Honest: the cited row doesn't exist in this run's corpus.
      setHlEid(null);
      return;
    }
    if (!filtered.some((it) => it.e_id === eId)) {
      // The sticky tier toggle hides the target — relax once ("ALL" shows
      // every scoped row, so this cannot loop).
      setTierFilter("ALL");
      return;
    }
    setHlEid(eId);
    // Scroll after paint; jsdom has no scrollIntoView — guard it.
    const raf = requestAnimationFrame(() => {
      const el = bodyRef.current?.querySelector(`[data-eid="${eId}"]`);
      if (el && typeof (el as HTMLElement).scrollIntoView === "function") {
        (el as HTMLElement).scrollIntoView({ block: "center", behavior: "smooth" });
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [open, eId, data, scoped, filtered]);

  if (!open) return null;
  const citedScope = (eIds?.length ?? 0) > 0;
  const scopeTitle = subcapId ?? (citedScope ? "Cited evidence" : "All evidence");
  // "supports:" chips deep-link into the heatmap synthesis drawer — the
  // same navigation the insight modal's affects chips use (leaf ids →
  // ?synthesis=, category-grain → ?synthcat=).
  const openSubcap = (sid: string): void => {
    if (!displayId) return;
    onClose();
    const param = sid.includes(".") ? "synthesis" : "synthcat";
    navigate(`/clients/${displayId}/heatmap?${param}=${encodeURIComponent(sid)}`);
  };
  return (
    <>
    <div className="drawer-mask" onClick={onClose} />
    <aside className="drawer drawer-right" role="dialog" aria-label="Evidence drawer">
      <header className="drawer-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
            <span className="b b-teal">EVIDENCE</span>
            {subcapId ? <span className="chip purple">{subcapId}</span> : null}
            {eId ? <span className="chip">{eId}</span> : null}
          </div>
          <div className="drawer-title">{scopeTitle}</div>
          <div className="sub" data-testid="evidence-subline">
            {scoped.length} evidence item{scoped.length === 1 ? "" : "s"}
            {score != null ? ` · score ${score.toFixed(1)}` : ""}
            {confidence ? ` · ${confidence}` : ""}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-tertiary btn-icon"
          onClick={onClose}
          aria-label="Close evidence drawer"
        ><Icon name="x" size={16} /></button>
      </header>
      <div className="drawer-body" ref={bodyRef}>
        {audience !== "customer" && (subcapId || citedScope) ? (
          <div className="co co-teal" style={{ marginBottom: 12 }} data-testid="evidence-rationale">
            <Icon name="info" size={14} />
            <div>
              <div className="co-title">Rationale</div>
              <div className="co-body">
                {citedScope
                  ? `Scoped to the ${eIds!.length} E-ID${eIds!.length === 1 ? "" : "s"} the opening card cites — cited rows always render, regardless of tier.`
                  : `Evidence citing ${subcapId} or any of its parent/child capabilities in this run.`}
              </div>
            </div>
          </div>
        ) : null}

        {scoped.length > 1 || (scoped.length > 0 && tierFilter !== "ALL") ? (
          <div className="drawer-filters" role="group" aria-label="Filter by evidence tier"
               style={{ padding: 0, border: 0, marginBottom: 12 }}>
            <button
              type="button"
              className="chip"
              aria-pressed={tierFilter === "ALL"}
              style={tierFilter === "ALL"
                ? { background: "var(--z-dark)", color: "#fff" }
                : undefined}
              onClick={() => setTierFilter("ALL")}
            >
              All · {scoped.length}
            </button>
            {dist.map(([t, n]) => (
              <button
                key={t}
                type="button"
                className={`tier-chip tier-T${t}`}
                title={tierLabel(t)}
                aria-pressed={tierFilter === t}
                style={{ opacity: tierFilter === "ALL" || tierFilter === t ? 1 : 0.45, cursor: "pointer" }}
                onClick={() => setTierFilter(t === tierFilter ? "ALL" : t)}
              >
                T{t} · {n}
              </button>
            ))}
          </div>
        ) : null}

        {isLoading ? (
          <div className="page-loading"><Spinner /> Loading evidence…</div>
        ) : error && !data ? (
          <EmptyState title="Couldn't load evidence" body={(error as Error)?.message} />
        ) : !data ? (
          <EmptyState title="Couldn't load evidence" />
        ) : filtered.length === 0 ? (
          scoped.length > 0 ? (
            <EmptyState
              title="No evidence in this tier"
              body="Pick another tier chip — or All — to clear the filter."
            />
          ) : subcapId ? (
            <EmptyState
              title="No evidence cites this capability"
              body={`No evidence in this run is linked to ${subcapId} or its parent/child capabilities.`}
            />
          ) : (
            // Honest empty naming the E-ID (2026-07-06 E-037 drilldown):
            // never blame a tier filter for a missing citation.
            <EmptyState
              title="No evidence on record"
              body={eId
                ? `${eId} isn't in this run's evidence corpus.`
                : "This run shipped no evidence rows."}
            />
          )
        ) : (
          <ul className="evidence-list">
            {filtered.map((item) => {
              const band = computeBand(item.published_date, item.recency_months ?? null);
              const badge = getBadgeStyle(band);
              const host = sourceHost(item.source_url);
              return (
              <li
                key={item.id}
                className={`evidence-row${item.e_id === hlEid ? " evidence-row-hl" : ""}`}
                data-eid={item.e_id}
              >
                <div className="evidence-row-head" style={{ flexWrap: "wrap" }}>
                  <span className="chip">{item.e_id}</span>
                  <span className={`tier-chip tier-T${item.tier}`} title={tierLabel(item.tier)}>
                    T{item.tier} · {tierLabel(item.tier)}
                  </span>
                  {item.claim_type ? <span className="b b-purple">{item.claim_type}</span> : null}
                  {item.recency_months != null ? (
                    <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      ~{item.recency_months} mo old
                    </span>
                  ) : item.published_date ? (
                    <span style={{ fontSize: 10, color: "var(--z-muted)" }}>
                      {item.published_date.slice(0, 10)}
                    </span>
                  ) : null}
                  <span
                    className={badge.className}
                    title={badge.tooltip}
                    data-band={band}
                  >
                    {badge.label}
                  </span>
                  <SeenInRunsChip evidenceId={item.id} />
                </div>
                <div className="evidence-title"
                     style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)", marginBottom: 5 }}>
                  {item.source_name}
                </div>
                {/* Excerpt = the prototype's tier-tinted quote block
                    (italic, tier bg + 3px accent border). */}
                <div className="evidence-excerpt"
                     style={{
                       fontStyle: "italic",
                       padding: "8px 10px",
                       background: tierBg(item.tier),
                       borderLeft: `3px solid ${tierColor(item.tier)}`,
                       borderRadius: 3,
                     }}>
                  “{item.excerpt}”
                </div>
                <div className="evidence-source">
                  {item.source_url ? (
                    <a href={item.source_url} target="_blank" rel="noopener noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Icon name="external" size={11} /> {host ?? item.source_name}
                    </a>
                  ) : (
                    item.source_name
                  )}
                </div>
                {item.linked_subcap_ids.length > 0 ? (
                  <div className="evidence-links" style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="muted" style={{ fontSize: 10 }}>· supports:</span>
                    {item.linked_subcap_ids.slice(0, 3).map((sid) => (
                      <button
                        key={sid}
                        type="button"
                        className="chip"
                        title={`Open ${sid} on the heatmap`}
                        onClick={() => openSubcap(sid)}
                      >
                        {sid}
                      </button>
                    ))}
                  </div>
                ) : null}
              </li>
              );
            })}
          </ul>
        )}
      </div>
      <footer className="drawer-foot">
        <button type="button" className="btn btn-tertiary" onClick={() => {
          const lines = filtered.map((it) => `${it.e_id} · T${it.tier} · ${it.source_name} — "${it.excerpt}"${it.source_url ? ` (${it.source_url})` : ""}`).join("\n");
          try { void navigator.clipboard.writeText(lines); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard unavailable */ }
        }}>
          <Icon name="copy" size={13} /> {copied ? "Copied" : "Copy citation"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
      </footer>
    </aside>
    </>
  );
}
