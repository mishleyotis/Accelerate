/**
 * Evidence eId spine (plan Part 11.1/11.2) + 2026-07-06 drawer rebuild —
 * the cross-page drilldown contract that makes every E-ID chip open the
 * EXACT cited row:
 *
 *   1. DrawerHost payload parsing — `asEvidencePayload` must carry `eId`
 *      AND the card's cited list `eIds` (+ optional score/confidence
 *      header context) through the host → drawer hand-off.
 *   2. EvidenceDrawer scope + reveal behaviour —
 *        eIds[] passed          → list scoped to exactly the cited rows;
 *                                 zero resolvable cited rows → falls back
 *                                 to the subcap scope (never empty-by-scope)
 *        subcapId passed        → HIERARCHICAL match (P2C1 ⇄ P2C1.1.6);
 *                                 the clicked eId is force-included even
 *                                 when its tags don't match the scope
 *        row present            → `.evidence-row-hl` highlight + header chip
 *        row tier-filtered out  → tier-chip filter auto-relaxes to "All"
 *        row absent entirely    → honest render, no highlight; an EMPTY
 *                                 corpus names the E-ID
 *   3. Tier-distribution chips — client-side toggle with counts
 *      ("All · N", "T2 · n"), per proto 374f91c6; the old server-side
 *      min-tier <select> is gone.
 *   4. Pack-first fetch — default view resolves via snapshotOrApi
 *      (pageSnapshot "evidence" first); a selected run goes API-first
 *      (apiOrSnapshot) and forwards ?run=.
 *   5. URL reader (`useEvidenceDeepLink`, hosted in ClientShell) —
 *      `?drawer=evidence&e=E-123&subcap=P1C1.1.1` opens the drawer with
 *      the deep-linked scope, then strips the consumed `drawer`/`e`
 *      params (keeping `subcap`, which the heatmap deep-link shares).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (opts: unknown) => mockUseQuery(opts),
}));
vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));
// Pack-first plumbing — spied so the fetch-path tests can assert which
// resolver the drawer picked without a network layer.
type Resolver = (
  getter: () => Promise<unknown>, displayId: string | null, page: string,
) => Promise<unknown>;
const mockSnapshotOrApi = vi.fn<Resolver>(async (getter) => getter());
const mockApiOrSnapshot = vi.fn<Resolver>(async (getter) => getter());
vi.mock("@/lib/startup-pages", () => ({
  USE_STARTUP_PACK: true,
  snapshotOrApi: (...a: Parameters<Resolver>) => mockSnapshotOrApi(...a),
  apiOrSnapshot: (...a: Parameters<Resolver>) => mockApiOrSnapshot(...a),
  pageSnapshot: vi.fn(async () => null),
}));
// ClientShell + DrawerHost children pull the full queries surface — stub
// every hook they import; the code under test doesn't touch them.
vi.mock("@/lib/queries", () => ({
  useEntityOverview: () => ({ data: null, isLoading: true, error: null }),
  useEntityRuns: () => ({ data: null, isLoading: false, error: null }),
  useRequestNewRun: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { apiGet } from "@/lib/api";
import { EvidenceDrawer, subcapMatches } from "../EvidenceDrawer";
import { asEvidencePayload } from "../DrawerHost";
import { useEvidenceDeepLink } from "../ClientShell";
import { useUiStore } from "@/store/ui";

function mkQuery(over: Record<string, unknown>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function evidenceResp(items: Array<Record<string, unknown>>) {
  return {
    entity_display_id: "alma",
    run_request_id: "REQ-1",
    filter_subcap_id: null,
    filter_min_tier: 8,
    filter_e_ids: [],
    items,
  };
}

function row(eId: string, tier: number, tags: string[] = ["P1C1.1.1"]) {
  return {
    id: `uuid-${eId}`, e_id: eId,
    source_name: "FT.com", source_url: null,
    excerpt: `excerpt for ${eId}`, claim_type: "FACT", tier,
    recency_months: 3,
    published_date: "2025-01-01",
    linked_subcap_ids: tags,
  };
}

/** Route every "evidence" useQuery to the given items (full-list fetch —
 *  the drawer filters client-side, so the mock never varies by key). */
function mockEvidence(items: Array<Record<string, unknown>>) {
  mockUseQuery.mockImplementation((opts: any) => {
    if (opts.queryKey?.[0] === "evidence") {
      return mkQuery({ data: evidenceResp(items) });
    }
    return mkQuery({});
  });
}

beforeEach(() => {
  mockUseQuery.mockReset();
  mockSnapshotOrApi.mockClear();
  mockApiOrSnapshot.mockClear();
  (apiGet as ReturnType<typeof vi.fn>).mockReset();
  window.location.hash = "";
  useUiStore.setState({ selectedRunId: null, audience: "internal" });
});

describe("DrawerHost.asEvidencePayload (eId + eIds spine)", () => {
  it("carries eId + eIds + subcapId + displayId + score/confidence through", () => {
    expect(
      asEvidencePayload({
        displayId: "alma", subcapId: "P1C1.1.1", eId: "E-042",
        eIds: ["E-042", "E-043"], score: 2.1, confidence: "HIGH",
      }),
    ).toEqual({
      displayId: "alma", subcapId: "P1C1.1.1", eId: "E-042",
      eIds: ["E-042", "E-043"], score: 2.1, confidence: "HIGH",
    });
  });

  it("null-fills missing / malformed fields", () => {
    const empty = {
      displayId: null, subcapId: null, eId: null,
      eIds: null, score: null, confidence: null,
    };
    expect(asEvidencePayload({ displayId: "alma" }))
      .toEqual({ ...empty, displayId: "alma" });
    expect(asEvidencePayload({ displayId: "alma", eId: 42 }))
      .toEqual({ ...empty, displayId: "alma" });
    expect(asEvidencePayload({ displayId: "alma", eId: "  " }))
      .toEqual({ ...empty, displayId: "alma" });
    // eIds: non-array / empty / non-string members are dropped.
    expect(asEvidencePayload({ displayId: "alma", eIds: "E-1" }))
      .toEqual({ ...empty, displayId: "alma" });
    expect(asEvidencePayload({ displayId: "alma", eIds: [] }))
      .toEqual({ ...empty, displayId: "alma" });
    expect(asEvidencePayload({ displayId: "alma", eIds: [42, "  ", "E-7"] }))
      .toEqual({ ...empty, displayId: "alma", eIds: ["E-7"] });
    expect(asEvidencePayload({ score: "2.1", confidence: 3 }))
      .toEqual(empty);
    expect(asEvidencePayload(null)).toEqual(empty);
    expect(asEvidencePayload("E-001")).toEqual(empty);
  });

  it("ignores extra opener-provenance keys (origin etc.)", () => {
    expect(
      asEvidencePayload({ displayId: "alma", eId: "E-007", origin: "why-now" }),
    ).toEqual({
      displayId: "alma", subcapId: null, eId: "E-007",
      eIds: null, score: null, confidence: null,
    });
  });
});

describe("EvidenceDrawer.subcapMatches (hierarchical twin of the SQL predicate)", () => {
  it("matches exact, parent→child and child→parent", () => {
    expect(subcapMatches("P2C1.1.6", ["P2C1.1.6"])).toBe(true);
    expect(subcapMatches("P2C1", ["P2C1.1.6"])).toBe(true);   // screenshot case
    expect(subcapMatches("P2C1.1.6", ["P2C1"])).toBe(true);   // leaf vs coarse tags
  });

  it("respects dot boundaries (P2C10 is not under P2C1)", () => {
    expect(subcapMatches("P2C1", ["P2C10"])).toBe(false);
    expect(subcapMatches("P2C10", ["P2C1.1.1"])).toBe(false);
    expect(subcapMatches("P2C1", ["P2C2.1.1"])).toBe(false);
    expect(subcapMatches("P2C1", [])).toBe(false);
    expect(subcapMatches("", ["P2C1"])).toBe(false);
  });
});

describe("EvidenceDrawer eId highlight", () => {
  it("highlights + marks the cited row and shows the header chip", () => {
    mockEvidence([row("E-001", 2), row("E-042", 3)]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" eId="E-042" onClose={() => {}} />,
    );
    const hl = container.querySelector(".evidence-row-hl");
    expect(hl).not.toBeNull();
    expect(hl!.getAttribute("data-eid")).toBe("E-042");
    // The other row is NOT highlighted.
    const other = container.querySelector('[data-eid="E-001"]');
    expect(other!.classList.contains("evidence-row-hl")).toBe(false);
    // Header carries the target chip.
    const head = container.querySelector(".drawer-head");
    expect(head!.textContent).toContain("E-042");
    expect(head!.textContent).toContain("EVIDENCE");
  });

  it("auto-relaxes a tightened tier-chip filter when the target row is hidden", () => {
    mockEvidence([row("E-001", 1), row("E-042", 6)]);
    const view = render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    // Operator narrows to tier 1 via the distribution chip — only the
    // tier-1 row stays rendered.
    fireEvent.click(screen.getByRole("button", { name: "T1 · 1" }));
    expect(view.container.querySelector('[data-eid="E-042"]')).toBeNull();
    expect(view.container.querySelector('[data-eid="E-001"]')).not.toBeNull();

    // Same instance re-opens pinned to the tier-6 row (payload change via
    // DrawerHost): the sticky filter must relax back to "All" and the row
    // must be highlighted.
    view.rerender(<EvidenceDrawer open displayId="alma" eId="E-042" onClose={() => {}} />);
    expect(view.container.querySelector('.evidence-row-hl[data-eid="E-042"]')).not.toBeNull();
    expect(view.container.querySelector('[data-eid="E-001"]')).not.toBeNull();
  });

  it("force-includes the clicked eId when the subcap scope wouldn't contain it", () => {
    // Successor of the old server-side scope-drop: a citation may be
    // linked to different subcaps than the surface it was cited on — the
    // clicked row must always win.
    mockEvidence([
      row("E-001", 2, ["P9C9.9.9"]),
      row("E-042", 3, ["P1C1.1.1"]),
    ]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" subcapId="P9C9.9.9" eId="E-042" onClose={() => {}} />,
    );
    expect(container.querySelector('.evidence-row-hl[data-eid="E-042"]')).not.toBeNull();
    // The subcap-scoped row still renders alongside it.
    expect(container.querySelector('[data-eid="E-001"]')).not.toBeNull();
  });

  it("renders honestly (no highlight) when the eId is absent from the run", () => {
    mockEvidence([row("E-001", 2)]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" eId="E-999" onClose={() => {}} />,
    );
    expect(container.querySelector(".evidence-row-hl")).toBeNull();
    // List still renders — nothing is hidden or fabricated.
    expect(container.querySelector('[data-eid="E-001"]')).not.toBeNull();
  });

  it("empty corpus + eId names the missing citation instead of blaming a tier filter", () => {
    mockEvidence([]);
    render(<EvidenceDrawer open displayId="alma" eId="E-037" onClose={() => {}} />);
    expect(screen.getByText("No evidence on record")).toBeTruthy();
    expect(screen.getByText(/E-037 isn't in this run's evidence corpus/)).toBeTruthy();
    expect(screen.queryByText(/Loosen the tier filter/)).toBeNull();
  });
});

describe("EvidenceDrawer tier-distribution chips (proto 374f91c6)", () => {
  it("defaults to All: every fetched tier renders, no min-tier select", () => {
    mockEvidence([row("E-001", 1), row("E-002", 3), row("E-003", 4)]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" onClose={() => {}} />,
    );
    expect(container.querySelectorAll(".evidence-row").length).toBe(3);
    // The old server-side min-tier select is gone.
    expect(container.querySelector("select")).toBeNull();
    // Chip row: "All · 3" + one exact-tier chip per tier present.
    const group = screen.getByRole("group", { name: "Filter by evidence tier" });
    expect(group.textContent).toContain("All · 3");
    expect(group.textContent).toContain("T1 · 1");
    expect(group.textContent).toContain("T3 · 1");
    expect(group.textContent).toContain("T4 · 1");
    // No chips for tiers the corpus doesn't have.
    expect(group.textContent).not.toContain("T8");
  });

  it("renders 'All · N' + per-tier counts and toggles client-side", () => {
    mockEvidence([row("E-001", 1), row("E-002", 1), row("E-003", 3)]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" onClose={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "All · 3" })).toBeTruthy();
    const t1 = screen.getByRole("button", { name: "T1 · 2" });
    expect(screen.getByRole("button", { name: "T3 · 1" })).toBeTruthy();
    // Narrow to T1 → only the two tier-1 rows render.
    fireEvent.click(t1);
    expect(container.querySelectorAll(".evidence-row").length).toBe(2);
    expect(container.querySelector('[data-eid="E-003"]')).toBeNull();
    // Click the same chip again → back to All.
    fireEvent.click(screen.getByRole("button", { name: "T1 · 2" }));
    expect(container.querySelectorAll(".evidence-row").length).toBe(3);
  });

  it("a sticky tier pick that empties the next scope shows the tier empty-state", () => {
    mockEvidence([row("E-001", 1), row("E-002", 3)]);
    const view = render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "T3 · 1" }));
    // Re-open scoped to a citation list that only resolves the tier-1 row —
    // the sticky T3 pick now hides everything (no eId → no auto-relax).
    view.rerender(
      <EvidenceDrawer open displayId="alma" eIds={["E-001"]} onClose={() => {}} />,
    );
    expect(screen.getByText("No evidence in this tier")).toBeTruthy();
    // Actionable copy names the chips, not the removed min-tier select.
    expect(screen.getByText(/Pick another tier chip/)).toBeTruthy();
  });

  it("rows render the prototype structure: tier-tinted excerpt quote + source + supports", () => {
    mockEvidence([row("E-001", 1)]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" onClose={() => {}} />,
    );
    const el = container.querySelector('[data-eid="E-001"]') as HTMLElement;
    expect(el.querySelector(".tier-chip.tier-T1")?.textContent)
      .toBe("T1 · Primary disclosure");
    expect(el.querySelector(".evidence-excerpt")?.textContent)
      .toContain("excerpt for E-001");
    expect(el.querySelector(".evidence-source")?.textContent).toContain("FT.com");
    expect(el.querySelector(".evidence-links")?.textContent).toContain("P1C1.1.1");
    // Freshness badge + head chips stay.
    expect(el.querySelector("[data-band]")).not.toBeNull();
  });
});

describe("EvidenceDrawer eIds scoping (card citations)", () => {
  it("scopes the list to exactly the cited rows + counts them in the subline", () => {
    mockEvidence([
      row("E-001", 1), row("E-002", 2), row("E-003", 3), row("E-004", 4),
    ]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" eIds={["E-002", "E-004"]} onClose={() => {}} />,
    );
    expect(container.querySelectorAll(".evidence-row").length).toBe(2);
    expect(container.querySelector('[data-eid="E-002"]')).not.toBeNull();
    expect(container.querySelector('[data-eid="E-004"]')).not.toBeNull();
    expect(container.querySelector('[data-eid="E-001"]')).toBeNull();
    expect(screen.getByTestId("evidence-subline").textContent)
      .toContain("2 evidence items");
  });

  it("falls back to the subcap scope when zero cited rows resolve", () => {
    mockEvidence([
      row("E-001", 1, ["P2C1.1.6"]),
      row("E-002", 2, ["P3C2"]),
    ]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" subcapId="P2C1"
                      eIds={["E-777"]} onClose={() => {}} />,
    );
    // E-777 doesn't exist → subcap scope wins (hierarchical: P2C1 ⇄ P2C1.1.6).
    expect(container.querySelectorAll(".evidence-row").length).toBe(1);
    expect(container.querySelector('[data-eid="E-001"]')).not.toBeNull();
  });

  it("renders the internal-only Rationale callout for the cited scope", () => {
    mockEvidence([row("E-001", 1)]);
    render(
      <EvidenceDrawer open displayId="alma" eIds={["E-001"]} onClose={() => {}} />,
    );
    expect(screen.getByTestId("evidence-rationale").textContent).toContain("Rationale");
    expect(screen.getByTestId("evidence-rationale").textContent).toContain("1 E-ID");
  });

  it("hides the Rationale callout for the customer audience", () => {
    useUiStore.setState({ audience: "customer" });
    mockEvidence([row("E-001", 1)]);
    render(
      <EvidenceDrawer open displayId="alma" eIds={["E-001"]} onClose={() => {}} />,
    );
    expect(screen.queryByTestId("evidence-rationale")).toBeNull();
  });
});

describe("EvidenceDrawer hierarchical subcap scope", () => {
  it("category scope matches leaf-tagged rows and vice versa (screenshot case)", () => {
    mockEvidence([
      row("E-001", 1, ["P2C1.1.6"]),   // leaf tag
      row("E-002", 2, ["P2C1"]),       // category tag
      row("E-003", 3, ["P3C2.1.1"]),   // unrelated
      row("E-004", 4, ["P2C10"]),      // dot-boundary lookalike
    ]);
    const { container } = render(
      <EvidenceDrawer open displayId="alma" subcapId="P2C1" onClose={() => {}} />,
    );
    expect(container.querySelector('[data-eid="E-001"]')).not.toBeNull();
    expect(container.querySelector('[data-eid="E-002"]')).not.toBeNull();
    expect(container.querySelector('[data-eid="E-003"]')).toBeNull();
    expect(container.querySelector('[data-eid="E-004"]')).toBeNull();
  });

  it("shows the scope-aware empty state when nothing cites the subcap", () => {
    mockEvidence([row("E-001", 1, ["P3C2"])]);
    render(
      <EvidenceDrawer open displayId="alma" subcapId="P9C9" onClose={() => {}} />,
    );
    expect(screen.getByText("No evidence cites this capability")).toBeTruthy();
    // The old unactionable copy ("Loosen the tier filter…") must be gone.
    expect(screen.queryByText(/Loosen the tier filter/)).toBeNull();
  });
});

describe("EvidenceDrawer pack-first fetch", () => {
  it("default (active-run) view resolves snapshot-first via page 'evidence'", async () => {
    mockEvidence([]);
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(evidenceResp([]));
    render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    const evidenceOpts = mockUseQuery.mock.calls
      .map((c) => c[0])
      .filter((o) => o?.queryKey?.[0] === "evidence")
      .at(-1);
    expect(evidenceOpts.queryKey).toEqual(["evidence", "alma", "active", "internal"]);
    await evidenceOpts.queryFn();
    expect(mockSnapshotOrApi).toHaveBeenCalledTimes(1);
    expect(mockSnapshotOrApi.mock.calls[0][1]).toBe("alma");
    expect(mockSnapshotOrApi.mock.calls[0][2]).toBe("evidence");
    expect(mockApiOrSnapshot).not.toHaveBeenCalled();
    // The API getter fetches the FULL list at the loosest server filter.
    expect(apiGet).toHaveBeenCalledWith(
      "/api/v1/entities/alma/evidence",
      { min_tier: 8, limit: 500, run: undefined },
    );
  });

  it("a selected run goes API-first and forwards ?run=", async () => {
    useUiStore.setState({ selectedRunId: "REQ-9" });
    mockEvidence([]);
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(evidenceResp([]));
    render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    const evidenceOpts = mockUseQuery.mock.calls
      .map((c) => c[0])
      .filter((o) => o?.queryKey?.[0] === "evidence")
      .at(-1);
    expect(evidenceOpts.queryKey).toEqual(["evidence", "alma", "REQ-9", "internal"]);
    await evidenceOpts.queryFn();
    expect(mockApiOrSnapshot).toHaveBeenCalledTimes(1);
    expect(mockSnapshotOrApi).not.toHaveBeenCalled();
    expect(apiGet).toHaveBeenCalledWith(
      "/api/v1/entities/alma/evidence",
      { min_tier: 8, limit: 500, run: "REQ-9" },
    );
  });
});

describe("useEvidenceDeepLink (?drawer=evidence&e= URL reader)", () => {
  function Probe({ displayId }: { displayId: string }) {
    useEvidenceDeepLink(displayId);
    return <div data-testid="probe" />;
  }

  beforeEach(() => {
    mockUseQuery.mockImplementation(() => mkQuery({}));
    useUiStore.setState({ activeDrawer: null, drawerPayload: null });
  });

  it("opens the evidence drawer with eId + subcap scope, then strips drawer/e", async () => {
    const openSpy = vi.fn(useUiStore.getState().openDrawer);
    useUiStore.setState({ openDrawer: openSpy });
    window.location.hash =
      "#/clients/alma/overview?drawer=evidence&e=E-042&subcap=P1C1.1.1&run=REQ-9";
    await act(async () => {
      render(<Probe displayId="alma" />);
    });
    expect(openSpy).toHaveBeenCalledWith("evidence", {
      displayId: "alma",
      eId: "E-042",
      subcapId: "P1C1.1.1",
      origin: "url",
    });
    // Consumed params stripped; subcap + run survive (heatmap/run share them).
    expect(window.location.hash).not.toContain("drawer=");
    expect(window.location.hash).not.toContain("e=E-042");
    expect(window.location.hash).toContain("subcap=P1C1.1.1");
    expect(window.location.hash).toContain("run=REQ-9");
  });

  it("supports the legacy subcap_id param and drawer-only links (no eId)", async () => {
    const openSpy = vi.fn();
    useUiStore.setState({ openDrawer: openSpy });
    window.location.hash = "#/clients/alma/heatmap?drawer=evidence&subcap_id=P2C1.2.1";
    await act(async () => {
      render(<Probe displayId="alma" />);
    });
    expect(openSpy).toHaveBeenCalledWith("evidence", {
      displayId: "alma",
      eId: null,
      subcapId: "P2C1.2.1",
      origin: "url",
    });
  });

  it("does nothing without the drawer param", async () => {
    const openSpy = vi.fn();
    useUiStore.setState({ openDrawer: openSpy });
    window.location.hash = "#/clients/alma/overview?run=REQ-1";
    await act(async () => {
      render(<Probe displayId="alma" />);
    });
    expect(openSpy).not.toHaveBeenCalled();
    expect(window.location.hash).toContain("run=REQ-1");
  });
});
