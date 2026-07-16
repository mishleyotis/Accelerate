/**
 * TopBar breadcrumbs — wireframe header contract (chrome.jsx TopBar):
 * `Clients › {entity.name} › {Tab}` where the separator is the 12px
 * chevron-r SVG icon with class "sep" — NEVER a text glyph. The old
 * `<span class="sep"> / </span>` collided with the generic `.sep`
 * divider rule (height:1px + background) and rendered as solid grey
 * "⎮" boxes on every client page (2026-07-06 production screenshots).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { TopBar } from "@/components/TopBar";
import * as hashRouter from "@/lib/hash-router";
import * as queries from "@/lib/queries";

function withClient(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function mockRoute(path: string) {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path, query: {}, hash: path, navigate: vi.fn(), setQuery: vi.fn(),
  });
}

function mockOverviewName(name: string | null) {
  vi.spyOn(queries, "useEntityOverview").mockReturnValue({
    data: name ? { entity: { name } } : undefined,
    isLoading: false, isError: false, error: null,
  } as unknown as ReturnType<typeof queries.useEntityOverview>);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TopBar breadcrumbs (wireframe header)", () => {
  it("client pages: Clients › {entity name} › {Tab} with chevron SVG separators", () => {
    mockRoute("/clients/ibkr-0001/insights");
    mockOverviewName("Interactive Brokers Group, Inc.");
    const { container } = render(withClient(<TopBar audience="internal" />));
    const crumbs = container.querySelector(".topbar-crumbs")!;

    // Separators are SVG chevron icons with class "sep" — one between
    // each crumb pair, none after the last.
    const seps = crumbs.querySelectorAll("svg.sep");
    expect(seps.length).toBe(2);
    // No text glyph separators (the "⎮"/"/" regression class).
    expect(crumbs.textContent).not.toMatch(/[/|⎮‖]/);

    // Trail: link → link → current (entity NAME, never the slug).
    const links = crumbs.querySelectorAll("a");
    expect(links[0].textContent).toBe("Clients");
    expect(links[1].textContent).toBe("Interactive Brokers Group, Inc.");
    expect(crumbs.querySelector(".current")?.textContent).toBe("Insights");
  });

  it("techstack tab crumb renders the prototype casing 'Tech stack'", () => {
    mockRoute("/clients/ibkr-0001/techstack");
    mockOverviewName("Interactive Brokers Group, Inc.");
    const { container } = render(withClient(<TopBar audience="internal" />));
    expect(container.querySelector(".topbar-crumbs .current")?.textContent)
      .toBe("Tech stack");
  });

  it("global pages render a single crumb with no separator", () => {
    mockRoute("/clients");
    mockOverviewName(null);
    const { container } = render(withClient(<TopBar audience="internal" />));
    const crumbs = container.querySelector(".topbar-crumbs")!;
    expect(crumbs.querySelectorAll("svg.sep").length).toBe(0);
    expect(crumbs.textContent).toBe("Clients");
  });
});
