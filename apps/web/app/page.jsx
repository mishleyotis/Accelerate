import { cookies } from "next/headers";
import { verify, COOKIE } from "../lib/session";

export const dynamic = "force-dynamic";

// The app IS the prototype: its modules run verbatim (compiled at build
// time), booted from live data instead of the mock. This host page
// verifies the session server-side, fetches the bootstrap from svc_api,
// and hands both to the SPA via window.DMA_LIVE before any module runs.

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

export default async function Home() {
  const session = verify(cookies().get(COOKIE)?.value);
  const catalogue = await apiFetch("/v1/catalogue");
  const directory = await apiFetch("/v1/directory");
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
  const boot = `window.DMA_LIVE=${JSON.stringify(live).replace(/</g, "\\u003c")};`;
  return (
    <>
      <div id="app" />
      <script dangerouslySetInnerHTML={{ __html: boot }} />
      {SCRIPTS.map((s) => (
        <script key={s} src={`/${s}`} defer />
      ))}
    </>
  );
}
