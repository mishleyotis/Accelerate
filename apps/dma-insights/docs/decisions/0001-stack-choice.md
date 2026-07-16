# ADR 0001 — Frontend stack: Vite + React 18 + TS, not Next.js

**Status**: Accepted (2026-05-20)

## Context

The visual contract for DMA Insights is the prototype shipped in
`/tmp/design-pkg/dma-insights-website/project/`. It is a Vite + React 18 SPA
with hash routing, a single `main.jsx` that mounts a custom `useRoute()` hook,
and a flat `pages/*.jsx` structure with `chrome.jsx` + `drawers.jsx` +
`utils.jsx` shared components. The sibling app (`capability-intelligence`)
uses Next.js — but that's a different product surface with different routing
needs.

Revision 1 of the plan picked Next.js. The user rejected it because:

1. It diverges from the prototype's actual structure — a 1:1 visual port
   becomes a rewrite.
2. Server-side rendering is unnecessary for an internal, auth-gated tool.
3. Hash routing is the prototype's contract; a `pages/`-router or
   `app/`-router rewrite would erase the deep-link semantics the design
   already encodes.

## Decision

Frontend = **Vite 5 + React 18.3 + TypeScript 5.5 strict**. Hash routing via
the prototype's `useRoute()` hook ported verbatim. CSS = `tokens.css` + `app.css`
copied byte-for-byte; Tailwind only for new utility classes (never overriding
design tokens). State = Zustand (UI) + TanStack Query 5 (server). Build emits
two artifacts:

1. `dist/` — normal SPA, served by Cloud Run static.
2. `dist-standalone/DMA Insights · Standalone.html` — single-file
   wireframe-guide demo with all assets base64-inlined and mock `data.ts`
   baked in. Not used by AEs; not connected to live data.

## Consequences

- Pixel-identical port of the prototype is mechanical: add TS annotations,
  swap `DMA.XXX` mock calls for TanStack Query hooks.
- No SSR means SEO/perf trade-offs are irrelevant (auth-gated internal app).
- The hash router means deep links like `?card=IC-003&drawer=evidence` work
  out of the box without React Router or Next.js routing config.
- Standalone build needs a custom Vite post-process (gzip + base64 manifest)
  to mirror the prototype's `__bundler` self-extracting loader.
