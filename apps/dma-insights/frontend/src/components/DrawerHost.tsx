/**
 * DrawerHost — single global mount point for every drawer/modal the app
 * uses. Replaces the per-page mounts so pages don't each carry their own
 * `useState` for an evidence drawer.
 *
 * Driven by `useUiStore.activeDrawer` / `drawerPayload`; close-on-Esc and
 * close-on-backdrop-click are handled by each child (existing contract).
 *
 * Drawer kinds wired (per 2026-06 wireframe):
 *   - evidence       payload: { displayId, subcapId?, eId?, eIds?, score?,
 *                    confidence? }  (EvidenceDrawerPayload + scope extensions)
 *   - recommendation payload: { recommendationId }
 *   - newRun         payload: undefined  (RequestDmaModal)
 *   - insight        payload: { displayId, icId }      (TBD InsightModal)
 *   - synthesis      payload: { displayId, subcapId }  (TBD SynthesisDrawer)
 *
 * The host also renders the IntelligencePanel and the toast stack so every
 * page gets them without re-mounting.
 */
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { IntelligencePanel } from "@/components/IntelligencePanel";
import { RecommendationModal } from "@/components/RecommendationModal";
import { RequestDmaModal } from "@/components/RequestDmaModal";
import { ToastStack } from "@/components/ToastStack";
import { useUiStore, type EvidenceDrawerPayload } from "@/store/ui";

interface RecommendationPayload {
  recommendationId: string | null;
  // Entity scope — required by openers that only hold the REC-NN
  // display code (stairstep, roadmap chevrons): codes are unique per
  // run, so the detail endpoint resolves them via ?display_id=.
  displayId: string | null;
}
interface IpDescriptor {
  surface: string;
  ref: string;
  title?: string;
}

/** Evidence payload as parsed by the host — the store's
 *  `EvidenceDrawerPayload` plus the citation-scope extensions
 *  (2026-07-06 remediation): `eIds` is the opening card's cited E-ID
 *  list (proto `ic.evidence` scope — the drawer's membership can never
 *  diverge from the chips on the card), `score`/`confidence` feed the
 *  header subline when the opener has them (heatmap synthesis cell). */
export interface EvidenceScopePayload extends EvidenceDrawerPayload {
  eIds: string[] | null;
  score: number | null;
  confidence: string | null;
}

/** Narrow an arbitrary drawer payload into the evidence shape. Exported
 *  for the vitest payload-parsing contract (Part 11.1: every E-ID chip's
 *  `eId` must survive the host → drawer hand-off — pre-fix this dropped
 *  `eId`, so every chip opened a subcap-scoped drawer ignoring the
 *  clicked ID; same contract now covers `eIds`). */
export function asEvidencePayload(v: unknown): EvidenceScopePayload {
  if (typeof v === "object" && v !== null) {
    const o = v as Record<string, unknown>;
    const eIds = Array.isArray(o.eIds)
      ? o.eIds.filter((x): x is string => typeof x === "string" && x.trim() !== "")
      : [];
    return {
      displayId: typeof o.displayId === "string" ? o.displayId : null,
      subcapId: typeof o.subcapId === "string" ? o.subcapId : null,
      eId: typeof o.eId === "string" && o.eId.trim() !== "" ? o.eId : null,
      eIds: eIds.length > 0 ? eIds : null,
      score: typeof o.score === "number" && Number.isFinite(o.score) ? o.score : null,
      confidence: typeof o.confidence === "string" && o.confidence.trim() !== ""
        ? o.confidence
        : null,
    };
  }
  return { displayId: null, subcapId: null, eId: null, eIds: null, score: null, confidence: null };
}

export function asRecPayload(v: unknown): RecommendationPayload {
  if (typeof v === "object" && v !== null) {
    const o = v as Record<string, unknown>;
    return {
      recommendationId:
        typeof o.recommendationId === "string" ? o.recommendationId : null,
      // pack-first fallback scope: openers that know the client pass it;
      // rec_id-form ids can only resolve inside a client's own pack rows.
      displayId: typeof o.displayId === "string" ? o.displayId : null,
    };
  }
  return { recommendationId: null, displayId: null };
}

function asIpDescriptor(surface: string, ctx: unknown): IpDescriptor {
  if (typeof ctx === "object" && ctx !== null) {
    const o = ctx as Record<string, unknown>;
    const ref = typeof o.ref === "string" ? o.ref : "";
    const title = typeof o.title === "string" ? o.title : undefined;
    return { surface, ref, title };
  }
  return { surface, ref: typeof ctx === "string" ? ctx : "" };
}

export function DrawerHost(): JSX.Element {
  const {
    activeDrawer,
    drawerPayload,
    closeDrawer,
    ipOpen,
    ipSurface,
    ipContext,
    setIpOpen,
    audience,
  } = useUiStore();

  const evidencePayload = asEvidencePayload(drawerPayload);
  const recPayload = asRecPayload(drawerPayload);
  const ip = asIpDescriptor(ipSurface, ipContext);

  return (
    <>
      <EvidenceDrawer
        open={activeDrawer === "evidence"}
        onClose={closeDrawer}
        displayId={evidencePayload.displayId}
        subcapId={evidencePayload.subcapId}
        eId={evidencePayload.eId}
        eIds={evidencePayload.eIds}
        score={evidencePayload.score}
        confidence={evidencePayload.confidence}
      />
      <RecommendationModal
        open={activeDrawer === "recommendation"}
        onClose={closeDrawer}
        recommendationId={recPayload.recommendationId}
        displayId={recPayload.displayId}
      />
      <RequestDmaModal
        open={activeDrawer === "newRun"}
        onClose={closeDrawer}
      />
      {/* Internal-only per the UI/UX brief: the rail + panel never
          render in customer audience (it exposes E-IDs + internal
          rationale). When closed the component renders the wireframe's
          vertical "✦ INTELLIGENCE" rail on every authed page. */}
      {audience !== "customer" ? (
        <IntelligencePanel
          open={ipOpen}
          onOpen={() => setIpOpen(true)}
          onClose={() => setIpOpen(false)}
          surface={ip.surface}
          ref_={ip.ref}
          title={ip.title}
        />
      ) : null}
      <ToastStack />
    </>
  );
}
