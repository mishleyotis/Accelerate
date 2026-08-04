import { cookies } from "next/headers";
import { COOKIE, verify } from "../lib/session";

export const dynamic = "force-dynamic";

// The app IS the prototype: its modules run verbatim (compiled at build
// time) inside a plain HTML document — a route handler, not a React
// page, so no framework hydration ever reconciles SPA-owned DOM. The
// session is verified server-side and the live bootstrap (catalogue,
// promoted directory) is inlined as window.DMA_LIVE before any module
// runs — mirroring prototype/template.html's own structure.

async function apiFetch(path) {
  const base = process.env.API_URL;
  if (!base) return null;
  const headers = {};
  try {
    const t = await fetch(
      "http://metadata.google.internal/computeMetadata/v1/instance/" +
        `service-accounts/default/identity?audience=${encodeURIComponent(base)}`,
      { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" }
    );
    if (t.ok) headers.Authorization = `Bearer ${await t.text()}`;
  } catch {}
  try {
    const r = await fetch(`${base}${path}`, { headers, cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

const SCRIPTS = [
  "vendor/react.production.min.js",
  "vendor/react-dom.production.min.js",
  "proto/js/data.js",
  "proto/js/utils.js",
  "proto/js/chrome.js",
  "proto/js/drawers.js",
  "proto/js/pages-auth-dashboard-directory.js",
  "proto/js/cards-data-driven.js",
  "proto/js/pages-d1-overview.js",
  "proto/js/pages-d3-heatmap.js",
  "proto/js/pages-d3-d4.js",
  "proto/js/pages-d5-d6-tech-runs.js",
  "proto/js/pages-alerts-prospecting-admin.js",
  "proto/js/tweaks-panel.js",
  "proto/js/app-root.js",
];

export async function GET() {
  const session = verify(cookies().get(COOKIE)?.value);
  const [catalogue, directory] = await Promise.all([
    apiFetch("/v1/catalogue"),
    apiFetch("/v1/directory"),
  ]);
  const live = {
    authed: !!session,
    role: session?.role || null,
    email: session?.email || null,
    pillars: catalogue?.pillars || null,
    categories: catalogue?.categories || null,
    entities: directory?.entities || [],
    active_runs: directory?.active_runs || [],
    pending_review: directory?.pending_review || [],
  };
  const boot = JSON.stringify(live).replace(/</g, "\\u003c");
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DMA Insights</title>
<link rel="stylesheet" href="/proto/app.css">
<link rel="icon" href="/brand/icon_teal.png">
</head>
<body>
<div id="app"></div>
<script>window.DMA_LIVE=${boot};</script>
${SCRIPTS.map((s) => `<script src="/${s}" defer></script>`).join("\n")}
</body>
</html>`;
  return new Response(html, {
    headers: { "content-type": "text/html; charset=utf-8",
               "cache-control": "no-store" },
  });
}
