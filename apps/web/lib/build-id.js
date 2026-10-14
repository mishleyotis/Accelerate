// Which build of the browser bundle this server is serving: a hash of the
// compiled modules and stylesheet under public/proto, computed once per
// process. Every instance of one image computes the same value, and only a
// real code change moves it (an env-only revision does not).
//
// Why: the app is one page. Moving between tabs never re-downloads code, so a
// tab opened before a release keeps running the old bundle until it is
// reloaded — the owner saw the client heatmap still greyed out an hour after
// the fix was live (2026-10-07). The page compares this value with its own
// (utils.jsx UpdateWatcher) and offers the reload.
import crypto from "crypto";
import fs from "fs";
import path from "path";

const cache = new Map();

export function buildId(root = path.join(process.cwd(), "public", "proto")) {
  if (cache.has(root)) return cache.get(root);
  let id;
  try {
    const h = crypto.createHash("sha256");
    const js = path.join(root, "js");
    for (const f of fs.readdirSync(js).filter((n) => n.endsWith(".js")).sort()) {
      h.update(f).update(fs.readFileSync(path.join(js, f)));
    }
    h.update(fs.readFileSync(path.join(root, "app.css")));
    id = h.digest("hex").slice(0, 16);
  } catch {
    id = process.env.K_REVISION || null;   // Cloud Run's revision, if the files are not readable
  }
  cache.set(root, id);
  return id;
}
