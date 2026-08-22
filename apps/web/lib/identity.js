// Role grants and display identity — ONE server-side resolution.
//
// ADMIN and ANALYST are strict allowlists (deploy-time env; the users
// table replaces this at the auth stage). Every other authenticated
// @zennify.com account is an AE — that is the default view, not a
// downgrade. Nothing is ever inferred from what an email "looks like".

const DOMAIN = "@zennify.com";

function list(name) {
  return (process.env[name] || "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function domainOk(email) {
  return typeof email === "string" && email.toLowerCase().endsWith(DOMAIN);
}

export function grantedRole(email) {
  const e = (email || "").toLowerCase();
  if (list("ADMIN_EMAILS").includes(e)) return "ADMIN";
  if (list("ANALYST_EMAILS").includes(e)) return "ANALYST";
  return "AE";
}

// Grants surfaced to ADMIN sessions only (the admin Users & roles card
// renders the real allowlists instead of a mock roster).
export function roleGrants() {
  return { admins: list("ADMIN_EMAILS"), analysts: list("ANALYST_EMAILS"), default: "AE" };
}

// Privilege order, least first. Used to clamp an "acting as" request.
const RANK = { AE: 0, ANALYST: 1, ADMIN: 2 };

// Only these may act as another role at all. An AE has one view — its own —
// so the toggle is not rendered for one, and asking for another role changes
// nothing here either.
export function mayActAs(granted) {
  return RANK[String(granted || "").toUpperCase()] >= RANK.ANALYST;
}

// The role the API should apply for this request.
//
// The rule is monotone: a request may only ever NARROW. An ADMIN previewing the
// AE view gets a server-computed AE view — the same withholding a real AE gets,
// not a client-side hide over admin data — while an AE asking for ADMIN is
// answered as an AE. Escalation is therefore impossible by construction rather
// than by the UI declining to render a control.
export function effectiveRole(granted, requested) {
  const g = String(granted || "AE").toUpperCase();
  const r = String(requested || "").toUpperCase();
  if (!(r in RANK)) return g;
  if (!mayActAs(g)) return g;
  return RANK[r] < RANK[g] ? r : g;
}

// Display name from the verified email's local part. Dotted/dashed
// parts title-case ("mishley.otiende" → "Mishley Otiende"); a short
// undelimited local part is an acronym account ("dma" → "DMA").
export function displayName(email) {
  const local = String(email || "").split("@")[0];
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length === 1 && parts[0].length <= 3) return parts[0].toUpperCase();
  return parts.map((w) => w[0].toUpperCase() + w.slice(1)).join(" ") || local;
}
