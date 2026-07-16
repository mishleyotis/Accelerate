/**
 * CustomizableKpiStrip (B-8) — the per-focus-area KPI editor the 2026-06
 * wireframe ships on the D3 focus-area surface.
 *
 * Each row is one KPI override (`focus_area_kpi_overrides` per migration
 * 025). Per the wireframe spec, the operator can:
 *   - Add a new override (label + source mode + current/target).
 *   - Cycle the source mode: public → client → hidden.
 *   - Inline-edit current/target values.
 * Writes go through `useSaveKpiOverrides` (idempotent UPSERT keyed by
 * entity_id + fa_id + kpi_label).
 *
 * The strip is read-only when the operator is in audience='customer'
 * mode (the wireframe hides it; we render a static summary so the page
 * doesn't shift).
 */
import { useState } from "react";
import {
  useFocusAreaKpis,
  useSaveKpiOverrides,
  type KpiOverrideInput,
  type KpiOverrideOut,
  type KpiSourceMode,
} from "@/lib/queries";
import { useUiStore } from "@/store/ui";

const SOURCE_NEXT: Record<KpiSourceMode, KpiSourceMode> = {
  public: "client",
  client: "hidden",
  hidden: "public",
};

const SOURCE_PILL: Record<KpiSourceMode, string> = {
  public: "pill-ice",
  client: "pill-teal",
  hidden: "pill-neutral",
};

interface Props {
  displayId: string;
  faId: string;
  faTitle: string;
  /** Derived KPI rows embedded on the focus_areas pack surface
   *  (FocusAreaOut.kpis, Part 6.1b) — render source while the live
   *  overrides query is loading/empty so the strip first-paints on a
   *  cold serve. Live override rows always win once present. */
  fallbackKpis?: Array<Record<string, unknown>>;
}

export function CustomizableKpiStrip({ displayId, faId, faTitle, fallbackKpis }: Props): JSX.Element {
  const { data, isLoading } = useFocusAreaKpis(displayId, faId);
  const save = useSaveKpiOverrides();
  const audience = useUiStore((s) => s.audience);
  const pushToast = useUiStore((s) => s.pushToast);
  const liveItems = data?.items ?? [];
  const items: KpiOverrideOut[] = liveItems.length > 0
    ? liveItems
    : (fallbackKpis ?? [])
        .map((k) => ({
          fa_id: faId,
          kpi_label: String(k.kpi_label ?? ""),
          source_mode: ((k.source_mode as KpiSourceMode) ?? "public"),
          current_value: (k.current_value as string | null) ?? null,
          target_value: (k.target_value as string | null) ?? null,
          updated_at: "",
        }))
        .filter((k) => k.kpi_label);

  const [draft, setDraft] = useState<KpiOverrideInput>({
    kpi_label: "",
    source_mode: "public",
    current_value: "",
    target_value: "",
  });

  async function persist(next: KpiOverrideInput[]): Promise<void> {
    try {
      await save.mutateAsync({ displayId, faId, overrides: next });
      pushToast("KPI override saved", "success");
    } catch (err) {
      pushToast(`Couldn't save: ${(err as Error).message}`, "error");
    }
  }

  function patchRow(idx: number, patch: Partial<KpiOverrideOut>): void {
    const next: KpiOverrideInput[] = items.map((r, i) => {
      const base: KpiOverrideInput = {
        kpi_label: r.kpi_label,
        source_mode: r.source_mode,
        current_value: r.current_value,
        target_value: r.target_value,
      };
      return i === idx ? { ...base, ...patch } : base;
    });
    void persist(next);
  }

  function addRow(e: React.FormEvent): void {
    e.preventDefault();
    if (!draft.kpi_label.trim()) return;
    const next: KpiOverrideInput[] = [
      ...items.map((r) => ({
        kpi_label: r.kpi_label,
        source_mode: r.source_mode,
        current_value: r.current_value,
        target_value: r.target_value,
      })),
      { ...draft, kpi_label: draft.kpi_label.trim() },
    ];
    void persist(next).then(() => {
      setDraft({ kpi_label: "", source_mode: "public", current_value: "", target_value: "" });
    });
  }

  if (audience === "customer") {
    // Customer-safe view: show labels + values where source_mode allows.
    if (items.length === 0) return <></>;
    const visible = items.filter((r) => r.source_mode !== "hidden");
    if (visible.length === 0) return <></>;
    return (
      <section className="card kpi-strip kpi-strip-customer" aria-label={`KPIs for ${faTitle}`}>
        <header className="card-head">
          <h4 className="card-title">KPIs</h4>
        </header>
        <ul className="kpi-list">
          {visible.map((r) => (
            <li key={r.kpi_label} className="kpi-row">
              <span className="kpi-label">{r.kpi_label}</span>
              <span className="kpi-cur">{r.current_value ?? "—"}</span>
              <span className="kpi-target">→ {r.target_value ?? "—"}</span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  return (
    <section className="card kpi-strip" aria-label={`Customise KPIs for ${faTitle}`}>
      <header className="card-head">
        <h4 className="card-title">KPI strip · customise</h4>
        <span className="muted small">{faTitle}</span>
      </header>
      {isLoading ? (
        <div className="muted small">Loading…</div>
      ) : items.length === 0 ? (
        <p className="muted small">No KPI overrides yet — add the first below.</p>
      ) : (
        <ul className="kpi-list">
          {items.map((r, idx) => (
            <li key={r.kpi_label} className="kpi-row">
              <span className="kpi-label">{r.kpi_label}</span>
              <input
                className="kpi-input"
                value={r.current_value ?? ""}
                placeholder="current"
                aria-label={`Current value for ${r.kpi_label}`}
                onChange={(e) => patchRow(idx, { current_value: e.target.value })}
              />
              <span aria-hidden="true">→</span>
              <input
                className="kpi-input"
                value={r.target_value ?? ""}
                placeholder="target"
                aria-label={`Target value for ${r.kpi_label}`}
                onChange={(e) => patchRow(idx, { target_value: e.target.value })}
              />
              <button
                type="button"
                className={`pill ${SOURCE_PILL[r.source_mode]} kpi-source`}
                aria-label={`Source: ${r.source_mode}, click to cycle`}
                onClick={() => patchRow(idx, { source_mode: SOURCE_NEXT[r.source_mode] })}
              >
                {r.source_mode}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="kpi-add-row" onSubmit={addRow}>
        <input
          className="kpi-input"
          placeholder="New KPI label"
          aria-label="New KPI label"
          value={draft.kpi_label}
          onChange={(e) => setDraft((d) => ({ ...d, kpi_label: e.target.value }))}
          required
          disabled={save.isPending}
        />
        <input
          className="kpi-input"
          placeholder="current"
          aria-label="Initial current value"
          value={draft.current_value ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, current_value: e.target.value }))}
          disabled={save.isPending}
        />
        <input
          className="kpi-input"
          placeholder="target"
          aria-label="Initial target value"
          value={draft.target_value ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, target_value: e.target.value }))}
          disabled={save.isPending}
        />
        <select
          aria-label="Source mode"
          value={draft.source_mode}
          onChange={(e) => setDraft((d) => ({ ...d, source_mode: e.target.value as KpiSourceMode }))}
          disabled={save.isPending}
        >
          <option value="public">public</option>
          <option value="client">client</option>
          <option value="hidden">hidden</option>
        </select>
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          disabled={save.isPending || !draft.kpi_label.trim()}
        >
          Add
        </button>
      </form>
    </section>
  );
}
