import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": "/src" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // jsdom stubs (canvas / matchMedia / ResizeObserver) — silences
    // 17+ "Not implemented" lines per run so real failures surface.
    setupFiles: ["./vitest.setup.ts"],
    include: [
      "src/**/__tests__/**/*.test.{ts,tsx}",
      "src/__tests__/**/*.test.{ts,tsx}",
    ],
  },
});
