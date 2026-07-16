/**
 * D2 ClientInsights — ported 1:1 from prototype
 * (standalone-src/src/pages-d1-overview.jsx · ClientInsights).
 *
 * .page-head with critical/opportunity/monitor count pills + Export PDF
 * + Add note. .filter-bar with pillar / flag / confidence selects.
 * .g2 grid of .ic cards (.ic-head + .ic-id + pillar+flag b's + NOTE
 * badge + .ic-title + .ic-body + .tier-chip evidence chips + .ic-foot
 * meta). "Technology landscape" .card.flush w/ 4-tile .g4 (Confirmed /
 * Inferred / Claimed / Gaps).
 *
 * 2026-07-02 (plan Part 5.2) modal drilldowns aligned to the prototype
 * InsightModal (374f91c6:121-256):
 *   - header gains the confidence chip + implicated-platform badge;
 *   - Detail tab renders ALL `affects[]` chips (cross-pillar) that
 *     NAVIGATE to the heatmap synthesis drawer (`?synthesis=<leaf>` /
 *     `?synthcat=<category>`), not the evidence drawer;
 *   - per-E-ID chips pass `eId` so the EvidenceDrawer scopes+highlights
 *     THAT item (Part 11.1 spine);
 *   - counter-signals "But also…" block (contradictory evidence when it
 *     exists; honest empty copy otherwise);
 *   - Linked tab lists implicated platforms + the affects set;
 *   - zero-evidence cards render their `basis` chip ("scores + peer
 *     benchmark") from the interconnections marker.
 * Tech-landscape strip binds the REAL 4-state `status` field
 * (CONFIRMED/INFERRED/CLAIMED/ABSENT from services/techstack_read) with
 * the named primary gap — the old tiles inferred status from
 * source/evidence presence and always rendered Claimed "—".
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { printView } from "@/lib/export";
import { stripLabelPrefix } from "@/lib/sanitize";
import { humanizeEnum } from "@/lib/labels";
import { Modal } from "@/components/Modal";
import { useRoute } from "@/lib/hash-router";
import {
  useEntityInsights,
  useInsightAnnotations,
  useSaveAnnotation,
  type AnnotationStatus,
  type InsightCardOut,
} from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { Icon, EmptyState, Pill, Spinner } from "@/components/utils";
import { lookupRecUuid, useEntityRecommendations } from "@/lib/entityRecommendations";

const PILLARS = [
  { id: "P1", short: "Strategy" },
  { id: "P2", short: "Customer" },
  { id: "P3", short: "Operations" },
  { id: "P4", short: "Data & Tech" },
];

/** The five scored platform families (backend `platform_id` values). */
const PLATFORM_NAMES: Record<string, string> = {
  salesforce: "Salesforce",
  ncino: "nCino",
  databricks: "Databricks",
  tableau: "Tableau",
  twilio: "Twilio",
};

function platformName(id: string): string {
  return PLATFORM_NAMES[id] ?? humanizeEnum(id);
}

/** The card's `basis` interconnection marker (evidence-ladder final
 *  rung): a zero-/thin-evidence card must state what it stands on. */
function basisNote(c: InsightCardOut): string | null {
  const marker = (c.interconnections ?? []).find(
    (i) => (i as { kind?: string }).kind === "basis",
  ) as { note?: string } | undefined;
  return marker?.note ?? null;
}

/** All capabilities this card touches — multi-affects when derived,
 *  anchor-only fallback for legacy rows. */
function affectsOf(c: InsightCardOut): string[] {
  const xs = c.affects ?? [];
  return xs.length > 0 ? xs : [c.linked_subcap_id];
}

function getDisplayId(path: string): string | null {
  const m = path.match(/^\/clients\/([^/]+)\/insights$/);
  return m ? m[1] : null;
}

function flagFromSeverity(s: string): "CRITICAL" | "OPPORTUNITY" | "MONITOR" {
  if (s === "critical") return "CRITICAL";
  if (s === "high") return "OPPORTUNITY";
  return "MONITOR";
}

function flagBadgeClass(f: string): string {
  return f === "CRITICAL" ? "b-below" : f === "OPPORTUNITY" ? "b-org" : "b-teal";
}

export function InsightsPage(): JSX.Element {
  const { path, query, setQuery } = useRoute();
  const displayId = getDisplayId(path);
  // 2026-06-06 QA-1: propagate `?run=<request_id>` so cards/pillars
  // reflect the selected run instead of always-latest ACTIVE.
  const selectedRun = typeof query.run === "string" ? query.run : null;
  const pushToast = useUiStore((s) => s.pushToast);

  const insightsQ = useEntityInsights(displayId, selectedRun);
  const items = insightsQ.data?.items ?? [];

  const [pillar, setPillar] = useState<string>("ALL");
  const [flag, setFlag] = useState<string>("ALL");
  const [conf, setConf] = useState<string>("ALL");

  const filtered = useMemo(() => {
    const xs = items.filter((c) => {
      const cf = flagFromSeverity(c.severity);
      const cp = c.linked_subcap_id.slice(0, 2);
      if (pillar !== "ALL" && cp !== pillar) return false;
      if (flag !== "ALL" && cf !== flag) return false;
      if (conf !== "ALL") {
        const band = (c as { confidence_band?: string }).confidence_band ?? "MEDIUM";
        if (band.toUpperCase() !== conf) return false;
      }
      return true;
    });
    const order: Record<string, number> = { CRITICAL: 0, OPPORTUNITY: 1, MONITOR: 2 };
    xs.sort((a, b) => {
      const fa = flagFromSeverity(a.severity);
      const fb = flagFromSeverity(b.severity);
      return (order[fa] - order[fb]) || a.ic_id.localeCompare(b.ic_id);
    });
    return xs;
  }, [items, pillar, flag, conf]);

  const counts = { CRITICAL: 0, OPPORTUNITY: 0, MONITOR: 0 };
  items.forEach((c) => { counts[flagFromSeverity(c.severity)]++; });

  const openCard = query.card ? items.find((c) => c.ic_id === query.card) ?? null : null;

  if (insightsQ.isLoading) {
    return <div className="page-loading"><Spinner /> Loading insights…</div>;
  }
  if (insightsQ.error) {
    return <EmptyState title="Couldn't load insights" body={(insightsQ.error as Error).message} />;
  }

  return (
    <div className="page" data-page="insights" data-source="api">
      <div className="page-head">
        <div>
          <div className="eyebrow">Insight cards</div>
          <h1>{items.length} insight cards</h1>
          <div className="sub">
            <span className="b b-below" style={{ marginRight: 6 }}>{counts.CRITICAL} CRITICAL</span>
            <span className="b b-org" style={{ marginRight: 6 }}>{counts.OPPORTUNITY} OPPORTUNITY</span>
            <span className="b b-teal">{counts.MONITOR} MONITOR</span>
          </div>
        </div>
        <div className="actions">
          {/* PDF export via the browser's native print-to-PDF; the
              @media print rules in app.css drop the chrome so the
              insight cards export cleanly. */}
          <button type="button" className="btn btn-tertiary"
                  onClick={() => printView()}>
            <Icon name="download" size={13} /> Export PDF
          </button>
          <button type="button" className="btn btn-secondary"
                  onClick={() => pushToast("Click a card to add a note", "success")}>
            <Icon name="plus" size={13} /> Add note
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <select className="inp" style={{ maxWidth: 160 }}
                value={pillar} onChange={(e) => setPillar(e.target.value)}
                aria-label="Filter by pillar">
          <option value="ALL">All pillars</option>
          {PILLARS.map((p) => (
            <option key={p.id} value={p.id}>{p.id} · {p.short}</option>
          ))}
        </select>
        <select className="inp" style={{ maxWidth: 160 }}
                value={flag} onChange={(e) => setFlag(e.target.value)}
                aria-label="Filter by flag">
          <option value="ALL">All flags</option>
          <option>CRITICAL</option>
          <option>OPPORTUNITY</option>
          <option>MONITOR</option>
        </select>
        <select className="inp" style={{ maxWidth: 180 }}
                value={conf} onChange={(e) => setConf(e.target.value)}
                aria-label="Filter by confidence">
          <option value="ALL">All confidence</option>
          <option>HIGH</option>
          <option>MEDIUM</option>
          <option>LOW</option>
        </select>
        <span className="spacer" />
        <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{filtered.length} matching</span>
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <h3>No insight cards yet</h3>
          <p>They appear once the assessment completes.</p>
        </div>
      ) : (
        <div className="g2" style={{ marginBottom: 18 }}>
          {filtered.map((c) => (
            <InsightCard
              key={c.id}
              c={c}
              displayId={displayId}
              onOpen={() => setQuery({ card: c.ic_id })}
            />
          ))}
        </div>
      )}

      <TechnologyLandscapeStrip displayId={displayId} />

      <Modal
        open={openCard !== null}
        onClose={() => setQuery({ card: undefined })}
        title={openCard ? stripLabelPrefix(openCard.title) : "Insight"}
        size="wide"
        footer={openCard ? (
          <InsightModalFooter card={openCard} onClose={() => setQuery({ card: undefined })} />
        ) : null}
      >
        {openCard ? <InsightModalBody card={openCard} displayId={displayId} onClose={() => setQuery({ card: undefined })} /> : null}
      </Modal>
    </div>
  );
}

function InsightCard({
  c, displayId, onOpen,
}: {
  c: InsightCardOut;
  displayId: string | null;
  onOpen: () => void;
}): JSX.Element {
  const flag = flagFromSeverity(c.severity);
  const pillar = c.linked_subcap_id.slice(0, 2);
  return (
    <div className={`ic ${flag.toLowerCase()}`} onClick={onOpen} role="button" tabIndex={0}>
      <div className="ic-head">
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className="ic-id">{c.ic_id}</span>
          <span className="b b-purple">{pillar}</span>
          <span className={`b ${flagBadgeClass(flag)}`}>{flag}</span>
        </div>
        <AnnotationChip displayId={displayId} icId={c.ic_id} />
      </div>
      <div className="ic-title">{stripLabelPrefix(c.title)}</div>
      <div className="ic-body">
        {(c.what_text ?? "").slice(0, 180)}{(c.what_text ?? "").length > 180 ? "…" : ""}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
        {/* DATA-GAP(O3-cardtier): the insights payload's linked_e_ids are
            bare E-IDs with no per-item tier (real tiers live in the
            EvidenceDrawer), so render the neutral base chip rather than
            fabricate a tier colour as the old hardcoded `tier-3` did. */}
        {c.linked_e_ids.slice(0, 4).map((eid) => (
          <span key={eid} className="tier-chip">{eid}</span>
        ))}
        {c.linked_e_ids.length > 4 ? (
          <span className="chip muted">+{c.linked_e_ids.length - 4}</span>
        ) : null}
        {/* Evidence-ladder final rung: a zero-evidence card states its
            basis instead of rendering an unexplained empty chip row. */}
        {basisNote(c) ? (
          <span className="chip muted" data-testid="basis-chip">
            Basis: {basisNote(c)}
          </span>
        ) : null}
      </div>
      <div className="ic-foot">
        <span style={{ fontSize: 10, color: "var(--z-muted)", marginRight: "auto" }}>
          {/* Prototype footer (06_pages_b.js:546): "N evidence · M caps".
              Counter-signals shown only when present (real backend
              concept; "0 counter" read as broken text). */}
          {c.linked_e_ids.length} evidence · 1 cap
          {(((c as { counter_e_ids?: string[] }).counter_e_ids ?? []).length > 0)
            ? ` · ${((c as { counter_e_ids?: string[] }).counter_e_ids ?? []).length} counter-signals`
            : ""}
        </span>
      </div>
    </div>
  );
}

function AnnotationChip({
  displayId, icId,
}: {
  displayId: string | null;
  icId: string;
}): JSX.Element | null {
  const q = useInsightAnnotations(displayId, icId);
  const n = q.data?.items.length ?? 0;
  if (n === 0) return null;
  return (
    <span className="b b-above" title={`${n} annotation${n === 1 ? "" : "s"}`}>
      <Icon name="edit" size={9} /> NOTE{n > 1 ? ` ×${n}` : ""}
    </span>
  );
}

type InsightTab = "detail" | "evidence" | "annotations" | "linked";
const INSIGHT_TABS: Array<[InsightTab, string]> = [
  ["detail", "Detail"],
  ["evidence", "Evidence"],
  ["annotations", "Annotations"],
  ["linked", "Linked"],
];

// 2026-06-09 prototype parity (04_components_c.js:121): the insight modal is
// a TABBED surface (detail / evidence / annotations / linked) with a badge
// header — not the four stacked sections it used to render. Evidence chips +
// the affected-capability chip open the EvidenceDrawer scoped to the card's
// subcap (the production evidence-detail surface).
function InsightModalBody({
  card, displayId, onClose,
}: {
  card: InsightCardOut;
  displayId: string | null;
  onClose: () => void;
}): JSX.Element {
  const [tab, setTab] = useState<InsightTab>("detail");
  const navigate = useRoute().navigate;
  const openDrawer = useUiStore((s) => s.openDrawer);
  const audience = useUiStore((s) => s.audience);
  const recRows = useEntityRecommendations(displayId).data;
  const flag = flagFromSeverity(card.severity);
  const pillar = card.linked_subcap_id.slice(0, 2);
  const affects = affectsOf(card);
  const platforms = card.platforms ?? [];
  const counters = card.counter_e_ids ?? [];
  const basis = basisNote(card);
  // Per-E-ID scoping (Part 11.1 spine): the chip passes eId so the
  // EvidenceDrawer scrolls-to + highlights THAT row instead of the
  // whole subcap list. `eIds` carries the card's FULL citation list
  // (supporting + counter-signals) so the drawer scopes to exactly what
  // the card cites — membership can never diverge from the chips
  // (prototype `ic.evidence` contract; 2026-07-06 remediation).
  const cardEids = [...new Set([...(card.linked_e_ids ?? []), ...counters])];
  const openEvidence = (eId?: string): void =>
    openDrawer("evidence", {
      displayId, subcapId: card.linked_subcap_id,
      eId: eId ?? null,
      eIds: cardEids.length > 0 ? cardEids : null,
      origin: "insight-modal",
    });
  // Affects chips NAVIGATE to the heatmap synthesis drawer (prototype
  // openSubcap) — leaf ids deep-link `?synthesis=`, category-grain ids
  // open the category synthesis via `?synthcat=`.
  const gotoHeatmap = (sid: string): void => {
    if (!displayId) return;
    onClose();
    const param = sid.includes(".") ? "synthesis" : "synthcat";
    navigate(`/clients/${displayId}/heatmap?${param}=${encodeURIComponent(sid)}`);
  };
  // Linked recommendation (D2 callout): prefer the faithful single
  // source_rec_id; fall back to the first subcap-join related rec (works on
  // existing data). Hidden for the customer audience (prototype parity).
  const linkedRecId = card.source_rec_id ?? card.related_rec_ids[0] ?? null;
  const linkedRec = linkedRecId
    ? recRows?.find((r) => r.rec_id === linkedRecId) ?? null
    : null;
  const openLinkedRec = (): void => {
    if (!linkedRecId) return;
    const uuid = lookupRecUuid(recRows, linkedRecId);
    if (!uuid) return;
    onClose();
    openDrawer("recommendation", { recommendationId: uuid, displayId });
  };

  return (
    <div className="insight-modal">
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <span className="b b-purple">{pillar}</span>
        <span className={`b ${flagBadgeClass(flag)}`}>{flag}</span>
        <span className="chip">{card.ic_id}</span>
        {platforms[0] ? (
          <span className="b b-teal" data-testid="modal-platform-badge">
            {platformName(platforms[0])}
          </span>
        ) : null}
        {card.theme ? <span className="chip muted">{card.theme}</span> : null}
        {card.confidence_band ? (
          <span style={{ fontSize: 11, color: "var(--z-muted)" }}
                data-testid="confidence-chip">
            Confidence · {card.confidence_band.toUpperCase()}
          </span>
        ) : null}
      </div>

      <div role="tablist" aria-label="Insight detail" style={{ display: "flex", borderBottom: "1px solid var(--z-sep)", marginBottom: 14 }}>
        {INSIGHT_TABS.map(([t, label]) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            className="client-tab"
            style={{
              background: "transparent",
              color: tab === t ? "var(--z-teal)" : "var(--z-muted)",
              borderBottom: tab === t ? "2px solid var(--z-teal)" : "2px solid transparent",
            }}
            onClick={() => setTab(t)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "detail" ? (
        <div>
          <section>
            <h4>What</h4>
            <p>{card.what_text}</p>
            {card.linked_e_ids.length > 0 ? (
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
                {card.linked_e_ids.map((eid) => (
                  <button key={eid} type="button" className="chip"
                          style={{ cursor: "pointer", border: 0 }}
                          onClick={() => openEvidence(eid)}>
                    {eid}
                  </button>
                ))}
              </div>
            ) : basis ? (
              <p className="muted small" data-testid="basis-chip">
                Basis: {basis} — no direct evidence citations.
              </p>
            ) : null}
          </section>
          <section>
            <h4>Why</h4>
            <p>{card.why_text}</p>
          </section>
          {/* Counter-signals — the app argues, it doesn't just claim.
              Contradictory same-subcap evidence renders as chips; the
              honest empty state names the homework that was done. */}
          <section data-testid="counter-signals">
            <h4>But also…</h4>
            {counters.length > 0 ? (
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
                <span className="muted small" style={{ marginRight: 4 }}>
                  Evidence pointing the other way:
                </span>
                {counters.map((eid) => (
                  <button key={eid} type="button" className="chip"
                          style={{ cursor: "pointer", border: 0 }}
                          onClick={() => openEvidence(eid)}>
                    {eid}
                  </button>
                ))}
              </div>
            ) : (
              <p className="muted small">No counter-signals identified.</p>
            )}
          </section>
          <section>
            <h4>So what</h4>
            <p style={{ background: "var(--z-ice)", borderLeft: "2px solid var(--z-teal)", padding: "8px 12px", borderRadius: 6 }}>
              {card.so_what_text}
            </p>
          </section>
          <div style={{ background: "var(--z-lav)", borderRadius: 8, padding: "12px 14px", marginTop: 14 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", color: "var(--z-muted)", marginBottom: 8, textTransform: "uppercase" }}>
              Affects · {affects.length} capabilit{affects.length === 1 ? "y" : "ies"}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {affects.map((sid) => (
                <button key={sid} type="button" className="chip purple"
                        style={{ cursor: "pointer", border: 0 }}
                        title={`Open ${sid} on the heatmap`}
                        onClick={() => gotoHeatmap(sid)}>
                  {sid}
                </button>
              ))}
            </div>
          </div>
          {linkedRecId && audience !== "customer" ? (
            <div className="co co-teal" style={{ marginTop: 12, cursor: "pointer" }}
                 role="button" tabIndex={0} onClick={openLinkedRec}>
              <Icon name="platform" size={14} />
              <div style={{ flex: 1 }}>
                <div className="co-title">Linked recommendation · click for impact</div>
                <div className="co-body">
                  <strong>{linkedRecId}</strong>{linkedRec?.title ? ` — ${linkedRec.title}` : ""}
                </div>
              </div>
              <Icon name="arrow-r" size={14} />
            </div>
          ) : null}
        </div>
      ) : tab === "evidence" ? (
        <section>
          <h4>Evidence</h4>
          {card.linked_e_ids.length === 0 ? (
            <p className="muted small">
              No evidence linked to this insight.
              {basis ? ` Basis: ${basis}.` : ""}
            </p>
          ) : (
            <>
              <p className="muted small">{card.linked_e_ids.length} evidence item(s) — click a chip to open the drawer scoped to that item.</p>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "8px 0 12px" }}>
                {card.linked_e_ids.map((eid) => (
                  <button key={eid} type="button" className="chip"
                          style={{ cursor: "pointer", border: 0 }}
                          onClick={() => openEvidence(eid)}>
                    {eid}
                  </button>
                ))}
              </div>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => openEvidence()}>
                <Icon name="evidence" size={13} /> View evidence for {card.linked_subcap_id}
              </button>
            </>
          )}
          {counters.length > 0 ? (
            <div style={{ marginTop: 12 }}>
              <p className="muted small">Counter-signals (opposing polarity, same capability):</p>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                {counters.map((eid) => (
                  <button key={eid} type="button" className="chip"
                          style={{ cursor: "pointer", border: 0 }}
                          onClick={() => openEvidence(eid)}>
                    {eid}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : tab === "annotations" ? (
        displayId ? (
          <AnnotationsSection displayId={displayId} icId={card.ic_id} />
        ) : (
          <p className="muted small">Annotations unavailable.</p>
        )
      ) : (
        <section>
          <h4>Linked</h4>
          <p style={{ marginBottom: 6 }}><strong>Subcapabilities affected:</strong></p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
            {affects.map((sid) => (
              <button key={sid} type="button" className="chip purple"
                      style={{ cursor: "pointer", border: 0 }}
                      onClick={() => gotoHeatmap(sid)}>
                {sid}
              </button>
            ))}
          </div>
          <p style={{ marginBottom: 6 }}><strong>Implicated platforms:</strong></p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}
               data-testid="linked-platforms">
            {platforms.length > 0 ? platforms.map((p) => (
              <span key={p} className="b b-teal">{platformName(p)}</span>
            )) : <span className="muted small">None derived for this card.</span>}
          </div>
          {card.linked_e_ids.length > 0 ? (
            <p>
              Evidence:{" "}
              {card.linked_e_ids.map((eid) => (
                <button key={eid} type="button" className="chip"
                        style={{ marginRight: 4, cursor: "pointer", border: 0 }}
                        onClick={() => openEvidence(eid)}>
                  {eid}
                </button>
              ))}
            </p>
          ) : null}
        </section>
      )}
    </div>
  );
}

// Modal footer — 1:1 port of the prototype InsightModal `.modal-foot`
// (drawers.jsx:305-311). Copy card → clipboard summary; Export → download
// the card as markdown; Close. Frontend-only — no new endpoints.
function InsightModalFooter({
  card, onClose,
}: {
  card: InsightCardOut;
  onClose: () => void;
}): JSX.Element {
  const pushToast = useUiStore((s) => s.pushToast);
  const asText = (): string =>
    `${card.ic_id} — ${stripLabelPrefix(card.title)}\n\n`
    + `WHAT\n${card.what_text ?? ""}\n\nWHY\n${card.why_text ?? ""}\n\n`
    + `SO WHAT\n${card.so_what_text ?? ""}\n\n`
    + `Affects: ${card.linked_subcap_id}\n`
    + `Evidence: ${card.linked_e_ids.join(", ") || "—"}\n`;

  const copy = (): void => {
    if (!navigator.clipboard) { pushToast("Clipboard unavailable", "warn"); return; }
    void navigator.clipboard.writeText(asText()).then(
      () => pushToast("Card copied to clipboard", "success"),
      () => pushToast("Couldn't access the clipboard", "error"),
    );
  };
  const exportMd = (): void => {
    const url = URL.createObjectURL(new Blob([asText()], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${card.ic_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
    pushToast("Card exported", "success");
  };

  return (
    <>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="btn btn-tertiary" onClick={copy}>
          <Icon name="copy" size={13} /> Copy card
        </button>
        <button type="button" className="btn btn-tertiary" onClick={exportMd}>
          <Icon name="download" size={13} /> Export
        </button>
      </div>
      <button type="button" className="btn btn-primary" onClick={onClose}>Close</button>
    </>
  );
}

function AnnotationsSection({
  displayId, icId,
}: {
  displayId: string;
  icId: string;
}): JSX.Element {
  const q = useInsightAnnotations(displayId, icId);
  const items = q.data?.items ?? [];
  const save = useSaveAnnotation();
  const pushToast = useUiStore((s) => s.pushToast);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<AnnotationStatus>("ACTIONED");
  const [sfOpp, setSfOpp] = useState("");

  const submit = (): void => {
    const body = note.trim();
    if (!body || save.isPending) return;
    save.mutate(
      { displayId, icId, body, status, sf_opp_id: sfOpp.trim() || null },
      {
        onSuccess: () => { setNote(""); setSfOpp(""); pushToast("Note saved", "success"); },
        onError: (e) => pushToast(`Couldn't save note — ${(e as Error).message}`, "error"),
      },
    );
  };

  return (
    <section className="annotations">
      <h4>Annotations</h4>
      {items.length === 0 ? (
        <p className="muted small">No annotations yet.</p>
      ) : (
        <ul className="annotation-list">
          {items.map((a) => (
            <li key={a.id} className="annotation-item">
              <header className="annotation-head">
                <strong>{a.author}</strong>
                <Pill tone="neutral">{a.role}</Pill>
                <Pill tone={a.status === "ACTIONED" ? "teal" : a.status === "PENDING" ? "amber" : "neutral"}>
                  {humanizeEnum(a.status)}
                </Pill>
                {a.sf_opp_id ? <code className="sf-opp">{a.sf_opp_id}</code> : null}
                <time className="muted small">
                  {new Date(a.created_at).toLocaleString()}
                </time>
              </header>
              <p className="annotation-body">{a.body}</p>
            </li>
          ))}
        </ul>
      )}

      {/* Add-note form — 1:1 port of the prototype InsightModal annotations
          tab (drawers.jsx:281-292), wired to the real useSaveAnnotation
          mutation (POST → invalidates the list query). */}
      <div className="field-group" style={{ marginTop: 14 }}>
        <label className="inp-label" htmlFor="ann-note">Add a note</label>
        <textarea
          id="ann-note"
          className="inp"
          rows={4}
          placeholder="Discussed with Delivery Lead before the call…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select className="inp" style={{ maxWidth: 180 }} value={status}
                  onChange={(e) => setStatus(e.target.value as AnnotationStatus)}
                  aria-label="Annotation status">
            <option value="ACTIONED">Actioned</option>
            <option value="PENDING">Pending</option>
            <option value="SUPERSEDED">Superseded</option>
          </select>
          <input className="inp" style={{ maxWidth: 220 }}
                 placeholder="Salesforce opp ID (optional)"
                 value={sfOpp} onChange={(e) => setSfOpp(e.target.value)}
                 aria-label="Salesforce opportunity ID" />
          <span className="spacer" />
          <button type="button" className="btn btn-primary btn-sm"
                  disabled={!note.trim() || save.isPending} onClick={submit}>
            <Icon name="check" size={12} /> {save.isPending ? "Saving…" : "Save note"}
          </button>
        </div>
      </div>
    </section>
  );
}


/* ── Technology landscape (wireframe 06_pages_b.js:554-582) ─────────
   Four quadrant tiles below the insight grid, bound to the REAL
   4-state read model (Part 9, services/techstack_read.derive_status):
   CONFIRMED (source-asserted or T1-T3 evidence) / INFERRED
   (technographic/job/press detection) / CLAIMED (T4-T5 marketing-tier
   evidence only) / ABSENT (server-generated scored-family gap rows,
   `primary_gap` named). Honest zeros — a real 0 renders 0, never "—". */
interface TechItemLite {
  vendor?: string | null;
  product?: string | null;
  status?: string | null;
  primary_gap?: boolean | null;
}

function TechnologyLandscapeStrip({ displayId }: { displayId: string | null }): JSX.Element | null {
  const navigate = useRoute().navigate;
  const techQ = useQuery({
    queryKey: ["techlandscape", displayId],
    queryFn: () => apiGet<{ items: TechItemLite[] }>(`/api/v1/entities/${displayId}/techstack`),
    enabled: !!displayId,
    staleTime: 60 * 1000,
  });
  const items = techQ.data?.items ?? [];
  if (!displayId || techQ.isLoading) return null;
  if (items.length === 0) return null; // source-genuine sparsity — honest absence

  const byStatus = (s: string): TechItemLite[] =>
    items.filter((t) => (t.status ?? "").toUpperCase() === s);
  const confirmed = byStatus("CONFIRMED");
  const inferred = byStatus("INFERRED");
  const claimed = byStatus("CLAIMED");
  const absent = byStatus("ABSENT");
  // Named gaps, primary (catalogue-addressable) families first.
  const gapNames = [...absent]
    .sort((a, b) => Number(b.primary_gap ?? false) - Number(a.primary_gap ?? false))
    .map((t) => t.vendor ?? "")
    .filter(Boolean);
  const primaryGap = absent.find((t) => t.primary_gap)?.vendor ?? null;

  const tiles = [
    { label: "Confirmed", count: confirmed.length, tone: "b-teal",
      sub: "Deployment confirmed",
      desc: "Source-asserted deployments or T1–T3 evidence." },
    { label: "Inferred", count: inferred.length, tone: "b-purple",
      sub: "Detection signal",
      desc: "Technographic / job-posting / press detection without confirming evidence." },
    { label: "Claimed", count: claimed.length, tone: "b-org",
      sub: "T4–T5 marketing",
      desc: claimed.length
        ? "Vendor-marketing-tier evidence only — verify before relying on it."
        : "No marketing-tier-only claims in this stack." },
    { label: "Gaps", count: absent.length, tone: "b-below",
      sub: primaryGap ? `Primary gap: ${primaryGap}` : "Scored platforms absent",
      desc: gapNames.length ? gapNames.join(" · ") : "All five platform families detected." },
  ];

  return (
    <div className="card flush" style={{ marginBottom: 18 }} data-testid="tech-landscape">
      <div className="card-head">
        <h3>Technology landscape</h3>
        <button type="button" className="btn btn-tertiary btn-sm"
                onClick={() => navigate(`/clients/${displayId}/techstack`)}>
          Open full stack <Icon name="arrow-r" size={11} />
        </button>
      </div>
      <div className="card-body">
        <div className="g4">
          {tiles.map((q) => (
            <div key={q.label} className="card-tile">
              <div className="row" style={{ marginBottom: 8 }}>
                <span className={`b ${q.tone}`}>{q.label}</span>
                <span className="spacer" />
                <span style={{ fontSize: 24, fontWeight: 200, color: "var(--z-teal)", letterSpacing: "-.02em", lineHeight: 1 }}>
                  {q.count ?? "—"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{q.sub}</div>
              <div style={{ fontSize: 11.5, color: "var(--z-body)", marginTop: 6, lineHeight: 1.5 }}>{q.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
