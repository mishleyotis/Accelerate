/**
 * D7 ClientTechStack — 1:1 port of the wireframe ClientTechStack
 * (proto ClientTechStack, 28883abf:709-866) bound to the Part 9 honest
 * read model.
 *
 * Anatomy: .page-head (eyebrow / h1 / sub + "✓ Explorium synced" chip +
 * Export) → legend+filter card (4 status swatches · layer select ·
 * hide-absent switch) → g4 stat strip → one bordered card per L1-L5
 * layer (primary-gap layer gets the 1.5px --z-blue border + PRIMARY GAP
 * LAYER chip) holding status-tinted TechRow buttons → displacement
 * banner grounded on the REAL ABSENT rows.
 *
 * Data honesty (Part 9):
 *   status         4-state served by the backend: CONFIRMED (source-asserted
 *                  deployment or T1-T3 evidence) / INFERRED (technographic ·
 *                  job postings · press) / CLAIMED (marketing-tier source
 *                  only) / ABSENT (server-generated scored-family gap row),
 *                  plus CONFIRMED_REMOVED. Legacy snapshot rows (DETECTED /
 *                  'active') are normalised in mapStatus — DETECTED was
 *                  always a technographic inference, so it reads INFERRED.
 *   ABSENT rows    REAL rows from the backend (per scored platform family
 *                  missing from the detected stack, carrying addressable
 *                  subcaps + peer_coverage + primary_gap). "Hide absent"
 *                  is therefore functional, and the displacement banner is
 *                  grounded on these rows. A legacy snapshot without them
 *                  falls back to the old family-regex count (banner only).
 *   since          real deployment date mined from evidence; absent →
 *                  the row shows "Detected {ingest date}" instead (the old
 *                  "Since {detected_at}" mislabelled the ingest timestamp).
 *   note           clean server-composed descriptor (never the raw source
 *                  cell); legacy rows fall back to a short product string.
 *   layers         L1-L5 ladder from the backend (`layer_code`); L1
 *                  Strategy appears when the catalogue implies it. Legacy
 *                  rows map platform→L2, application→L3, intelligence→L4,
 *                  foundation→L5.
 *   Engineering signals (languages/frameworks/OS) are NOT platform rows —
 *   the backend excludes them from items and sends their names; a muted
 *   strip shows them honestly. Unknown vendors sit in a review queue
 *   (count shown), never rendered as platforms.
 *
 *   Export = real client-side CSV blob download of the stack (no toast).
 */
import { useMemo, useState } from "react";
import { nameFromSlug } from "@/lib/sanitize";
import { techSourceLabel } from "@/lib/labels";
import { useRoute } from "@/lib/hash-router";
import { useUiStore } from "@/store/ui";
import { useEntityOverview, useTechStack } from "@/lib/queries";
import type { TechStackEntryOut } from "@/lib/queries";
import { Icon, EmptyState, Spinner } from "@/components/utils";

// Re-exported so TechStackDetailPage + tests keep a single import site.
export type { TechStackEntryOut } from "@/lib/queries";

/* Prototype L1-L5 layer ladder (L1 Strategy restored per Part 9). */
export const LAYER_ORDER = ["L1", "L2", "L3", "L4", "L5"] as const;
export const LAYER_INFO: Record<string, { name: string; short: string; dma: string; primary_gap?: boolean }> = {
  L1: { name: "Strategy & governance",     short: "Strategy",   dma: "P1" },
  L2: { name: "Operations & core banking", short: "Operations", dma: "P3" },
  L3: { name: "Customer engagement",       short: "Customer",   dma: "P2", primary_gap: true },
  L4: { name: "Data & analytics",          short: "Data",       dma: "P4" },
  L5: { name: "Infrastructure & cloud",    short: "Infra",      dma: "P4" },
};
/* Legacy backend-layer → display code (pre-Part-9 snapshot rows). */
const LEGACY_LAYER_CODE: Record<string, string> = {
  platform: "L2", application: "L3", intelligence: "L4", foundation: "L5",
};
export function layerCodeOf(t: Pick<TechStackEntryOut, "layer" | "layer_code">): string {
  return t.layer_code ?? LEGACY_LAYER_CODE[t.layer] ?? "L3";
}
/* Kept for TechStackDetailPage fallback labels (legacy layer → name). */
export const LAYER_META: Record<string, { name: string; short: string; dma: string; primary_gap?: boolean }> = {
  platform: LAYER_INFO.L2, application: LAYER_INFO.L3,
  intelligence: LAYER_INFO.L4, foundation: LAYER_INFO.L5,
};

/* Same five scored families + regexes as the backend's
   SCORED_PLATFORM_FAMILIES (tech_linker.py) — used ONLY as the legacy
   fallback when a pre-Part-9 snapshot carries no ABSENT rows. */
export const SCORED_PLATFORM_FAMILIES: Array<[string, RegExp]> = [
  ["Salesforce", /salesforce|mulesoft|tableau crm|marketing cloud|data cloud/i],
  ["Databricks", /databricks/i],
  ["Tableau", /tableau/i],
  ["Twilio", /twilio|segment/i],
  ["nCino", /ncino/i],
];

export type MappedStatus =
  | "CONFIRMED" | "INFERRED" | "CLAIMED" | "ABSENT" | "CONFIRMED_REMOVED";

const _VALID_STATUS = new Set<MappedStatus>([
  "CONFIRMED", "INFERRED", "CLAIMED", "ABSENT", "CONFIRMED_REMOVED",
]);

/** Honest 4-state enum, served by the backend. Legacy snapshot rows:
 *  DETECTED (a technographic inference by definition) → INFERRED; free-form
 *  'active'/'' fall back to the evidence heuristic. */
export function mapStatus(t: Pick<TechStackEntryOut, "status" | "source" | "evidence_e_ids">): MappedStatus {
  const s = (t.status ?? "").toUpperCase() as MappedStatus;
  if (_VALID_STATUS.has(s)) return s;
  if ((s as string) === "DETECTED") return "INFERRED";
  const backed = (t.evidence_e_ids?.length ?? 0) > 0 || Boolean(t.source && t.source.trim());
  return backed ? "CONFIRMED" : "INFERRED";
}

/* Pill palette — prototype STATUS_STYLE with CLAIMED on the PARTIAL tone. */
const STATUS_STYLE: Record<string, { bg: string; bd: string; color: string }> = {
  CONFIRMED:         { bg: "var(--z-ice)",           bd: "rgba(39,187,175,.4)",  color: "var(--z-mid)" },
  INFERRED:          { bg: "var(--ph0-lt)",          bd: "var(--ph0-bd)",        color: "var(--z-dpur)" },
  CLAIMED:           { bg: "rgba(254,151,50,.08)",   bd: "rgba(254,151,50,.3)",  color: "#7C3500" },
  ABSENT:            { bg: "rgba(194,80,8,.06)",     bd: "rgba(194,80,8,.25)",   color: "var(--z-below)" },
  CONFIRMED_REMOVED: { bg: "rgba(194,80,8,.06)",     bd: "rgba(194,80,8,.25)",   color: "var(--z-below)" },
};

/** Human label for the status pill (CONFIRMED_REMOVED → "REMOVED"). */
function statusLabel(s: MappedStatus): string {
  return s === "CONFIRMED_REMOVED" ? "REMOVED" : s;
}

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/techstack$/);
  return m ? m[1] : null;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/** Wireframe source-badge palette keyed onto the corpus's real source strings. */
function sourceBadgeClass(src: string): string {
  if (/explorium/i.test(src)) return "b-teal";
  if (/press|report/i.test(src)) return "b-purple";
  if (/job/i.test(src)) return "b-ph1";
  return "b-muted";
}

function csvCell(v: string): string {
  return `"${(v ?? "").replace(/"/g, '""')}"`;
}

/** Real client-side CSV download of the stack list (no fake toast). */
function exportCsv(items: TechStackEntryOut[], displayId: string | null): void {
  const header = ["tech_id", "vendor", "product_name", "l3_id", "layer_code", "layer_full", "status", "primary_gap", "since", "peer_coverage", "note", "source", "evidence_e_ids", "linked_subcap_ids", "detected_at"];
  const lines = items.map((t) => [
    t.tech_id, t.vendor, t.product_name ?? t.product, t.l3_id ?? "",
    layerCodeOf(t), t.layer_full ?? LAYER_INFO[layerCodeOf(t)]?.name ?? t.layer,
    mapStatus(t), t.primary_gap ? "true" : "",
    t.since ?? "", t.peer_coverage != null ? String(t.peer_coverage) : "",
    t.note ?? "", t.source,
    (t.evidence_e_ids ?? []).join("; "),
    (t.linked_subcap_ids ?? []).join("; "),
    t.detected_at ?? "",
  ].map(csvCell).join(","));
  const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${displayId ?? "client"}-techstack.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function TechStackPage(): JSX.Element {
  const { path, navigate } = useRoute();
  const displayId = getDisplayId(path);
  // Entity name for the H1 ("Technology stack - {name}", per prototype),
  // served from the ClientShell's cached overview query (no extra request).
  const entityName = useEntityOverview(displayId).data?.entity?.name ?? nameFromSlug(displayId);
  const [layer, setLayer] = useState<string>("ALL");
  const [hideAbsent, setHideAbsent] = useState<boolean>(false);

  const { data, isLoading, error } = useTechStack(displayId);

  const list = useMemo(() => {
    if (!data) return [] as TechStackEntryOut[];
    return data.items.filter((t) => {
      if (layer !== "ALL" && layerCodeOf(t) !== layer) return false;
      // Functional now: the backend serves real ABSENT gap rows (Part 9).
      if (hideAbsent && mapStatus(t) === "ABSENT") return false;
      return true;
    });
  }, [data, layer, hideAbsent]);

  if (isLoading) return <div className="page-loading"><Spinner /> Loading tech stack…</div>;
  if (error || !data) return <EmptyState title="Couldn't load tech stack" body={(error as Error | null)?.message} />;

  const allTech = data.items;

  // Real ABSENT gap rows (server-generated per scored family). A legacy
  // snapshot without them keeps the old family-regex count so the banner
  // stays truthful until the pack regenerates.
  const absentRows = allTech.filter((t) => mapStatus(t) === "ABSENT");
  const hay = allTech.map((t) => `${t.vendor ?? ""} ${t.product ?? ""}`).join(" · ");
  const legacyAbsentFamilies = absentRows.length > 0
    ? [] : SCORED_PLATFORM_FAMILIES.filter(([, rx]) => !rx.test(hay));

  const counts = {
    CONFIRMED: allTech.filter((t) => mapStatus(t) === "CONFIRMED").length,
    INFERRED:  allTech.filter((t) => ["INFERRED", "CLAIMED"].includes(mapStatus(t))).length,
    ABSENT:    absentRows.length || legacyAbsentFamilies.length,
    PRIMARY:   absentRows.filter((t) => t.primary_gap).length
               || legacyAbsentFamilies.length,
  };

  // ISO-8601 strings sort lexicographically — latest detection timestamp.
  const syncedAt = data.last_synced_at
    ?? allTech.reduce<string | null>((max, t) => (t.detected_at && (!max || t.detected_at > max) ? t.detected_at : max), null);

  const byLayer: Record<string, TechStackEntryOut[]> = { L1: [], L2: [], L3: [], L4: [], L5: [] };
  for (const t of list) byLayer[layerCodeOf(t)]?.push(t);

  const engSignals = data.engineering_signals ?? [];
  const engCount = data.engineering_signal_count ?? 0;
  const reviewCount = data.review_queue_count ?? 0;

  const absentBannerNames = absentRows.length > 0
    ? absentRows.map((t) => t.vendor)
    : legacyAbsentFamilies.map(([n]) => n);

  return (
    <div className="page" data-page="techstack" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Technology intelligence</div>
          <h1>Technology stack - {entityName ?? "client"}</h1>
          <div className="sub">
            Confirmed vs absent across the product layers
            {syncedAt ? <> · Explorium synced {fmtDate(syncedAt)}</> : null}
          </div>
        </div>
        <div className="actions">
          {allTech.length > 0 ? (
            <span className="b b-teal" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Icon name="check" size={10} /> Explorium synced
            </span>
          ) : null}
          <button type="button" className="btn btn-tertiary" disabled={allTech.length === 0}
                  onClick={() => exportCsv(allTech, displayId)}>
            <Icon name="download" size={13} /> Export
          </button>
        </div>
      </div>

      {allTech.length === 0 ? (
        <EmptyState
          title="Tech stack still building"
          body="Explorium sync pending. Detected tech will appear here weekly."
        />
      ) : (
        <>
          {/* Status legend + filters (honest 4-state descriptions) */}
          <div className="card" style={{ marginBottom: 14, padding: "12px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
              <div className="eyebrow" style={{ margin: 0 }}>Legend</div>
              {([
                { label: "Confirmed", s: STATUS_STYLE.CONFIRMED, desc: "Source-asserted · T1-T3 evidence" },
                { label: "Inferred",  s: STATUS_STYLE.INFERRED,  desc: "Technographic · job postings · press" },
                { label: "Claimed",   s: STATUS_STYLE.CLAIMED,   desc: "Marketing-tier source only" },
                { label: "Absent",    s: STATUS_STYLE.ABSENT,    desc: "Scored platform family not detected" },
              ]).map(({ label, s, desc }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--z-body)" }}>
                  <span style={{ width: 14, height: 14, background: s.bg, border: `1.5px solid ${s.bd}`, borderRadius: 3 }} />
                  <strong style={{ color: s.color }}>{label}</strong>
                  <span className="muted" style={{ fontSize: 10.5 }}>{desc}</span>
                </div>
              ))}
              <span className="spacer" />
              <div className="row" style={{ gap: 6 }}>
                <span style={{ fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>Layer</span>
                <select className="inp" style={{ width: 200, padding: "5px 10px", fontSize: 12 }}
                        value={layer} onChange={(e) => setLayer(e.target.value)} aria-label="Layer">
                  <option value="ALL">All layers</option>
                  {LAYER_ORDER.map((L) => <option key={L} value={L}>{LAYER_INFO[L].name}</option>)}
                </select>
              </div>
              <label className="row" style={{ fontSize: 11.5, cursor: "pointer" }}>
                <span className={`switch ${hideAbsent ? "on" : ""}`} data-testid="hide-absent-switch"
                      onClick={() => setHideAbsent((v) => !v)} />
                Hide absent
              </label>
            </div>
            {engCount > 0 || reviewCount > 0 ? (
              <div data-testid="taxonomy-triage-strip"
                   style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)" }}>
                {engCount > 0 ? (
                  <>Engineering signals ({engCount}, build-vs-buy evidence — not platform rows): {engSignals.slice(0, 10).join(" · ")}{engSignals.length > 10 ? " …" : ""}</>
                ) : null}
                {engCount > 0 && reviewCount > 0 ? " — " : null}
                {reviewCount > 0 ? <>{reviewCount} off-catalogue detection{reviewCount === 1 ? "" : "s"} in the taxonomy review queue</> : null}
              </div>
            ) : null}
          </div>

          {/* Stat strip — bound to the REAL 4-state statuses */}
          <div className="g4" style={{ marginBottom: 14 }} data-testid="techstack-stat-strip">
            {([
              { l: "Confirmed",          v: counts.CONFIRMED, c: "var(--z-mid)" },
              { l: "Inferred / claimed", v: counts.INFERRED,  c: "var(--z-dpur)" },
              { l: "Absent",             v: counts.ABSENT,    c: "var(--z-below)" },
              { l: "Primary gaps",       v: counts.PRIMARY,   c: "var(--z-blue)" },
            ]).map((s) => (
              <div key={s.l} className="card-tile" style={{ borderLeft: `3px solid ${s.c}` }}>
                <div style={{ fontSize: 10, color: "var(--z-muted)", letterSpacing: ".08em", textTransform: "uppercase" }}>{s.l}</div>
                <div style={{ fontSize: 28, fontWeight: 200, color: s.c, lineHeight: 1, marginTop: 6 }}>{s.v}</div>
              </div>
            ))}
          </div>

          {/* Layer cards (L1-L5 ladder) */}
          {LAYER_ORDER.map((L) => {
            const LM = LAYER_INFO[L];
            const techList = byLayer[L];
            if (!techList || techList.length === 0) return null;
            const isPrimaryGap = LM.primary_gap;
            return (
              <div key={L} className="card" data-testid="techstack-layer-card" style={{
                marginBottom: 12, padding: 16,
                borderColor: isPrimaryGap ? "var(--z-blue)" : "var(--z-sep)",
                borderWidth: isPrimaryGap ? 1.5 : 1, borderStyle: "solid",
              }}>
                <div className="row" style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{LM.name}</div>
                  {isPrimaryGap ? <span className="b b-ph1" style={{ background: "var(--ph1-lt)" }}>PRIMARY GAP LAYER</span> : null}
                  <span className="spacer" />
                  <span className="b b-teal">{LM.dma}</span>
                  <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                    {techList.filter((t) => mapStatus(t) !== "ABSENT").length} of {techList.length} detected
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {techList.map((t) => (
                    <TechRow key={t.id} t={t} displayId={displayId}
                             onOpen={() => navigate(`/clients/${displayId}/techstack/${t.tech_id}`)} />
                  ))}
                </div>
              </div>
            );
          })}

          {/* Displacement banner — grounded on the REAL ABSENT gap rows */}
          {absentBannerNames.length > 0 ? (
            <div className="card" data-testid="displacement-banner"
                 style={{ background: "var(--z-lav)", border: "none", padding: 14, display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--z-below)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon name="platform" size={18} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>
                  {absentBannerNames.length} scored platform famil{absentBannerNames.length === 1 ? "y" : "ies"} absent from the detected stack — displacement conversation available
                </div>
                <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 3 }}>
                  {absentBannerNames.join(" · ")} — open the platform matrix for the displacement story.
                </div>
              </div>
              <button type="button" className="btn btn-primary btn-sm"
                      onClick={() => navigate(`/clients/${displayId}/platform`)}>
                View platform matrix <Icon name="arrow-r" size={11} />
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function TechRow({ t, onOpen, displayId }: { t: TechStackEntryOut; onOpen: () => void; displayId: string | null }): JSX.Element {
  const { navigate } = useRoute();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const status = mapStatus(t);
  const S = STATUS_STYLE[status] ?? STATUS_STYLE.CONFIRMED;
  // Prototype-style display name: canonical vendor + specific product.
  const productName = t.product_name ?? t.product;
  const title = productName && productName.toLowerCase() !== t.vendor.toLowerCase()
    ? `${t.vendor} · ${productName}` : t.vendor;
  // Clean server-composed note; legacy snapshot rows fall back to a SHORT
  // product descriptor (never a raw multi-vendor blob).
  const note = t.note
    ?? (productName && productName !== t.vendor && productName.length <= 80 && !productName.includes(":")
        ? productName : null);
  return (
    // role="button" (not <button>) so the row can host the nested l3_id /
    // evidence chip buttons below without invalid button-in-button nesting.
    <div role="button" tabIndex={0} onClick={onOpen} data-testid="tech-row" data-status={status}
         onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } }}
         style={{
              background: S.bg, border: `1.5px solid ${S.bd}`, borderRadius: 8,
              padding: "10px 14px", textAlign: "left", display: "flex",
              gap: 12, alignItems: "flex-start", cursor: "pointer",
              transition: "transform 120ms, box-shadow 120ms",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "var(--sh-md)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ marginBottom: 4, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--z-dark)" }}>{title}</span>
          <span style={{
            fontSize: 9.5, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: ".06em", color: S.color,
          }}>{statusLabel(status)}</span>
          {t.primary_gap ? <span className="b b-ph1" style={{ fontSize: 9 }}>PRIMARY GAP</span> : null}
          {t.l3_id ? (
            <button type="button" className="chip" style={{ fontSize: 10, padding: "1px 5px" }}
                    title={`Open platform area: ${t.l3_id}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/clients/${displayId}/platform?platform=${encodeURIComponent(t.l3_id as string)}`);
                    }}>▸ {t.l3_id}</button>
          ) : null}
          {(t.evidence_e_ids ?? []).map((eid) => (
            <button key={eid} type="button" className="chip purple" style={{ fontSize: 10, padding: "1px 5px" }}
                    title="View evidence"
                    onClick={(e) => {
                      e.stopPropagation();
                      openDrawer("evidence", { eId: eid, eIds: t.evidence_e_ids ?? null, displayId, origin: "techstack-row" });
                    }}>{eid}</button>
          ))}
        </div>
        {note ? (
          <div style={{ fontSize: 11.5, color: "var(--z-body)", lineHeight: 1.5 }}>{note}</div>
        ) : null}
        {(t.linked_subcap_ids ?? []).length > 0 ? (
          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
            {t.linked_subcap_ids.slice(0, 8).map((s) => <span key={s} className="chip">{s}</span>)}
          </div>
        ) : null}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end", maxWidth: 170 }}>
        {t.source ? (
          <span className={`b ${sourceBadgeClass(t.source)}`} style={{ fontSize: 9 }}
                title={t.source}>{techSourceLabel(t.source)}</span>
        ) : null}
        {t.peer_coverage != null ? (
          <span style={{ fontSize: 9.5, color: "var(--z-muted)" }}>{Math.round(t.peer_coverage * 100)}% of peers</span>
        ) : null}
        {t.since ? (
          <span style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2 }}>Since {t.since}</span>
        ) : t.detected_at ? (
          <span style={{ fontSize: 9.5, color: "var(--z-muted)", marginTop: 2 }}>Detected {fmtDate(t.detected_at)}</span>
        ) : null}
      </div>
      <span data-testid="tech-row-chevron" aria-hidden="true"
            style={{ alignSelf: "center", color: "var(--z-muted)", display: "inline-flex" }}>
        <Icon name="chevron-r" size={14} />
      </span>
    </div>
  );
}
