import { cookies } from "next/headers";
import { COOKIE, verify } from "../lib/session";
import { verifyIapAssertion } from "../lib/iap";
import { displayName, domainOk, grantedRole, roleGrants } from "../lib/identity";

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
  // Local QA only: on Cloud Run the ID token comes from the metadata
  // server, which does not exist on a developer machine.
  if (process.env.API_ID_TOKEN) {
    headers.Authorization = `Bearer ${process.env.API_ID_TOKEN}`;
  }
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
  "proto/js/pages-live-client.js",
  "proto/js/tweaks-panel.js",
  "proto/js/app-root.js",
];

export async function GET(req) {
  let session = verify(cookies().get(COOKIE)?.value);

  // IAP already authenticated this request with Google. If the app
  // session is missing (first visit, expiry), mint it from the verified
  // assertion right here — the user signed in once at Google's door and
  // never re-types anything. The explicit /login page remains only for
  // post-sign-out and local dev.
  let setCookieValue = null;
  if (!session) {
    const iap = await verifyIapAssertion(req.headers.get("x-goog-iap-jwt-assertion"));
    if (iap && domainOk(iap.email)) {
      const role = grantedRole(iap.email);
      const name = displayName(iap.email);
      session = { email: iap.email, role, name };
      const { sign, maxAge } = await import("../lib/session");
      setCookieValue = { value: sign(iap.email, role, name), maxAge: maxAge() };
    }
  }

  const [catalogue, directory, scans] = await Promise.all([
    apiFetch("/v1/catalogue"),
    apiFetch("/v1/directory"),
    session?.role === "ADMIN" ? apiFetch("/v1/ops/import-scans") : Promise.resolve(null),
  ]);
  const live = {
    authed: !!session,
    role: session?.role || null,
    email: session?.email || null,
    name: session?.name || (session?.email ? displayName(session.email) : null),
    role_grants: session?.role === "ADMIN" ? roleGrants() : null,
    intake_folder_id: session?.role === "ADMIN" ? (process.env.INTAKE_FOLDER_ID || null) : null,
    import_scans: session?.role === "ADMIN" ? (scans?.scans || []) : null,
    catalogue_version: catalogue?.version || null,
    dev_login: process.env.ALLOW_DEV_LOGIN === "1",
    pillars: catalogue?.pillars || null,
    categories: catalogue?.categories || null,
    entities: directory?.entities || [],
    subvertical_labels: directory?.subvertical_labels || {},
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
  const headers = { "content-type": "text/html; charset=utf-8",
                    "cache-control": "no-store" };
  const res = new Response(html, { headers });
  if (setCookieValue) {
    res.headers.append(
      "set-cookie",
      `${COOKIE}=${setCookieValue.value}; Path=/; Max-Age=${setCookieValue.maxAge}; HttpOnly; Secure; SameSite=Lax`
    );
  }
  return res;
}
