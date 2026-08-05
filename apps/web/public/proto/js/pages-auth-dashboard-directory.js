/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Login + Dashboard home + Entity directory
   Sections 19, 20, 21 of the UI/UX brief.
   ═══════════════════════════════════════════════════════════════════════ */

/* ── /login (s19) ─────────────────────────────────────────────────── */
function LoginPage() {
  const {
    setRole,
    setAuthed
  } = useApp();
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | verifying | granting
  const [email, setEmail] = useState("");

  // Production: identity comes from the Google sign-in IAP performed at
  // the door — /api/signin reads the VERIFIED assertion and mints the
  // app session; nothing typed here is ever trusted. The email input
  // renders only when the server says dev-login is on (local compose).
  const devLogin = !!(window.DMA_LIVE && window.DMA_LIVE.dev_login);
  const signIn = async () => {
    const e = email.trim().toLowerCase();
    if (devLogin && !e) {
      setErr("Enter your @zennify.com email to sign in.");
      return;
    }
    setLoading(true);
    setErr(null);
    setPhase("verifying");
    try {
      const r = await fetch("/api/signin", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(devLogin ? {
          email: e
        } : {})
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setLoading(false);
        setPhase("idle");
        setErr(body.error || "Sign-in failed. Please use your Zennify Google account.");
        return;
      }
      setPhase("granting");
      // Full reload: the server re-renders DMA_LIVE with the verified
      // identity and fresh directory data — the SPA never renders a
      // session it only half-knows about.
      window.location.assign("/");
    } catch (ex) {
      setLoading(false);
      setPhase("idle");
      setErr("Could not reach the sign-in service. Try again.");
    }
  };
  if (phase === "verifying" || phase === "granting") {
    return /*#__PURE__*/React.createElement(LoadingScreen, {
      variant: "auth",
      dark: true,
      title: phase === "verifying" ? "Verifying with Google…" : "Setting up your workspace…",
      body: phase === "verifying" ? "Checking your Zennify account and OAuth scopes." : "Loading your role, alerts, and recent runs.",
      detail: phase === "verifying" ? "Google OAuth · @zennify.com domain check" : "Hydrating session · 1 of 3 caches loaded"
    });
  }
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: "100vh",
      display: "grid",
      gridTemplateColumns: "minmax(420px, 1fr) minmax(0, 1.1fr)",
      background: "var(--z-bg)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      padding: "40px 56px",
      maxWidth: 560,
      width: "100%",
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 36
    }
  }, /*#__PURE__*/React.createElement(ZennifyWordmark, {
    height: 28,
    color: "dark"
  })), /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      marginBottom: 8
    }
  }, "DMA Insights"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 30,
      fontWeight: 600,
      color: "var(--z-dark)",
      letterSpacing: "-.02em",
      lineHeight: 1.15,
      marginBottom: 12
    }
  }, "The DMA, made navigable."), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14,
      color: "var(--z-body)",
      lineHeight: 1.6,
      marginBottom: 28,
      maxWidth: 440
    }
  }, "Sign in to explore every assessment, drill into the evidence, and lead with the platform conversation your client needs to hear."), devLogin ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("label", {
    className: "inp-label",
    htmlFor: "signin-email",
    style: {
      display: "block",
      fontSize: 12,
      fontWeight: 600,
      color: "var(--z-dark)",
      marginBottom: 6
    }
  }, "Work email (dev gate)"), /*#__PURE__*/React.createElement("input", {
    id: "signin-email",
    className: "inp",
    type: "email",
    placeholder: "you@zennify.com",
    value: email,
    onChange: e => setEmail(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter") signIn();
    },
    style: {
      width: "100%",
      marginBottom: 10
    },
    autoFocus: true
  })) : null, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    disabled: loading,
    onClick: () => signIn(),
    style: {
      width: "100%",
      padding: "12px",
      fontSize: 14,
      justifyContent: "center",
      marginBottom: 10,
      gap: 10
    }
  }, loading ? "Verifying…" : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 48 48",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    fill: "#FFC107",
    d: "M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#FF3D00",
    d: "m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#4CAF50",
    d: "M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
  }), /*#__PURE__*/React.createElement("path", {
    fill: "#1976D2",
    d: "M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 40.4 44 35 44 24c0-1.3-.1-2.6-.4-3.9z"
  })), "Continue with Google")), /*#__PURE__*/React.createElement("div", {
    className: "inp-help",
    style: {
      marginBottom: 12
    }
  }, "Google sign-in \xB7 @zennify.com accounts only (enforced server-side) \xB7 session expires after 8 hours"), err ? /*#__PURE__*/React.createElement("div", {
    className: "co co-auth",
    style: {
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 14
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "co-title"
  }, "Domain restricted"), /*#__PURE__*/React.createElement("div", {
    className: "co-body"
  }, err))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--z-lav)",
      padding: 12,
      borderRadius: 8,
      fontSize: 11.5,
      color: "var(--z-body)",
      display: "flex",
      gap: 8,
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 13,
    style: {
      color: "var(--z-mid)",
      flexShrink: 0,
      marginTop: 1
    }
  }), /*#__PURE__*/React.createElement("span", null, "Your role is detected automatically from your Zennify Google account. You can switch roles any time from the account menu.")), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: "auto",
      paddingTop: 56,
      fontSize: 11,
      color: "var(--z-muted)",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\xA9 2026 Zennify \xB7 Confidential"), /*#__PURE__*/React.createElement("span", null, "Confidential"))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      background: "linear-gradient(135deg, var(--z-dark2), var(--z-dark) 60%, var(--z-navy))",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("illo_pavilion", "brand/illustrations/pavilion_zennify_branded.jpg"),
    alt: "",
    style: {
      position: "absolute",
      inset: 0,
      width: "100%",
      height: "100%",
      objectFit: "cover",
      opacity: .92
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      background: "linear-gradient(135deg, rgba(28,74,77,.45), rgba(0,30,72,.55))"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      zIndex: 2,
      height: "100%",
      display: "flex",
      flexDirection: "column",
      padding: "44px 56px",
      color: "#fff"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 28
    }
  }, /*#__PURE__*/React.createElement(BrandMark, {
    size: 36
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600
    }
  }, "DMA Insights"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-mint-lt)"
    }
  }, "by Zennify"))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "rgba(0,30,72,.55)",
      backdropFilter: "blur(10px)",
      border: "1px solid rgba(255,255,255,.10)",
      borderRadius: 14,
      padding: "20px 22px",
      maxWidth: 460
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow",
    style: {
      color: "var(--z-mint-lt)",
      marginBottom: 8
    }
  }, "What you'll find inside"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, [{
    icon: "heatmap",
    label: "4-level maturity heatmap",
    sub: "Pillar → Category → Capability → Subcap · 708 cells per run"
  }, {
    icon: "insight",
    label: "Insight cards · WHAT/WHY/SO WHAT",
    sub: "Annotated · evidence-linked · platform-tagged"
  }, {
    icon: "platform",
    label: "Platform opportunity matrix",
    sub: "Fit Score per platform · readiness prerequisites · conversation starters"
  }, {
    icon: "timeline",
    label: "Why now signals + roadmap",
    sub: "Triggers from the timeline · 3-phase transformation plan"
  }].map(p => /*#__PURE__*/React.createElement("div", {
    key: p.icon,
    className: "row"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 32,
      height: 32,
      borderRadius: 8,
      background: "rgba(39,187,175,.18)",
      color: "var(--z-mint)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: p.icon,
    size: 15
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "#fff"
    }
  }, p.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-mint-lt)"
    }
  }, p.sub)))))))));
}

/* ── / Dashboard home (s20) ──────────────────────────────────────── */
function DashboardHome() {
  const {
    role,
    openAlerts,
    audience,
    openNewRun
  } = useApp();
  const ent = DMA.ENTITIES;
  const active = ent.filter(e => e.in_progress);
  const recent = ent.filter(e => !e.in_progress).slice().sort((a, b) => new Date(b.assessment_date) - new Date(a.assessment_date));
  const stale = ent.filter(e => e.assessment_date && DMA.helpers.freshnessOf(e.assessment_date).tone !== "ok").slice(0, 3);
  const totalAlerts = DMA.ALERTS.filter(a => a.status === "OPEN").length;
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Dashboard",
    crumbs: [{
      label: "Home"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Command centre"), /*#__PURE__*/React.createElement("h1", null, (h => h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening")(new Date().getHours()), ", ", sessionUser().first), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, ent.length, " entities \xB7 ", totalAlerts, " open alerts \xB7 ", active.length, " run", active.length === 1 ? "" : "s", " in progress")), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary",
    onClick: () => navigate("/admin")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), " Re-scan Drive"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: openNewRun
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), " New run"))), /*#__PURE__*/React.createElement("div", {
    className: "g4",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(KpiCard, {
    label: "Active assessments",
    value: ent.filter(e => !e.in_progress).length,
    sub: "all subverticals",
    icon: "users",
    accent: "var(--z-teal)"
  }), /*#__PURE__*/React.createElement(KpiCard, {
    label: "Open alerts",
    value: totalAlerts,
    sub: "thin-evidence",
    icon: "bell",
    accent: "var(--z-org)"
  }), /*#__PURE__*/React.createElement(KpiCard, {
    label: "Insight cards",
    value: DMA.INSIGHT_CARDS.length * ent.length / 7,
    sub: "across all runs",
    icon: "insight",
    accent: "var(--z-mid)",
    rounding: true
  }), (() => {
    const scored = ent.filter(e => e.overall);
    const avg = scored.length ? scored.reduce((a, e) => a + e.overall, 0) / scored.length : null;
    return /*#__PURE__*/React.createElement(KpiCard, {
      label: "Avg maturity",
      value: avg == null ? "—" : avg.toFixed(1),
      sub: avg == null ? "no promoted runs yet" : DMA.helpers.maturityLabel(avg),
      icon: "heatmap",
      accent: "var(--z-dpur)"
    });
  })()), active.length > 0 ? /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 14,
    style: {
      color: "var(--z-mid)"
    }
  }), /*#__PURE__*/React.createElement("h3", null, "Active runs"), /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, "SSE LIVE")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, active.length, " in progress")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16
    }
  }, active.map(e => {
    const r = e.runs[0];
    return /*#__PURE__*/React.createElement("div", {
      key: e.id,
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 280px",
        gap: 18,
        alignItems: "center",
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        marginBottom: 6
      }
    }, /*#__PURE__*/React.createElement("strong", {
      style: {
        fontSize: 14
      }
    }, e.name), /*#__PURE__*/React.createElement("span", {
      className: "b b-muted"
    }, DMA.SUBVERTICAL_LABEL[e.subvertical]), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--z-muted)"
      }
    }, "Batch ", r.current_batch, " / 6 \xB7 ", r.status.replace(/_/g, " ").toLowerCase())), /*#__PURE__*/React.createElement("div", {
      className: "batch-row"
    }, ["Setup", "Evidence", "Peers", "Scoring", "Analysis", "Final"].map((b, i) => /*#__PURE__*/React.createElement("div", {
      key: b,
      className: `batch-pill ${i + 1 < r.current_batch ? "done" : i + 1 === r.current_batch ? "active" : ""}`
    }, i + 1)))), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-secondary btn-sm",
      onClick: () => navigate(`/clients/${e.id}/overview`)
    }, "Open ", /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-r",
      size: 11
    })));
  }))) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: role === "AE" ? "1fr" : "1fr 320px",
      gap: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "users",
    size: 15
  }), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      margin: 0
    }
  }, "Recent assessments"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("a", {
    href: "#/clients",
    style: {
      fontSize: 11,
      color: "var(--z-mid)",
      fontWeight: 600
    }
  }, "View all \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "g2"
  }, recent.slice(0, 6).map(e => /*#__PURE__*/React.createElement(DashboardEntityCard, {
    key: e.id,
    e: e
  })))), role !== "AE" ? /*#__PURE__*/React.createElement("div", {
    className: "col",
    style: {
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "rgba(254,151,50,.18)",
      color: "var(--z-org)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 14
  })), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13
    }
  }, "Needs attention"), /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    style: {
      marginLeft: "auto"
    }
  }, totalAlerts)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12,
      color: "var(--z-body)",
      marginBottom: 10,
      lineHeight: 1.55
    }
  }, "Thin-evidence alerts across ", new Set(DMA.ALERTS.filter(a => a.status === "OPEN").map(a => a.entity_id)).size, " entities."), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    style: {
      width: "100%",
      justifyContent: "center"
    },
    onClick: () => navigate("/alerts")
  }, "Review alerts ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))), /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "rgba(194,80,8,.14)",
      color: "var(--z-below)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "warn",
    size: 14
  })), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13
    }
  }, "Stale entities")), stale.map(e => /*#__PURE__*/React.createElement("div", {
    key: e.id,
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "8px 0",
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600
    },
    className: "txt-fit-1"
  }, e.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, relTime(e.assessment_date))), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => navigate(`/clients/${e.id}/overview`)
  }, "Rerun")))), role === "ADMIN" ? /*#__PURE__*/React.createElement("div", {
    className: "card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 28,
      height: 28,
      borderRadius: 7,
      background: "var(--ph0-lt)",
      color: "var(--z-dpur)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "drive",
    size: 14
  })), /*#__PURE__*/React.createElement("strong", {
    style: {
      fontSize: 13
    }
  }, "System health")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8,
      fontSize: 11.5
    }
  }, window.DMA_LIVE ? /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Package scan"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "not yet scheduled")) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Drive crawl"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "2 hr ago")), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Vertex AI budget"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, "$184 / $400"))), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Pending review"), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", null, DMA.PENDING_REVIEW.length, " entities"))), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    style: {
      width: "100%",
      justifyContent: "center",
      marginTop: 10
    },
    onClick: () => navigate("/admin")
  }, "Open admin ", /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-r",
    size: 11
  }))) : null) : null));
}
function KpiCard({
  label,
  value,
  sub,
  icon,
  accent,
  rounding
}) {
  const display = rounding && typeof value === "number" ? Math.round(value) : value;
  return /*#__PURE__*/React.createElement("div", {
    className: "card-tile",
    style: {
      padding: 14,
      borderTop: `3px solid ${accent}`
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 14,
    style: {
      color: accent
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      textTransform: "uppercase",
      letterSpacing: ".08em"
    }
  }, label)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 28,
      fontWeight: 200,
      color: "var(--z-dark)",
      letterSpacing: "-.02em",
      lineHeight: 1
    }
  }, display), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, sub));
}
function DashboardEntityCard({
  e
}) {
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  const matHex = DMA.helpers.maturityHex(e.overall || 2.5);
  const matLabel = DMA.helpers.maturityLabel(e.overall || 2.5);
  return /*#__PURE__*/React.createElement("div", {
    className: "card-tile clickable",
    onClick: () => navigate(`/clients/${e.id}/overview`),
    style: {
      padding: 14,
      display: "flex",
      flexDirection: "column"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 10,
      alignItems: "flex-start",
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 36,
      height: 36,
      borderRadius: 8,
      background: `linear-gradient(135deg, ${matHex}, var(--z-mid))`,
      color: "#fff",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 14,
      fontWeight: 700,
      flexShrink: 0
    }
  }, e.name.split(" ").map(n => n[0]).slice(0, 2).join("")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: "var(--z-dark)",
      lineHeight: 1.3
    },
    className: "txt-fit-2",
    title: e.name
  }, e.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--z-muted)",
      marginTop: 2,
      lineHeight: 1.35
    },
    className: "txt-fit-2",
    title: `${DMA.SUBVERTICAL_LABEL[e.subvertical]} · ${e.hq}`
  }, DMA.SUBVERTICAL_LABEL[e.subvertical], " \xB7 ", e.hq)), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "right",
      flexShrink: 0,
      display: "flex",
      flexDirection: "column",
      alignItems: "flex-end"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 22,
      fontWeight: 200,
      color: matHex,
      lineHeight: 1
    }
  }, e.overall?.toFixed(1) || "-"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 8.5,
      color: matHex,
      fontWeight: 700,
      textTransform: "uppercase",
      letterSpacing: ".04em",
      marginTop: 3,
      whiteSpace: "nowrap"
    }
  }, matLabel))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 6,
      marginBottom: 10
    }
  }, DMA.PILLARS.map(p => {
    const s = e.pillar_scores?.[p.id];
    return /*#__PURE__*/React.createElement("div", {
      key: p.id,
      title: `${p.id} · ${s?.toFixed(1) || "-"}`,
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 2
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        fontWeight: 600
      }
    }, p.id), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: "var(--z-body)",
        fontWeight: 600
      }
    }, s ? s.toFixed(1) : "–")), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 5,
        background: "var(--z-sep)",
        borderRadius: 2.5,
        overflow: "hidden"
      }
    }, s ? /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${s / 5 * 100}%`,
        height: "100%",
        background: DMA.helpers.maturityHex(s)
      }
    }) : null));
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      paddingTop: 8,
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 4,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`
  }, e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"), e.open_alerts > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 9
  }), " ", e.open_alerts) : null, /*#__PURE__*/React.createElement(FreshnessDot, {
    date: e.assessment_date
  })), top ? /*#__PURE__*/React.createElement("span", {
    className: "spacer",
    style: {
      fontSize: 11,
      color: "var(--z-mid)",
      textAlign: "right"
    }
  }, DMA.getPlatform(top[0])?.short, " ", /*#__PURE__*/React.createElement("strong", null, top[1])) : null));
}

/* ── /clients Entity directory (s21) ─────────────────────────────── */
function EntityDirectoryPage() {
  const {
    openNewRun,
    pushToast
  } = useApp();
  const [q, setQ] = useState("");
  const [subvFilter, setSubvFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("date");
  const [view, setView] = useState("grid"); // grid | table

  const filtered = useMemo(() => {
    const ql = q.toLowerCase();
    let xs = DMA.ENTITIES.filter(e => {
      if (subvFilter !== "ALL" && e.subvertical !== subvFilter) return false;
      if (sourceFilter !== "ALL" && e.data_source !== sourceFilter) return false;
      if (ql && !(e.name.toLowerCase().includes(ql) || (e.domain || "").includes(ql))) return false;
      return true;
    });
    if (sortBy === "date") xs.sort((a, b) => new Date(b.assessment_date || 0) - new Date(a.assessment_date || 0));
    if (sortBy === "oss") xs.sort((a, b) => (b.oss && Math.max(...Object.values(b.oss)) || 0) - (a.oss && Math.max(...Object.values(a.oss)) || 0));
    if (sortBy === "alerts") xs.sort((a, b) => b.open_alerts - a.open_alerts);
    return xs;
  }, [q, subvFilter, sourceFilter, sortBy]);
  return /*#__PURE__*/React.createElement(PageShell, {
    title: "Clients",
    crumbs: [{
      label: "Clients"
    }]
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "eyebrow"
  }, "Entity directory"), /*#__PURE__*/React.createElement("h1", null, "Clients"), /*#__PURE__*/React.createElement("div", {
    className: "sub"
  }, filtered.length, " of ", DMA.ENTITIES.length, " entities \xB7 sorted by ", sortBy)), /*#__PURE__*/React.createElement("div", {
    className: "actions"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toggle-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: view === "grid" ? "on" : "",
    onClick: () => setView("grid")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "grid",
    size: 13
  })), /*#__PURE__*/React.createElement("button", {
    className: view === "table" ? "on" : "",
    onClick: () => setView("table")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "menu",
    size: 13
  }))), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary",
    onClick: () => pushToast(`Exporting ${filtered.length} clients as CSV…`, "success")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), " Export"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: openNewRun
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), " New run"))), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 14,
    style: {
      position: "absolute",
      top: 10,
      left: 10,
      color: "var(--z-muted)"
    }
  }), /*#__PURE__*/React.createElement("input", {
    className: "inp",
    style: {
      paddingLeft: 32
    },
    placeholder: "Search by name or domain\u2026",
    value: q,
    onChange: e => setQ(e.target.value)
  })), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 200
    },
    value: subvFilter,
    onChange: e => setSubvFilter(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All subverticals"), Object.entries(DMA.SUBVERTICAL_LABEL).map(([k, v]) => /*#__PURE__*/React.createElement("option", {
    key: k,
    value: k
  }, v))), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 200
    },
    value: sourceFilter,
    onChange: e => setSourceFilter(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "ALL"
  }, "All sources"), /*#__PURE__*/React.createElement("option", {
    value: "PROJECT_API"
  }, "Project API"), /*#__PURE__*/React.createElement("option", {
    value: "DRIVE_PARSE"
  }, "Drive parse")), /*#__PURE__*/React.createElement("select", {
    className: "inp",
    style: {
      maxWidth: 200
    },
    value: sortBy,
    onChange: e => setSortBy(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "date"
  }, "Sort: Run date"), /*#__PURE__*/React.createElement("option", {
    value: "oss"
  }, "Sort: Top OSS"), /*#__PURE__*/React.createElement("option", {
    value: "alerts"
  }, "Sort: Open alerts")), q || subvFilter !== "ALL" || sourceFilter !== "ALL" ? /*#__PURE__*/React.createElement("button", {
    className: "btn btn-tertiary btn-sm",
    onClick: () => {
      setQ("");
      setSubvFilter("ALL");
      setSourceFilter("ALL");
    }
  }, "Clear filters") : null), filtered.length === 0 ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement("div", {
    className: "icon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 22
  })), /*#__PURE__*/React.createElement("h3", null, "No clients match your search"), /*#__PURE__*/React.createElement("p", null, "Try clearing filters or broaden the search term.")) : view === "grid" ? /*#__PURE__*/React.createElement("div", {
    className: "g3"
  }, filtered.map(e => /*#__PURE__*/React.createElement(EntityCard, {
    key: e.id,
    e: e
  }))) : /*#__PURE__*/React.createElement("div", {
    className: "card flush"
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl tbl-clickable"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Entity"), /*#__PURE__*/React.createElement("th", null, "Subvertical"), /*#__PURE__*/React.createElement("th", null, "Date"), /*#__PURE__*/React.createElement("th", null, "Source"), /*#__PURE__*/React.createElement("th", null, "Open alerts"), /*#__PURE__*/React.createElement("th", null, "Top OSS"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Score"))), /*#__PURE__*/React.createElement("tbody", null, filtered.map(e => /*#__PURE__*/React.createElement("tr", {
    key: e.id,
    onClick: () => navigate(`/clients/${e.id}/overview`)
  }, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, e.name), /*#__PURE__*/React.createElement("div", {
    className: "f-mono",
    style: {
      fontSize: 10,
      color: "var(--z-muted)"
    }
  }, e.domain || e.assessment_id)), /*#__PURE__*/React.createElement("td", null, DMA.SUBVERTICAL_LABEL[e.subvertical]), /*#__PURE__*/React.createElement("td", null, fmtDate(e.assessment_date)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("span", {
    className: `b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`
  }, e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API")), /*#__PURE__*/React.createElement("td", null, e.open_alerts > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, e.open_alerts) : /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "0")), /*#__PURE__*/React.createElement("td", null, e.oss ? (() => {
    const top = Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0];
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600
      }
    }, top[1]), " ", /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, DMA.getPlatform(top[0])?.short));
  })() : /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "-")), /*#__PURE__*/React.createElement("td", {
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement(MaturityChip, {
    score: e.overall
  }))))))));
}
function EntityCard({
  e
}) {
  const top = e.oss ? Object.entries(e.oss).sort((a, b) => b[1] - a[1])[0] : null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card-tile clickable",
    onClick: () => navigate(`/clients/${e.id}/overview`)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      fontSize: 14,
      color: "var(--z-dark)",
      marginBottom: 2
    }
  }, e.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, DMA.SUBVERTICAL_LABEL[e.subvertical], " \xB7 ", e.hq)), e.in_progress ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org",
    style: {
      display: "inline-flex",
      gap: 4
    }
  }, "\u25CF IN PROGRESS") : /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 26,
      fontWeight: 200,
      color: "var(--z-teal)",
      lineHeight: 1,
      letterSpacing: "-.02em"
    }
  }, e.overall?.toFixed(1) || "-"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9,
      color: "var(--z-muted)",
      marginTop: 2
    }
  }, "maturity"))), e.pillar_scores ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4,1fr)",
      gap: 4,
      marginBottom: 10
    }
  }, DMA.PILLARS.map(p => {
    const s = e.pillar_scores[p.id];
    const w = s / 5 * 100;
    return /*#__PURE__*/React.createElement("div", {
      key: p.id
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--z-muted)",
        marginBottom: 3
      }
    }, p.id), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 6,
        background: "var(--z-sep)",
        borderRadius: 3,
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${w}%`,
        height: "100%",
        background: DMA.helpers.maturityHex(s)
      }
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        color: "var(--z-dark)",
        marginTop: 2
      }
    }, s.toFixed(1)));
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog"
  }, /*#__PURE__*/React.createElement("div", {
    className: "prog-fill",
    style: {
      width: `${e.runs[0].current_batch / 6 * 100}%`,
      background: "var(--z-org)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, "Batch ", e.runs[0].current_batch, " of 6")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      paddingTop: 10,
      borderTop: "1px solid var(--z-sep)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      flexWrap: "wrap"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: `b ${e.data_source === "DRIVE_PARSE" ? "b-ph0" : "b-ph1"}`
  }, e.data_source === "DRIVE_PARSE" ? "DRIVE" : "API"), e.assessment_date ? /*#__PURE__*/React.createElement(FreshnessDot, {
    date: e.assessment_date
  }) : null, e.open_alerts > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "b b-org"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bell",
    size: 9
  }), " ", e.open_alerts) : null), top ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--z-mid)"
    }
  }, "Top OSS \xB7 ", DMA.getPlatform(top[0])?.short, " ", /*#__PURE__*/React.createElement("strong", {
    style: {
      marginLeft: 4
    }
  }, top[1])) : null));
}
Object.assign(window, {
  LoginPage,
  DashboardHome,
  EntityDirectoryPage
});