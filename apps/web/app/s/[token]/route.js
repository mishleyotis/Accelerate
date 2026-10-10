import { accessCookieName, audit, cookieFrom, readAccess, shareMode } from "../../../lib/share";
import { liveLink } from "../../../lib/share-ledger";
import { dashboardPage, deadLinkPage, gatePage, unavailablePage } from "../../../lib/share-page";
import { entityRow, readAsLink } from "../../../lib/share-read";
import { upstreamHeaders } from "../../../lib/upstream";
import { clientSession, deviceOf, linkFields, logUsage } from "../../../lib/usage";

export const dynamic = "force-dynamic";

// GET /s/<token> — a client link, on the public share service only.
//
//   bad / expired / revoked token  → the dead-link page (404)
//   ledger unreadable              → refused (503): revocation unknown
//   valid, reader not yet admitted → the email gate
//   valid and admitted             → the client dashboard, booted with this
//                                    link's one client and nothing else
export async function GET(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? unavailablePage() : deadLinkPage();

  // The reader's identity for this link (lib/share: readAccess). The name on
  // the gate comes from the client's own customer-audience payload.
  const email = readAccess(p, cookieFrom(req, accessCookieName(p)));
  const ov = await readAsLink(p, "overview");
  let body = null;
  try { body = ov.status === 200 ? JSON.parse(ov.body) : null; } catch {}
  if (!body || !body.entity || body.entity.display_id !== p.e) return deadLinkPage();
  if (!email) return gatePage(params.token, body.entity.entity_name);

  audit("share_link_opened", { jti: p.jti, entity: p.e, run: p.r, email });
  // Usage analytics: this recipient opened this link (lib/usage LINK_EVENTS).
  logUsage("link_open", clientSession(email),
           linkFields(p, { device: deviceOf(req.headers.get("user-agent")) }));
  const catRes = await fetch(`${process.env.API_URL}/v1/catalogue`, {
    headers: await upstreamHeaders(process.env.API_URL),
    cache: "no-store" }).catch(() => null);
  const catalogue = catRes && catRes.ok ? await catRes.json().catch(() => null) : null;
  return dashboardPage({
    authed: true, role: "AE", email: null, name: email,
    // The client link this document is: the SPA locks the client frame on
    // it (utils.jsx CLIENT_LINK) whatever the URL fragment says, and reads
    // through this link's own scoped API rather than the app's.
    share: { entity: p.e, expires_at: new Date(p.exp * 1000).toISOString() },
    api_base: `/s/${params.token}/api`,
    entities: [entityRow(body)],
    subvertical_labels: {}, active_runs: [], pending_review: [],
    role_grants: null, intake_folder_id: null, import_scans: null,
    catalogue_version: (catalogue && catalogue.version) || null,
    l3_platforms: (catalogue && catalogue.l3_platforms) || null,
    pillars: (catalogue && catalogue.pillars) || null,
    categories: (catalogue && catalogue.categories) || null,
    dev_login: false,
  });
}
