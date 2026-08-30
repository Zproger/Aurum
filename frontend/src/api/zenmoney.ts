import { api } from "@/api/client";
import type { ZenmoneyStatus, ZenmoneySyncResult } from "@/types";

export function fetchZenmoneyStatus() {
  return api.get<ZenmoneyStatus>("/zenmoney/status");
}

export function syncZenmoney(forceFull = false) {
  return api.post<ZenmoneySyncResult>("/zenmoney/sync", { force_full: forceFull });
}
