import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../lib/session";

// Fires one execution of the package-scan worker Job (the same Job the
// Cloud Scheduler trigger runs every 30 minutes). ADMIN sessions only —
// the server-granted role, not the acting one.
export async function POST() {
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session || session.role !== "ADMIN") {
    return NextResponse.json({ error: "Admin session required." }, { status: 403 });
  }
  const project = process.env.GCP_PROJECT;
  const region = process.env.GCP_REGION || "us-central1";
  const job = process.env.WORKER_JOB || "dmai-worker";
  if (!project) {
    return NextResponse.json(
      { error: "Scan trigger not configured on this deployment." }, { status: 501 });
  }
  try {
    const t = await fetch(
      "http://metadata.google.internal/computeMetadata/v1/instance/" +
        "service-accounts/default/token?scopes=" +
        encodeURIComponent("https://www.googleapis.com/auth/cloud-platform"),
      { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" }
    );
    if (!t.ok) throw new Error(`token ${t.status}`);
    const { access_token } = await t.json();
    const r = await fetch(
      `https://run.googleapis.com/v2/projects/${project}/locations/${region}/jobs/${job}:run`,
      { method: "POST", headers: { Authorization: `Bearer ${access_token}` } }
    );
    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      return NextResponse.json(
        { error: `Job trigger failed (${r.status}).`, detail: detail.slice(0, 300) },
        { status: 502 });
    }
    const body = await r.json().catch(() => ({}));
    return NextResponse.json({
      ok: true,
      execution: body?.metadata?.name || body?.name || null,
    });
  } catch (e) {
    return NextResponse.json({ error: "Could not reach the Jobs API." }, { status: 502 });
  }
}
