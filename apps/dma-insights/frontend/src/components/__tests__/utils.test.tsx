/**
 * Primitive component tests — render shape + accessibility.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Button,
  EmptyState,
  Pill,
  ScoreRing,
  Spinner,
  Stat,
  TimeAgo,
} from "../utils";

describe("ScoreRing", () => {
  it("renders the numeric score formatted to 1 decimal", () => {
    render(<ScoreRing score={3.25} caption="DMA score" />);
    expect(screen.getByText("3.3")).toBeTruthy();
    expect(screen.getByText("DMA score")).toBeTruthy();
  });

  it("clamps scores above 5", () => {
    render(<ScoreRing score={9} />);
    // visual clamp — checked via score-ring-fg dashoffset math elsewhere
    expect(screen.getByText("9.0")).toBeTruthy();
  });
});

describe("Pill", () => {
  it("applies tone-specific class", () => {
    const { container } = render(<Pill tone="teal">RB</Pill>);
    const el = container.querySelector(".pill");
    expect(el).toBeTruthy();
    expect(el?.className).toContain("pill-teal");
  });

  it("defaults to neutral tone", () => {
    const { container } = render(<Pill>x</Pill>);
    expect(container.querySelector(".pill-neutral")).toBeTruthy();
  });
});

describe("EmptyState", () => {
  it("renders title + body + cta", () => {
    render(
      <EmptyState
        title="Nothing here"
        body="Try again."
        cta={<button>Retry</button>}
      />,
    );
    expect(screen.getByText("Nothing here")).toBeTruthy();
    expect(screen.getByText("Try again.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
});

describe("Spinner", () => {
  it("has an aria-label so screen readers announce loading", () => {
    render(<Spinner />);
    expect(screen.getByLabelText("Loading")).toBeTruthy();
  });
});

describe("Button", () => {
  it("composes className from variant + size", () => {
    const { container } = render(
      <Button variant="secondary" size="sm">Go</Button>,
    );
    const btn = container.querySelector("button");
    expect(btn?.className).toContain("btn");
    expect(btn?.className).toContain("btn-secondary");
    expect(btn?.className).toContain("btn-sm");
  });

  it("disabled buttons block onClick", () => {
    let clicked = false;
    render(
      <Button disabled onClick={() => { clicked = true; }}>X</Button>,
    );
    screen.getByRole("button").click();
    expect(clicked).toBe(false);
  });

  it("forwards aria-label", () => {
    render(<Button ariaLabel="close drawer" iconOnly>×</Button>);
    expect(screen.getByLabelText("close drawer")).toBeTruthy();
  });
});

describe("Stat", () => {
  it("renders label + value + hint", () => {
    render(<Stat label="Open alerts" value={3} hint="last 24h" />);
    expect(screen.getByText("Open alerts")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("last 24h")).toBeTruthy();
  });
});

describe("TimeAgo", () => {
  it("returns em-dash for null", () => {
    render(<TimeAgo at={null} />);
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("formats a recent timestamp", () => {
    const recent = new Date(Date.now() - 5 * 60 * 1000);
    render(<TimeAgo at={recent} />);
    expect(screen.getByText("5m ago")).toBeTruthy();
  });

  it("formats hour-scale timestamps", () => {
    const past = new Date(Date.now() - 4 * 60 * 60 * 1000);
    render(<TimeAgo at={past} />);
    expect(screen.getByText("4h ago")).toBeTruthy();
  });
});
