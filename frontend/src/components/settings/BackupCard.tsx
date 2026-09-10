import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/api/client";
import { exportBackup, importBackup } from "@/api/backup";
import { useTranslation } from "@/lib/i18n";

export function BackupCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function handleExport() {
    setIsExporting(true);
    setMessage(null);
    try {
      await exportBackup();
      setMessage({ kind: "success", text: t("backup.exportSuccess") });
    } catch {
      // Never surface error.message here — it's the raw backend/HTTP
      // response text (English, unlocalized), unlike every other error
      // path in the app, which always shows a translated fallback.
      setMessage({ kind: "error", text: t("backup.exportError") });
    } finally {
      setIsExporting(false);
    }
  }

  function handleImportClick() {
    fileInputRef.current?.click();
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    const confirmed = window.confirm(t("backup.confirmImport", { filename: file.name }));
    if (!confirmed) return;

    setIsImporting(true);
    setMessage(null);
    try {
      await importBackup(file);
      await queryClient.invalidateQueries();
      setMessage({ kind: "success", text: t("backup.importSuccess") });
    } catch (error) {
      // importBackup throws a plain Error with an already-translated message
      // for a malformed file (t("backup.invalidFile")) — relay that one
      // as-is. A failed API call throws ApiError with the raw backend detail
      // text (English, unlocalized) instead — never show that, fall back to
      // the generic translated message like every other error path in the app.
      const text = error instanceof ApiError ? t("backup.importError") : error instanceof Error ? error.message : t("backup.importError");
      setMessage({ kind: "error", text });
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("backup.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">{t("backup.description")}</p>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button onClick={handleExport} disabled={isExporting} className="sm:w-auto">
            <Download size={16} />
            {isExporting ? t("backup.exporting") : t("backup.exportButton")}
          </Button>
          <Button variant="secondary" onClick={handleImportClick} disabled={isImporting} className="sm:w-auto">
            <Upload size={16} />
            {isImporting ? t("backup.importing") : t("backup.importButton")}
          </Button>
          {/* Visually hidden via opacity/size, not `display:none` — Firefox on
              Linux can silently fail to open the native file dialog when
              .click() targets a file input removed from layout entirely. */}
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            onChange={handleFileSelected}
            className="absolute h-px w-px overflow-hidden opacity-0"
            tabIndex={-1}
          />
        </div>

        {message && (
          <p className={`text-sm ${message.kind === "error" ? "text-danger" : "text-success"}`}>{message.text}</p>
        )}

        <p className="text-xs text-text-muted">{t("backup.footerWarning")}</p>
      </CardContent>
    </Card>
  );
}
