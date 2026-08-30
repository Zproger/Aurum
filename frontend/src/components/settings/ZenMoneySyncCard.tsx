import { useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, RotateCcw, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useZenmoneyStatus, useSyncZenmoney } from "@/hooks/useZenmoney";
import { useTranslation } from "@/lib/i18n";
import { ApiError } from "@/api/client";

export function ZenMoneySyncCard() {
  const { t } = useTranslation();
  const { data: status, isLoading } = useZenmoneyStatus();
  const syncMutation = useSyncZenmoney();
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function handleSync(forceFull = false) {
    if (forceFull) {
      const confirmed = window.confirm(t("zenmoney.fullResyncConfirm"));
      if (!confirmed) return;
    }

    setFeedback(null);
    try {
      const result = await syncMutation.mutateAsync(forceFull);
      setFeedback({
        kind: "success",
        text: `${t("zenmoney.syncSuccess")} (${t("zenmoney.syncedTransactions", { count: result.transactions_synced })})`,
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : t("zenmoney.syncError");
      setFeedback({ kind: "error", text: msg });
    }
  }

  const isConfigured = Boolean(status?.is_configured);
  const isSyncing = syncMutation.isPending;

  function formatLastSynced(dateStr: string | null | undefined): string {
    if (!dateStr) return t("zenmoney.neverSynced");
    try {
      const d = new Date(dateStr);
      return d.toLocaleString();
    } catch {
      return dateStr;
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-amber-500" />
          <CardTitle>{t("zenmoney.title")}</CardTitle>
        </div>
        {!isLoading && (
          <Badge
            className={
              isConfigured
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
            }
          >
            {isConfigured ? t("zenmoney.statusConnected") : t("zenmoney.statusNotConnected")}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">{t("zenmoney.description")}</p>

        {!isConfigured ? (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-text-primary dark:border-amber-500/30">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <div className="space-y-2">
                <p className="font-medium text-amber-700 dark:text-amber-400">
                  {t("zenmoney.notConfiguredTitle")}
                </p>
                <p className="text-xs text-text-secondary leading-relaxed">
                  {t("zenmoney.notConfiguredDescription")}
                </p>
                <div className="rounded bg-surface-2 px-2.5 py-1.5 font-mono text-xs text-text-primary">
                  AURUM_ZENMONEY_TOKEN=your_zenmoney_token_here
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-3 sm:grid-cols-4">
              <div className="space-y-0.5">
                <span className="text-xs text-text-muted">Статус</span>
                <p className="text-xs font-semibold text-text-primary">
                  {formatLastSynced(status?.last_synced_at)}
                </p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-text-muted">Счета</span>
                <p className="text-sm font-semibold text-text-primary">
                  {status?.synced_accounts_count ?? 0}
                </p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-text-muted">Категории</span>
                <p className="text-sm font-semibold text-text-primary">
                  {status?.synced_categories_count ?? 0}
                </p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-text-muted">Транзакции</span>
                <p className="text-sm font-semibold text-text-primary">
                  {status?.synced_transactions_count ?? 0}
                </p>
              </div>
            </div>

            {feedback && (
              <div
                className={`flex items-center gap-2 rounded-lg p-3 text-xs font-medium ${
                  feedback.kind === "success"
                    ? "border border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "border border-danger/20 bg-danger/10 text-danger"
                }`}
              >
                {feedback.kind === "success" ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 text-danger" />
                )}
                <span>{feedback.text}</span>
              </div>
            )}

            {status?.last_error && !feedback && (
              <div className="flex items-center gap-2 rounded-lg border border-danger/20 bg-danger/10 p-3 text-xs text-danger">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{status.last_error}</span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2.5 pt-1">
              <Button
                variant="primary"
                onClick={() => handleSync(false)}
                disabled={isSyncing || isLoading}
                className="gap-2"
              >
                <RefreshCw className={`h-4 w-4 ${isSyncing ? "animate-spin" : ""}`} />
                {isSyncing ? t("zenmoney.syncing") : t("zenmoney.syncButton")}
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleSync(true)}
                disabled={isSyncing || isLoading}
                className="gap-2"
              >
                <RotateCcw className="h-4 w-4" />
                {t("zenmoney.fullResyncButton")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
