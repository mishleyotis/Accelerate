// Reads made on behalf of a client link. Whatever the browser asks for, the
// API is asked for exactly one thing: this link's client, this link's run,
// the customer audience, the AE role. Nothing the request carries can widen
// it — the browser's audience, role and run parameters are not read.
import { upstreamHeaders } from "./upstream.js";

export async function readAsLink(payload, page, eIds) {
  const base = process.env.API_URL;
  if (!base) return { status: 501, body: JSON.stringify({ error: "api_not_configured" }) };
  const target = new URL(`${base}/v1/entities/${encodeURIComponent(payload.e)}/${page}`);
  target.searchParams.set("audience", "customer");
  target.searchParams.set("role", "AE");
  target.searchParams.set("run", payload.r);
  if (eIds) target.searchParams.set("e_ids", String(eIds).slice(0, 4000));
  try {
    const r = await fetch(target, { headers: await upstreamHeaders(base), cache: "no-store" });
    return { status: r.status, body: await r.text() };
  } catch {
    return { status: 502, body: JSON.stringify({ error: "api_unreachable" }) };
  }
}

// The one entity row the SPA's directory needs, built from the client's OWN
// customer-audience overview envelope — never from the internal directory,
// which lists other institutions. Only these fields cross.
export function entityRow(body) {
  const e = (body && body.entity) || {};
  const r = (body && body.run) || {};
  const date = r.assessment_date || (r.completed_at ? String(r.completed_at).slice(0, 10) : null);
  const run = { id: r.request_id || r.run_id, run_id: r.run_id, date,
                status: "ACTIVE", data_source: null,
                overall: r.composite != null ? r.composite : null };
  return {
    id: e.display_id, slug: e.display_id, name: e.entity_name,
    trading_name: e.trading_name || null, subvertical: e.sub_vertical || null,
    supplementary_subverticals: e.supplementary_sub_verticals || [],
    size_tier: e.size_tier || null, hq: null, status: "ACTIVE", data_source: null,
    open_alerts: 0, overall: run.overall, assessment_date: date,
    pillar_scores: {}, runs: [run],
  };
}
