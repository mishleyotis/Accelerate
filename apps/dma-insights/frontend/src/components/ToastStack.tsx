/**
 * ToastStack — global toast queue host. Toasts are pushed via
 * `useUiStore.getState().pushToast(text, kind)` from anywhere; auto-dismiss
 * fires from the store after 4.2s.
 */
import { useUiStore } from "@/store/ui";

export function ToastStack(): JSX.Element | null {
  const toasts = useUiStore((s) => s.toasts);
  const dismiss = useUiStore((s) => s.dismissToast);
  if (toasts.length === 0) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast-${t.kind}`}
          onClick={() => dismiss(t.id)}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
