// Service-to-service identity for calls to svc_api: a Google-signed ID token
// for the API's audience, from the metadata server on Cloud Run. Local QA
// passes API_ID_TOKEN instead, because a developer machine has no metadata
// server. Same mechanism app/route.js and the entity proxy use inline.
// The header the IAP assertion travels in from dmai-web to dmai-api. NOT
// Google's own `x-goog-iap-jwt-assertion`: Google's front end treats that name
// as its own and does not deliver a caller-supplied copy to a service, so the
// API never saw it — "this write must be attributable to a verified person"
// on every Users & roles change (2026-10-08). The token itself is unchanged
// and the API verifies it exactly as before (dma_api.identity).
export const ASSERTION_HEADER = "x-dmai-iap-assertion";

export async function upstreamHeaders(base) {
  const headers = {};
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
  return headers;
}
