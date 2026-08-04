/* ═══════════════════════════════════════════════════════════════════════
   DMA INSIGHTS · Shared utilities, SVG icons, layout primitives
   ═══════════════════════════════════════════════════════════════════════ */
const {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  createContext,
  useContext
} = React;

/* ── App context ─────────────────────────────────────────────────────
   Holds: current route, role, audience mode, toasts, intelligence panel
*/
const AppCtx = createContext(null);
const useApp = () => useContext(AppCtx);

/* ── Portal ──────────────────────────────────────────────────────────
   Renders children at document.body so overlays (popovers, drawers,
   modals) escape any ancestor stacking context (e.g. the sticky topbar
   at z-index:50) and honour their own z-index globally. */
function Portal({
  children
}) {
  return ReactDOM.createPortal(children, document.body);
}

/* ── Hash router ─────────────────────────────────────────────────── */
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const params = {};
  if (qs) qs.split("&").forEach(kv => {
    const [k, v] = kv.split("=");
    if (k) params[decodeURIComponent(k)] = v == null ? true : decodeURIComponent(v.replace(/\+/g, " "));
  });
  return {
    path,
    params
  };
}
function buildHash(path, params) {
  const keys = params ? Object.keys(params).filter(k => params[k] != null && params[k] !== false) : [];
  const qs = keys.length ? "?" + keys.map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`).join("&") : "";
  return `#${path}${qs}`;
}
function navigate(path, params) {
  window.location.hash = buildHash(path, params || {}).slice(1);
}
function useRoute() {
  const [route, setRoute] = useState(parseHash());
  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

/* ── Icons ───────────────────────────────────────────────────────── */
function Icon({
  name,
  size = 16,
  ...rest
}) {
  const s = size;
  const props = {
    width: s,
    height: s,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    ...rest
  };
  switch (name) {
    case "home":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 11l9-8 9 8"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M5 10v10h14V10"
      }));
    case "grid":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "3",
        width: "7",
        height: "7",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "14",
        y: "3",
        width: "7",
        height: "7",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "14",
        width: "7",
        height: "7",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "14",
        y: "14",
        width: "7",
        height: "7",
        rx: "1"
      }));
    case "bell":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M6 8a6 6 0 1 1 12 0c0 6 3 7 3 7H3s3-1 3-7"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M10 21a2 2 0 0 0 4 0"
      }));
    case "search":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "11",
        cy: "11",
        r: "7"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M21 21l-4.3-4.3"
      }));
    case "user":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "8",
        r: "4"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M4 21c0-4 4-6 8-6s8 2 8 6"
      }));
    case "settings":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "3"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"
      }));
    case "drive":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M6 4l-4 8 4 8h12l4-8-4-8H6z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M6 4l8 16"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M18 4l-8 16"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M2 12h20"
      }));
    case "x":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M6 6l12 12M18 6L6 18"
      }));
    case "check":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M5 12l5 5L20 7"
      }));
    case "chevron-r":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M9 6l6 6-6 6"
      }));
    case "chevron-l":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M15 6l-6 6 6 6"
      }));
    case "chevron-d":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M6 9l6 6 6-6"
      }));
    case "chevron-u":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M6 15l6-6 6 6"
      }));
    case "arrow-r":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M5 12h14M13 6l6 6-6 6"
      }));
    case "arrow-up":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 19V5M6 11l6-6 6 6"
      }));
    case "arrow-dn":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 5v14M6 13l6 6 6-6"
      }));
    case "lock":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "5",
        y: "11",
        width: "14",
        height: "10",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M8 11V7a4 4 0 0 1 8 0v4"
      }));
    case "external":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M14 4h6v6"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M20 4L10 14"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"
      }));
    case "filter":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 5h18l-7 8v7l-4-2v-5L3 5z"
      }));
    case "plus":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 5v14M5 12h14"
      }));
    case "minus":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M5 12h14"
      }));
    case "edit":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 20h9"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"
      }));
    case "download":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 3v12"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M6 11l6 6 6-6"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 21h18"
      }));
    case "copy":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "9",
        y: "9",
        width: "13",
        height: "13",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M5 15V5a2 2 0 0 1 2-2h10"
      }));
    case "warn":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M12 9v4"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "17",
        r: ".5"
      }));
    case "info":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "9"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M12 8v.5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M12 12v4"
      }));
    case "evidence":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "4",
        y: "4",
        width: "16",
        height: "16",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M8 9h8M8 13h8M8 17h5"
      }));
    case "ai":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 2l1.6 4.4L18 8l-4.4 1.6L12 14l-1.6-4.4L6 8l4.4-1.6L12 2z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"
      }));
    case "menu":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 6h18M3 12h18M3 18h18"
      }));
    case "logout":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M16 17l5-5-5-5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M21 12H9"
      }));
    case "platform":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 12l9-9 9 9-9 9z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 12l9 4 9-4"
      }));
    case "heatmap":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "3",
        width: "6",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "11",
        y: "3",
        width: "6",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "11",
        width: "6",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "11",
        y: "11",
        width: "6",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "19",
        y: "3",
        width: "2",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "19",
        y: "11",
        width: "2",
        height: "6",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "19",
        width: "6",
        height: "2",
        rx: "1"
      }), /*#__PURE__*/React.createElement("rect", {
        x: "11",
        y: "19",
        width: "6",
        height: "2",
        rx: "1"
      }));
    case "insight":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M9 22h6"
      }));
    case "timeline":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 6h18M3 12h18M3 18h18"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "7",
        cy: "6",
        r: "1.4",
        fill: "currentColor",
        stroke: "none"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "13",
        cy: "12",
        r: "1.4",
        fill: "currentColor",
        stroke: "none"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "9",
        cy: "18",
        r: "1.4",
        fill: "currentColor",
        stroke: "none"
      }));
    case "shield":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 2l9 4v6c0 5-3.5 9-9 10-5.5-1-9-5-9-10V6l9-4z"
      }));
    case "stack":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 2l10 5-10 5L2 7l10-5z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M2 12l10 5 10-5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M2 17l10 5 10-5"
      }));
    case "drilldown":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 3h18v18H3z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M9 9h6v6H9z"
      }));
    case "users":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "9",
        cy: "8",
        r: "3"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 21c0-3 3-5 6-5s6 2 6 5"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "17",
        cy: "6",
        r: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M16 11h.5c2.5 0 4.5 2 4.5 5"
      }));
    case "envelope":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "5",
        width: "18",
        height: "14",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 7l9 6 9-6"
      }));
    case "money":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "6",
        width: "18",
        height: "12",
        rx: "2"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "2.5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M7 12h.01M17 12h.01"
      }));
    case "refresh":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 12a9 9 0 0 1 15-6.7L21 8"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M21 3v5h-5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M21 12a9 9 0 0 1-15 6.7L3 16"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 21v-5h5"
      }));
    case "scale":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 6h18"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M16 6l3 7a3 3 0 0 1-6 0l3-7zM8 6l3 7a3 3 0 0 1-6 0l3-7z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M12 6v15M9 21h6"
      }));
    case "sparkle":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4L12 3z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M19 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2zM5 16l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4z"
      }));
    case "calendar":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "5",
        width: "18",
        height: "16",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 9h18M8 3v4M16 3v4"
      }));
    case "linkedin":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "3",
        y: "3",
        width: "18",
        height: "18",
        rx: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M8 11v6M8 7v.01M12 17v-4a2 2 0 1 1 4 0v4M12 17v-6"
      }));
    case "phone":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"
      }));
    case "doc":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M14 3v5h5"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M9 13h6M9 17h6M9 9h2"
      }));
    case "route":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "6",
        cy: "19",
        r: "2"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "18",
        cy: "5",
        r: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M8 19h6a4 4 0 0 0 0-8H10a4 4 0 0 1 0-8h6"
      }));
    case "building":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("rect", {
        x: "4",
        y: "2",
        width: "16",
        height: "20",
        rx: "1"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"
      }));
    case "stairs":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M3 19h4v-4h4v-4h4v-4h4V3"
      }));
    case "play":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("polygon", {
        points: "6 4 20 12 6 20 6 4"
      }));
    case "globe":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "9"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"
      }));
    case "share":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "6",
        cy: "12",
        r: "2"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "18",
        cy: "6",
        r: "2"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: "18",
        cy: "18",
        r: "2"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M8 11l8-4M8 13l8 4"
      }));
    case "switch":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M7 8h14l-3-3M17 16H3l3 3"
      }));
    case "lightbulb":
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("path", {
        d: "M9 18h6"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M10 21h4"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M12 3a6 6 0 0 0-4 10.5c1 .9 1.5 2.2 1.5 3.5h5c0-1.3.5-2.6 1.5-3.5A6 6 0 0 0 12 3z"
      }));
    default:
      return /*#__PURE__*/React.createElement("svg", props, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "6"
      }));
  }
}

/* ── Asset resolver (resolves to bundled blob URL or falls back to path) ─ */
function assetUrl(id, fallback) {
  return typeof window !== "undefined" && window.__resources && window.__resources[id] || fallback;
}

/* ── Brand mark ──────────────────────────────────────────────────── */
function BrandMark({
  size = 28
}) {
  return /*#__PURE__*/React.createElement("img", {
    src: assetUrl("brand_iconTeal", "brand/icon_teal.png"),
    width: size,
    height: size,
    alt: "Zennify",
    style: {
      borderRadius: Math.round(size * 0.22),
      display: "block",
      flexShrink: 0,
      objectFit: "cover"
    }
  });
}
function ZennifyWordmark({
  height = 22,
  color = "dark"
}) {
  const src = color === "dark" ? assetUrl("brand_fullDark", "brand/full_dark.png") : assetUrl("brand_fullLight", "brand/full_light.png");
  return /*#__PURE__*/React.createElement("img", {
    src: src,
    height: height,
    alt: "Zennify",
    style: {
      height,
      width: "auto",
      display: "block"
    }
  });
}

/* ── Pillar badge ────────────────────────────────────────────────── */
function PillarBadge({
  pillar
}) {
  const p = DMA.PILLARS.find(x => x.id === pillar);
  return /*#__PURE__*/React.createElement("span", {
    className: "b b-purple"
  }, pillar);
}

/* ── Maturity cell helper (small inline) ─────────────────────────── */
function MaturityChip({
  score,
  large
}) {
  if (score == null) return /*#__PURE__*/React.createElement("span", {
    className: "chip muted"
  }, "-");
  const cls = DMA.helpers.maturityClass(score);
  return /*#__PURE__*/React.createElement("span", {
    className: `b ${cls}`,
    style: large ? {
      padding: "5px 9px",
      fontSize: 13
    } : null
  }, score.toFixed(1));
}

/* ── Toast manager ───────────────────────────────────────────────── */
function ToastStack({
  toasts,
  remove
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "toast-stack"
  }, toasts.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    className: `toast ${t.kind || ""}`,
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: t.kind === "warn" ? "warn" : t.kind === "error" ? "warn" : "check",
    size: 16
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1
    }
  }, t.text), /*#__PURE__*/React.createElement("button", {
    onClick: () => remove(t.id),
    "aria-label": "Dismiss",
    className: "icon-btn",
    style: {
      width: 24,
      height: 24,
      color: "rgba(255,255,255,.7)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 14
  })))));
}

/* ── Format helpers ──────────────────────────────────────────────── */
function fmtDate(s) {
  if (!s) return "-";
  const d = new Date(s);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}
function fmtAssets(n) {
  if (n == null || n === 0) return "-";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}
function fmtPct(n) {
  return `${(n * 100).toFixed(0)}%`;
}
function relTime(s) {
  if (!s) return "-";
  const months = Math.round((new Date() - new Date(s)) / (1000 * 60 * 60 * 24 * 30.4));
  if (months < 1) return "just now";
  if (months < 12) return `${months} mo ago`;
  return `${Math.round(months / 12 * 10) / 10} yr ago`;
}

/* ── Freshness dot ───────────────────────────────────────────────── */
function FreshnessDot({
  date,
  withLabel
}) {
  if (!date) return null;
  const f = DMA.helpers.freshnessOf(date);
  const color = f.tone === "ok" ? "var(--z-mid)" : f.tone === "warn" ? "var(--z-org)" : "var(--z-below)";
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 4,
      background: color,
      display: "inline-block"
    }
  }), withLabel ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--z-muted)"
    }
  }, f.label, " \xB7 ", f.months, " mo") : null);
}

/* ── Loading screens ─────────────────────────────────────────────── */
function LoadingScreen({
  variant,
  title,
  body,
  detail,
  dark
}) {
  // variants: "boot" | "section" | "offline" | "stale" | "default"
  const presets = {
    boot: {
      title: "Loading DMA Insights…",
      body: "Stitching together the assessment workspace.",
      detail: "Hydrating data layer · checking cached runs"
    },
    section: {
      title: "Loading…",
      body: "Pulling the latest data for this view.",
      detail: "Hot cache · usually < 500ms"
    },
    offline: {
      title: "You're offline",
      body: "We've lost the connection. Reconnect to keep working.",
      detail: "Cached views remain available · no live updates"
    },
    slow: {
      title: "Slow connection",
      body: "The network is sluggish — we're still working on it.",
      detail: "Falling back to cached responses where possible"
    },
    unreachable: {
      title: "Service temporarily unreachable",
      body: "The DMA Insights service isn't responding. We'll retry automatically.",
      detail: "Last attempt failed · next retry in 12 s"
    },
    stale: {
      title: "Sign-in is taking longer than usual",
      body: "Google OAuth is responding slowly. We're still waiting.",
      detail: "Retry pending"
    },
    auth: {
      title: "Signing you in…",
      body: "Verifying your Zennify account and loading your role.",
      detail: "OAuth callback received · upserting session"
    },
    default: {
      title: "Loading…",
      body: "Just a moment.",
      detail: ""
    }
  };
  const p = presets[variant] || presets.default;
  return /*#__PURE__*/React.createElement("div", {
    className: `loader-page ${dark ? "full-dark" : ""}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "loader-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: `loader-glyph ${dark ? "dark" : ""}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "ring"
  }), /*#__PURE__*/React.createElement("div", {
    className: "ring-2"
  }), /*#__PURE__*/React.createElement("div", {
    className: "core"
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("brand_iconTeal", "brand/icon_teal.png"),
    width: "36",
    height: "36",
    alt: "",
    style: {
      borderRadius: 8,
      display: "block"
    }
  }))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "loader-title"
  }, title || p.title), /*#__PURE__*/React.createElement("div", {
    className: "loader-body",
    style: {
      marginTop: 6
    }
  }, body || p.body)), /*#__PURE__*/React.createElement("div", {
    className: "loader-progress"
  }), /*#__PURE__*/React.createElement("div", {
    className: "loader-detail"
  }, detail || p.detail)));
}

/* ── Inline section loader (for tab/route transitions) ─────────── */
function SectionLoader({
  label,
  sub
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "loader-section"
  }, /*#__PURE__*/React.createElement("div", {
    className: "loader-glyph"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ring"
  }), /*#__PURE__*/React.createElement("div", {
    className: "ring-2"
  }), /*#__PURE__*/React.createElement("div", {
    className: "core"
  }, /*#__PURE__*/React.createElement("img", {
    src: assetUrl("brand_iconTeal", "brand/icon_teal.png"),
    width: "34",
    height: "34",
    alt: "",
    style: {
      borderRadius: 7
    }
  }))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      color: "var(--z-dark)"
    }
  }, label || "Loading…"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--z-muted)",
      marginTop: 4
    }
  }, sub || "Pulling fresh data")), /*#__PURE__*/React.createElement("div", {
    className: "loader-progress"
  }));
}

/* ── Connection / latency watcher ────────────────────────────────── */
function ConnectionWatcher() {
  const [state, setState] = useState("ok"); // ok | slow | offline | unreachable
  const [retryIn, setRetryIn] = useState(null);
  useEffect(() => {
    const onOffline = () => setState("offline");
    const onOnline = () => setState("ok");
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    if (typeof navigator !== "undefined" && navigator.onLine === false) setState("offline");
    // Watch effective connection type for "slow" condition
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (c) {
      const onChange = () => {
        const et = c.effectiveType;
        if (state === "offline") return;
        if (et === "slow-2g" || et === "2g") setState("slow");else if (state === "slow") setState("ok");
      };
      c.addEventListener && c.addEventListener("change", onChange);
      onChange();
      return () => {
        window.removeEventListener("offline", onOffline);
        window.removeEventListener("online", onOnline);
        c.removeEventListener && c.removeEventListener("change", onChange);
      };
    }
    return () => {
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, []);

  // Simulated retry countdown if offline
  useEffect(() => {
    if (state !== "offline" && state !== "unreachable") {
      setRetryIn(null);
      return;
    }
    setRetryIn(12);
    const id = setInterval(() => setRetryIn(r => r == null ? null : r <= 1 ? 12 : r - 1), 1000);
    return () => clearInterval(id);
  }, [state]);
  if (state === "ok") return null;
  if (state === "offline") {
    return /*#__PURE__*/React.createElement("div", {
      className: "offline-banner"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "warn",
      size: 14
    }), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("strong", null, "You're offline."), " Cached views still work \u2014 live updates paused. Reconnecting", retryIn != null ? ` in ${retryIn}s` : "", "\u2026"));
  }
  if (state === "slow") {
    return /*#__PURE__*/React.createElement("div", {
      className: "offline-banner warn"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "info",
      size: 14
    }), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("strong", null, "Slow connection."), " Some views may take a few extra seconds to load."));
  }
  if (state === "unreachable") {
    return /*#__PURE__*/React.createElement("div", {
      className: "offline-banner"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "warn",
      size: 14
    }), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("strong", null, "Service temporarily unreachable."), " Retrying", retryIn != null ? ` in ${retryIn}s` : "…"));
  }
  return null;
}

/* ── Export to window ────────────────────────────────────────────── */
Object.assign(window, {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  createContext,
  useContext,
  AppCtx,
  useApp,
  Icon,
  BrandMark,
  ZennifyWordmark,
  PillarBadge,
  MaturityChip,
  ToastStack,
  LoadingScreen,
  SectionLoader,
  ConnectionWatcher,
  parseHash,
  buildHash,
  navigate,
  useRoute,
  fmtDate,
  fmtAssets,
  fmtPct,
  relTime,
  FreshnessDot,
  assetUrl
});