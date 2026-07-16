/**
 * LoginPage — ported 1:1 from prototype
 * (standalone-src/src/pages-a.jsx · LoginPage).
 *
 * Two-column shell: left sign-in card (Zennify wordmark + eyebrow + h1
 * "The DMA, made navigable." + email .inp + Google button + .co.co-auth
 * error + info callout + footer); right dark hero panel with brand mark
 * + 4 feature tiles (4-level maturity heatmap / Insight cards /
 * Platform opportunity matrix / Why now signals).
 *
 * Real auth flow: Google OIDC via @react-oauth/google → POSTs id_token
 * to /api/v1/auth/google → backend re-checks hd=zennify.com + email_verified
 * → upserts user + sets HttpOnly session cookie → onSuccess fires →
 * whoAmI() populates auth store.
 */
import { useState } from "react";
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";
import { Icon, Spinner } from "@/components/utils";
import { exchangeGoogleIdToken, type CurrentUser } from "@/lib/auth";

interface LoginPageProps {
  onSuccess: (user: CurrentUser) => void;
}

const FALLBACK_CLIENT_ID =
  "306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com";

function resolveClientId(): string {
  const raw =
    (import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID as string | undefined) ?? "";
  const trimmed = raw.trim();
  if (trimmed.length === 0) return FALLBACK_CLIENT_ID;
  if (!trimmed.endsWith(".apps.googleusercontent.com")) {
    return FALLBACK_CLIENT_ID;
  }
  return trimmed;
}

const CLIENT_ID = resolveClientId();

const FEATURE_TILES = [
  {
    icon: "heatmap",
    label: "4-level maturity heatmap",
    sub: "Pillar → Category → Capability → Subcap · every cell evidence-backed",
  },
  {
    icon: "insight",
    label: "Insight cards · WHAT/WHY/SO WHAT",
    sub: "Annotated · evidence-linked · platform-tagged",
  },
  {
    icon: "platform",
    label: "Platform opportunity matrix",
    sub: "Fit Score per platform · readiness prerequisites · conversation starters",
  },
  {
    icon: "timeline",
    label: "Why now signals + roadmap",
    sub: "Triggers from the timeline · 3-phase transformation plan",
  },
];

function LoginCard({ onSuccess }: LoginPageProps): JSX.Element {
  const [busy, setBusy] = useState(false);

  // Dev sign-in: posts the backend's documented dev-login (404s when
  // OAuth is fully configured in prod — button is dev-builds only).
  async function devSignIn(): Promise<void> {
    setBusy(true);
    try {
      const email = window.prompt("Dev sign-in email", "richard.odhiambo@zennify.com");
      if (!email) { setBusy(false); return; }
      const res = await fetch(`/api/v1/auth/dev-login?email=${encodeURIComponent(email)}`, {
        method: "POST", credentials: "include",
      });
      if (!res.ok) throw new Error(String(res.status));
      window.location.hash = "#/";
      window.location.reload();
    } catch {
      setError("Dev sign-in unavailable (backend has OAuth configured).");
      setBusy(false);
    }
  }
  const [error, setError] = useState<string | null>(null);

  // 2026-06 — switched from `useGoogleLogin` back to the hosted
  // `<GoogleLogin>` widget. The implicit flow returns `access_token`,
  // NOT `id_token`, so our custom-button → `useGoogleLogin` path was
  // surfacing "Google returned no id_token" on every sign-in attempt.
  // The hosted widget returns the credential (id_token) reliably and
  // is what `/api/v1/auth/google` expects to verify against Google's
  // public JWKS.
  async function handleCredential(idToken: string | undefined): Promise<void> {
    if (!idToken) {
      setError("Google returned no id_token. Retry.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user = await exchangeGoogleIdToken(idToken);
      onSuccess(user);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
      <div data-page="login" className="auth-split" style={{
        minHeight: "100vh",
        background: "var(--z-bg)",
      }}>
        {/* Left — sign-in card */}
        <div style={{
          display: "flex", flexDirection: "column", justifyContent: "center",
          padding: "40px 56px", maxWidth: 560, width: "100%", margin: "0 auto",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 36 }}>
            <img src="/brand/full_dark.png" alt="Zennify" height={28} />
          </div>

          <div className="eyebrow" style={{ marginBottom: 8 }}>DMA Insights</div>
          <h1 style={{
            fontSize: 30, fontWeight: 600, color: "var(--z-dark)",
            letterSpacing: "-.02em", lineHeight: 1.15, marginBottom: 12,
          }}>
            The DMA, made navigable.
          </h1>
          <p style={{
            fontSize: 14, color: "var(--z-body)", lineHeight: 1.6,
            marginBottom: 28, maxWidth: 440,
          }}>
            Sign in to explore every assessment, drill into the evidence, and lead with the platform conversation your client needs to hear.
          </p>

          {/* Sign-in. Hosted Google widget returns `credential` (id_token)
              which our backend verifies against Google's JWKS at
              /api/v1/auth/google. Removed the prior custom button +
              `useGoogleLogin` because the implicit flow returns
              access_token only, breaking sign-in for every user. */}
          {busy ? (
            <div role="status" aria-live="polite" style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 14px", background: "var(--z-lav)", borderRadius: 8,
              fontSize: 13, color: "var(--z-body)", marginBottom: 12,
            }}>
              <Spinner /> Verifying with backend…
            </div>
          ) : (
            <div style={{ marginBottom: 12 }}>
              <GoogleLogin
                hosted_domain="zennify.com"
                onSuccess={(resp) => { void handleCredential(resp.credential); }}
                onError={() => setError("Google sign-in failed. Try again.")}
                useOneTap={false}
                width={320}
                size="large"
                text="continue_with"
                shape="rectangular"
              />
            </div>
          )}

          {/* Dev sign-in (non-prod builds only) posts the documented
              /auth/dev-login flow. Production relies solely on the hosted
              Google widget above. */}
          <noscript>
            <div className="co co-auth">Enable JavaScript to sign in.</div>
          </noscript>
          {!busy && import.meta.env.MODE !== "production" ? (
            <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => { void devSignIn(); }}
              >
                Dev sign-in
              </button>
            </div>
          ) : null}
          <div style={{
            fontSize: 11, color: "var(--z-muted)", marginBottom: 12,
          }}>
            Domain-restricted · Google OAuth · session expires after 8 hours
          </div>

          {error ? (
            <div className="co co-auth" style={{ marginBottom: 12 }} role="alert">
              <div className="co-body">
                <strong>Domain restricted</strong> — {error}
              </div>
            </div>
          ) : null}

          <div style={{
            background: "var(--z-lav)", padding: 12, borderRadius: 8,
            fontSize: 11.5, color: "var(--z-body)", display: "flex",
            gap: 8, alignItems: "flex-start",
          }}>
            <Icon name="info" size={14} style={{ color: "var(--z-mid)", flexShrink: 0, marginTop: 1 }} />
            <span>
              Your role is detected automatically from your Zennify Google account.
              You can switch roles any time from the account menu.
            </span>
          </div>

          <div style={{
            display: "flex", justifyContent: "space-between",
            marginTop: 56, fontSize: 11, color: "var(--z-muted)",
          }}>
            <span>© 2026 Zennify · Confidential</span>
            <span>Confidential</span>
          </div>
        </div>

        {/* Right — dark hero panel. Gradient uses the canonical Zennify
            tokens (--z-dark2 → --z-dark → --z-navy) so the teal matches
            the uploaded prototype exactly. The prior hardcoded HEX
            stops (#0F2A2D → #061A1C → #001E48) were ~30% darker than
            the tokens; side-by-side Playwright comparison showed the
            live panel rendering closer to black-teal than the
            prototype's brighter sea-green-teal. */}
        <div style={{
          position: "relative",
          background: "linear-gradient(135deg, var(--z-dark2), var(--z-dark) 60%, var(--z-navy))",
          overflow: "hidden",
        }}>
          {/* Zennify pavilion hero — the prototype's branded JPG. The
              earlier SVG substitute (`pavilion.svg`) was a stand-in
              because the JPG never made it into the standalone bundle;
              extracted from the uploaded prototype blob on 2026-06-05
              and committed at public/brand/illustrations/
              pavilion_zennify_branded.jpg (110KB, 1200x565). The SVG
              stays in the repo as the SSO/offline fallback referenced
              by the test harness. */}
          <img
            src="/brand/illustrations/pavilion_zennify_branded.jpg"
            alt=""
            aria-hidden="true"
            style={{
              position: "absolute", inset: 0,
              width: "100%", height: "100%",
              objectFit: "cover", opacity: .92,
            }}
          />
          <div style={{
            position: "absolute", inset: 0,
            background: "linear-gradient(135deg, rgba(28,74,77,.45), rgba(0,30,72,.55))",
          }} />

          <div style={{
            position: "relative", zIndex: 2, height: "100%",
            display: "flex", flexDirection: "column",
            padding: "44px 56px", color: "#fff",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
              <img src="/brand/icon_teal.png" alt="" width={36} height={36}
                   style={{ borderRadius: 8 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>DMA Insights</div>
                <div style={{ fontSize: 10.5, color: "#9FE5DC" }}>by Zennify</div>
              </div>
            </div>

            <div style={{ flex: 1 }} />

            <div style={{
              background: "rgba(0,30,72,.55)",
              backdropFilter: "blur(10px)",
              border: "1px solid rgba(255,255,255,.10)",
              borderRadius: 14,
              padding: "20px 22px",
              maxWidth: 460,
            }}>
              <div className="eyebrow" style={{ color: "#9FE5DC", marginBottom: 12 }}>
                What you'll find inside
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {FEATURE_TILES.map((t) => (
                  <div key={t.label} style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: 8,
                      background: "rgba(39,187,175,.18)", color: "#7FE3D6",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      flexShrink: 0, fontSize: 15,
                    }}>
                      <Icon name={t.icon} size={15} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>{t.label}</div>
                      <div style={{ fontSize: 11, color: "#9FE5DC" }}>{t.sub}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
  );
}

export function LoginPage({ onSuccess }: LoginPageProps): JSX.Element {
  return (
    <GoogleOAuthProvider clientId={CLIENT_ID}>
      <LoginCard onSuccess={onSuccess} />
    </GoogleOAuthProvider>
  );
}
