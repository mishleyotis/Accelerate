/**
 * IntelligencePanel — phase transitions + SSE event handling + chat
 * contract (answer_markdown / citations / feedback / session round-trip)
 * + fallback banner copy keyed to real flags + no-auto-open guard.
 *
 * We monkey-patch the lib/sse `subscribeSSE` so tests don't need a real
 * EventSource, and mock lib/api so no fetch leaves the process. Each
 * test feeds events through the handler map and asserts visible state.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntelligencePanel, WhyNowSignals } from "../IntelligencePanel";
import * as sse from "@/lib/sse";
import { apiGet, apiPost } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    apiGet: vi.fn(() => Promise.reject(new Error("no backend in tests"))),
    apiPost: vi.fn(() => Promise.reject(new Error("no backend in tests"))),
  };
});

type HandlerMap = Record<string, (data: string) => void>;

function mockSubscribe() {
  const captured: { handlers: HandlerMap | null; closed: boolean } = {
    handlers: null,
    closed: false,
  };
  const spy = vi.spyOn(sse, "subscribeSSE").mockImplementation(
    (_url: string, handlers: HandlerMap) => {
      captured.handlers = handlers;
      return {
        close: () => { captured.closed = true; },
        isOpen: () => !captured.closed,
      };
    },
  );
  return { captured, spy };
}

/** The panel now consumes useEntityOverview (why_now deep signals) — every
 *  mount needs a QueryClientProvider. */
function renderPanel(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
    .mockImplementation(() => Promise.reject(new Error("no backend in tests")));
  vi.mocked(apiPost).mockReset()
    .mockImplementation(() => Promise.reject(new Error("no backend in tests")));
  window.sessionStorage.clear();
});

describe("IntelligencePanel", () => {
  it("renders nothing when closed", () => {
    const { container } = renderPanel(
      <IntelligencePanel open={false} onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the opening spinner before any tokens arrive", () => {
    mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    expect(screen.getByLabelText("Loading")).toBeTruthy();
    expect(screen.getByText(/Opening stream/i)).toBeTruthy();
  });

  it("concatenates token events into the live text + shows cursor", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.token(JSON.stringify({ text: "Hello, " }));
      captured.handlers!.token(JSON.stringify({ text: "world." }));
    });
    expect(screen.getByText(/Hello, world\./)).toBeTruthy();
    // Cursor visible during streaming
    expect(document.querySelector(".ip-cursor")).toBeTruthy();
  });

  it("marks done + shows cited evidence chips + closes the stream on done", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.token(JSON.stringify({ text: "Final answer." }));
      captured.handlers!.done(JSON.stringify({ cited_evidence_ids: ["E-1", "E-9"] }));
    });
    expect(screen.getByText(/Final answer\./)).toBeTruthy();
    expect(screen.getByText("E-1")).toBeTruthy();
    expect(screen.getByText("E-9")).toBeTruthy();
    // Cursor gone after done
    expect(document.querySelector(".ip-cursor")).toBeNull();
    // Stream closed so the auto-reconnect can't re-trigger the builder.
    expect(captured.closed).toBe(true);
  });

  it("close button is accessible-labeled and triggers onClose", () => {
    mockSubscribe();
    const onClose = vi.fn();
    renderPanel(
      <IntelligencePanel open onClose={onClose}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    const closeBtn = screen.getByLabelText("Close intelligence panel");
    closeBtn.click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("unsubscribes when the component closes", async () => {
    const { captured } = mockSubscribe();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <IntelligencePanel open onClose={() => undefined}
          surface="subcap_narrative" ref_="P1C1.1.1" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    rerender(
      <QueryClientProvider client={qc}>
        <IntelligencePanel open={false} onClose={() => undefined}
          surface="subcap_narrative" ref_="P1C1.1.1" />
      </QueryClientProvider>,
    );
    expect(captured.closed).toBe(true);
  });
});

describe("IntelligencePanel fallback contract (served_text/text + flags)", () => {
  it("renders the served_text body with the vertex_error banner copy", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.fallback(JSON.stringify({
        flags: { vertex_error: "quota exceeded", deterministic: true },
        served_text: "Digital Onboarding (P1C1.1.1) scores 3.2 / 5. Peer median is 3.5.",
        cited_evidence_ids: ["E-101"],
      }));
    });
    // Body read from `served_text` (pre-fix the panel only read `text`
    // and rendered an EMPTY amber banner).
    expect(screen.getByText(/Digital Onboarding \(P1C1\.1\.1\) scores 3\.2/)).toBeTruthy();
    // Banner copy reflects the ACTUAL flag (not the old blanket
    // "failed grounding validation" claim).
    expect(screen.getByText(/Gemini unavailable — showing the grounded summary below/)).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    // Deterministic fallback ships real citations.
    expect(screen.getByText("E-101")).toBeTruthy();
    expect(captured.closed).toBe(true);
  });

  it("reads the forward-compat `text` key too", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="why_now" ref_="fce-001" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.fallback(JSON.stringify({
        flags: { vertex_error: "cold" },
        text: "Grounded deterministic why-now body.",
      }));
    });
    expect(screen.getByText(/Grounded deterministic why-now body\./)).toBeTruthy();
  });

  it("labels validator rejections as withheld", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.fallback(JSON.stringify({
        flags: { fabricated_e_ids: ["E-9999"] },
        served_text: "Insight withheld — grounding validation failed. Analyst review pending.",
      }));
    });
    expect(screen.getByText(/Withheld — grounding validation failed\./)).toBeTruthy();
  });

  it("gives context errors an honest banner", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.fallback(JSON.stringify({
        flags: { context_error: "DB unavailable" },
        served_text: "Insight not available — the grounding data for this surface could not be loaded.",
      }));
    });
    expect(
      screen.getByText(/Insight unavailable — the grounding data for this surface could not be loaded/),
    ).toBeTruthy();
  });
});

describe("IntelligencePanel stream health events", () => {
  it("wires the reconnecting indicator to reconnect/error/__reconnecting and clears on tokens", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => captured.handlers!.__reconnecting(""));
    expect(screen.getByText("Reconnecting…")).toBeTruthy();
    act(() => captured.handlers!.token(JSON.stringify({ text: "back " })));
    expect(screen.queryByText("Reconnecting…")).toBeNull();
    act(() => captured.handlers!.reconnect(JSON.stringify({ reason: "max_stream_age" })));
    expect(screen.getByText("Reconnecting…")).toBeTruthy();
    act(() => captured.handlers!.__connected(""));
    expect(screen.queryByText("Reconnecting…")).toBeNull();
    act(() => captured.handlers!.error(JSON.stringify({ reason: "redis_unavailable" })));
    expect(screen.getByText("Reconnecting…")).toBeTruthy();
  });

  it("shows an idle note on stream_idle", async () => {
    const { captured } = mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => captured.handlers!.stream_idle(JSON.stringify({ polls_silent: 30 })));
    expect(screen.getByText(/Stream idle/)).toBeTruthy();
  });
});

describe("IntelligencePanel chat contract", () => {
  it("renders answer_markdown + citation chips + stale disclaimer, and round-trips session_id", async () => {
    const { captured } = mockSubscribe();
    vi.mocked(apiPost).mockResolvedValue({
      session_id: "s-1",
      message_id: "m-1",
      answer_markdown: "Grounded answer body [E-7].",
      cited_evidence_ids: ["E-7"],
      citations: [{ e_id: "E-7", source_name: "10-K", kind: "evidence" }],
      validators_passed: true,
      fallback_used: false,
      stale_disclaimer: "⚠ Most of the evidence behind this answer is more than 3 years old — read with caution.",
    });
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    fireEvent.click(screen.getByText("What pulled this score down?"));
    await waitFor(() =>
      expect(screen.getByText(/Grounded answer body \[E-7\]\./)).toBeTruthy(),
    );
    // answer_markdown is the contract key (answer_md/answer never existed
    // server-side — reading them rendered "No answer returned." forever).
    expect(screen.queryByText("No answer returned.")).toBeNull();
    // Citation chip + stale disclaimer surfaced from the response.
    expect(screen.getByText("E-7")).toBeTruthy();
    expect(screen.getByText(/more than 3 years old/)).toBeTruthy();
    // session_id persisted for the round-trip.
    expect(
      window.sessionStorage.getItem("dma:ip-chat-session:subcap_narrative:fce-001:P1C1.1.1"),
    ).toBe("s-1");

    // Second ask sends the stored session_id.
    fireEvent.click(screen.getByText("Show me peer benchmarks for this subcap."));
    await waitFor(() => expect(vi.mocked(apiPost).mock.calls.length).toBeGreaterThanOrEqual(2));
    const secondBody = vi.mocked(apiPost).mock.calls[1][1] as { session_id?: string };
    expect(secondBody.session_id).toBe("s-1");
  });

  it("marks fallback answers and posts 👍/👎 feedback to the chat feedback endpoint", async () => {
    const { captured } = mockSubscribe();
    vi.mocked(apiPost)
      .mockResolvedValueOnce({
        session_id: "s-2",
        message_id: "m-2",
        answer_markdown: "Deterministic offline body.",
        cited_evidence_ids: [],
        citations: [],
        fallback_used: true,
      })
      .mockResolvedValueOnce({ id: "fb-1", message_id: "m-2", rating: 1 });
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    fireEvent.click(screen.getByText("What pulled this score down?"));
    await waitFor(() => expect(screen.getByText(/Deterministic offline body\./)).toBeTruthy());
    // fallback_used surfaces as a badge.
    expect(screen.getByText("Fallback")).toBeTruthy();
    // 👍 posts to the existing feedback endpoint with the message id.
    fireEvent.click(screen.getByLabelText("Mark answer helpful"));
    await waitFor(() => {
      const calls = vi.mocked(apiPost).mock.calls;
      const fb = calls.find(([path]) => String(path).includes("/feedback"));
      expect(fb).toBeTruthy();
      expect(fb![0]).toBe("/api/v1/chat/messages/m-2/feedback");
      expect(fb![1]).toEqual({ rating: 1 });
    });
  });

  it("posts response_style deeper via the Deeper · Pro button", async () => {
    const { captured } = mockSubscribe();
    vi.mocked(apiPost).mockResolvedValue({
      session_id: "s-3", message_id: "m-3",
      answer_markdown: "Deeper analysis.", cited_evidence_ids: [], citations: [],
    });
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="platform_story" ref_="fce-001:salesforce" />,
    );
    await waitFor(() => expect(captured.handlers).not.toBeNull());
    act(() => {
      captured.handlers!.token(JSON.stringify({ text: "Streamed story." }));
      captured.handlers!.done(JSON.stringify({ cited_evidence_ids: [] }));
    });
    fireEvent.click(screen.getByText("Deeper · Pro"));
    await waitFor(() => expect(vi.mocked(apiPost)).toHaveBeenCalled());
    const body = vi.mocked(apiPost).mock.calls[0][1] as { response_style?: string };
    expect(body.response_style).toBe("deeper");
  });

  it("hydrates prior turns from GET /api/v1/chat/sessions/{id} on open", async () => {
    mockSubscribe();
    window.sessionStorage.setItem(
      "dma:ip-chat-session:subcap_narrative:fce-001:P1C1.1.1", "sess-9",
    );
    vi.mocked(apiGet).mockImplementation((path: string) => {
      if (path === "/api/v1/chat/sessions/sess-9") {
        return Promise.resolve({
          id: "sess-9",
          messages: [
            { id: "u1", role: "user", content_markdown: "Prior question?" },
            { id: "a1", role: "assistant", content_markdown: "Prior grounded answer.", cited_evidence_ids: ["E-3"] },
          ],
        });
      }
      return Promise.reject(new Error("unexpected GET " + path));
    });
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="subcap_narrative" ref_="fce-001:P1C1.1.1" />,
    );
    await waitFor(() => expect(screen.getByText("Prior question?")).toBeTruthy());
    expect(screen.getByText("Prior grounded answer.")).toBeTruthy();
    expect(screen.getByText("E-3")).toBeTruthy();
    // Starter header switches to follow-up mode with history present.
    expect(screen.getByText("Follow-ups")).toBeTruthy();
  });
});

describe("IntelligencePanel parity ports", () => {
  it("ships the focus_area starter set (prototype 04_components_c.js)", async () => {
    mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="focus_area" ref_="fce-001:fa-1" />,
    );
    expect(screen.getByText("Which subcaps move the most if we close this focus area?")).toBeTruthy();
    expect(screen.getByText("What's the customer impact, not the technical impact?")).toBeTruthy();
    expect(screen.getByText("Show me peers that closed this focus area in the last 18 months.")).toBeTruthy();
    expect(screen.getByText("Focus area synthesis")).toBeTruthy();
  });

  it("aligns the default starter copy with the prototype", async () => {
    mockSubscribe();
    renderPanel(
      <IntelligencePanel open onClose={() => undefined}
        surface="rag_answer" ref_="fce-001" />,
    );
    expect(screen.getByText("Summarise this entity in 30 seconds.")).toBeTruthy();
    expect(screen.getByText("What is the most-asked question on a first call here?")).toBeTruthy();
    expect(screen.getByText("What's our differentiation against the incumbent?")).toBeTruthy();
  });
});

describe("WhyNowSignals accordion", () => {
  const SIGNAL = {
    label: "nCino core migration in flight",
    category: "core_migration",
    strength: "STRONG",
    window: "6–9 months",
    confidence: "HIGH",
    claim: "FACT",
    detail: "Migration completing Q2; data fragmentation across three cores.",
    metric: "5 Data Cloud Architect openings",
    peer_context: "Synovus closed the same gap in 9 months.",
    play: "Open the Data Cloud conversation before go-live.",
    risk: "Point-solution CDP commitment forecloses the substrate play.",
    impact: "Foundation window closes at go-live.",
    evidence: ["E-47", "E-89"],
    timeline: { date: "2026-04-01", event: "nCino go-live target" },
  };

  it("renders every deep field and opens evidence chips", () => {
    const onEvidence = vi.fn();
    render(<WhyNowSignals signals={[SIGNAL]} onEvidence={onEvidence} />);
    fireEvent.click(screen.getByText("nCino core migration in flight"));
    expect(screen.getByText("STRONG")).toBeTruthy();
    expect(screen.getByText(/HIGH confidence/)).toBeTruthy();
    expect(screen.getByText("FACT")).toBeTruthy();
    expect(screen.getByText(/5 Data Cloud Architect openings/)).toBeTruthy();
    expect(screen.getByText(/Migration completing Q2/)).toBeTruthy();
    expect(screen.getByText(/Synovus closed the same gap/)).toBeTruthy();
    expect(screen.getByText(/Open the Data Cloud conversation/)).toBeTruthy();
    expect(screen.getByText(/Point-solution CDP commitment/)).toBeTruthy();
    expect(screen.getByText(/Foundation window closes/)).toBeTruthy();
    expect(screen.getByText("2026-04-01")).toBeTruthy();
    expect(screen.getByText("6–9 months")).toBeTruthy();
    fireEvent.click(screen.getByText("E-47"));
    expect(onEvidence).toHaveBeenCalledWith("E-47");
  });

  it("renders defensively when deep fields are absent (pre-D1 data)", () => {
    render(
      <WhyNowSignals
        signals={[{ label: "Sparse signal" }]}
        onEvidence={() => undefined}
      />,
    );
    fireEvent.click(screen.getByText("Sparse signal"));
    // No evidence → honest inferred note; nothing crashes.
    expect(screen.getByText("Inferred — confirm in discovery")).toBeTruthy();
  });

  it("renders nothing for an empty signal list", () => {
    const { container } = render(
      <WhyNowSignals signals={[]} onEvidence={() => undefined} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("HeatmapPage synthesis drawer — no embedded auto-open panel", () => {
  // vitest cwd is the frontend package root.
  const heatmapSrc = readFileSync(
    resolve(process.cwd(), "src/pages/HeatmapPage.tsx"),
    "utf8",
  );

  it("no longer embeds an <IntelligencePanel> inside the SynthesisDrawer", () => {
    // The embedded `<IntelligencePanel open={!!data} onClose={noop}>`
    // auto-opened over every subcap drilldown and was un-dismissable.
    expect(heatmapSrc).not.toMatch(/<IntelligencePanel/);
    expect(heatmapSrc).not.toMatch(/from "@\/components\/IntelligencePanel"/);
  });

  it("offers the explicit ask button wired through the ui store instead", () => {
    expect(heatmapSrc).toContain("Ask AI about this subcap");
    expect(heatmapSrc).toMatch(
      /setIpSurface\("subcap_narrative", \{ ref: `\$\{displayId\}:\$\{subcapId\}` \}\);\s*setIpOpen\(true\);/,
    );
  });

  it("synthesis overlays layer on the app drawer scale, not above it", () => {
    expect(heatmapSrc).not.toMatch(/zIndex:\s*600/);
    expect(heatmapSrc).toMatch(/zIndex:\s*90/);
  });
});
