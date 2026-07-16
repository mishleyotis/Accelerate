/**
 * ClientShell — wraps every `/clients/{display_id}/*` page with the
 * ClientBar (entity name + status pills + run selector + audience toggle
 * + tab bar + banners) so the page body only renders the section content.
 *
 * Hydrates entity name + active run via `useEntityOverview` so the bar
 * has real data on first paint; pages don't need to re-fetch the
 * overview for the chrome.
 *
 * Also hosts the evidence deep-link reader (plan Part 11.1/11.2):
 * `?drawer=evidence&e=E-123&subcap=P1C1.1.1` on any client route opens
 * the global EvidenceDrawer scoped to that row. This is what makes the
 * SCQA narrative chips + IntelligencePanel citation fallbacks live —
 * both write these hash params and, pre-fix, nothing read them.
 */
import { useEffect, type ReactNode } from "react";
import { nameFromSlug } from "@/lib/sanitize";
import { ClientBar } from "@/components/ClientBar";
import { EmptyState, Spinner } from "@/components/utils";
import { buildHash, useRoute } from "@/lib/hash-router";
import { useEntityOverview } from "@/lib/queries";
import { useUiStore } from "@/store/ui";

interface ClientShellProps {
  displayId: string;
  children: ReactNode;
}

/**
 * Watch the hash query for `?drawer=evidence` and open the global
 * EvidenceDrawer with the deep-linked scope:
 *   e=E-123           → exact row highlight (EvidenceDrawer eId contract)
 *   subcap=P1C1.1.1   → subcap scoping (also accepts legacy `subcap_id=`)
 *
 * After opening, the consumed `drawer` + `e` params are stripped via a
 * replace-navigation so (a) closing the drawer doesn't leave a stale
 * deep-link in the URL, and (b) re-clicking the same chip produces a
 * fresh hashchange (an identical hash never fires the event). `subcap`
 * is left in place — the heatmap deep-link (`/heatmap?subcap=`) shares
 * that param and other pages ignore it harmlessly.
 *
 * Exported for the vitest URL-reader contract.
 */
export function useEvidenceDeepLink(displayId: string): void {
  const { path, query, navigate } = useRoute();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const drawer = query.drawer ?? null;
  const eId = query.e ?? null;
  const subcapId = query.subcap ?? query.subcap_id ?? null;

  useEffect(() => {
    if (drawer !== "evidence") return;
    openDrawer("evidence", {
      displayId,
      eId,
      subcapId,
      origin: "url",
    });
    const rest: Record<string, string | undefined> = { ...query };
    delete rest.drawer;
    delete rest.e;
    navigate(buildHash(path, rest), { replace: true });
    // `query` is a fresh object each parse — key on the scalar params so
    // the effect fires once per deep-link, not once per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawer, eId, subcapId, displayId]);
}

export function ClientShell({ displayId, children }: ClientShellProps): JSX.Element {
  const { data, isLoading, error } = useEntityOverview(displayId);
  // Deep-link reader runs regardless of load state so `?drawer=evidence`
  // works even while the overview hydrates.
  useEvidenceDeepLink(displayId);

  if (isLoading && !data) {
    return (
      <div className="client-shell">
        <div className="client-bar client-bar-loading" data-source="loading">
          <Spinner /> Loading client…
        </div>
        <div className="client-content" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="client-shell">
        <EmptyState
          title="Client not found"
          body={
            error ? `Backend error: ${(error as Error).message}` :
              `No active assessment for ${displayId}.`
          }
        />
      </div>
    );
  }

  const run = data.run
    ? {
        request_id: data.run.request_id,
        status: data.run.status ?? null,
        data_source: data.run.data_source ?? null,
        completed_at: data.run.completed_at ?? null,
      }
    : null;

  return (
    <div className="client-shell">
      <ClientBar
        displayId={displayId}
        entityName={data.entity?.name ?? nameFromSlug(displayId)}
        activeRun={run}
        openAlerts={(data as { open_alerts?: number }).open_alerts}
      />
      <div className="client-content">{children}</div>
    </div>
  );
}
