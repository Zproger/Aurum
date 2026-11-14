import { useState } from "react";
import { Wallet } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useAccountFilter } from "@/hooks/useAccountFilter";
import { useTranslation } from "@/lib/i18n";

/** "Accounts: all / 3 of 5" button with a checklist. The selection is shared
 * by the Dashboard, Cash Flow and Reports (see hooks/useAccountFilter). */
export function AccountFilter() {
  const { t } = useTranslation();
  const { accounts, excluded, setExcluded } = useAccountFilter();
  const [open, setOpen] = useState(false);

  if (accounts.length < 2) return null;
  const included = accounts.length - excluded.length;
  const label = excluded.length === 0
    ? t("accountFilter.all")
    : t("accountFilter.some", { count: included, total: accounts.length });

  function toggle(id: number) {
    if (excluded.includes(id)) {
      setExcluded(excluded.filter((item) => item !== id));
    } else if (included > 1) {
      // At least one account always stays selected.
      setExcluded([...excluded, id]);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant={excluded.length === 0 ? "secondary" : "primary"}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <Wallet size={16} aria-hidden="true" />
        <span className="truncate">{label}</span>
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title={t("accountFilter.title")}>
        <p className="mb-3 text-sm text-text-secondary">{t("accountFilter.hint")}</p>
        <ul className="space-y-1">
          {accounts.map((account) => {
            const checked = !excluded.includes(account.id);
            const locked = checked && included === 1;
            return (
              <li key={account.id} className="flex items-center gap-2">
                <label className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-lg px-2 hover:bg-surface-2">
                  <input
                    type="checkbox"
                    className="h-5 w-5 shrink-0"
                    checked={checked}
                    disabled={locked}
                    onChange={() => toggle(account.id)}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{account.name}</span>
                  <span className="shrink-0 text-xs text-text-muted">
                    {account.currency}{account.is_archived ? ` · ${t("accountFilter.archived")}` : ""}
                  </span>
                </label>
                <button
                  type="button"
                  className="min-h-11 shrink-0 rounded-lg px-2 text-xs text-text-secondary underline underline-offset-4 hover:text-text-primary"
                  onClick={() => setExcluded(accounts.filter((item) => item.id !== account.id).map((item) => item.id))}
                >
                  {t("accountFilter.only")}
                </button>
              </li>
            );
          })}
        </ul>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" disabled={excluded.length === 0} onClick={() => setExcluded([])}>
            {t("accountFilter.selectAll")}
          </Button>
          <Button type="button" onClick={() => setOpen(false)}>{t("accountFilter.done")}</Button>
        </div>
      </Dialog>
    </>
  );
}

/** Small notice that totals cover only part of the accounts. */
export function AccountFilterNotice() {
  const { t } = useTranslation();
  const { accounts, excluded } = useAccountFilter();
  if (excluded.length === 0) return null;
  const names = accounts.filter((account) => excluded.includes(account.id)).map((account) => account.name);
  return (
    <p className="rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm text-text-secondary" role="status">
      {t("accountFilter.notice", { names: names.join(", ") })}
    </p>
  );
}
