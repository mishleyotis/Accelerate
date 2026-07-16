/**
 * Modal — keyboard + accessibility + close affordances.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "../Modal";

describe("Modal", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <Modal open={false} onClose={() => undefined} title="Hi">body</Modal>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders title and children when open", () => {
    render(
      <Modal open onClose={() => undefined} title="Hello">
        <p>body content</p>
      </Modal>,
    );
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("body content")).toBeTruthy();
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="x">y</Modal>);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(<Modal open onClose={onClose} title="x">y</Modal>);
    const backdrop = container.querySelector(".modal-mask") as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close when the inner modal panel is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(<Modal open onClose={onClose} title="x">y</Modal>);
    const panel = container.querySelector(".modal") as HTMLElement;
    fireEvent.click(panel);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("exposes role=dialog and aria-modal=true", () => {
    render(<Modal open onClose={() => undefined} title="Title">body</Modal>);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("Title");
  });

  it("close button has accessible label", () => {
    render(<Modal open onClose={() => undefined} title="x">y</Modal>);
    expect(screen.getByLabelText("Close")).toBeTruthy();
  });
});
