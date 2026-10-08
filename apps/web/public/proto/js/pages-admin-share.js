/* ─────────────────────── Admin › Client links ───────────────────────
   Owner, 2026-10-07: "The admin page should also have a place where I can
   revoke access." Every client link generated from a Client Dashboard, who
   it was shared with and by whom, and the two ways to take access back:

     Revoke link        the whole link stops opening, for everyone
     × on a recipient   that address (or everyone at that domain) is refused;
                        the rest of the link keeps working

   Both can be undone (Restore). The server is the authority: the share
   service re-checks the ledger on every request (lib/share-ledger), so a
   change lands within seconds — including for a reader already inside.
   A link generated before the ledger existed is not in the list; paste it
   (or its link ID, shown when it was generated) to revoke it. */
const {
  useState: useStateSL,
  useEffect: useEffectSL
} = React;
const SL_STATUS = {
  active: {
    label: "Active",
    cls: "b-above"
  },
  revoked: {
    label: "Revoked",
    cls: "b-org"
  },
  expired: {
    label: "Expired",
    cls: "b-muted"
  },
  unrecorded: {
    label: "Not recorded",
    cls: "b-muted"
  }
};
function slClientName(id) {
  const e = DMA.getEntity && DMA.getEntity(id);
  return e && (e.name || e.trading_name) || id || "Unknown client";
}
function ShareLinksCard() {
  const {
    pushToast
  } = useApp();
  const LIVE = !!window.DMA_LIVE;
  const [data, setData] = useStateSL(null); // { status, links, detail? }
  const [show, setShow] = useStateSL("active"); // active | all
  const [busy, setBusy] = useStateSL(null); // `${jti}:${action}:${target}`
  const [confirm, setConfirm] = useStateSL(null); // jti awaiting "Confirm revoke"
  const [paste, setPaste] = useStateSL("");
  const load = () => {
    if (!LIVE) {
      setData({
        status: "prototype",
        links: []
      });
      return;
    }
    fetch("/api/admin/share-links", {
      cache: "no-store"
    }).then(r => r.json().then(b => r.ok ? b : {
      status: "error",
      detail: b.error,
      links: []
    })).then(setData).catch(() => setData({
      status: "error",
      detail: "network",
      links: []
    }));
  };
  useEffectSL(load, []);
  // Whitelisted client domains changes the same ledger; re-read when it does.
  useEffectSL(() => {
    const f = e => {
      if (e.detail !== "links") load();
    };
    window.addEventListener("dma-share-ledger-changed", f);
    return () => window.removeEventListener("dma-share-ledger-changed", f);
  }, []);
  const act = (link, action, target) => {
    const key = `${link}:${action}:${target ? target.email || target.domain : ""}`;
    setBusy(key);
    return fetch("/api/admin/share-links", {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        link,
        action,
        ...(target || {})
      })
    }).then(r => r.json().then(b => ({
      ok: r.ok,
      b
    }))).then(({
      ok,
      b
    }) => {
      setBusy(null);
      setConfirm(null);
      if (!ok) {
        pushToast(b.detail || b.error || "That change was not saved", "warn");
        return false;
      }
      const what = {
        revoke: "Link revoked - it no longer opens",
        restore: "Link restored",
        remove: `${target && (target.email || `@${target.domain}`)} can no longer open this link`,
        readd: `${target && (target.email || `@${target.domain}`)} restored`
      }[action];
      pushToast(what, "success");
      load();
      window.dispatchEvent(new CustomEvent("dma-share-ledger-changed", {
        detail: "links"
      }));
      return true;
    }).catch(() => {
      setBusy(null);
      pushToast("That change was not saved", "warn");
      return false;
    });
  };
  const links = data && data.links || [];
  const shown = show === "all" ? links : links.filter(l => l.status === "active");
  const counts = links.reduce((a, l) => (a[l.status] = (a[l.status] || 0) + 1, a), {});
  const chip = (l, kind, value) => {
    const removed = l.revocation && (kind === "email" ? l.revocation.emails : l.revocation.domains).includes(value);
    const target = kind === "email" ? {
      email: value
    } : {
      domain: value
    };
    const key = `${l.jti}:${removed ? "readd" : "remove"}:${value}`;
    const canEdit = l.status === "active";
    return /*#__PURE__*/React.createElement("span", {
      key: `${kind}:${value}`,
      className: "chip",
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        textDecoration: removed ? "line-through" : "none",
        opacity: removed ? 0.6 : 1
      },
      title: removed ? "Access removed" : kind === "domain" ? `Anyone with an @${value} address` : value
    }, kind === "domain" ? `anyone @${value}` : value, canEdit ? /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        padding: "0 4px",
        minHeight: 0,
        lineHeight: 1.2,
        fontSize: 11
      },
      disabled: busy === key,
      "aria-label": removed ? `Restore ${value}` : `Remove access for ${value}`,
      onClick: () => act(l.jti, removed ? "readd" : "remove", target)
    }, busy === key ? "…" : removed ? "Restore" : "×") : null);
  };
  const body = () => {
    if (!data) return /*#__PURE__*/React.createElement("div", {
      className: "card-body muted",
      style: {
        fontSize: 12
      }
    }, "Loading client links\u2026");
    if (data.status === "prototype") return /*#__PURE__*/React.createElement("div", {
      className: "card-body muted",
      style: {
        fontSize: 12
      }
    }, "Client links are managed in the live app.");
    if (data.status === "not_configured") return /*#__PURE__*/React.createElement("div", {
      className: "card-body",
      style: {
        fontSize: 12,
        color: "var(--z-body)"
      }
    }, "The client-link ledger is not configured on this deployment (", /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, "SHARE_LEDGER_BUCKET"), "), so links cannot be listed or revoked here. Break-glass: add the link ID to ", /*#__PURE__*/React.createElement("span", {
      className: "f-mono"
    }, "infra/share-revoked.txt"), " and release.");
    if (data.status !== "ok") return /*#__PURE__*/React.createElement("div", {
      className: "card-body",
      style: {
        fontSize: 12,
        color: "var(--z-org)"
      }
    }, "The client-link ledger could not be read (", data.detail || "error", "). Shared links refuse to open while it is unreadable.", /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      style: {
        marginLeft: 8
      },
      onClick: load
    }, "Retry"));
    if (!shown.length) return /*#__PURE__*/React.createElement("div", {
      className: "card-body muted",
      style: {
        fontSize: 12
      }
    }, show === "active" ? "No active client links." : "No client links have been generated yet.");
    return /*#__PURE__*/React.createElement("div", {
      style: {
        overflowX: "auto"
      }
    }, /*#__PURE__*/React.createElement("table", {
      className: "tbl"
    }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Client"), /*#__PURE__*/React.createElement("th", null, "Shared with"), /*#__PURE__*/React.createElement("th", null, "Shared by"), /*#__PURE__*/React.createElement("th", null, "Expires"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", {
      style: {
        textAlign: "right"
      }
    }, "Access"))), /*#__PURE__*/React.createElement("tbody", null, shown.map(l => {
      const st = SL_STATUS[l.status] || SL_STATUS.active;
      return /*#__PURE__*/React.createElement("tr", {
        key: l.jti,
        "data-link": l.jti,
        style: {
          opacity: l.status === "active" ? 1 : 0.7
        }
      }, /*#__PURE__*/React.createElement("td", {
        "data-label": "Client"
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontWeight: 600,
          color: "var(--z-dark)"
        }
      }, l.unrecorded ? "Not recorded" : slClientName(l.entity)), /*#__PURE__*/React.createElement("div", {
        className: "f-mono",
        style: {
          fontSize: 10,
          color: "var(--z-muted)"
        }
      }, "Link ID ", l.jti)), /*#__PURE__*/React.createElement("td", {
        "data-label": "Shared with"
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          display: "flex",
          flexWrap: "wrap",
          gap: 4
        }
      }, (l.emails || []).map(e => chip(l, "email", e)), (l.domains || []).map(d => chip(l, "domain", d)), l.unrecorded ? /*#__PURE__*/React.createElement("span", {
        className: "muted",
        style: {
          fontSize: 11.5
        }
      }, "Generated before the ledger; revoked by ID") : null)), /*#__PURE__*/React.createElement("td", {
        "data-label": "Shared by",
        style: {
          fontSize: 11.5
        }
      }, /*#__PURE__*/React.createElement("div", null, l.minted_by || "Not recorded"), /*#__PURE__*/React.createElement("div", {
        className: "muted",
        style: {
          fontSize: 10.5
        }
      }, l.minted_at ? fmtDate(l.minted_at) : "")), /*#__PURE__*/React.createElement("td", {
        "data-label": "Expires",
        style: {
          fontSize: 11.5,
          color: "var(--z-muted)"
        }
      }, l.expires_at ? fmtDate(l.expires_at) : "Not recorded"), /*#__PURE__*/React.createElement("td", {
        "data-label": "Status"
      }, /*#__PURE__*/React.createElement("span", {
        className: `b ${st.cls}`
      }, st.label)), /*#__PURE__*/React.createElement("td", {
        "data-label": "Access",
        style: {
          textAlign: "right",
          whiteSpace: "nowrap"
        }
      }, l.status === "active" ? confirm === l.jti ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
        className: "btn btn-tertiary btn-sm",
        onClick: () => setConfirm(null)
      }, "Cancel"), /*#__PURE__*/React.createElement("button", {
        className: "btn btn-primary btn-sm",
        style: {
          background: "var(--z-org)",
          borderColor: "var(--z-org)"
        },
        disabled: busy === `${l.jti}:revoke:`,
        onClick: () => act(l.jti, "revoke")
      }, busy === `${l.jti}:revoke:` ? "Revoking…" : "Confirm revoke")) : /*#__PURE__*/React.createElement("button", {
        className: "btn btn-secondary btn-sm",
        onClick: () => setConfirm(l.jti)
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "lock",
        size: 11
      }), " Revoke link") : l.status === "revoked" || l.status === "unrecorded" ? /*#__PURE__*/React.createElement("button", {
        className: "btn btn-tertiary btn-sm",
        disabled: busy === `${l.jti}:restore:`,
        onClick: () => act(l.jti, "restore")
      }, "Restore") : null));
    }))));
  };
  const submitPaste = () => {
    const v = paste.trim();
    if (!v) return;
    act(v, "revoke").then(ok => {
      if (ok) setPaste("");
    });
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16
    },
    "data-screen-label": "Admin \xB7 Client links"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head",
    style: {
      flexWrap: "wrap",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "share",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Client links \xB7 access")), data && data.status === "ok" ? /*#__PURE__*/React.createElement("span", {
    className: "b b-teal"
  }, counts.active || 0, " active") : null, /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), data && data.status === "ok" ? /*#__PURE__*/React.createElement("div", {
    className: "toggle-row",
    role: "group",
    "aria-label": "Which links"
  }, /*#__PURE__*/React.createElement("button", {
    className: show === "active" ? "on" : "",
    onClick: () => setShow("active")
  }, "Active"), /*#__PURE__*/React.createElement("button", {
    className: show === "all" ? "on" : "",
    onClick: () => setShow("all")
  }, "All (", links.length, ")")) : null), body(), data && data.status === "ok" ? /*#__PURE__*/React.createElement("div", {
    className: "card-body",
    style: {
      borderTop: "1px solid var(--z-sep)",
      display: "flex",
      gap: 8,
      flexWrap: "wrap",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 13,
    style: {
      color: "var(--z-muted)",
      flexShrink: 0
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)",
      flex: "1 1 260px"
    }
  }, "Changes take effect within 15 seconds, including for anyone already viewing. Revoke a link that is not listed:"), /*#__PURE__*/React.createElement("input", {
    className: "inp inp-sm",
    id: "share-revoke-paste",
    value: paste,
    onChange: e => setPaste(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter") submitPaste();
    },
    placeholder: "Paste the client link or its link ID",
    "aria-label": "Client link or link ID to revoke",
    style: {
      flex: "1 1 260px",
      minWidth: 0
    }
  }), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-secondary btn-sm",
    disabled: !paste.trim() || !!busy,
    onClick: submitPaste
  }, "Revoke")) : null);
}

/* ── Whitelisted client domains ─────────────────────────────────────
   Owner, 2026-10-08: "the whitelist should show me a list of whitelisted
   client domains and allow me to revoke access. Similar to the user list
   above." One row per organisation domain a client link admits, laid out as
   Users & roles is: Domain · Clients · Recipients · Expires · Status · Action.
   Revoke access takes the domain AND every address named at it off every
   live link (lib/share-ledger changeDomainAccess); Restore puts them back.
   Expired and revoked links already open for nobody and are not counted. */
function cdRows(links) {
  const by = new Map();
  for (const l of links) {
    if (l.status !== "active") continue;
    const rev = l.revocation || {
      emails: [],
      domains: []
    };
    const doms = new Set((l.domains || []).map(d => d.toLowerCase()));
    (l.emails || []).forEach(e => doms.add(e.split("@")[1].toLowerCase()));
    for (const d of doms) {
      const r = by.get(d) || {
        domain: d,
        clients: new Set(),
        emails: new Set(),
        links: 0,
        open: 0,
        expires: null
      };
      const named = (l.emails || []).filter(e => e.toLowerCase().endsWith(`@${d}`));
      const domOpen = (l.domains || []).map(x => x.toLowerCase()).includes(d) && !(rev.domains || []).includes(d);
      const emailOpen = named.some(e => !(rev.emails || []).includes(e));
      r.links += 1;
      if (domOpen || emailOpen) r.open += 1;
      r.clients.add(l.entity);
      named.forEach(e => r.emails.add(e));
      if (l.expires_at && (!r.expires || l.expires_at > r.expires)) r.expires = l.expires_at;
      by.set(d, r);
    }
  }
  return [...by.values()].sort((a, b) => (b.open > 0) - (a.open > 0) || a.domain.localeCompare(b.domain));
}
function ClientDomainsCard() {
  const {
    pushToast
  } = useApp();
  const LIVE = !!window.DMA_LIVE;
  const [data, setData] = useStateSL(LIVE ? null : {
    status: "ok",
    links: [{
      jti: "p1",
      entity: "golden-1",
      status: "active",
      emails: ["cfo@golden1.com", "cio@golden1.com"],
      domains: ["golden1.com"],
      expires_at: "2026-11-06T00:00:00Z"
    }, {
      jti: "p2",
      entity: "arbor-bank",
      status: "active",
      emails: ["coo@arborbank.com"],
      domains: ["arborbank.com"],
      expires_at: "2026-10-30T00:00:00Z"
    }, {
      jti: "p3",
      entity: "swbc",
      status: "active",
      emails: ["it.lead@swbc.com"],
      domains: ["swbc.com"],
      revocation: {
        emails: ["it.lead@swbc.com"],
        domains: ["swbc.com"]
      },
      expires_at: "2026-10-21T00:00:00Z"
    }]
  });
  const [busy, setBusy] = useStateSL(null);
  const load = () => {
    if (!LIVE) return;
    fetch("/api/admin/share-links", {
      cache: "no-store"
    }).then(r => r.json().then(b => r.ok ? b : {
      status: "error",
      detail: b.detail || b.error,
      links: []
    })).then(setData).catch(() => setData({
      status: "error",
      detail: "The client-link ledger did not answer.",
      links: []
    }));
  };
  useEffectSL(load, []);
  // The Client links card changes the same ledger; re-read when it does.
  useEffectSL(() => {
    const f = e => {
      if (e.detail !== "domains") load();
    };
    window.addEventListener("dma-share-ledger-changed", f);
    return () => window.removeEventListener("dma-share-ledger-changed", f);
  }, []);
  const rows = data && data.status === "ok" ? cdRows(data.links || []) : [];
  const toggle = r => {
    const action = r.open > 0 ? "revoke" : "restore";
    if (!LIVE) {
      setData(d => ({
        ...d,
        links: d.links.map(l => {
          if (!cdRows([l]).some(x => x.domain === r.domain)) return l;
          const rev = l.revocation || {
            emails: [],
            domains: []
          };
          const named = (l.emails || []).filter(e => e.endsWith(`@${r.domain}`));
          return {
            ...l,
            revocation: action === "revoke" ? {
              emails: [...new Set([...rev.emails, ...named])],
              domains: [...new Set([...rev.domains, r.domain])]
            } : {
              emails: rev.emails.filter(e => !named.includes(e)),
              domains: rev.domains.filter(x => x !== r.domain)
            }
          };
        })
      }));
      pushToast(`@${r.domain} ${action === "revoke" ? "access revoked" : "access restored"}`, action === "revoke" ? "warn" : "success");
      return;
    }
    setBusy(r.domain);
    fetch("/api/admin/share-links", {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        domain: r.domain,
        action
      })
    }).then(res => res.json().then(b => ({
      ok: res.ok,
      b
    }))).then(({
      ok,
      b
    }) => {
      setBusy(null);
      if (!ok) {
        pushToast(b.detail || b.error || "That change was not saved", "warn");
        return;
      }
      const n = (b.links || []).length;
      pushToast(`@${r.domain} ${action === "revoke" ? "access revoked" : "access restored"} · ${n} link${n === 1 ? "" : "s"}`, action === "revoke" ? "warn" : "success");
      load();
      window.dispatchEvent(new CustomEvent("dma-share-ledger-changed", {
        detail: "domains"
      }));
    }).catch(() => {
      setBusy(null);
      pushToast("That change was not saved", "warn");
    });
  };
  const note = !data ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "spinner"
  }), " Loading client domains\u2026") : data.status === "not_configured" ? /*#__PURE__*/React.createElement(React.Fragment, null, "The client-link ledger is not configured on this deployment (", /*#__PURE__*/React.createElement("span", {
    className: "f-mono"
  }, "SHARE_LEDGER_BUCKET"), ").") : data.status !== "ok" ? /*#__PURE__*/React.createElement(React.Fragment, null, "The client-link ledger could not be read \xB7 ", /*#__PURE__*/React.createElement("span", {
    className: "f-mono",
    style: {
      fontSize: 10.5
    }
  }, data.detail || "error")) : !rows.length ? "No client domains are whitelisted: no live client link has been generated." : null;
  return /*#__PURE__*/React.createElement("div", {
    className: "card flush",
    style: {
      marginBottom: 16
    },
    "data-screen-label": "Admin \xB7 Whitelisted client domains"
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "lock",
    size: 14
  }), /*#__PURE__*/React.createElement("h3", null, "Whitelisted client domains")), /*#__PURE__*/React.createElement("span", {
    className: "b b-muted"
  }, rows.filter(r => r.open > 0).length, " active")), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: "auto"
    }
  }, /*#__PURE__*/React.createElement("table", {
    className: "tbl"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "Domain"), /*#__PURE__*/React.createElement("th", null, "Client"), /*#__PURE__*/React.createElement("th", null, "Recipients"), /*#__PURE__*/React.createElement("th", null, "Expires"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: "right"
    }
  }, "Action"))), /*#__PURE__*/React.createElement("tbody", null, note ? /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: 6,
    style: {
      fontSize: 12,
      color: "var(--z-muted)"
    }
  }, note)) : rows.map(r => {
    const on = r.open > 0;
    return /*#__PURE__*/React.createElement("tr", {
      key: r.domain,
      "data-domain": r.domain,
      style: {
        opacity: on ? 1 : 0.55
      }
    }, /*#__PURE__*/React.createElement("td", {
      "data-label": "Domain"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontWeight: 600,
        color: "var(--z-dark)"
      }
    }, "@", r.domain), /*#__PURE__*/React.createElement("div", {
      className: "f-mono",
      style: {
        fontSize: 10,
        color: "var(--z-muted)"
      }
    }, r.links, " live link", r.links === 1 ? "" : "s")), /*#__PURE__*/React.createElement("td", {
      "data-label": "Client",
      style: {
        fontSize: 12
      }
    }, [...r.clients].map(slClientName).join(" · ")), /*#__PURE__*/React.createElement("td", {
      "data-label": "Recipients",
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)"
      }
    }, [...r.emails].length ? [...r.emails].map(e => /*#__PURE__*/React.createElement("div", {
      key: e,
      className: "f-mono",
      style: {
        fontSize: 10.5
      }
    }, e)) : "Anyone at the domain"), /*#__PURE__*/React.createElement("td", {
      "data-label": "Expires",
      style: {
        fontSize: 11.5,
        color: "var(--z-muted)"
      }
    }, r.expires ? fmtDate(r.expires) : "Not recorded"), /*#__PURE__*/React.createElement("td", {
      "data-label": "Status"
    }, /*#__PURE__*/React.createElement("span", {
      className: `b ${on ? "b-above" : "b-muted"}`
    }, on ? "Active" : "Revoked")), /*#__PURE__*/React.createElement("td", {
      "data-label": "Action",
      style: {
        textAlign: "right"
      }
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-tertiary btn-sm",
      disabled: busy === r.domain,
      onClick: () => toggle(r)
    }, on ? "Revoke access" : "Restore")));
  })))));
}
Object.assign(window, {
  ShareLinksCard,
  ClientDomainsCard,
  cdRows
});