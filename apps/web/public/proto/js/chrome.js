/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · App shell - Sidebar, TopBar, ClientShell, Banners
   ═══════════════════════════════════════════════════════════════════════ */

function Sidebar() {
  const {
    route,
    role,
    openAlerts,
    activeRuns,
    setAuthed,
    sidebarOpen,
    setSidebarOpen
  } = useApp();
  const path = route.path;
  const allHrefs = ["/", "/clients", "/alerts", "/prospecting", "/admin", "/admin/import", "/admin/import/audit"];
  const activeHref = (() => {
    if (path === "/") return "/";
    const matches = allHrefs.filter(h => h !== "/" && (path === h || path.startsWith(h + "/")));
    if (matches.length === 0) return null;
    // Pick longest (most specific)
    return matches.sort((a, b) => b.length - a.length)[0];
  })();
  const isOn = href => href === activeHref;
  const go = href => {
    setSidebarOpen(false);
    navigate(href);
  };
  const NavItem = ({
    href,
    icon,
    label,
    badge,
    dim,
    dot,
    indent
  }) => /*#__PURE__*/React.createElement("button", {
    className: `sb-a ${isOn(href) ? "on" : ""} ${dim ? "dim" : ""}`,
    onClick: () => !dim && go(href),
    style: indent ? {
      marginLeft: 12
    } : null
  }, icon ? /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 15
  }) : null, /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, label), badge != null && badge > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "sb-badge"
  }, badge) : null, dot ? /*#__PURE__*/React.createElement("span", {
    className: "sb-dot"
  }) : null);
  return /*#__PURE__*/React.createElement(React.Fragment, null, sidebarOpen ? /*#__PURE__*/React.createElement("div", {
    className: "sb-backdrop",
    onClick: () => setSidebarOpen(false)
  }) : null, /*#__PURE__*/React.createElement("aside", {
    className: `sb ${sidebarOpen ? "open" : ""}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-head"
  }, /*#__PURE__*/React.createElement(BrandMark, {
    size: 32
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-brand"
  }, "DMA Insights"), /*#__PURE__*/React.createElement("div", {
    className: "sb-sub"
  }, "Zennify")), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    style: {
      color: "rgba(255,255,255,.6)",
      display: "none"
    },
    onClick: () => setSidebarOpen(false),
    "aria-label": "Close menu"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 14
  }))), /*#__PURE__*/React.createElement("nav", {
    className: "sb-nav"
  }, /*#__PURE__*/React.createElement(NavItem, {
    href: "/",
    icon: "home",
    label: "Dashboard"
  }), /*#__PURE__*/React.createElement(NavItem, {
    href: "/clients",
    icon: "users",
    label: "Clients",
    dot: activeRuns > 0
  }), /*#__PURE__*/React.createElement(NavItem, {
    href: "/alerts",
    icon: "bell",
    label: "Alerts",
    badge: role === "ANALYST" || role === "ADMIN" ? openAlerts : null,
    dim: role === "AE"
  }), /*#__PURE__*/React.createElement(NavItem, {
    href: "/prospecting",
    icon: "envelope",
    label: "Prospecting"
  }), role === "ADMIN" ? /*#__PURE__*/React.createElement("div", {
    className: "sb-grp"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-gl"
  }, "Admin"), /*#__PURE__*/React.createElement(NavItem, {
    href: "/admin",
    icon: "settings",
    label: "Admin home"
  }), /*#__PURE__*/React.createElement(NavItem, {
    href: "/admin/import",
    icon: "drive",
    label: "Import & jobs"
  }), /*#__PURE__*/React.createElement(NavItem, {
    href: "/admin/import/audit",
    icon: "evidence",
    label: "Import audit"
  })) : null), /*#__PURE__*/React.createElement("div", {
    className: "sb-foot"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-avatar"
  }, sessionUser().initials), /*#__PURE__*/React.createElement("div", {
    className: "sb-foot-meta"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-foot-name"
  }, sessionUser().short), /*#__PURE__*/React.createElement("div", {
    className: "sb-foot-role"
  }, role)), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    style: {
      color: "rgba(255,255,255,.6)"
    },
    title: "Sign out",
    onClick: () => {
      setAuthed(false);
      signOutSession();
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "logout",
    size: 14
  })))));
}

/* ── Top bar (global) ─────────────────────────────────────────────── */
function TopBar({
  title,
  crumbs,
  right
}) {
  const {
    setSidebarOpen
  } = useApp();
  const [openPop, setOpenPop] = useState(null); // 'notif' | 'settings' | 'search' | null
  const [q, setQ] = useState("");
  const [showMobileSearch, setShowMobileSearch] = useState(false);

  // Quick search results
  const ql = q.toLowerCase().trim();
  const searchResults = useMemo(() => {
    if (!ql) return null;
    const entities = DMA.ENTITIES.filter(e => e.name.toLowerCase().includes(ql) || (e.domain || "").includes(ql)).slice(0, 4).map(e => ({
      kind: "entity",
      title: e.name,
      sub: DMA.SUBVERTICAL_LABEL[e.subvertical],
      route: `/clients/${e.id}/overview`,
      icon: "users"
    }));
    const insights = DMA.INSIGHT_CARDS.filter(c => c.title.toLowerCase().includes(ql) || c.id.toLowerCase().includes(ql)).slice(0, 3).map(c => ({
      kind: "insight",
      title: c.title,
      sub: `${c.id} · ${c.flag}`,
      route: `/clients/fce-001/insights?card=${c.id}`,
      icon: "insight"
    }));
    const evidence = DMA.EVIDENCE.filter(e => e.title.toLowerCase().includes(ql) || e.id.toLowerCase().includes(ql)).slice(0, 3).map(e => ({
      kind: "evidence",
      title: e.title,
      sub: `${e.id} · ${e.tier}`,
      route: `/clients/fce-001/insights?evidence=${e.id}`,
      icon: "evidence"
    }));
    return [...entities, ...insights, ...evidence];
  }, [ql]);

  // ⌘K shortcut
  useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpenPop("search");
      } else if (e.key === "Escape") setOpenPop(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const notifUnread = DMA.NOTIFICATIONS.filter((n, i) => i < 3).length;
  return /*#__PURE__*/React.createElement("header", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "sb-mobile-btn",
    onClick: () => setSidebarOpen(o => !o),
    "aria-label": "Menu",
    title: "Menu"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "menu",
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    className: "topbar-l"
  }, crumbs ? /*#__PURE__*/React.createElement("div", {
    className: "topbar-crumbs"
  }, crumbs.map((c, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: i
  }, c.href ? /*#__PURE__*/React.createElement("a", {
    href: `#${c.href}`
  }, c.label) : /*#__PURE__*/React.createElement("span", {
    className: i === crumbs.length - 1 ? "current" : ""
  }, c.label), i < crumbs.length - 1 ? /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-r",
    size: 12,
    className: "sep"
  }) : null))) : /*#__PURE__*/React.createElement("div", {
    className: "topbar-title"
  }, title)), /*#__PURE__*/React.createElement("div", {
    className: "topbar-r"
  }, /*#__PURE__*/React.createElement("div", {
    className: "topbar-search",
    onClick: () => setOpenPop("search")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 14
  }), /*#__PURE__*/React.createElement("input", {
    placeholder: "Search clients, evidence, IC-ID\u2026",
    value: openPop === "search" ? q : "",
    onChange: e => {
      setQ(e.target.value);
      setOpenPop("search");
    },
    onFocus: () => setOpenPop("search")
  }), /*#__PURE__*/React.createElement("kbd", null, "\u2318K")), right, /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: () => setOpenPop(o => o === "notif" ? null : "notif"),
    "aria-label": "Notifications"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 16
  }), notifUnread > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "dot"
  }) : null), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: () => setOpenPop(o => o === "settings" ? null : "settings"),
    "aria-label": "Settings"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "settings",
    size: 16
  }))), /*#__PURE__*/React.createElement(Portal, null, openPop ? /*#__PURE__*/React.createElement("div", {
    className: "popover-mask",
    onClick: () => setOpenPop(null)
  }) : null, openPop === "search" ? /*#__PURE__*/React.createElement(SearchPopover, {
    q: q,
    setQ: setQ,
    results: searchResults,
    onClose: () => setOpenPop(null)
  }) : null, openPop === "notif" ? /*#__PURE__*/React.createElement(NotificationsPopover, {
    onClose: () => setOpenPop(null)
  }) : null, openPop === "settings" ? /*#__PURE__*/React.createElement(SettingsPopover, {
    onClose: () => setOpenPop(null)
  }) : null));
}
function SearchPopover({
  q,
  setQ,
  results,
  onClose
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "popover",
    style: {
      top: 50,
      right: "auto",
      left: "50%",
      transform: "translateX(-50%)",
      width: 480,
      maxHeight: 520
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "popover-head",
    style: {
      padding: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      flex: 1,
      padding: "12px 14px"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 14,
    style: {
      position: "absolute",
      top: 16,
      left: 14,
      color: "var(--z-muted)"
    }
  }), /*#__PURE__*/React.createElement("input", {
    autoFocus: true,
    placeholder: "Search entities, insights (IC-XXX), evidence (E-XXX)\u2026",
    value: q,
    onChange: e => setQ(e.target.value),
    style: {
      width: "100%",
      padding: "6px 0 6px 26px",
      border: 0,
      outline: 0,
      fontSize: 14,
      background: "transparent"
    }
  })), /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 14
  }))), /*#__PURE__*/React.createElement("div", {
    className: "popover-body"
  }, !q.trim() ? /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "8px 14px",
      fontSize: 11,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".1em"
    }
  }, "Quick links") : null, !q.trim() ? [{
    title: "Farm Credit East",
    sub: "Farm Credit · CT, NY",
    route: "/clients/fce-001/overview",
    icon: "users"
  }, {
    title: "All clients",
    sub: "Browse directory",
    route: "/clients",
    icon: "grid"
  }, {
    title: "Alerts",
    sub: "Thin-evidence alerts",
    route: "/alerts",
    icon: "bell"
  }, {
    title: "Prospecting",
    sub: "Scorecard export",
    route: "/prospecting",
    icon: "envelope"
  }].map((r, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    className: "popover-row",
    style: {
      width: "100%",
      border: 0,
      background: "none",
      textAlign: "left"
    },
    onClick: () => {
      navigate(r.route);
      onClose();
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon-wrap",
    style: {
      background: "var(--z-ice)",
      color: "var(--z-mid)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: r.icon,
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, r.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, r.sub)))) : null, results && results.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty",
    style: {
      padding: 20
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 13
    }
  }, "No results"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 11
    }
  }, "Try an entity name, IC-XXX, or E-XXX.")) : null, results && results.length > 0 ? results.map((r, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    className: "popover-row",
    style: {
      width: "100%",
      border: 0,
      background: "none",
      textAlign: "left"
    },
    onClick: () => {
      navigate(r.route);
      onClose();
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon-wrap",
    style: {
      background: r.kind === "evidence" ? "var(--ph0-lt)" : r.kind === "insight" ? "var(--z-ice)" : "var(--z-lav)",
      color: r.kind === "evidence" ? "var(--z-dpur)" : "var(--z-mid)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: r.icon,
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)"
    },
    className: "txt-fit-1"
  }, r.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, r.sub)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".06em"
    }
  }, r.kind))) : null), /*#__PURE__*/React.createElement("div", {
    className: "popover-foot",
    style: {
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, "\u2191 \u2193 to navigate \xB7 enter to open"), /*#__PURE__*/React.createElement("span", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, "esc to close")));
}
function NotificationsPopover({
  onClose
}) {
  const {
    pushToast
  } = useApp();
  const ICONS = {
    alert: "bell",
    completion: "check",
    system: "info"
  };
  const COLORS = {
    alert: {
      bg: "rgba(254,151,50,.16)",
      c: "#7C3500"
    },
    completion: {
      bg: "var(--z-ice)",
      c: "var(--z-mid)"
    },
    system: {
      bg: "var(--z-lav)",
      c: "var(--z-dpur)"
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "popover"
  }, /*#__PURE__*/React.createElement("div", {
    className: "popover-head"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 14
  }), /*#__PURE__*/React.createElement("h4", null, "Notifications"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      pushToast("All notifications marked as read", "success");
      onClose();
    }
  }, "Mark all read")), /*#__PURE__*/React.createElement("div", {
    className: "popover-body"
  }, DMA.NOTIFICATIONS.map(n => {
    const C = COLORS[n.kind];
    return /*#__PURE__*/React.createElement("button", {
      key: n.id,
      className: "popover-row",
      style: {
        width: "100%",
        border: 0,
        background: "none",
        textAlign: "left"
      },
      onClick: () => {
        navigate(n.route);
        onClose();
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "icon-wrap",
      style: {
        background: C.bg,
        color: C.c
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: ICONS[n.kind],
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        fontWeight: 600,
        color: "var(--z-dark)"
      },
      className: "txt-fit-1"
    }, n.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      },
      className: "txt-fit-1"
    }, n.body)), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)",
        flexShrink: 0
      }
    }, n.when));
  })), /*#__PURE__*/React.createElement("div", {
    className: "popover-foot"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#/alerts",
    onClick: onClose,
    style: {
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "View all in alerts \u2192")));
}
function SettingsPopover({
  onClose
}) {
  const {
    role,
    setRole,
    audience,
    setAudience,
    setAuthed,
    grantedRole: granted,
    canActAs
  } = useApp();
  const items = [{
    label: "Profile",
    icon: "user",
    route: "/admin",
    sub: sessionUser().name
  }, {
    label: "Tweaks panel",
    icon: "settings",
    action: () => {
      try {
        window.parent.postMessage({
          type: "__activate_edit_mode"
        }, "*");
      } catch (e) {}
      ;
      window.dispatchEvent(new MessageEvent("message", {
        data: {
          type: "__activate_edit_mode"
        }
      }));
      onClose();
    },
    sub: "Toggle in-page tweaks"
  }, {
    label: "Sign out",
    icon: "logout",
    action: () => {
      setAuthed(false);
      signOutSession();
      onClose();
    },
    sub: "End session"
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "popover",
    style: {
      width: 280
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "popover-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sb-avatar",
    style: {
      width: 32,
      height: 32,
      fontSize: 11
    }
  }, sessionUser().initials), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, sessionUser().name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-mid)"
    }
  }, sessionUser().email))), canActAs ? /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "10px 14px",
      borderBottom: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".1em",
      color: "var(--z-muted)",
      textTransform: "uppercase",
      marginBottom: 6
    }
  }, "Acting as"), /*#__PURE__*/React.createElement("div", {
    className: "toggle-row",
    style: {
      width: "100%"
    }
  }, (() => {
    const RANK = {
      AE: 0,
      ANALYST: 1,
      ADMIN: 2
    };
    const cap = RANK[String(granted).toUpperCase()] ?? 0;
    return [["AE", "AE"], ["ANALYST", "Analyst"], ["ADMIN", "Admin"]].filter(([k]) => RANK[k] <= cap).map(([k, l]) => /*#__PURE__*/React.createElement("button", {
      key: k,
      className: role === k ? "on" : "",
      style: {
        flex: 1
      },
      onClick: () => {
        setRole(k);
        onClose();
      }
    }, l));
  })()), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 6
    }
  }, "Granted ", String(granted).toUpperCase(), " \xB7 the server answers for the view you pick, so a narrower view shows exactly what that role sees.")) : /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "10px 14px",
      borderBottom: "1px solid var(--z-sep)",
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, "Signed in as ", /*#__PURE__*/React.createElement("strong", {
    style: {
      color: "var(--z-dark)"
    }
  }, "AE"), " \u2014 the field view. Internal views are allow-listed."), /*#__PURE__*/React.createElement("div", {
    className: "popover-body",
    style: {
      padding: 0
    }
  }, items.map((it, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    className: "popover-row",
    style: {
      width: "100%",
      border: 0,
      background: "none",
      textAlign: "left"
    },
    onClick: () => {
      if (it.route) navigate(it.route);
      if (it.action) it.action();
      onClose();
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon-wrap",
    style: {
      background: "var(--z-lav)",
      color: "var(--z-dark2)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: it.icon,
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 500,
      color: "var(--z-dark)"
    }
  }, it.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, it.sub)), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-r",
    size: 12,
    style: {
      color: "var(--z-muted)"
    }
  })))));
}

/* ── Client bar (dark client-context strip + tabs) ──────────────── */
function ClientBar({
  entity,
  run,
  tab
}) {
  const {
    audience,
    setAudience,
    role
  } = useApp();
  const [runOpen, setRunOpen] = useState(false);
  const fresh = entity.assessment_date ? DMA.helpers.freshnessOf(entity.assessment_date) : null;
  const isSuperseded = run && run.status !== "ACTIVE" && !run.status.includes("IN_PROGRESS");
  const dsPill = run?.data_source === "DRIVE_PARSE" ? "pill-drive" : "pill-api";
  const TAB = (id, label, badge, icon) => /*#__PURE__*/React.createElement("button", {
    key: id,
    className: `client-tab ${tab === id ? "on" : ""}`,
    onClick: () => navigate(`/clients/${entity.id}/${id}`, run ? {
      run: run.id
    } : null)
  }, icon ? /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 13
  }) : null, /*#__PURE__*/React.createElement("span", null, label), badge ? /*#__PURE__*/React.createElement("span", {
    className: "count"
  }, badge) : null);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "client-bar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "icon-btn",
    style: {
      color: "rgba(255,255,255,.7)"
    },
    onClick: () => navigate("/clients"),
    title: "Back to directory"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-l",
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "name"
  }, entity.name), run ? /*#__PURE__*/React.createElement("span", {
    className: `pill pill-active`
  }, run.status.replace(/_/g, " ")) : null, run ? /*#__PURE__*/React.createElement("span", {
    className: `pill ${dsPill}`
  }, run.data_source === "DRIVE_PARSE" ? "DRIVE PARSE" : "PROJECT API") : null, fresh ? /*#__PURE__*/React.createElement("span", {
    className: `pill ${fresh.tone === "ok" ? "pill-fresh" : "pill-stale"}`
  }, "\u25CF ", fresh.label, " \xB7 ", fresh.months, " mo") : null), /*#__PURE__*/React.createElement("div", {
    className: "client-bar-r"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "run-selector",
    onClick: () => setRunOpen(o => !o)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "calendar",
    size: 12
  }), /*#__PURE__*/React.createElement("span", null, run ? `${fmtDate(run.date)} · ${run.overall ?? "-"}` : "Pick a run"), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-d",
    size: 12
  })), runOpen ? /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: "calc(100% + 6px)",
      right: 0,
      background: "#fff",
      border: "1px solid var(--z-sep)",
      borderRadius: 8,
      boxShadow: "var(--sh-lg)",
      padding: 6,
      zIndex: 92,
      minWidth: 320
    }
  }, entity.runs.map(r => /*#__PURE__*/React.createElement("button", {
    key: r.id,
    style: {
      display: "flex",
      width: "100%",
      padding: "8px 10px",
      borderRadius: 5,
      textAlign: "left",
      gap: 10,
      alignItems: "center",
      background: run?.id === r.id ? "var(--z-ice)" : "transparent",
      color: "var(--z-dark)"
    },
    onClick: () => {
      setRunOpen(false);
      navigate(`/clients/${entity.id}/${tab}`, {
        run: r.id
      });
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600
    }
  }, fmtDate(r.date), " \xB7 ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--z-teal)"
    }
  }, r.overall ?? "-")), /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, r.id)), /*#__PURE__*/React.createElement("span", {
    className: `b ${r.status === "ACTIVE" ? "b-teal" : "b-muted"}`
  }, r.status), /*#__PURE__*/React.createElement("span", {
    className: `b ${r.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`
  }, r.data_source === "DRIVE_PARSE" ? "DRIVE" : "API")))) : null), /*#__PURE__*/React.createElement("div", {
    className: `audience-toggle ${audience === "customer" ? "customer" : ""}`,
    title: "Internal view shows full team-prep data. Customer view strips fields that should not be screen-shared."
  }, /*#__PURE__*/React.createElement("button", {
    className: audience === "internal" ? "on" : "",
    onClick: () => setAudience("internal")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 11
  }), " Internal"), /*#__PURE__*/React.createElement("button", {
    className: audience === "customer" ? "on" : "",
    onClick: () => setAudience("customer")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 11
  }), " Customer")))), /*#__PURE__*/React.createElement("div", {
    className: "client-tabs"
  }, TAB("overview", "Overview", null, "home"), TAB("insights", "Insights", null, "insight"), TAB("heatmap", "Heatmap", null, "heatmap"), TAB("platform", "Platform", null, "platform"), audience !== "customer" ? TAB("context", "Context", null, "timeline") : null, TAB("techstack", "Tech stack", null, "stack"), (role === "ANALYST" || role === "ADMIN") && audience !== "customer" ? TAB("health", "Health", entity.open_alerts, "shield") : null, TAB("runs", "Runs", null, "refresh")), audience === "customer" ? /*#__PURE__*/React.createElement("div", {
    className: "customer-banner"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("strong", null, "Customer view"), " - share-safe presentation mode \xB7 evidence rationale, ERS, alert counts, and the Context tab are hidden"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      color: "#7C3500",
      whiteSpace: "nowrap",
      flexShrink: 0
    },
    onClick: () => setAudience("internal")
  }, "Switch back to Internal \u2192")) : null, isSuperseded ? /*#__PURE__*/React.createElement("div", {
    className: "superseded-banner"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "Viewing ", /*#__PURE__*/React.createElement("strong", null, fmtDate(run.date)), " run \xB7 ", /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, "SUPERSEDED"), ". The ACTIVE run is from ", fmtDate(entity.runs[0].date), "."), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate(`/clients/${entity.id}/${tab}`)
  }, "Return to active \u2192")) : null);
}

/* ── Page layout shells ──────────────────────────────────────────── */
function PageShell({
  title,
  crumbs,
  children,
  narrow,
  right
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "shell"
  }, /*#__PURE__*/React.createElement(Sidebar, null), /*#__PURE__*/React.createElement("div", {
    className: "main"
  }, /*#__PURE__*/React.createElement(TopBar, {
    title: title,
    crumbs: crumbs,
    right: right
  }), /*#__PURE__*/React.createElement("main", {
    className: `page ${narrow ? "page-narrow" : ""}`
  }, children)));
}
function ClientShell({
  entity,
  run,
  tab,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "shell"
  }, /*#__PURE__*/React.createElement(Sidebar, null), /*#__PURE__*/React.createElement("div", {
    className: "main"
  }, /*#__PURE__*/React.createElement(TopBar, {
    crumbs: [{
      label: "Clients",
      href: "/clients"
    }, {
      label: entity.name
    }, {
      label: tab[0].toUpperCase() + tab.slice(1).replace("stack", " stack")
    }]
  }), /*#__PURE__*/React.createElement(ClientBar, {
    entity: entity,
    run: run,
    tab: tab
  }), /*#__PURE__*/React.createElement("main", {
    className: "page"
  }, children)));
}
Object.assign(window, {
  Sidebar,
  TopBar,
  ClientBar,
  PageShell,
  ClientShell
});