/**
 * W5-FINISH overlay fidelity on the Insights surface:
 *   O3a — card evidence chips render the neutral `.tier-chip` (the old
 *         hardcoded `tier-3` fabricated a tier the payload doesn't carry).
 *   O3b — the InsightModal annotations tab has an add-note form wired to
 *         the real `useSaveAnnotation` mutation (1:1 with the prototype).
 *   O3c — the InsightModal `.modal-foot` exposes Copy card / Export / Close.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { InsightsPage } from "@/pages/InsightsPage";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import * as entityRecs from "@/lib/entityRecommendations";
import { useUiStore } from "@/store/ui";
import type { InsightCardOut } from "@/lib/queries";

function withClient(ui: ReactNode): JSX.Element {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const CARD: InsightCardOut = {
  id: "uuid-1",
  ic_id: "IC-1",
  severity: "critical",
  title: "Fragmented onboarding",
  what_text: "what text",
  why_text: "why text",
  so_what_text: "so what text",
  linked_subcap_id: "P2C1.1.1",
  linked_e_ids: ["E-001", "E-002"],
  source_rec_id: null,
  related_rec_ids: [],
};

function setup(card: InsightCardOut = CARD): { mutate: ReturnType<typeof vi.fn>; setQuery: ReturnType<typeof vi.fn> } {
  const mutate = vi.fn();
  const setQuery = vi.fn();
  vi.spyOn(queries, "useEntityInsights").mockReturnValue({
    data: { items: [card] }, isLoading: false, error: null,
  } as unknown as ReturnType<typeof queries.useEntityInsights>);
  vi.spyOn(queries, "useInsightAnnotations").mockReturnValue({
    data: { items: [] },
  } as unknown as ReturnType<typeof queries.useInsightAnnotations>);
  vi.spyOn(queries, "useSaveAnnotation").mockReturnValue({
    mutate, isPending: false,
  } as unknown as ReturnType<typeof queries.useSaveAnnotation>);
  vi.spyOn(entityRecs, "useEntityRecommendations").mockReturnValue({
    data: [{ id: "uuid-rec-3", rec_id: "REC-03", title: "Adopt Marketing Cloud", platform_id: null }],
  } as unknown as ReturnType<typeof entityRecs.useEntityRecommendations>);
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/x/insights", query: { card: "IC-1" },
    setQuery, navigate: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  return { mutate, setQuery };
}

const ORIG_AUDIENCE = useUiStore.getState().audience;
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useUiStore.setState({ audience: ORIG_AUDIENCE });
});

describe("Insights overlay fidelity (W5-FINISH)", () => {
  it("O3a: card evidence chips use the neutral .tier-chip (no fabricated tier-3)", () => {
    setup();
    const { container } = render(withClient(<InsightsPage />));
    const chip = container.querySelector(".tier-chip");
    expect(chip).toBeTruthy();
    expect(chip?.className).toBe("tier-chip");
    expect(container.querySelector(".tier-3")).toBeNull();
  });

  it("O3b: the annotations note-form posts via useSaveAnnotation and reads the form state", () => {
    const { mutate } = setup();
    render(withClient(<InsightsPage />));
    fireEvent.click(screen.getByRole("tab", { name: "Annotations" }));
    fireEvent.change(
      screen.getByPlaceholderText(/Discussed with Delivery Lead/i),
      { target: { value: "Met with the CTO" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Save note/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toMatchObject({
      displayId: "x", icId: "IC-1", body: "Met with the CTO",
      status: "ACTIONED", sf_opp_id: null,
    });
  });

  it("O3b: Save is disabled until a note is typed", () => {
    setup();
    render(withClient(<InsightsPage />));
    fireEvent.click(screen.getByRole("tab", { name: "Annotations" }));
    const save = screen.getByRole("button", { name: /Save note/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
  });

  it("O3c: the modal footer exposes Copy card / Export / Close", () => {
    setup();
    const { container } = render(withClient(<InsightsPage />));
    // Scope to .modal-foot — the header has its own aria-label="Close" X,
    // and the page head has an "Export PDF" button.
    const foot = container.querySelector(".modal-foot");
    expect(foot).toBeTruthy();
    expect(foot?.textContent).toMatch(/Copy card/);
    expect(foot?.textContent).toMatch(/Export/);
    expect(foot?.querySelector("button.btn-primary")?.textContent).toMatch(/Close/);
  });

  it("O3-callout: renders the linked-recommendation callout, preferring source_rec_id", () => {
    setup({ ...CARD, source_rec_id: "REC-03", related_rec_ids: ["REC-09"] });
    render(withClient(<InsightsPage />));
    expect(screen.getByText(/Linked recommendation/i)).toBeTruthy();
    expect(screen.getByText("REC-03")).toBeTruthy();
    expect(screen.getByText(/Adopt Marketing Cloud/)).toBeTruthy();
  });

  it("O3-callout: falls back to related_rec_ids[0] when there is no source_rec_id", () => {
    setup({ ...CARD, source_rec_id: null, related_rec_ids: ["REC-03"] });
    render(withClient(<InsightsPage />));
    expect(screen.getByText(/Linked recommendation/i)).toBeTruthy();
    expect(screen.getByText("REC-03")).toBeTruthy();
  });

  it("O3-callout: no callout when the insight has no linked rec", () => {
    setup({ ...CARD, source_rec_id: null, related_rec_ids: [] });
    const { container } = render(withClient(<InsightsPage />));
    expect(screen.queryByText(/Linked recommendation/i)).toBeNull();
    expect(container.querySelector(".co-teal")).toBeNull();
  });

  it("O3-callout: hidden for the customer audience", () => {
    // afterEach restores the audience (after unmount, avoiding an act() warning).
    useUiStore.setState({ audience: "customer" });
    setup({ ...CARD, source_rec_id: "REC-03", related_rec_ids: [] });
    render(withClient(<InsightsPage />));
    expect(screen.queryByText(/Linked recommendation/i)).toBeNull();
  });
});
