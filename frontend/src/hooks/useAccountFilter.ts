import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useAccounts } from "@/hooks/useAccounts";
import { useWorkspace } from "@/contexts/WorkspaceContext";

/**
 * One account selection shared by the Dashboard, Cash Flow and Reports.
 *
 * The *excluded* ids are stored (per workspace, in this browser only), so an
 * account created later is included automatically. ``accountIds`` is
 * ``undefined`` when nothing is excluded: the API then sums every account,
 * exactly as before the filter existed.
 */
const listeners = new Set<() => void>();
// Parsed value per key, remembered together with the raw stored string so the
// snapshot stays referentially stable for useSyncExternalStore and still
// follows whatever is actually in storage.
const cache = new Map<string, { raw: string | null; value: number[] }>();
// Used only when storage is unavailable (private mode, blocked site data).
const memoryFallback = new Map<string, string>();

function storageKey(workspaceId: string | undefined): string {
  return `aurum:account-filter:${workspaceId ?? "legacy"}`;
}

function readRaw(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return memoryFallback.get(key) ?? null;
  }
}

function read(key: string): number[] {
  const raw = readRaw(key);
  const cached = cache.get(key);
  if (cached && cached.raw === raw) return cached.value;
  let value: number[] = [];
  try {
    const parsed: unknown = JSON.parse(raw ?? "[]");
    if (Array.isArray(parsed)) value = parsed.filter((id): id is number => Number.isInteger(id));
  } catch {
    // Corrupt value: fall back to "every account".
  }
  cache.set(key, { raw, value });
  return value;
}

function write(key: string, ids: number[]): void {
  const raw = JSON.stringify([...new Set(ids)].sort((a, b) => a - b));
  try {
    localStorage.setItem(key, raw);
  } catch {
    // The selection still applies for this session.
    memoryFallback.set(key, raw);
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAccountFilter() {
  const workspace = useWorkspace();
  const key = storageKey(workspace?.activeWorkspace.id);
  const excludedRaw = useSyncExternalStore(subscribe, () => read(key));
  const { data: accounts } = useAccounts(true);

  const known = useMemo(() => new Set((accounts ?? []).map((account) => account.id)), [accounts]);
  // Ids of accounts deleted since they were excluded are simply ignored.
  const excluded = useMemo(() => excludedRaw.filter((id) => known.has(id)), [excludedRaw, known]);
  const accountIds = useMemo(() => {
    if (!accounts || excluded.length === 0) return undefined;
    const included = accounts.map((account) => account.id).filter((id) => !excluded.includes(id));
    return included.length > 0 ? included.sort((a, b) => a - b) : undefined;
  }, [accounts, excluded]);

  const setExcluded = useCallback((ids: number[]) => write(key, ids), [key]);

  return { accounts: accounts ?? [], excluded, accountIds, setExcluded };
}

/** Repeated query parameters (?account_ids=1&account_ids=2), as FastAPI expects. */
export function appendAccountIds(params: URLSearchParams, accountIds: number[] | undefined): URLSearchParams {
  accountIds?.forEach((id) => params.append("account_ids", String(id)));
  return params;
}
