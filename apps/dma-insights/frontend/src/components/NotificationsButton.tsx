/**
 * NotificationsButton — TopBar bell with unseen-count badge + a popover
 * listing the most recent items. Reads `useNotifications()` (B-9); the
 * "Mark all read" action calls `useMarkNotificationsRead()` with an empty
 * id list (server clears every unseen row for the user).
 *
 * Per-kind tone (mirrors wireframe NotificationsPopover):
 *   alert      → red dot
 *   completion → teal dot
 *   system     → purple dot
 */
import { useEffect, useRef, useState } from "react";
import { useMarkNotificationsRead, useNotifications, type NotificationOut } from "@/lib/queries";
import { useRoute } from "@/lib/hash-router";
import { Icon } from "@/components/utils";

const KIND_TONE: Record<NotificationOut["kind"], string> = {
  alert: "pill-red",
  completion: "pill-teal",
  system: "pill-purple",
};

export function NotificationsButton(): JSX.Element {
  const { data, isError } = useNotifications();
  const markRead = useMarkNotificationsRead();
  const { navigate } = useRoute();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click + Escape — popover hygiene.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unseen = data?.unseen_count ?? 0;
  const items = data?.items ?? [];

  // Fail-soft: if the user isn't authenticated or the endpoint 401/500s,
  // hide the bell entirely so it doesn't ghost-error in the chrome.
  if (isError) return <></>;

  return (
    <div className="notifications" ref={containerRef}>
      <button
        type="button"
        className="btn btn-tertiary btn-icon notifications-trigger"
        aria-label={
          unseen > 0
            ? `Notifications · ${unseen} unread`
            : "Notifications"
        }
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" size={16} aria-hidden="true" />
        {unseen > 0 ? (
          <span className="badge b-org notifications-badge">{unseen}</span>
        ) : null}
      </button>
      {open ? (
        <div className="popover notifications-popover" role="dialog" aria-label="Notifications">
          <header className="popover-head">
            <strong>Notifications</strong>
            {unseen > 0 ? (
              <button
                type="button"
                className="btn btn-sm btn-tertiary"
                disabled={markRead.isPending}
                onClick={() => void markRead.mutateAsync({ ids: [] })}
              >
                Mark all read
              </button>
            ) : null}
          </header>
          {items.length === 0 ? (
            <div className="popover-body popover-empty muted">
              No notifications yet.
            </div>
          ) : (
            <ul className="popover-body" role="list">
              {items.slice(0, 20).map((n) => (
                <li
                  key={n.id}
                  className={`notification-row notification-${n.kind} ${n.seen_at ? "seen" : "unseen"}`}
                >
                  <button
                    type="button"
                    className="notification-action"
                    onClick={() => {
                      if (n.route) navigate(n.route);
                      setOpen(false);
                    }}
                  >
                    <span className={`pill ${KIND_TONE[n.kind] ?? "pill-neutral"}`}>
                      {n.kind}
                    </span>
                    <span className="notification-title">{n.title}</span>
                    {n.body ? (
                      <span className="notification-body">{n.body}</span>
                    ) : null}
                    <time className="notification-when">
                      {new Date(n.created_at).toLocaleString()}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <footer className="popover-foot">
            <button
              type="button"
              className="link-button"
              onClick={() => {
                navigate("/alerts");
                setOpen(false);
              }}
            >
              View all in alerts →
            </button>
          </footer>
        </div>
      ) : null}
    </div>
  );
}
