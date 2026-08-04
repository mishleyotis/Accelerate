import { BANDS, bandFor } from "../lib/bands";

export const dynamic = "force-dynamic";

// Server-side call to svc_api (private Cloud Run service): mint an ID
// token from the metadata server. Local dev falls through unauthenticated.
async function fetchMeta() {
  const base = process.env.API_URL;
  if (!base) return { error: "API_URL not configured" };
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
    const r = await fetch(`${base}/v1/meta`, { headers, cache: "no-store" });
    if (!r.ok) return { error: `api ${r.status}` };
    return await r.json();
  } catch (e) {
    return { error: String(e) };
  }
}

const DASHBOARDS = [
  ["D1", "Overview", "13 surfaces — the page an AE is guaranteed to read"],
  ["D2", "Insights", "Cards are claims, not topics"],
  ["D3", "Heatmap", "The workbook grid; everything else cites its linkage"],
  ["D4", "Platform", "One shared recommendation id space"],
  ["D5", "Context", "Internal-only dashboard"],
  ["D6", "Tech stack", "Layered register plus detail sub-page"],
  ["D7", "Health", "Safeguards, evidence age, coverage"],
];

const PAGE_ORDER = ["heatmap", "overview", "insights", "platform", "context", "techstack"];

export default async function Home() {
  const meta = await fetchMeta();
  const pages = meta?.serving?.pages ?? {};
  const promoted = meta?.serving?.promoted_runs ?? 0;

  return (
    <main>
      <header
        style={{
          background: "var(--z-navy)",
          color: "#fff",
          padding: "14px 28px",
          display: "flex",
          alignItems: "baseline",
          gap: 14,
        }}
      >
        <strong style={{ fontSize: 18 }}>DMA Insights</strong>
        <span style={{ color: "var(--z-lt-blue)", fontSize: 13 }}>
          walking skeleton · serving tier live · content enters only through the connector
        </span>
      </header>

      <section style={{ maxWidth: 1080, margin: "28px auto", padding: "0 20px" }}>
        <div
          style={{
            background: "#fff",
            borderRadius: "var(--r-lg)",
            boxShadow: "var(--sh-md)",
            padding: 20,
            marginBottom: 20,
          }}
        >
          <h2 style={{ color: "var(--z-dark)", fontSize: 15, marginBottom: 10 }}>
            Build state (live from production)
          </h2>
          {meta.error ? (
            <p style={{ color: "var(--z-below)" }}>api unreachable: {meta.error}</p>
          ) : (
            <>
              <p style={{ fontSize: 13, marginBottom: 8 }}>
                {(meta.catalogues || [])
                  .map(
                    (c) =>
                      `${c.version} — ${c.cells} cells, ${c.categories} categories${c.current ? " (current)" : ""}`
                  )
                  .join(" · ") || "no catalogue loaded"}
                {" · "}
                <strong>{promoted}</strong> promoted run{promoted === 1 ? "" : "s"}
              </p>
              <table style={{ borderCollapse: "collapse", fontSize: 13 }}>
                <tbody>
                  <tr>
                    {PAGE_ORDER.map((p) => (
                      <td
                        key={p}
                        style={{
                          border: "1px solid var(--z-sep)",
                          padding: "6px 12px",
                          background: pages[p]?.rows ? "var(--z-ice)" : "#fff",
                        }}
                      >
                        {p}
                        <div style={{ color: "var(--z-muted)", fontSize: 11 }}>
                          {pages[p]?.rows ?? 0} rows
                        </div>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </>
          )}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 14,
          }}
        >
          {DASHBOARDS.map(([id, name, blurb]) => (
            <div
              key={id}
              style={{
                background: "#fff",
                borderRadius: "var(--r-lg)",
                boxShadow: "var(--sh-sm)",
                padding: 16,
                opacity: 0.85,
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span
                  style={{
                    background: "var(--z-lav)",
                    color: "var(--z-dpur)",
                    borderRadius: "var(--r-sm)",
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "2px 6px",
                  }}
                >
                  {id}
                </span>
                <strong style={{ color: "var(--z-dark)", fontSize: 14 }}>{name}</strong>
              </div>
              <p style={{ fontSize: 12, color: "var(--z-muted)", marginTop: 6 }}>{blurb}</p>
              <p style={{ fontSize: 11, color: "var(--z-purple)", marginTop: 8 }}>
                renders after first promote
              </p>
            </div>
          ))}
        </div>

        <div
          style={{
            background: "#fff",
            borderRadius: "var(--r-lg)",
            boxShadow: "var(--sh-sm)",
            padding: 16,
            marginTop: 20,
          }}
        >
          <h3 style={{ color: "var(--z-dark)", fontSize: 13, marginBottom: 8 }}>
            Maturity bands — four, strict less-than, resolved from the raw score
          </h3>
          <div style={{ display: "flex", gap: 8 }}>
            {[1.5, 2.5, 3.5, 4.2].map((s) => {
              const band = bandFor(s);
              const { fill, text } = BANDS[band];
              return (
                <span
                  key={band}
                  style={{
                    background: fill,
                    color: text,
                    borderRadius: "var(--r-sm)",
                    padding: "4px 10px",
                    fontSize: 12,
                    fontWeight: 500,
                  }}
                >
                  {band}
                </span>
              );
            })}
          </div>
        </div>
      </section>
    </main>
  );
}
