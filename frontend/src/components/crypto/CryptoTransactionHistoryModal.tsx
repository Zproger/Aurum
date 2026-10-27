import { Pencil, Trash2 } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { useCryptoTransactions, useDeleteCryptoTransaction } from "@/hooks/useCrypto";
import { formatCryptoAmount, formatTransactionDate, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding, CryptoTransaction } from "@/types";

interface CryptoTransactionHistoryModalProps {
  open: boolean;
  onClose: () => void;
  holding: CryptoHolding | null;
  hidden: boolean;
  onEdit: (transaction: CryptoTransaction) => void;
}

export function CryptoTransactionHistoryModal({ open, onClose, holding, hidden, onEdit }: CryptoTransactionHistoryModalProps) {
  const { t } = useTranslation();
  const { data: transactions, isLoading } = useCryptoTransactions(holding ? holding.asset_id : null);
  const deleteTransaction = useDeleteCryptoTransaction();

  if (!holding) return null;

  function handleDelete(transactionId: number) {
    if (window.confirm(t("crypto.history.confirmDelete"))) {
      deleteTransaction.mutate(transactionId);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("crypto.history.title", { name: holding.name })}>
      {isLoading ? (
        <p className="py-6 text-center text-sm text-text-muted">{t("common.loading")}</p>
      ) : !transactions || transactions.length === 0 ? (
        <p className="py-6 text-center text-sm text-text-muted">{t("crypto.history.empty")}</p>
      ) : (
        <ul className="max-h-96 divide-y divide-gridline overflow-y-auto">
          {transactions.map((tx) => (
            <li key={tx.id} className="flex items-center gap-3 py-2.5">
              <span
                className="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium"
                style={{
                  color: tx.type === "buy" ? "var(--success)" : "var(--danger)",
                  backgroundColor: tx.type === "buy" ? "color-mix(in srgb, var(--success) 12%, transparent)" : "color-mix(in srgb, var(--danger) 12%, transparent)",
                }}
              >
                {tx.type === "buy" ? t("crypto.form.buy") : t("crypto.form.sell")}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-text-primary">
                  {maskAmount(`${Number(tx.quantity)} ${holding.symbol} · ${formatCryptoAmount(tx.price_per_unit_original, tx.price_currency)}`, hidden)}
                </span>
                <span className="block text-xs text-text-muted">
                  {formatTransactionDate(tx.date, true)}
                  {tx.price_currency !== "USD" && ` · ${formatCryptoAmount(tx.price_per_unit, "USD")}`}
                  {tx.note && ` · ${tx.note}`}
                </span>
              </span>
              <span className="flex shrink-0 gap-1">
                <button
                  type="button"
                  aria-label={t("common.edit")}
                  onClick={() => onEdit(tx)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <Pencil size={15} />
                </button>
                <button
                  type="button"
                  aria-label={t("common.delete")}
                  onClick={() => handleDelete(tx.id)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={15} />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
