/**
 * Per-page deploy snapshot fallback.
 *
 * The build copies the committed per-page payloads (apps/.../startup-data) into
 * the served output, so every detail surface is retrievable as static JSON at
 * `/startup-data/clients/{display_id}/{page}.json`. `apiOrSnapshot` runs the
 * live API getter first and, only if it throws (cold/unreachable backend on a
 * fresh deploy), falls back to that committed snapshot — so no detail page ever
 * first-paints empty. The snapshot is the exact route-handler response, so the
 * shape is identical and the live API silently replaces it on success.
 */
const SNAP_BASE = "/startup-data/clients";

/**
 * JSON-pack-first is active everywhere EXCEPT the standalone mock-data build.
 *
 * The committed 94-client pack is the SOURCE OF TRUTH the app serves (dev,
 * prod, and the e2e all run pack-first — the e2e validates this against the
 * startup pages, which are what the backend will be linked to). Only the
 * standalone wireframe build (mock data, visual baselines) opts out so its
 * baselines don't drift.
 */
export const USE_STARTUP_PACK: boolean =
  !(typeof __STANDALONE__ !== "undefined" && __STANDALONE__);

export async function pageSnapshot<T>(
  displayId: string | null,
  page: string,
): Promise<T | null> {
  if (!displayId) return null;
  try {
    const res = await fetch(
      `${SNAP_BASE}/${encodeURIComponent(displayId)}/${page}.json`,
      { cache: "force-cache" },
    );
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function apiOrSnapshot<T>(
  getter: () => Promise<T>,
  displayId: string | null,
  page: string,
): Promise<T> {
  try {
    return await getter();
  } catch (err) {
    const snap = await pageSnapshot<T>(displayId, page);
    if (snap != null) return snap;
    throw err;
  }
}

/**
 * JSON-pack-FIRST resolver (2026-06-18 operator mandate: "on deployment the app
 * is to use the local backfill ie the JSON files").
 *
 * The committed startup-data pack is the SOURCE OF TRUTH for the 94 starter
 * clients on a fresh deploy. We serve the snapshot first so a junk / stale /
 * still-warming backend DB can NEVER override the clean baked pages (the
 * recurring "all pages show ~100 junk entities" symptom). The live API is the
 * fallback ONLY for a client that has no snapshot yet — e.g. a NEW client the
 * drive backfill has added but not yet baked into the pack. Refreshing the 94
 * is the drive backfill's job: it regenerates the startup pages.
 */
export async function snapshotOrApi<T>(
  getter: () => Promise<T>,
  displayId: string | null,
  page: string,
): Promise<T> {
  const snap = await pageSnapshot<T>(displayId, page);
  if (snap != null) return snap;
  return getter();
}
