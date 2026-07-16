/**
 * Hash router — ported verbatim from the prototype's `useRoute()` hook in
 * `_prototype/main.proto.tsx`, but typed.
 *
 * Behavior contract (preserved from prototype):
 *   - Reads from `window.location.hash` (form: `#/path?query=…`)
 *   - Updates listen on `hashchange`
 *   - `navigate("/clients")` sets `location.hash`
 *   - `navigate("/clients?x=1", { replace: true })` uses replaceState
 *   - Empty / undefined hash → `path = "/"`
 *
 * The prototype's behavior is the source of truth for the gate G03.HASH.ROUTER.
 */
import { useEffect, useState, useCallback } from "react";

export interface RouteState {
  path: string;
  query: Record<string, string>;
  hash: string;
}

export function parseHash(hash: string): RouteState {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, qs = ""] = raw.split("?");
  const query: Record<string, string> = {};
  if (qs) {
    const params = new URLSearchParams(qs);
    params.forEach((v, k) => {
      query[k] = v;
    });
  }
  return { path: path || "/", query, hash: raw };
}

export function buildHash(path: string, query: Record<string, string | undefined> = {}): string {
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") cleaned[k] = v;
  }
  const qs = new URLSearchParams(cleaned).toString();
  return qs ? `${path}?${qs}` : path;
}

export function useRoute(): RouteState & {
  navigate: (to: string, opts?: { replace?: boolean }) => void;
  setQuery: (next: Record<string, string | undefined>) => void;
} {
  const [state, setState] = useState<RouteState>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((to: string, opts?: { replace?: boolean }) => {
    const target = "#" + (to.startsWith("/") ? to : "/" + to);
    if (opts?.replace) {
      window.history.replaceState(null, "", target);
      setState(parseHash(target));
    } else {
      window.location.hash = target.slice(1);
    }
  }, []);

  const setQuery = useCallback(
    (next: Record<string, string | undefined>) => {
      const merged = { ...state.query, ...next };
      for (const [k, v] of Object.entries(next)) {
        if (v === undefined || v === null || v === "") delete merged[k];
      }
      navigate(buildHash(state.path, merged));
    },
    [navigate, state.path, state.query],
  );

  return { ...state, navigate, setQuery };
}
