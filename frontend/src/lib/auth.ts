import { useSyncExternalStore } from "react";

/**
 * Client-side mirror of the HTTP Basic Auth credentials Aurum's own login
 * screen collects (see components/auth/LoginScreen.tsx), so every fetch can
 * attach `Authorization` itself instead of relying on the browser's own
 * unstyled Basic Auth prompt. nginx's `auth_basic` (see
 * frontend/docker-entrypoint.d/20-basic-auth.sh) is still the actual gate —
 * this only avoids ever triggering that native prompt, by never letting an
 * unauthenticated request happen without us attaching the header ourselves.
 *
 * Two storage tiers, chosen at login time by the "remember me" checkbox:
 *  - sessionStorage (default): gone as soon as the tab closes.
 *  - localStorage, with an explicit expiry stamped into the stored value:
 *    survives closing the tab/browser, but only for REMEMBER_DAYS — an
 *    unbounded "stay logged in forever" is too much for a finance app.
 * The expiry is only checked when this module loads (i.e. on page load/
 * reload) — a tab left open across the expiry moment without reloading
 * keeps working until its next reload or a 401 forces a fresh check.
 */
const SESSION_KEY = "aurum:basicAuth";
const REMEMBER_KEY = "aurum:basicAuth:remember";
// 7, not 30: what's stored is the Basic Auth header, i.e. the instance
// password recoverable in plaintext by anyone who can read localStorage (an
// XSS, a browser extension, someone with the machine). It can't be revoked
// server-side, so the only lever on that exposure is how long it sits there.
const REMEMBER_DAYS = 7;
const REMEMBER_MS = REMEMBER_DAYS * 24 * 60 * 60 * 1000;

interface RememberedEntry {
  header: string;
  expiresAt: number; // epoch ms
}

function readRemembered(): string | null {
  try {
    const raw = localStorage.getItem(REMEMBER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<RememberedEntry>;
    if (typeof parsed.header !== "string" || typeof parsed.expiresAt !== "number") {
      localStorage.removeItem(REMEMBER_KEY);
      return null;
    }
    if (Date.now() >= parsed.expiresAt) {
      localStorage.removeItem(REMEMBER_KEY);
      return null;
    }
    return parsed.header;
  } catch {
    return null;
  }
}

function readSession(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function readStored(): string | null {
  return readRemembered() ?? readSession();
}

let currentHeader: string | null = readStored();
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getAuthHeader(): string | null {
  return currentHeader;
}

// btoa() only handles Latin1 — the UI is bilingual RU/EN, so a Cyrillic
// password has to survive this, not just ASCII ones.
function encodeUtf8Base64(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

export function buildBasicAuthHeader(username: string, password: string): string {
  return `Basic ${encodeUtf8Base64(`${username}:${password}`)}`;
}

export function setCredentials(username: string, password: string, remember: boolean): void {
  currentHeader = buildBasicAuthHeader(username, password);
  try {
    if (remember) {
      const entry: RememberedEntry = { header: currentHeader, expiresAt: Date.now() + REMEMBER_MS };
      localStorage.setItem(REMEMBER_KEY, JSON.stringify(entry));
      sessionStorage.removeItem(SESSION_KEY);
    } else {
      sessionStorage.setItem(SESSION_KEY, currentHeader);
      localStorage.removeItem(REMEMBER_KEY);
    }
  } catch {
    // storage unavailable (private browsing, storage disabled) — the header
    // still works for the rest of this tab's life via the in-memory
    // variable above, it just won't survive a refresh.
  }
  notify();
}

/** Called on any 401 response (see api/client.ts) so a revoked or changed
 * password falls back to the login screen instead of every request failing
 * silently forever. */
export function clearCredentials(): void {
  if (currentHeader === null) return;
  currentHeader = null;
  try {
    sessionStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(REMEMBER_KEY);
  } catch {
    // ignore — nothing to clean up if storage was never usable
  }
  notify();
}

export type CredentialCheck = "ok" | "unauthorized" | "unreachable";

// A request with NO Authorization header at all, hitting an endpoint that
// replies 401 + WWW-Authenticate: Basic, is exactly what makes some
// browsers pop their own native Basic Auth dialog even for a plain
// fetch() — the one thing this whole login screen exists to avoid. A
// request that already carries *some* Authorization header, even a wrong
// one, never triggers that. So LoginGate's "is auth even required?" probe
// (called with header=null) uses this fixed placeholder instead of
// omitting the header — it's guaranteed wrong, which is exactly what's
// needed to tell "not configured" (200, header ignored) apart from
// "configured, please log in" (401).
const PROBE_HEADER = `Basic ${btoa("__aurum_probe__:__aurum_probe__")}`;

/** Hits a lightweight, always-protected endpoint with the given header (or
 * none) to find out whether Basic Auth is required/satisfied. Used both to
 * skip the login screen entirely when this instance has no auth configured
 * (see LoginGate.tsx), and to validate a login attempt before saving it
 * (see LoginScreen.tsx). */
export async function checkCredentials(header: string | null): Promise<CredentialCheck> {
  try {
    const response = await fetch("/api/accounts", {
      headers: { Authorization: header ?? PROBE_HEADER },
    });
    return response.status === 401 ? "unauthorized" : "ok";
  } catch {
    return "unreachable";
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthHeader(): string | null {
  return useSyncExternalStore(subscribe, () => currentHeader);
}
