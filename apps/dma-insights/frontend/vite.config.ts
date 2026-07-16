import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Two build modes:
//   default     → SPA bundle served via Cloud Run static  (dist/)
//   standalone  → wireframe-guide single-file artifact     (dist-standalone/)
//                 with mock data baked in (apps/.../src/mock/data.ts)
const STANDALONE = process.env.STANDALONE === "1";

// Honour BACKEND_URL for the dev-server proxy so the same vite command
// works in BOTH operator dev (uvicorn on localhost:8000) AND CI
// (sidecar backend at http://dma-ci-e2e-backend:8000 on the cloudbuild
// docker network). Without this override, every API call from the
// playwright-driven browser hits a hardcoded localhost:8000 inside the
// playwright container and gets ECONNREFUSED — the entire persona
// chain depends on this.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// 2026-06-11 operator mandate ("previous frontend completely
// destroyed"): every built bundle self-identifies. The deploy parity
// gate curls /__build.txt and refuses to pass a stale image.
// Copy the committed per-page startup-data snapshot (apps/.../startup-data)
// into the build output so it ships in the deployed image and is retrievable
// as static JSON at `/startup-data/clients/{id}/{page}.json`. The per-page
// hooks fall back to it when the live API is cold/unreachable on first paint,
// so no detail page ever renders empty on deployment.
const startupDataDevHandler = () => {
  // Dev/preview twin of the closeBundle copy below: the deployed image
  // serves the baked pack at /startup-data/* via nginx, but `pnpm dev`
  // (and therefore the CI e2e-personas stage, which tests THROUGH the
  // dev server) has no such route — the per-page snapshot fetch in
  // lib/startup-pages.ts 404'd, every pack-first client page fell back
  // to the live API, and any client not in the tiny seed_ci DB rendered
  // empty (the 2026-07-05 build's 23 Playwright failures on
  // frost-bank-0001). Serving the committed pack here makes dev/e2e
  // behave exactly like production.
  return async (
    req: { url?: string },
    res: {
      setHeader: (k: string, v: string) => void;
      end: (body?: unknown) => void;
      statusCode: number;
    },
    next: () => void,
  ) => {
    try {
      const { fileURLToPath } = await import("node:url");
      const path = await import("node:path");
      const fs = await import("node:fs");
      const here = path.dirname(fileURLToPath(import.meta.url));
      const root = path.resolve(here, "..", "startup-data");
      // connect strips the mount prefix — req.url is e.g.
      // "/clients/frost-bank-0001/overview.json?x=1".
      const rel = decodeURIComponent((req.url || "/").split("?")[0]);
      const file = path.resolve(root, "." + path.sep + rel);
      if (file !== root && !file.startsWith(root + path.sep)) return next();
      const st = fs.statSync(file, { throwIfNoEntry: false });
      if (!st || !st.isFile()) return next();
      res.setHeader(
        "Content-Type",
        file.endsWith(".json")
          ? "application/json; charset=utf-8"
          : file.endsWith(".md")
            ? "text/markdown; charset=utf-8"
            : "application/octet-stream",
      );
      res.end(fs.readFileSync(file));
    } catch {
      next();
    }
  };
};

const copyStartupDataPlugin = () => {
  let resolvedOutDir = "dist";
  return {
    name: "copy-startup-data",
    configResolved(cfg: { build: { outDir: string } }) {
      resolvedOutDir = cfg.build.outDir;
    },
    configureServer(server: { middlewares: { use: (route: string, h: unknown) => void } }) {
      server.middlewares.use("/startup-data", startupDataDevHandler());
    },
    configurePreviewServer(server: { middlewares: { use: (route: string, h: unknown) => void } }) {
      server.middlewares.use("/startup-data", startupDataDevHandler());
    },
    async closeBundle() {
      const { fileURLToPath } = await import("node:url");
      const path = await import("node:path");
      const fs = await import("node:fs");
      const here = path.dirname(fileURLToPath(import.meta.url));
      const src = path.join(here, "..", "startup-data");
      const outDir = path.isAbsolute(resolvedOutDir) ? resolvedOutDir : path.join(here, resolvedOutDir);
      const dst = path.join(outDir, "startup-data");
      if (fs.existsSync(src)) {
        fs.cpSync(src, dst, { recursive: true });
      }
    },
  };
};

const buildShaPlugin = () => {
  // Captured from the resolved config so we write into the ACTUAL output
  // dir, honouring a `--outDir` CLI override (a hardcoded "dist" failed
  // loudly under `--outDir`).
  let resolvedOutDir = "dist";
  return {
    name: "emit-build-sha",
    configResolved(cfg: { build: { outDir: string } }) {
      resolvedOutDir = cfg.build.outDir;
    },
    async closeBundle() {
      // vite.config is ESM ("type":"module") → __dirname is UNDEFINED here.
      // The prior version referenced __dirname inside a try/catch that
      // swallowed the ReferenceError, so dist/__build.txt was NEVER written
      // and the parity gate's /__build.txt check was structurally impossible.
      // Derive the dir from import.meta.url and let the write fail LOUDLY —
      // a build that can't stamp its SHA must not ship.
      const { fileURLToPath } = await import("node:url");
      const path = await import("node:path");
      const fs = await import("node:fs");
      const here = path.dirname(fileURLToPath(import.meta.url));
      let sha = process.env.BUILD_SHA || "";
      if (!sha) {
        try {
          const { execSync } = await import("node:child_process");
          sha = execSync("git rev-parse --short HEAD").toString().trim();
        } catch {
          sha = "unknown"; // non-git build context (e.g. docker without .git)
        }
      }
      const dir = path.isAbsolute(resolvedOutDir)
        ? resolvedOutDir
        : path.join(here, resolvedOutDir);
      fs.writeFileSync(path.join(dir, "__build.txt"), sha + "\n");
    },
  };
};

export default defineConfig({
  plugins: [buildShaPlugin(),
    ...(STANDALONE ? [] : [copyStartupDataPlugin()]),
    react(),
    ...(STANDALONE ? [viteSingleFile()] : []),
  ],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": BACKEND_URL,
      "/auth": BACKEND_URL,
    },
    // Allow importing the committed startup-data snapshot, which lives at
    // apps/dma-insights/startup-data (one level above the frontend root).
    fs: { allow: [".."] },
  },
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: STANDALONE
          ? undefined
          : {
              react: ["react", "react-dom"],
              query: [
                "@tanstack/react-query",
                "@tanstack/react-query-persist-client",
                "@tanstack/query-async-storage-persister",
              ],
              charts: ["recharts"],
            },
      },
    },
  },
  define: {
    __STANDALONE__: JSON.stringify(STANDALONE),
  },
});
