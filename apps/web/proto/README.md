# Prototype modules, running in production

These are the prototype's own modules (see `/prototype`, the layout and
rendering authority), compiled at build time and booted from live data.

Divergences from the verbatim prototype are DATA-FLOW ONLY, per the
charter's correction table ("static client-side data → everything
through svc_api"):

- `data.js` — a `window.DMA_LIVE` hook: catalogue and corpus-level lists
  come from svc_api; the mock stays as shape reference and local-preview
  fallback. Entity-scoped mock data is unreachable once ENTITIES is live.
- `pages-auth-dashboard-directory.jsx` — LoginPage posts to /api/signin
  (server-side domain gate + httpOnly session cookie); visuals untouched.
  The dashboard's Avg-maturity KPI renders its empty state instead of
  NaN over zero entities (invariant 9).
- `app-root.jsx` — initial `authed` comes from the server-verified
  session in DMA_LIVE.

- Client view (owner's client-view review, 2026-10-07): "Customer" reads
  "Client", the client view carries Overview · Insights · Heatmap only and
  hides the Zennify-only surfaces, and `?view=client` opens the chrome-less
  client link (`chrome.jsx`, `utils.jsx`, `app-root.jsx`,
  `pages-d1-overview.jsx`). Product behaviour, not data flow — recorded here
  so `/prototype` is not mistaken for the current client view.

Everything else is byte-identical to `/prototype`. Do not restyle here;
the prototype wins on layout, interaction and visual rendering.
