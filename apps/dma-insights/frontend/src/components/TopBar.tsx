/**
 * TopBar — breadcrumbs (built from the current route) + search + actions.
 *
 * Matches `.topbar-*` CSS in app.css.
 */
import { Fragment, type CSSProperties, type ReactNode, useEffect } from "react";
import { nameFromSlug } from "@/lib/sanitize";
import { NotificationsButton } from "@/components/NotificationsButton";
import { SearchPopover } from "@/components/SearchPopover";
import { Icon } from "@/components/utils";
import { useRoute } from "@/lib/hash-router";
import { useUiStore } from "@/store/ui";
import { useEntityOverview } from "@/lib/queries";
import { useAuthStore } from "@/store/auth";
import { logout, type Role } from "@/lib/auth";

interface TopBarProps {
  title?: ReactNode;
  rightActions?: ReactNode;
  audience?: "internal" | "customer";
}

function defaultTitle(path: string): string {
  if (path === "/" || path === "") return "Dashboard";
  if (path.startsWith("/clients/")) return "Client";
  if (path === "/clients") return "Clients";
  if (path === "/alerts") return "Alerts";
  if (path === "/prospecting") return "Prospecting";
  if (path === "/admin") return "Admin";
  if (path.startsWith("/admin/")) return "Admin";
  return "DMA Insights";
}

export function TopBar({ title, rightActions, audience = "internal" }: TopBarProps) {
  const { path, navigate } = useRoute();
  const toggleMobileNav = useUiStore((s) => s.toggleMobileNav);
  const activePopover = useUiStore((s) => s.activePopover);
  const openPopover = useUiStore((s) => s.openPopover);
  const closePopover = useUiStore((s) => s.closePopover);
  // Prototype crumbs show the entity NAME ("Farm Credit East"), never
  // the prettified display_id slug ("Corporate america credit 0001").
  // Resolve via the same cached overview query ClientShell already
  // fetched (cache-hit; run-independent name).
  const segs = path.split("/").filter(Boolean);
  const clientId = segs[0] === "clients" && segs[1] ? segs[1] : null;
  const entityName = useEntityOverview(clientId).data?.entity?.name ?? null;
  // Prototype ClientShell crumbs (03_components_b.js:405):
  // Clients / {entity.name} / {Tab} — no Dashboard prefix, entity NAME
  // never the display_id slug.
  const crumbs = clientId
    ? [
        { href: "/clients", label: "Clients" },
        { href: `/clients/${clientId}/overview`, label: entityName ?? nameFromSlug(clientId) },
        ...(segs[2]
          ? [{ href: path, label: prettify(segs[2]).replace("Techstack", "Tech stack") }]
          : []),
      ]
    : buildCrumbs(path);
  const shownTitle = title ?? defaultTitle(path);

  // ⌘K / Ctrl-K opens the search palette (prototype shortcut); Esc closes
  // whatever popover is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPopover("search");
      } else if (e.key === "Escape") {
        closePopover();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPopover, closePopover]);

  return (
    <header className="topbar">
      <button
        type="button"
        className="sb-mobile-btn"
        aria-label="Open navigation menu"
        onClick={toggleMobileNav}
      >
        <Icon name="menu" size={20} />
      </button>
      <div className="topbar-l">
        <div className="topbar-crumbs">
          {crumbs.map((crumb, idx) => {
            const isLast = idx === crumbs.length - 1;
            // Key must include the index: on the Overview tab the entity
            // crumb and the tab crumb share the SAME href, and duplicate
            // React keys made the list splice stale labels from the
            // previously-visited entity into the trail (2026-06-10
            // click-through: "Clients · Langley · Interactive Brokers ·
            // Langley · Overview").
            //
            // Structure mirrors the wireframe TopBar (chrome.jsx): link/
            // current-label per crumb, then a 12px chevron-r icon with
            // class "sep" AFTER every non-last crumb — never a text
            // glyph (the old `<span class="sep"> / </span>` collided
            // with the generic `.sep` divider rule and rendered as grey
            // "⎮" boxes in production, 2026-07-06).
            return (
              <Fragment key={`${idx}-${crumb.href}`}>
                {isLast ? (
                  <span className="current">{crumb.label}</span>
                ) : (
                  <a href={`#${crumb.href}`} onClick={(e) => {
                    e.preventDefault();
                    navigate(crumb.href);
                  }}>{crumb.label}</a>
                )}
                {!isLast ? <Icon name="chevron-r" size={12} className="sep" /> : null}
              </Fragment>
            );
          })}
        </div>
        {crumbs.length === 0 ? (
          <div className="topbar-title">{shownTitle}</div>
        ) : null}
      </div>
      <div className="topbar-r">
        <button
          type="button"
          className="topbar-search"
          aria-label="Search"
          aria-haspopup="dialog"
          aria-expanded={activePopover === "search"}
          onClick={() => openPopover("search")}
        >
          <Icon name="search" size={14} />
          <span className="topbar-search-placeholder">Search clients, evidence, IC-ID…</span>
          <kbd>⌘K</kbd>
        </button>
        {activePopover === "search" ? <SearchPopover onClose={closePopover} /> : null}
        {rightActions}
        <NotificationsButton />
        <button
          type="button"
          className="icon-btn"
          aria-label="Settings"
          aria-haspopup="dialog"
          aria-expanded={activePopover === "settings"}
          onClick={() => (activePopover === "settings" ? closePopover() : openPopover("settings"))}
        >
          <Icon name="settings" size={16} />
        </button>
        {activePopover === "settings" ? <SettingsPopover onClose={closePopover} /> : null}
      </div>
    </header>
  );
}

/**
 * Settings popover — ported from the wireframe (03_components_b.js:250):
 * avatar + name + email head, the ACTING-AS segmented control (downgrade-
 * only via the store), then the Profile / Tweaks panel / Sign out rows.
 * Every row is functional: Profile → /admin, Tweaks → the real audience
 * (internal/customer) display toggle, Sign out → logout + /login.
 */
function SettingsPopover({ onClose }: { onClose: () => void }): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const actingAs = useAuthStore((s) => s.actingAs);
  const setActingAs = useAuthStore((s) => s.setActingAs);
  const audience = useUiStore((s) => s.audience);
  const setAudience = useUiStore((s) => s.setAudience);
  const { navigate } = useRoute();
  const roles = (user?.can_act_as ?? [user?.role].filter(Boolean)) as Role[];
  const initials = (user?.name ?? user?.email ?? "?")
    .split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  async function signOut(): Promise<void> {
    try { await logout(); } finally { onClose(); navigate("/login"); }
  }

  return (
    <>
      <div className="popover-mask" onClick={onClose} />
      <div className="popover" style={{ top: 50, right: 12, width: 280 }} role="menu">
        <div className="popover-head">
          <div className="sb-avatar" style={{ width: 32, height: 32, fontSize: 11 }}>{initials}</div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--z-dark)" }} className="txt-trunc">
              {user?.name ?? "—"}
            </div>
            <div style={{ fontSize: 11, color: "var(--z-muted)" }} className="txt-trunc">
              {user?.email ?? ""}
            </div>
          </div>
        </div>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--z-sep)" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Acting as</div>
          <div className="toggle-row" role="group" aria-label="Acting as role">
            {roles.map((r) => (
              <button
                key={r}
                type="button"
                className={(actingAs ?? user?.role) === r ? "on" : ""}
                onClick={() => setActingAs(r === user?.role ? null : r)}
              >
                {r}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--z-muted)", marginTop: 10 }}>
            Role is downgrade-only — the server re-checks every request.
          </div>
        </div>
        <div className="popover-body" style={{ padding: "6px 0" }}>
          <button type="button" className="popover-row" role="menuitem" style={popoverRowBtn}
                  onClick={() => { navigate("/admin"); onClose(); }}>
            <span className="icon-wrap" style={{ background: "var(--z-lav)" }}><Icon name="user" size={14} /></span>
            <span style={{ flex: 1 }}>
              <span style={{ display: "block", fontSize: 13, fontWeight: 500 }}>Profile</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>{user?.name ?? "Account"}</span>
            </span>
          </button>
          <button type="button" className="popover-row" role="menuitem" style={popoverRowBtn}
                  onClick={() => setAudience(audience === "internal" ? "customer" : "internal")}>
            <span className="icon-wrap" style={{ background: "var(--z-lav)" }}><Icon name="settings" size={14} /></span>
            <span style={{ flex: 1 }}>
              <span style={{ display: "block", fontSize: 13, fontWeight: 500 }}>Tweaks panel</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>Display: {audience} view</span>
            </span>
            <span className={`switch ${audience === "customer" ? "on" : ""}`} aria-hidden />
          </button>
          <button type="button" className="popover-row" role="menuitem" style={popoverRowBtn} onClick={signOut}>
            <span className="icon-wrap" style={{ background: "rgba(194,80,8,.12)", color: "var(--z-below)" }}><Icon name="logout" size={14} /></span>
            <span style={{ flex: 1 }}>
              <span style={{ display: "block", fontSize: 13, fontWeight: 500 }}>Sign out</span>
              <span style={{ fontSize: 11, color: "var(--z-muted)" }}>End session</span>
            </span>
          </button>
        </div>
      </div>
    </>
  );
}

const popoverRowBtn: CSSProperties = {
  width: "100%", border: 0, background: "none", textAlign: "left", alignItems: "center",
};

const GLOBAL_CRUMB: Record<string, string> = {
  "": "Home",
  clients: "Clients",
  alerts: "Alerts",
  prospecting: "Prospecting",
  admin: "Admin",
};

function buildCrumbs(path: string): Array<{ href: string; label: string }> {
  const segments = path.split("/").filter(Boolean);
  // Prototype PageShell: ONE crumb per global page (Home / Clients /
  // Alerts / Prospecting / Admin) — no Dashboard-prefixed trail.
  const head = segments[0] ?? "";
  if (head in GLOBAL_CRUMB && segments.length <= 1) {
    return [{ href: "/" + head, label: GLOBAL_CRUMB[head] }];
  }
  // Nested non-client routes (e.g. /admin/import/audit) keep a short
  // trail rooted at their section.
  const acc: Array<{ href: string; label: string }> = [];
  let running = "";
  for (const seg of segments) {
    running += "/" + seg;
    acc.push({ href: running, label: GLOBAL_CRUMB[seg] ?? prettify(seg) });
  }
  return acc.length > 0 ? acc : [{ href: "/", label: "Home" }];
}

function prettify(segment: string): string {
  return segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, " ");
}
