/**
 * Generic modal overlay — keyboard-trap + Escape close + backdrop click.
 *
 * Used by InsightModal, RecommendationModal, NewRunModal. Renders into a
 * portal at `#app` so it sits above the shell.
 */
import { useEffect, type ReactNode } from "react";
import { Icon } from "@/components/utils";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  size?: "default" | "wide";
  ariaLabel?: string;
  /** Optional `.modal-foot` slot rendered after the body, mirroring the
   *  prototype's `.modal` > head + body + foot structure (drawers.jsx). */
  footer?: ReactNode;
}

export function Modal({ open, onClose, title, children, size = "default", ariaLabel, footer }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="modal-mask"
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === "string" ? title : ariaLabel}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`modal modal-${size}`}>
        <header className="modal-head">
          <div className="modal-title">{title}</div>
          <button
            type="button"
            className="btn btn-tertiary btn-icon"
            onClick={onClose}
            aria-label="Close"
          ><Icon name="x" size={16} /></button>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>
  );
}
