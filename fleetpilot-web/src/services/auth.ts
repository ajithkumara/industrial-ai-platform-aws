/**
 * Cognito Hosted UI sign-in (authorization code + PKCE). No secrets: client id and endpoints are
 * public and come from /config.js, which Terraform writes next to the site (window.TRACK_CONFIG).
 * When config.js is absent (local dev, offline preview) the app runs in demo mode with no login.
 */
export interface TrackConfig { apiUrl: string; authDomain: string; clientId: string; redirectUri: string }

declare global { interface Window { TRACK_CONFIG?: TrackConfig } }

export const authConfig = (): TrackConfig | undefined => (typeof window !== "undefined" ? window.TRACK_CONFIG : undefined);
export const liveConfigured = () => !!authConfig()?.apiUrl;

const b64u = (b: Uint8Array) => btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function login(c: TrackConfig): Promise<never> {
  const v = b64u(crypto.getRandomValues(new Uint8Array(32)));
  sessionStorage.setItem("fp_pkce", v);
  const ch = b64u(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v))));
  location.href = `${c.authDomain}/oauth2/authorize?response_type=code&client_id=${c.clientId}&redirect_uri=${encodeURIComponent(c.redirectUri)}&scope=openid+email&code_challenge_method=S256&code_challenge=${ch}`;
  return new Promise<never>(() => {}); // page is navigating away
}

async function exchange(c: TrackConfig, body: Record<string, string>) {
  const r = await fetch(`${c.authDomain}/oauth2/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(body) });
  if (!r.ok) throw new Error("token exchange failed");
  const j = (await r.json()) as { id_token: string; refresh_token?: string; expires_in: number };
  sessionStorage.setItem("fp_id", j.id_token);
  sessionStorage.setItem("fp_exp", String(Date.now() + j.expires_in * 1000 - 60_000));
  if (j.refresh_token) localStorage.setItem("fp_rt", j.refresh_token);
}

/** Returns a valid ID token, completing the redirect, refreshing, or redirecting to sign-in as needed. */
export async function getToken(): Promise<string> {
  const c = authConfig();
  if (!c) throw new Error("not configured");
  const code = new URLSearchParams(location.search).get("code");
  if (code) {
    await exchange(c, { grant_type: "authorization_code", client_id: c.clientId, code, redirect_uri: c.redirectUri, code_verifier: sessionStorage.getItem("fp_pkce") ?? "" });
    history.replaceState({}, "", location.pathname + location.hash);
  }
  const id = sessionStorage.getItem("fp_id");
  if (id && Date.now() < Number(sessionStorage.getItem("fp_exp"))) return id;
  const rt = localStorage.getItem("fp_rt");
  if (rt) {
    try { await exchange(c, { grant_type: "refresh_token", client_id: c.clientId, refresh_token: rt }); return sessionStorage.getItem("fp_id")!; }
    catch { localStorage.removeItem("fp_rt"); }
  }
  return login(c);
}

/** Signed-in user from the ID token (no verification needed client-side: the API verifies it). */
export function currentUser(): { sub: string; email: string } | null {
  const id = typeof sessionStorage !== "undefined" ? sessionStorage.getItem("fp_id") : null;
  if (!id) return null;
  try {
    const p = JSON.parse(atob(id.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/"))) as { sub: string; email?: string };
    return { sub: p.sub, email: p.email ?? "" };
  } catch { return null; }
}

export function logout() {
  const c = authConfig();
  // Cached live data belongs to this login only; never leave it for the next person on a shared computer.
  try { Object.keys(localStorage).filter((k) => k.startsWith("fleetpilot.live.state")).forEach((k) => localStorage.removeItem(k)); } catch { /* ignore */ }
  sessionStorage.removeItem("fp_id"); sessionStorage.removeItem("fp_exp"); localStorage.removeItem("fp_rt");
  if (c) location.href = `${c.authDomain}/logout?client_id=${c.clientId}&logout_uri=${encodeURIComponent(c.redirectUri)}`;
}
