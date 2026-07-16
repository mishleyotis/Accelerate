/**
 * Typed primitives — ported from `_prototype/utils.proto.tsx` with explicit
 * types and tighter contracts. Visual contract preserved via the matching
 * CSS class names in `styles/app.css`.
 */
import type { ReactNode, SVGProps } from "react";
import { maturityHex } from "@/lib/maturity";

// ---------- ScoreRing ----------

interface ScoreRingProps {
  score: number; // 0..5 (or null for empty)
  size?: number;
  thickness?: number;
  caption?: string;
}

export function ScoreRing({ score, size = 96, thickness = 8, caption }: ScoreRingProps) {
  const clamped = Math.max(0, Math.min(5, score));
  const pct = clamped / 5;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct);
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          className="ring-bg"
          cx={size / 2} cy={size / 2} r={radius}
          strokeWidth={thickness}
        />
        <circle
          className="ring-fg"
          cx={size / 2} cy={size / 2} r={radius}
          strokeWidth={thickness}
          stroke={maturityHex(score)}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className="num" style={{ color: maturityHex(score) }}>
        {score.toFixed(1)}
      </span>
      {caption ? <span className="sub">{caption}</span> : null}
    </div>
  );
}

// ---------- Pill ----------

export type PillTone = "neutral" | "teal" | "amber" | "red" | "green" | "ice";

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: PillTone }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

// ---------- EmptyState ----------

interface EmptyStateProps {
  title: string;
  body?: ReactNode;
  cta?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({ title, body, cta, icon }: EmptyStateProps) {
  return (
    <div className="empty">
      {icon ? <div className="icon">{icon}</div> : null}
      <h3>{title}</h3>
      {body ? <p>{body}</p> : null}
      {cta ?? null}
    </div>
  );
}

// ---------- Spinner ----------

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Loading">
      <circle cx="12" cy="12" r="10" fill="none"
        stroke="var(--z-teal)" strokeWidth="3" strokeLinecap="round"
        strokeDasharray="40 20">
        <animateTransform attributeName="transform" type="rotate"
          values="0 12 12;360 12 12" dur="0.9s" repeatCount="indefinite" />
      </circle>
    </svg>
  );
}

// ---------- Button ----------

export interface ButtonProps {
  children: ReactNode;
  variant?: "primary" | "secondary" | "tertiary" | "danger";
  size?: "default" | "sm" | "lg";
  iconOnly?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  ariaLabel?: string;
}

export function Button({
  children,
  variant = "primary",
  size = "default",
  iconOnly = false,
  disabled,
  onClick,
  type = "button",
  ariaLabel,
}: ButtonProps) {
  const classes = [
    "btn",
    `btn-${variant}`,
    size !== "default" ? `btn-${size}` : null,
    iconOnly ? "btn-icon" : null,
    disabled ? "btn-disabled" : null,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type={type}
      className={classes}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  );
}

// ---------- Stat ----------

interface StatProps {
  label: string;
  value: string | number;
  hint?: string;
  tone?: PillTone;
}

export function Stat({ label, value, hint, tone }: StatProps) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value}
        {tone ? <Pill tone={tone}>&nbsp;</Pill> : null}
      </div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

// ---------- TimeAgo ----------

export function TimeAgo({ at }: { at: string | Date | null | undefined }) {
  if (!at) return <span className="muted">—</span>;
  const date = typeof at === "string" ? new Date(at) : at;
  const ms = Date.now() - date.getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return <span>just now</span>;
  if (min < 60) return <span>{min}m ago</span>;
  const hr = Math.floor(min / 60);
  if (hr < 24) return <span>{hr}h ago</span>;
  const d = Math.floor(hr / 24);
  if (d < 30) return <span>{d}d ago</span>;
  return <span>{date.toLocaleDateString()}</span>;
}

// ---------- IconWrapper (lucide pass-through with sizing default) ----------

// Full 55-glyph registry ported verbatim from the 2026-06 prototype
// (docs/wireframe-2026-06 / _prototype/utils.proto.tsx). 1.8px round stroke,
// monochrome `currentColor`. This is the canonical icon set per the visual
// contract — no emoji anywhere (the heatmap cap marker uses the `lock` glyph).
export function Icon({
  name,
  size = 16,
  ...rest
}: { name: string; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  const props: SVGProps<SVGSVGElement> = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    ...rest,
  };
  switch (name) {
    case "home":      return <svg {...props}><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>;
    case "grid":      return <svg {...props}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
    case "bell":      return <svg {...props}><path d="M6 8a6 6 0 1 1 12 0c0 6 3 7 3 7H3s3-1 3-7"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>;
    case "search":    return <svg {...props}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>;
    case "user":      return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>;
    case "settings":  return <svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>;
    case "drive":     return <svg {...props}><path d="M6 4l-4 8 4 8h12l4-8-4-8H6z"/><path d="M6 4l8 16"/><path d="M18 4l-8 16"/><path d="M2 12h20"/></svg>;
    case "x":         return <svg {...props}><path d="M6 6l12 12M18 6L6 18"/></svg>;
    case "check":     return <svg {...props}><path d="M5 12l5 5L20 7"/></svg>;
    case "chevron-r": return <svg {...props}><path d="M9 6l6 6-6 6"/></svg>;
    case "chevron-l": return <svg {...props}><path d="M15 6l-6 6 6 6"/></svg>;
    case "chevron-d": return <svg {...props}><path d="M6 9l6 6 6-6"/></svg>;
    case "chevron-u": return <svg {...props}><path d="M6 15l6-6 6 6"/></svg>;
    case "arrow-r":   return <svg {...props}><path d="M5 12h14M13 6l6 6-6 6"/></svg>;
    case "arrow-up":  return <svg {...props}><path d="M12 19V5M6 11l6-6 6 6"/></svg>;
    case "arrow-dn":  return <svg {...props}><path d="M12 5v14M6 13l6 6 6-6"/></svg>;
    case "lock":      return <svg {...props}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>;
    case "external":  return <svg {...props}><path d="M14 4h6v6"/><path d="M20 4L10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>;
    case "filter":    return <svg {...props}><path d="M3 5h18l-7 8v7l-4-2v-5L3 5z"/></svg>;
    case "plus":      return <svg {...props}><path d="M12 5v14M5 12h14"/></svg>;
    case "minus":     return <svg {...props}><path d="M5 12h14"/></svg>;
    case "edit":      return <svg {...props}><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>;
    case "download":  return <svg {...props}><path d="M12 3v12"/><path d="M6 11l6 6 6-6"/><path d="M3 21h18"/></svg>;
    case "copy":      return <svg {...props}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>;
    case "warn":      return <svg {...props}><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><circle cx="12" cy="17" r=".5"/></svg>;
    case "info":      return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 8v.5"/><path d="M12 12v4"/></svg>;
    case "evidence":  return <svg {...props}><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>;
    case "ai":        return <svg {...props}><path d="M12 2l1.6 4.4L18 8l-4.4 1.6L12 14l-1.6-4.4L6 8l4.4-1.6L12 2z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/></svg>;
    case "menu":      return <svg {...props}><path d="M3 6h18M3 12h18M3 18h18"/></svg>;
    case "logout":    return <svg {...props}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>;
    case "platform":  return <svg {...props}><path d="M3 12l9-9 9 9-9 9z"/><path d="M3 12l9 4 9-4"/></svg>;
    case "heatmap":   return <svg {...props}><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="11" y="3" width="6" height="6" rx="1"/><rect x="3" y="11" width="6" height="6" rx="1"/><rect x="11" y="11" width="6" height="6" rx="1"/><rect x="19" y="3" width="2" height="6" rx="1"/><rect x="19" y="11" width="2" height="6" rx="1"/><rect x="3" y="19" width="6" height="2" rx="1"/><rect x="11" y="19" width="6" height="2" rx="1"/></svg>;
    case "insight":   return <svg {...props}><path d="M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2z"/><path d="M9 22h6"/></svg>;
    case "timeline":  return <svg {...props}><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="7" cy="6" r="1.4" fill="currentColor" stroke="none"/><circle cx="13" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="9" cy="18" r="1.4" fill="currentColor" stroke="none"/></svg>;
    case "shield":    return <svg {...props}><path d="M12 2l9 4v6c0 5-3.5 9-9 10-5.5-1-9-5-9-10V6l9-4z"/></svg>;
    case "stack":     return <svg {...props}><path d="M12 2l10 5-10 5L2 7l10-5z"/><path d="M2 12l10 5 10-5"/><path d="M2 17l10 5 10-5"/></svg>;
    case "drilldown": return <svg {...props}><path d="M3 3h18v18H3z"/><path d="M9 9h6v6H9z"/></svg>;
    case "users":     return <svg {...props}><circle cx="9" cy="8" r="3"/><path d="M3 21c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="6" r="2"/><path d="M16 11h.5c2.5 0 4.5 2 4.5 5"/></svg>;
    case "envelope":  return <svg {...props}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>;
    case "money":     return <svg {...props}><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M7 12h.01M17 12h.01"/></svg>;
    case "refresh":   return <svg {...props}><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>;
    case "scale":     return <svg {...props}><path d="M3 6h18"/><path d="M16 6l3 7a3 3 0 0 1-6 0l3-7zM8 6l3 7a3 3 0 0 1-6 0l3-7z"/><path d="M12 6v15M9 21h6"/></svg>;
    case "sparkle":   return <svg {...props}><path d="M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4L12 3z"/><path d="M19 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2zM5 16l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4z"/></svg>;
    case "calendar":  return <svg {...props}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>;
    case "linkedin":  return <svg {...props}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 11v6M8 7v.01M12 17v-4a2 2 0 1 1 4 0v4M12 17v-6"/></svg>;
    case "phone":     return <svg {...props}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>;
    case "doc":       return <svg {...props}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6M9 9h2"/></svg>;
    case "route":     return <svg {...props}><circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h6a4 4 0 0 0 0-8H10a4 4 0 0 1 0-8h6"/></svg>;
    case "building":  return <svg {...props}><rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/></svg>;
    case "stairs":    return <svg {...props}><path d="M3 19h4v-4h4v-4h4v-4h4V3"/></svg>;
    case "play":      return <svg {...props}><polygon points="6 4 20 12 6 20 6 4"/></svg>;
    case "globe":     return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>;
    case "share":     return <svg {...props}><circle cx="6" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 11l8-4M8 13l8 4"/></svg>;
    case "switch":    return <svg {...props}><path d="M7 8h14l-3-3M17 16H3l3 3"/></svg>;
    case "lightbulb": return <svg {...props}><path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c1 .9 1.5 2.2 1.5 3.5h5c0-1.3.5-2.6 1.5-3.5A6 6 0 0 0 12 3z"/></svg>;
    default:          return <svg {...props}><circle cx="12" cy="12" r="6"/></svg>;
  }
}

// ---------- FreshnessDot ----------
// Green < 7 days, amber 7–30 days, red > 30 days.
// Per UI/UX Brief §04 "per-section aging" spec.

type FreshnessLevel = "green" | "amber" | "red";

function freshnessLevel(dateStr: string | null | undefined): FreshnessLevel {
  if (!dateStr) return "red";
  const days = (Date.now() - new Date(dateStr).getTime()) / 86_400_000;
  if (days < 7) return "green";
  if (days <= 30) return "amber";
  return "red";
}

const FRESHNESS_COLOR: Record<FreshnessLevel, string> = {
  green: "var(--z-teal)",
  amber: "var(--m-bld)",
  red: "var(--z-below)",
};

const FRESHNESS_LABEL: Record<FreshnessLevel, string> = {
  green: "Fresh",
  amber: "Aging",
  red: "Stale",
};

export function FreshnessDot({
  at,
  withLabel = false,
}: {
  at: string | null | undefined;
  withLabel?: boolean;
}) {
  const level = freshnessLevel(at);
  const color = FRESHNESS_COLOR[level];
  return (
    <span
      className="freshness-dot"
      title={at ? `Last updated ${new Date(at).toLocaleDateString()}` : "No data date"}
      style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
    >
      <span
        role="img"
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
        aria-label={`Data freshness: ${FRESHNESS_LABEL[level]}`}
      />
      {withLabel ? (
        <span style={{ fontSize: 11, color: "var(--z-body)", fontWeight: 600 }}>
          {FRESHNESS_LABEL[level]}
        </span>
      ) : null}
    </span>
  );
}
