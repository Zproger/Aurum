import { useSyncExternalStore } from "react";

import { forgetCredential, isVaultAvailable, recallCredential, rememberCredential } from "@/lib/credentialVault";

/**
 * Client-side mirror of the HTTP Basic Auth credentials Aurum's own login
 * screen collects (see components/auth/LoginScreen.tsx), so every fetch can
 * attach `Authorization` itself instead of relying on the browser's own
 * unstyled Basic Auth prompt. nginx's `auth_basic` (see
 * frontend/docker-entrypoint.d/20-basic-auth.sh) is still the actual gate —
 * this only avoids ever triggering that native prompt, by never letting an
 * unauthenticated request happen without us attaching the header ourselves.
 *
 * Two tiers, chosen by the "remember me" checkbox:
 *  - sessionStorage (default): plain, but gone the moment the browser closes.
 *  - the encrypted vault (lib/credentialVault.ts): survives a restart for
 *    REMEMBER_DAYS. It used to be plain localStorage, which meant the
 *    instance password sat on disk recoverable with a single atob() — the
 *    vault encrypts it under a key the browser refuses to hand back.
 *
 * The vault needs a secure context, so on plain HTTP to anything but
 * localhost the remember tier is simply unavailable (isRememberSupported()) —
 * the login screen hides the checkbox rather than silently not remembering.
 */
const SESSION_KEY = "aurum:basicAuth";
// Where the pre-vault "remember me" tier kept its plaintext copy. Read never,
// deleted always: an install upgrading past that version would otherwise
// leave the password sitting on disk for up to a week with nothing left to
// clear it.
const LEGACY_REMEMBER_KEY = "aurum:basicAuth:remember";
const REMEMBER_DAYS = 7;
const REMEMBER_MS = REMEMBER_DAYS * 24 * 60 * 60 * 1000;

function forgetLegacyRememberedCredentials(): void {
  try {
    localStorage.removeItem(LEGACY_REMEMBER_KEY);
  } catch {
    // storage unavailable — nothing was stored there either
  }
}

function readSession(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function isRememberSupported(): boolean {
  return isVaultAvailable();
}

forgetLegacyRememberedCredentials();

let currentHeader: string | null = readSession();
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getAuthHeader(): string | null {
  return currentHeader;
}

/** Reading the vault is async (IndexedDB + WebCrypto), unlike the
 * sessionStorage tier that's already resolved by the time this module
 * finishes loading. LoginGate awaits this before deciding anything, so a
 * remembered login doesn't flash the login screen on its way in. Started
 * eagerly at module load rather than on demand, so the work overlaps with
 * React mounting instead of following it. */
const restored: Promise<void> = (async () => {
  if (currentHeader !== null) return;
  const remembered = await recallCredential();
  // A login that happened while the vault was being read wins — it's newer.
  if (remembered === null || currentHeader !== null) return;
  currentHeader = remembered;
  notify();
})();

export function whenAuthRestored(): Promise<void> {
  return restored;
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

export function setCredentials(username: string, password: string, remember = false): void {
  currentHeader = buildBasicAuthHeader(username, password);
  try {
    sessionStorage.setItem(SESSION_KEY, currentHeader);
  } catch {
    // storage unavailable (private browsing, storage disabled) — the header
    // still works for the rest of this tab's life via the in-memory
    // variable above, it just won't survive a refresh.
  }
  // Fire-and-forget: nothing downstream waits on the write, and a vault that
  // refuses to store only costs this login its persistence.
  if (remember) {
    void rememberCredential(currentHeader, REMEMBER_MS);
  } else {
    void forgetCredential();
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
    forgetLegacyRememberedCredentials();
  } catch {
    // ignore — nothing to clean up if storage was never usable
  }
  // A 401 means the stored credential is wrong or revoked, so the remembered
  // copy is wrong too — leaving it would restore the same rejected header on
  // the next reload and loop the user straight back to the login screen.
  void forgetCredential();
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
