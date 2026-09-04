import { Archive, ArchiveRestore, Banknote, CreditCard, Package, Pencil, PiggyBank, TrendingUp, Trash2, Wallet, type LucideIcon } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Account, AccountType, AccountWithBalance } from "@/types";

interface AccountListProps {
  items: AccountWithBalance[];
  onEdit: (account: Account) => void;
  onToggleArchived: (account: AccountWithBalance) => void;
  onDelete: (account: AccountWithBalance) => void;
}

const TYPE_ICONS: Record<AccountType, LucideIcon> = {
  checking: Wallet,
  debit_card: CreditCard,
  savings: PiggyBank,
  credit_card: CreditCard,
  cash: Banknote,
  investment: TrendingUp,
  other: Package,
};

export function AccountList({ items, onEdit, onToggleArchived, onDelete }: AccountListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("account.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((account) => {
        const Icon = TYPE_ICONS[account.type];
        const balance = Number(account.balance);

        return (
          <li key={account.id} className={`flex items-center gap-3 py-3 ${account.is_archived ? "opacity-50" : ""}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2">
              <Icon size={16} className="text-text-secondary" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 truncate text-sm font-medium text-text-primary">
                {account.name}
                {account.is_archived && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("account.archivedBadge")}
                  </span>
                )}
              </span>
              <span className="block truncate text-xs text-text-muted">
                {t(`account.type.${account.type}` as TranslationKey)}
              </span>
            </span>
            <span
              className="shrink-0 text-sm font-medium tabular-nums"
              style={{ color: balance < 0 ? "var(--danger)" : "var(--text-primary)" }}
            >
              {formatCurrency(balance)}
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={account.is_archived ? t("account.unarchiveLabel") : t("account.archiveLabel")}
                onClick={() => onToggleArchived(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                {account.is_archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
              </button>
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                onClick={() => onDelete(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
              >
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
