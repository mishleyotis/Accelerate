/**
 * SearchPopover — the TopBar ⌘K command palette, ported 1:1 from the
 * prototype `chrome.jsx` SearchPopover. Empty query shows static "Quick
 * links"; a real query (≥2 chars) calls `useSearch` and renders grouped
 * entity / insight / evidence hits, each routed to a real page.
 *
 * Keyboard contract (the prototype footer advertised it; this wires it):
 * ↑/↓ move the highlight, Enter opens the highlighted row, Esc closes.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useRoute } from "@/lib/hash-router";
import { useSearch, type SearchHit } from "@/lib/queries";
import { Icon } from "@/components/utils";

interface Row {
  kind?: SearchHit["kind"];
  title: string;
  sub: string;
  route: string;
  icon: string;
}

// Static destinations shown before the operator types (prototype parity).
const QUICK_LINKS: Row[] = [
  { title: "All clients", sub: "Browse directory", route: "/clients", icon: "grid" },
  { title: "Alerts", sub: "Thin-evidence alerts", route: "/alerts", icon: "bell" },
  { title: "Prospecting", sub: "Scorecard export", route: "/prospecting", icon: "envelope" },
  { title: "Dashboard", sub: "Recent runs + KPIs", route: "/", icon: "home" },
];

// Per-kind icon-chip tone, matching the prototype's result rows.
const KIND_TONE: Record<string, { bg: string; fg: string }> = {
  entity:   { bg: "var(--z-lav)",  fg: "var(--z-mid)" },
  insight:  { bg: "var(--z-ice)",  fg: "var(--z-mid)" },
  evidence: { bg: "var(--ph0-lt)", fg: "var(--z-dpur)" },
};

export function SearchPopover({ onClose }: { onClose: () => void }): JSX.Element {
  const { navigate } = useRoute();
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const term = q.trim();
  const showingQuickLinks = term.length < 2;

  const searchQ = useSearch(q);
  const results: SearchHit[] = searchQ.data?.results ?? [];
  const rows: Row[] = showingQuickLinks ? QUICK_LINKS : results;

  const [hi, setHi] = useState(0);
  // Reset the highlight whenever the visible list changes shape.
  useEffect(() => { setHi(0); }, [term, rows.length]);
  // Autofocus the palette input on open (prototype `autoFocus`).
  useEffect(() => { inputRef.current?.focus(); }, []);

  const go = (route: string): void => { navigate(route); onClose(); };

  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHi((i) => (rows.length ? Math.min(i + 1, rows.length - 1) : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const r = rows[hi];
      if (r) go(r.route);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  const hasQuery = term.length >= 2;
  const showEmpty = hasQuery && !searchQ.isLoading && results.length === 0;
  const headerLabel = useMemo(
    () => (showingQuickLinks ? "Quick links" : null),
    [showingQuickLinks],
  );

  return (
    <>
      <div className="popover-mask" onClick={onClose} />
      <div
        className="popover search-popover"
        role="dialog"
        aria-label="Search"
        style={{ top: 50, right: "auto", left: "50%", transform: "translateX(-50%)", width: 480, maxHeight: 520 }}
        onKeyDown={onKeyDown}
      >
        <div className="popover-head" style={{ padding: 0 }}>
          <div style={{ position: "relative", flex: 1, padding: "12px 14px" }}>
            <Icon name="search" size={14} style={{ position: "absolute", top: 16, left: 14, color: "var(--z-muted)" }} aria-hidden />
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search entities, insights (IC-XXX), evidence (E-XXX)…"
              aria-label="Search entities, insights, and evidence"
              style={{ width: "100%", padding: "6px 0 6px 26px", border: 0, outline: 0, fontSize: 14, background: "transparent" }}
            />
          </div>
          <button type="button" className="icon-btn" aria-label="Close search" onClick={onClose}>
            <Icon name="x" size={14} />
          </button>
        </div>

        <div className="popover-body" role="listbox" aria-label="Search results">
          {headerLabel ? (
            <div style={{ padding: "8px 14px", fontSize: 11, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".1em" }}>
              {headerLabel}
            </div>
          ) : null}

          {showEmpty ? (
            <div className="empty" style={{ padding: 20 }}>
              <h3 style={{ fontSize: 13 }}>No results</h3>
              <p style={{ fontSize: 11 }}>Try an entity name, IC-XXX, or E-XXX.</p>
            </div>
          ) : null}

          {rows.map((r, i) => {
            const tone = r.kind ? KIND_TONE[r.kind] : { bg: "var(--z-ice)", fg: "var(--z-mid)" };
            const active = i === hi;
            return (
              <button
                key={`${r.route}-${i}`}
                type="button"
                role="option"
                aria-selected={active}
                className={`popover-row${active ? " is-active" : ""}`}
                style={{ width: "100%", border: 0, textAlign: "left", background: active ? "var(--z-lav)" : "none" }}
                onMouseEnter={() => setHi(i)}
                onClick={() => go(r.route)}
              >
                <div className="icon-wrap" style={{ background: tone.bg, color: tone.fg }}>
                  <Icon name={r.icon} size={14} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="txt-fit-1" style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }}>{r.title}</div>
                  <div style={{ fontSize: 11, color: "var(--z-muted)" }}>{r.sub}</div>
                </div>
                {r.kind ? (
                  <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>{r.kind}</span>
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="popover-foot" style={{ justifyContent: "space-between" }}>
          <span className="muted" style={{ fontSize: 11 }}>↑ ↓ to navigate · enter to open</span>
          <span className="muted" style={{ fontSize: 11 }}>esc to close</span>
        </div>
      </div>
    </>
  );
}
