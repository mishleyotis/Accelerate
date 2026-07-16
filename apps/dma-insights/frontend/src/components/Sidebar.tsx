/**
 * Sidebar — ported 1:1 from the prototype (`standalone-src/src/chrome.jsx`
 * Sidebar component). Uses the BrandMark (icon_teal.png) — NOT the wide
 * wordmark — to match the prototype's dark sidebar head, plus the same
 * NavItem button pattern, icon set, sb-grp/sb-gl admin group structure,
 * Mishley O. avatar + role + sign-out footer.
 */
import { useAlerts, useDashboard } from "@/lib/queries";
import { useRoute } from "@/lib/hash-router";
import { logout as signOut } from "@/lib/auth";
import { useAuthStore, useEffectiveRole } from "@/store/auth";
import { useUiStore } from "@/store/ui";
import { Icon } from "@/components/utils";

interface NavItemProps {
  href: string;
  icon: string;
  label: string;
  badge?: number | null;
  dim?: boolean;
  dot?: boolean;
  active: boolean;
  onNav: (href: string) => void;
}

function NavItem({ href, icon, label, badge, dim, dot, active, onNav }: NavItemProps): JSX.Element {
  return (
    <button
      type="button"
      className={`sb-a ${active ? "on" : ""} ${dim ? "dim" : ""}`}
      onClick={() => { if (!dim) onNav(href); }}
      title={dim ? `${label} is not available for your role` : undefined}
    >
      <Icon name={icon} size={15} aria-hidden="true" />
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {label}
      </span>
      {badge != null && badge > 0 ? <span className="sb-badge">{badge}</span> : null}
      {dot ? <span className="sb-dot" /> : null}
    </button>
  );
}

export function Sidebar(): JSX.Element {
  const { user, setUser } = useAuthStore();
  const role = useEffectiveRole();
  const { path, navigate } = useRoute();
  const mobileNavOpen = useUiStore((s) => s.mobileNavOpen);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);
  // Navigating from the mobile drawer closes it (prototype behaviour).
  const navAndClose = (href: string): void => {
    setMobileNavOpen(false);
    navigate(href);
  };

  // Resolve active by longest-prefix match (mirrors prototype).
  const allHrefs = ["/", "/clients", "/alerts", "/prospecting", "/admin", "/admin/import", "/admin/import/audit"];
  const activeHref = (() => {
    if (path === "/") return "/";
    const matches = allHrefs.filter((h) => h !== "/" && (path === h || path.startsWith(h + "/")));
    return matches.length === 0 ? null : matches.sort((a, b) => b.length - a.length)[0];
  })();
  const isOn = (h: string) => h === activeHref;

  // Live counts: open alerts (for ANALYST/ADMIN) + active runs (dot on Clients).
  const alertsQ = useAlerts();
  const openAlerts = alertsQ.data?.open_count ?? 0;
  const dashQ = useDashboard("all");
  const activeRuns = dashQ.data?.active_runs?.length ?? 0;

  async function handleSignOut(): Promise<void> {
    try { await signOut(); } catch { /* ignore */ }
    setUser(null);
    navigate("/login");
  }

  return (
    <aside className={`sb${mobileNavOpen ? " open" : ""}`} aria-label="Primary navigation">
      <div className="sb-head">
        <img
          className="sb-logo"
          src="/brand/icon_teal.png"
          width={32}
          height={32}
          alt="Zennify"
          style={{ borderRadius: 7, display: "block", flexShrink: 0, objectFit: "cover" }}
        />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sb-brand">DMA Insights</div>
          <div className="sb-sub">Zennify</div>
        </div>
      </div>

      <nav className="sb-nav">
        <NavItem href="/" icon="home" label="Dashboard"
                 active={isOn("/")} onNav={navAndClose} />
        <NavItem href="/clients" icon="users" label="Clients"
                 active={isOn("/clients")} dot={activeRuns > 0} onNav={navAndClose} />
        <NavItem href="/alerts" icon="bell" label="Alerts"
                 active={isOn("/alerts")}
                 badge={role === "ANALYST" || role === "ADMIN" ? openAlerts : null}
                 dim={role === "AE"} onNav={navAndClose} />
        <NavItem href="/prospecting" icon="envelope" label="Prospecting"
                 active={isOn("/prospecting")} onNav={navAndClose} />

        {role === "ADMIN" ? (
          <div className="sb-grp">
            <div className="sb-gl">Admin</div>
            <NavItem href="/admin" icon="settings" label="Admin home"
                     active={isOn("/admin")} onNav={navAndClose} />
            <NavItem href="/admin/import" icon="drive" label="Import & jobs"
                     active={isOn("/admin/import")} onNav={navAndClose} />
            <NavItem href="/admin/import/audit" icon="evidence" label="Import audit"
                     active={isOn("/admin/import/audit")} onNav={navAndClose} />
          </div>
        ) : null}
      </nav>

      <div className="sb-foot">
        <div className="sb-avatar">
          {((user?.name ?? user?.email ?? "?")[0] ?? "?").toUpperCase()}
        </div>
        <div className="sb-foot-meta">
          <div className="sb-foot-name">{user?.name || user?.email || "—"}</div>
          <div className="sb-foot-role">{role}</div>
        </div>
        <button
          type="button"
          className="icon-btn"
          style={{ color: "rgba(255,255,255,.6)" }}
          title="Sign out"
          aria-label="Sign out"
          onClick={handleSignOut}
        >
          <Icon name="logout" size={14} />
        </button>
      </div>
    </aside>
  );
}
