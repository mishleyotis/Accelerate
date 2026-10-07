// Service-to-service identity for calls to svc_api: a Google-signed ID token
// for the API's audience, from the metadata server on Cloud Run. Local QA
// passes API_ID_TOKEN instead, because a developer machine has no metadata
// server. Same mechanism app/route.js and the entity proxy use inline.
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
