import { api } from "@/api/client";
import { getAuthHeader } from "@/lib/auth";
import { todayIso } from "@/lib/format";
import { t } from "@/lib/i18n";

export async function exportBackup(): Promise<void> {
  // Raw fetch (not api/client.ts's request()) — the response is a file
  // download, not JSON — so the Authorization header has to be attached
  // here by hand too, same as every other request.
  const authHeader = getAuthHeader();
  const response = await fetch("/api/backup/export", {
    headers: authHeader ? { Authorization: authHeader } : {},
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const date = todayIso();

  const link = document.createElement("a");
  link.href = url;
  link.download = `aurum-backup-${date}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function importBackup(file: File): Promise<void> {
  const text = await file.text();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(t("backup.invalidFile"));
  }
  await api.post<{ status: string }>("/backup/import", payload);
}
