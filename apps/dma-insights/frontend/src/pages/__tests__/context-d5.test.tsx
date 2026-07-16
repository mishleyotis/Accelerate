/**
 * D5 Context — Part 8 workstream tests:
 *   - access: NO frontend role gate (AE renders the page); the
 *     customer-audience strip is KEPT
 *   - EventDetail passes eId in the evidence drawer payload + renders
 *     cap-impact chips from subcap_ids + precision-aware date label
 *   - SentimentCard: structured expandable tiles (drilldown + themes +
 *     evidence chip w/ eId)
 *   - ContextLeadershipPanel: tenure / NEW / KEY SEAT / GAP badges
 *   - eventSignal: native payload signal wins; kind fallback for legacy rows
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as hashRouter from "@/lib/hash-router";
import * as queries from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import {
  ContextLeadershipPanel,
  ContextPage,
  EventDetail,
  SentimentCard,
  eventDateLabel,
  eventSignal,
} from "@/pages/ContextPage";
import type { TimelineEventOut } from "@/lib/queries";

function stubRoute(): void {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-0001/context", query: {}, navigate: vi.fn(), setQuery: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
}

function loaded<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function ev(over: Partial<TimelineEventOut> = {}): TimelineEventOut {
  return {
    id: "te1", event_date: "2024-06-01", kind: "product",
    title: "Bank launched rebuilt mobile app", body: "verbatim claim text",
    source_url: null, e_id: "E-100",
    signal: "positive", date_precision: "month",
    evidence_e_ids: ["E-100", "E-214"], subcap_ids: ["P2C1.1.1"],
    ...over,
  };
}

afterEach(() => {
  // Unmount BEFORE resetting the audience — flipping the store while the
  // page is mounted would re-render ContextPageData without the hook mocks.
  cleanup();
  useUiStore.setState({ audience: "internal" });
  vi.restoreAllMocks();
});

describe("D5 access (Part 8.1)", () => {
  it("customer audience stays hidden (server-side stripped)", () => {
    useUiStore.setState({ audience: "customer" });
    render(<ContextPage />);
    expect(screen.getByText(/Hidden in customer view/)).toBeTruthy();
  });

  it("internal audience renders the data page for ANY role — no role gate", () => {
    useUiStore.setState({ audience: "internal" });
    stubRoute();
    vi.spyOn(queries, "useEntityContext").mockReturnValue(
      { data: undefined, isLoading: true, isError: false, error: null } as
        ReturnType<typeof queries.useEntityContext>,
    );
    vi.spyOn(queries, "useEntityOverview").mockReturnValue(
      loaded(undefined) as unknown as ReturnType<typeof queries.useEntityOverview>,
    );
    render(<ContextPage />);
    expect(screen.queryByText(/Analyst access required/)).toBeNull();
    expect(screen.getByText(/Loading context/)).toBeTruthy();
  });
});

describe("eventSignal + eventDateLabel (Part 8.2)", () => {
  it("native payload signal wins over kind-derived polarity", () => {
    // kind='acquisition' would read positive under the legacy mapping —
    // the claim's own polarity (negative) must win.
    expect(eventSignal(ev({ kind: "acquisition", signal: "negative" }))).toBe("negative");
  });

  it("legacy rows without signal fall back to kind", () => {
    expect(eventSignal(ev({ kind: "regulatory", signal: null }))).toBe("negative");
    expect(eventSignal(ev({ kind: "acquisition", signal: undefined }))).toBe("positive");
  });

  it("publish_fallback dates render approximate; day dates render full", () => {
    expect(eventDateLabel(ev({ date_precision: "publish_fallback" }))).toBe("≈ 2024-06");
    expect(eventDateLabel(ev({ event_date: "2024-06-15", date_precision: "day" }))).toBe("2024-06-15");
    expect(eventDateLabel(ev({ date_precision: "year" }))).toBe("2024");
    expect(eventDateLabel(ev({ event_date: "2024-08-01", date_precision: "quarter" }))).toBe("Q3 2024");
  });
});

describe("EventDetail (Part 8.2 / 11.1)", () => {
  it("renders cap-impact chips and passes the clicked eId to the opener", () => {
    const onOpenEvidence = vi.fn();
    render(<EventDetail event={ev()} onClose={vi.fn()} onOpenEvidence={onOpenEvidence} />);
    // cap-impact chips from subcap_ids
    expect(screen.getByTestId("cap-impact-chip").textContent).toBe("P2C1.1.1");
    // one chip per evidence_e_ids entry; click carries the E-ID
    fireEvent.click(screen.getByRole("button", { name: "E-214" }));
    expect(onOpenEvidence).toHaveBeenCalledWith("E-214");
    fireEvent.click(screen.getByRole("button", { name: "E-100" }));
    expect(onOpenEvidence).toHaveBeenCalledWith("E-100");
  });

  it("legacy rows without evidence_e_ids fall back to the scalar e_id", () => {
    const onOpenEvidence = vi.fn();
    render(
      <EventDetail
        event={ev({ evidence_e_ids: [], subcap_ids: [] })}
        onClose={vi.fn()}
        onOpenEvidence={onOpenEvidence}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "E-100" }));
    expect(onOpenEvidence).toHaveBeenCalledWith("E-100");
  });

  it("flags approximate dates in the explainer", () => {
    render(
      <EventDetail
        event={ev({ date_precision: "publish_fallback" })}
        onClose={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );
    expect(screen.getByText(/Date is approximate/)).toBeTruthy();
  });
});

describe("SentimentCard (Part 8.5)", () => {
  const sentiment = {
    sources: [
      {
        source: "Glassdoor", kind: "employee", value: 3.8, max: 5, n: 412,
        polarity: "negative",
        themes: ["manual processing", "spreadsheet-heavy ops"],
        drilldown: "Recurring themes: manual processing, spreadsheet-heavy work in ops.",
        evidence_e_id: "E-236",
      },
      {
        source: "BauerFinancial", kind: "industry", value: null, max: null, n: null,
        polarity: "positive", themes: [], drilldown: null, evidence_e_id: null,
      },
    ],
  };

  it("tiles are collapsed by default and expand to the drilldown", () => {
    render(<SentimentCard sentiment={sentiment} />);
    expect(screen.queryByTestId("sentiment-drilldown")).toBeNull();
    const tiles = screen.getAllByTestId("sentiment-tile");
    expect(tiles.length).toBe(2);
    expect(tiles[0].textContent).toContain("3.8");
    expect(tiles[0].textContent).toContain("/5");
    expect(tiles[0].textContent).toContain("n=412");
    fireEvent.click(tiles[0]);
    const drill = screen.getByTestId("sentiment-drilldown");
    expect(drill.textContent).toContain("Recurring themes");
    expect(drill.textContent).toContain("manual processing");
  });

  it("the drilldown evidence chip passes the eId", () => {
    const onOpenEvidence = vi.fn();
    render(<SentimentCard sentiment={sentiment} onOpenEvidence={onOpenEvidence} />);
    fireEvent.click(screen.getAllByTestId("sentiment-tile")[0]);
    fireEvent.click(screen.getByRole("button", { name: "E-236" }));
    expect(onOpenEvidence).toHaveBeenCalledWith("E-236");
  });

  it("value-less sources render their polarity, not a fake number", () => {
    render(<SentimentCard sentiment={sentiment} />);
    expect(screen.getAllByTestId("sentiment-tile")[1].textContent).toContain("POSITIVE");
  });

  it("null sentiment renders the honest empty state", () => {
    render(<SentimentCard sentiment={null} />);
    expect(screen.getByText(/No public sentiment parsed/)).toBeTruthy();
  });
});

describe("ContextLeadershipPanel (Part 8.6)", () => {
  const leadership = [
    { name: "Diana Solis", title: "CTO", tenure_months: 2, critical_role: true,
      recent_hire: true, background: "From Wells Fargo. Hired April 2026." },
    { name: "Mark Hochberg", title: "CEO", tenure_months: 38, critical_role: false },
    { name: null, title: "CISO", gap_flag: true, critical_role: true,
      note: "Not confirmed from public evidence." },
  ];

  it("renders tenure / NEW / KEY SEAT / GAP badges + the gap counter", () => {
    render(<ContextLeadershipPanel leadership={leadership} />);
    const rows = screen.getAllByTestId("context-leader-row");
    expect(rows.length).toBe(3);
    expect(rows[0].textContent).toContain("NEW · 2 mo");
    expect(rows[0].textContent).toContain("KEY SEAT");
    expect(rows[1].textContent).toContain("3 yr");
    expect(rows[2].textContent).toContain("GAP");
    expect(screen.getByText(/1 critical seat unconfirmed/)).toBeTruthy();
  });

  it("renders nothing for an empty roster", () => {
    const { container } = render(<ContextLeadershipPanel leadership={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
