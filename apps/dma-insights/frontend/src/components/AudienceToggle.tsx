/**
 * AudienceToggle — the prototype's Internal | Customer segmented
 * control (03_components_b.js ClientBar, `.audience-toggle`).
 *
 * Wired to the UI store; persisted to localStorage so the toggle
 * sticks across reloads. The frontend hide is *defense-in-depth*; the
 * backend's audience_strip is the source of truth (see ADR 0006).
 *
 * Lives in the ClientBar's right rail (the prototype's TopBar carries
 * NO audience control — the 2026-06-10 chrome audit found the old
 * "Customer view" tertiary button rendered ghosted/unreadable on the
 * dark bar and duplicated across both bars).
 */
import { useUiStore } from "@/store/ui";
import { Icon } from "@/components/utils";

export function AudienceToggle() {
  const { audience, setAudience } = useUiStore();
  return (
    <div
      className={`audience-toggle ${audience === "customer" ? "customer" : ""}`}
      title="Internal view shows full team-prep data. Customer view strips fields that should not be screen-shared."
    >
      <button
        type="button"
        className={audience === "internal" ? "on" : ""}
        onClick={() => setAudience("internal")}
      >
        <Icon name="lock" size={11} /> <span>Internal</span>
      </button>
      <button
        type="button"
        className={audience === "customer" ? "on" : ""}
        onClick={() => setAudience("customer")}
      >
        <Icon name="users" size={11} /> <span>Customer</span>
      </button>
    </div>
  );
}
