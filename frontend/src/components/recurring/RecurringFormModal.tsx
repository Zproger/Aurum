import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useCreateRecurring, useUpdateRecurring } from "@/hooks/useRecurring";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import { CURRENCIES, getCurrencyLabel } from "@/lib/currency";
import type { RecurringFrequency, RecurringTransaction, TransactionType } from "@/types";

interface RecurringFormModalProps {
  open: boolean;
  onClose: () => void;
  recurring?: RecurringTransaction | null;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  type: "expense" as TransactionType,
  account_id: "",
  category_id: "",
  transfer_account_id: "",
  amount: "",
  currency: "USD",
  description: "",
  merchant: "",
  frequency: "monthly" as RecurringFrequency,
  anchor_date: todayIso(),
};

export function RecurringFormModal({ open, onClose, recurring }: RecurringFormModalProps) {
  const { t, language } = useTranslation();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const createRecurring = useCreateRecurring();
  const updateRecurring = useUpdateRecurring();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (recurring) {
      setForm({
        type: recurring.type,
        account_id: String(recurring.account_id),
        category_id: recurring.category_id ? String(recurring.category_id) : "",
        transfer_account_id: recurring.transfer_account_id ? String(recurring.transfer_account_id) : "",
        amount: recurring.amount,
        currency: recurring.currency,
        description: recurring.description,
        merchant: recurring.merchant ?? "",
        frequency: recurring.frequency,
        anchor_date: recurring.anchor_date,
      });
    } else {
      setForm({ ...EMPTY_FORM, account_id: accounts?.[0] ? String(accounts[0].id) : "", currency: accounts?.[0]?.currency ?? "USD" });
    }
    setError(null);
  }, [open, recurring, accounts]);

  const relevantCategories = (categories ?? []).filter((category) =>
    form.type === "income" ? category.kind === "income" : category.kind === "expense"
  );

  const isSaving = createRecurring.isPending || updateRecurring.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!form.account_id) {
      setError(t("transactions.form.errorSelectAccount"));
      return;
    }
    if (form.type === "transfer" && !form.transfer_account_id) {
      setError(t("transactions.form.errorSelectDestination"));
      return;
    }
    if (form.type === "transfer" && form.transfer_account_id === form.account_id) {
      setError(t("transactions.form.errorSameAccount"));
      return;
    }

    const payload = {
      type: form.type,
      account_id: Number(form.account_id),
      category_id: form.type === "transfer" ? null : form.category_id ? Number(form.category_id) : null,
      transfer_account_id: form.type === "transfer" ? Number(form.transfer_account_id) : null,
      amount: form.amount,
      currency: form.currency,
      description: form.description,
      merchant: form.merchant || null,
      frequency: form.frequency,
      anchor_date: form.anchor_date,
    };

    try {
      if (recurring) {
        await updateRecurring.mutateAsync({ id: recurring.id, input: payload });
      } else {
        await createRecurring.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("recurring.form.saveError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={recurring ? t("recurring.form.editTitle") : t("recurring.form.newTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="recurring-type">{t("transactions.form.typeLabel")}</Label>
            <Select
              id="recurring-type"
              value={form.type}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, type: event.target.value as TransactionType, category_id: "" }))
              }
            >
              <option value="expense">{t("transactions.form.typeExpense")}</option>
              <option value="income">{t("transactions.form.typeIncome")}</option>
              <option value="transfer">{t("transactions.form.typeTransfer")}</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="recurring-frequency">{t("recurring.form.frequencyLabel")}</Label>
            <Select
              id="recurring-frequency"
              value={form.frequency}
              onChange={(event) => setForm((prev) => ({ ...prev, frequency: event.target.value as RecurringFrequency }))}
            >
              <option value="weekly">{t("recurring.frequency.weekly")}</option>
              <option value="monthly">{t("recurring.frequency.monthly")}</option>
              <option value="yearly">{t("recurring.frequency.yearly")}</option>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="recurring-amount">{t("transactions.form.amountLabel")}</Label>
            <Input
              id="recurring-amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="recurring-anchor-date">{t("recurring.form.anchorDateLabel")}</Label>
            <Input
              id="recurring-anchor-date"
              type="date"
              required
              value={form.anchor_date}
              onChange={(event) => setForm((prev) => ({ ...prev, anchor_date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="recurring-currency">{language === "ru" ? "Валюта операции" : "Transaction currency"}</Label>
          <Select id="recurring-currency" value={form.currency} onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}>
            {CURRENCIES.map((currency) => <option key={currency.code} value={currency.code}>{getCurrencyLabel(currency.code, language)}</option>)}
          </Select>
        </div>

        <div>
          <Label htmlFor="recurring-description">{t("transactions.form.descriptionLabel")}</Label>
          <Input
            id="recurring-description"
            required
            placeholder={t("transactions.form.descriptionPlaceholder")}
            value={form.description}
            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="recurring-account">{t("transactions.form.accountLabel")}</Label>
          <Select
            id="recurring-account"
            required
            value={form.account_id}
            onChange={(event) => {
              const account = accounts?.find((item) => String(item.id) === event.target.value);
              setForm((prev) => ({ ...prev, account_id: event.target.value, currency: account?.currency ?? prev.currency }));
            }}
          >
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </div>

        {form.type === "transfer" ? (
          <div>
            <Label htmlFor="recurring-transfer-account">{t("transactions.form.transferAccountLabel")}</Label>
            <Select
              id="recurring-transfer-account"
              required
              value={form.transfer_account_id}
              onChange={(event) => setForm((prev) => ({ ...prev, transfer_account_id: event.target.value }))}
            >
              <option value="" disabled>
                {t("transactions.form.selectAccount")}
              </option>
              {accounts
                ?.filter((account) => String(account.id) !== form.account_id)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
            </Select>
          </div>
        ) : (
          <div>
            <Label htmlFor="recurring-category">{t("transactions.form.categoryLabel")}</Label>
            <Select
              id="recurring-category"
              value={form.category_id}
              onChange={(event) => setForm((prev) => ({ ...prev, category_id: event.target.value }))}
            >
              <option value="">{t("transactions.form.noCategory")}</option>
              {relevantCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </Select>
          </div>
        )}

        <div>
          <Label htmlFor="recurring-merchant">{t("transactions.form.merchantLabel")}</Label>
          <Input
            id="recurring-merchant"
            value={form.merchant}
            onChange={(event) => setForm((prev) => ({ ...prev, merchant: event.target.value }))}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
