# DMA Insights — front-end prototype (read-only reference)

Source modules extracted from the delivered standalone artifact
`DMA_Insights_Standalone_5.html` (kept here verbatim — open it in a browser
to see the working prototype). The JSX modules below are the same code,
unbundled, in **load order**:

| # | Module | Contents |
|---|--------|----------|
| 1 | `utils.jsx` | Shared utilities, SVG icons, layout primitives |
| 2 | `chrome.jsx` | App shell — Sidebar, TopBar, ClientShell, banners |
| 3 | `drawers.jsx` | Evidence drawer, insight modal, intelligence panel, toasts |
| 4 | `pages-auth-dashboard-directory.jsx` | Login, dashboard home, entity directory |
| 5 | `cards-data-driven.jsx` | Data-driven cards (real DMA deliverable shapes) |
| 6 | `pages-d1-overview.jsx` | D1 Entity Intelligence Hub |
| 7 | `pages-d3-heatmap.jsx` | D3 Maturity Heatmap (view modes, synthesis drawer, overlays) |
| 8 | `pages-d3-d4.jsx` | D3 heatmap pages, D4 Platform Matrix |
| 9 | `pages-d5-d6-tech-runs.jsx` | D5 Context, D6 Health, tech stack, runs |
| 10 | `pages-alerts-prospecting-admin.jsx` | Alerts, prospecting, admin |
| 11 | `tweaks-panel.jsx` | Tweaks shell + form-control helpers |
| 12 | `app-root.jsx` | App root — router + provider + tweaks |

Plus:
- `data.js` — the client-side **mock** data module. Contains the canonical
  band resolver boundaries (strict `<2 / <3 / <4 / ≥4`, hexes
  `#FFCB99 / #62D7B8 / #27BBAF / #139F94`, null → `#E5E7EB`).
- `template.html` — the page shell with the full CSS (tokens + app styles).

Vendor dependencies (not committed; embedded in the standalone artifact):
React 18 development build, ReactDOM, Babel standalone.

## Authority — read this before copying anything

Per the build kickoff (§3/§5) the prototype is authoritative for **layout,
interaction, visual rendering and the band resolver boundaries only**. Its
data vocabularies are partially superseded — see the corrections table in
the root `CLAUDE.md` (tech-stack layer keys, stack statuses, M5 removal,
freshness relabel, caps/gates split, surface IDs). **Never copy its
data-fetch logic**: `data.js` is a static client-side mock; the real app
serves everything through `svc_api` from serving tables.
