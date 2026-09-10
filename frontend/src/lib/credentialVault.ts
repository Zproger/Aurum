/**
 * Encrypted at-rest storage for the Basic Auth header, so "remember me" can
 * survive a browser restart without leaving the instance password readable on
 * disk.
 *
 * How it works: an AES-GCM key is generated with `extractable: false` and
 * kept in IndexedDB. The browser will happily store and hand back that
 * CryptoKey, but `crypto.subtle.exportKey` refuses to reveal its bytes — so
 * page code can decrypt with it and still cannot read it. Alongside it sits
 * the ciphertext of the header plus an expiry.
 *
 * What this actually buys, stated honestly:
 *  - Someone who copies the profile directory, restores a disk backup, reads
 *    synced storage, or just opens DevTools gets ciphertext. Previously they
 *    got `Basic dXNlcjpwYXNz`, which is the password in one `atob()`.
 *  - It does NOT stop code executing *inside* the page: an XSS can simply
 *    call decrypt() the same way the app does. That vector is what the
 *    Content-Security-Policy in frontend/nginx.conf is there to close;
 *    this and that are two halves of the same answer.
 *
 * Requires a secure context — `crypto.subtle` is undefined on plain HTTP to
 * anything but localhost. That's a real configuration here, not a hypothetical
 * (AURUM_BIND_ADDRESS makes LAN access over http:// possible), so callers must
 * check isVaultAvailable() and fall back to session-only storage.
 */
const DB_NAME = "aurum-auth";
const DB_VERSION = 1;
const STORE = "vault";
const KEY_ID = "wrapping-key";
const BLOB_ID = "remembered-credential";

interface StoredBlob {
  iv: Uint8Array;
  ciphertext: ArrayBuffer;
  expiresAt: number; // epoch ms
}

export function isVaultAvailable(): boolean {
  return (
    typeof indexedDB !== "undefined" &&
    typeof crypto !== "undefined" &&
    typeof crypto.subtle !== "undefined" &&
    typeof crypto.subtle.generateKey === "function"
  );
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function runRequest<T>(store: IDBObjectStore, request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    store.transaction.onabort = () => reject(store.transaction.error);
  });
}

async function withStore<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => Promise<T>): Promise<T> {
  const db = await openDb();
  try {
    return await run(db.transaction(STORE, mode).objectStore(STORE));
  } finally {
    db.close();
  }
}

/** Reuses the existing key when there is one: regenerating it on every login
 * would strand any ciphertext already written under the old key. */
async function getOrCreateKey(): Promise<CryptoKey> {
  const existing = await withStore("readonly", (store) => runRequest<CryptoKey | undefined>(store, store.get(KEY_ID)));
  if (existing) return existing;

  // extractable: false is the whole point — see the module comment.
  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  await withStore("readwrite", (store) => runRequest(store, store.put(key, KEY_ID)));
  return key;
}

export async function rememberCredential(header: string, ttlMs: number): Promise<void> {
  if (!isVaultAvailable()) return;
  try {
    const key = await getOrCreateKey();
    // A fresh IV per encryption: reusing one with AES-GCM under the same key
    // is what breaks the mode outright.
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(header));
    const blob: StoredBlob = { iv, ciphertext, expiresAt: Date.now() + ttlMs };
    await withStore("readwrite", (store) => runRequest(store, store.put(blob, BLOB_ID)));
  } catch {
    // Storage denied or unavailable (private window, quota, disabled) —
    // login still works for this session, it just won't be remembered.
  }
}

export async function recallCredential(): Promise<string | null> {
  if (!isVaultAvailable()) return null;
  try {
    const blob = await withStore("readonly", (store) => runRequest<StoredBlob | undefined>(store, store.get(BLOB_ID)));
    if (!blob) return null;
    if (Date.now() >= blob.expiresAt) {
      await forgetCredential();
      return null;
    }
    // Copied into a fresh view: structured clone hands the IV back typed over
    // ArrayBufferLike, which doesn't satisfy WebCrypto's BufferSource.
    const iv = new Uint8Array(blob.iv);
    const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, await getOrCreateKey(), blob.ciphertext);
    return new TextDecoder().decode(plaintext);
  } catch {
    // Tampered ciphertext, a key that no longer matches, or storage trouble.
    // Nothing recoverable either way — drop it and fall back to the login
    // screen rather than leaving a blob around that can never be read.
    await forgetCredential();
    return null;
  }
}

export async function forgetCredential(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    await withStore("readwrite", (store) => runRequest(store, store.delete(BLOB_ID)));
  } catch {
    // ignore — nothing usable to clean up
  }
}
