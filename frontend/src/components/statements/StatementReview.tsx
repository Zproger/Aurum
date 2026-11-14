import { Eye, EyeOff, FileText } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import type { LocalStatementDocument } from "@/hooks/useLocalStatementDocument";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { TranslationKey } from "@/lib/i18n";
import type { Category, StatementPreview, StatementRow, TransactionType } from "@/types";

// A card purchase the bank still holds: already spent, imported by default,
// but the user decides per row (see backend/app/importers/kaspi.py).
const BLOCKED_WARNING = "Blocked amount awaiting confirmation; imported as spent";

// pdf.js is large; it is downloaded only when a PDF statement is reviewed.
const PdfPreview = lazy(() => import("./PdfPreview").then((module) => ({ default: module.PdfPreview })));

const WARNING_KEYS: Record<string, TranslationKey> = {
  "Local OCR was used; review every row before importing": "statementImport.warning.ocrUsed",
  "OCR row requires explicit confirmation": "statementImport.warning.ocrConfirm",
  "Blocked amount is not a posted movement": "statementImport.warning.blocked",
  [BLOCKED_WARNING]: "statementImport.warning.blockedSpent",
  "Pending card amount is not a posted movement": "statementImport.warning.pending",
  "Statement contains pending amounts; they remain visible but are not imported": "statementImport.warning.pendingStatement",
  "Own-account transfer needs the other account and is not imported as income/expense":
    "statementImport.warning.ownTransfer",
  "Internal transfer needs both source and destination accounts": "statementImport.warning.internalTransfer",
  "Temporary reservation is not a posted cash movement": "statementImport.warning.reservation",
  "Trade settlement needs the broker trades report to avoid duplicate principal": "statementImport.warning.tradeSettlement",
  "Balance check passed: opening balance plus operations equals closing balance": "statementImport.warning.balancePassed",
  "Opening/closing balance was not found; reconciliation was not possible": "statementImport.warning.balanceUnavailable",
};

function localizedWarning(
  warning: string,
  language: "ru" | "en",
  t: (key: TranslationKey, params?: Record<string, string | number>) => string
) {
  const exactKey = WARNING_KEYS[warning];
  if (exactKey) return t(exactKey);
  if (warning.startsWith("Balance check failed:")) return t("statementImport.warning.balanceFailed");
  return language === "en" ? warning : t("statementImport.warning.unknown");
}

type RowEditorProps = {
  categories: Category[];
  currencyOptions: string[];
  index: number;
  language: "ru" | "en";
  mobile: boolean;
  preview: StatementPreview;
  row: StatementRow;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  updateAccountAmount: (index: number, amount: string) => void;
  updateRow: (index: number, patch: Partial<StatementRow>) => void;
};

function RowEditor({
  categories,
  currencyOptions,
  index,
  language,
  mobile,
  preview,
  row,
  t,
  updateAccountAmount,
  updateRow,
}: RowEditorProps) {
  const fieldClass = mobile ? "min-w-0" : "min-w-[118px]";
  const controlClass = mobile ? "min-h-11" : "";
  const labelClass = mobile ? "" : "sr-only";
  const fieldId = (field: string) => `statement-row-${mobile ? "mobile" : "desktop"}-${index}-${field}`;
  const wrapperClass = mobile
    ? "grid gap-3 rounded-xl border border-border bg-surface-1 p-4"
    : "grid min-w-[1180px] grid-cols-[130px_minmax(190px,1.6fr)_130px_120px_130px_120px_130px_minmax(170px,1fr)_170px] gap-2 border-t border-border p-2 align-top";

  return (
    <div className={wrapperClass} data-testid={mobile ? "statement-review-card" : undefined}>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("date")}>{t("transactions.form.dateLabel")}</Label>
        <Input
          id={fieldId("date")}
          className={controlClass}
          type="date"
          value={row.date}
          disabled={!row.importable}
          onChange={(event) => updateRow(index, { date: event.target.value })}
        />
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("description")}>{t("statementImport.operation")}</Label>
        <Input
          id={fieldId("description")}
          className={controlClass}
          value={row.description}
          disabled={!row.importable}
          onChange={(event) => updateRow(index, { description: event.target.value })}
        />
        {row.security_symbol && <span className="mt-1 block text-xs text-text-muted">{row.security_symbol}</span>}
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("amount")}>{t("transactions.form.amountLabel")}</Label>
        <Input
          id={fieldId("amount")}
          className={controlClass}
          type="number"
          step="0.01"
          min="0.01"
          value={row.amount}
          disabled={!row.importable}
          onChange={(event) => updateAccountAmount(index, event.target.value)}
        />
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("account-currency")}>{t("statementImport.accountCurrency")}</Label>
        <Select
          id={fieldId("account-currency")}
          className={controlClass}
          value={row.account_currency.toUpperCase()}
          disabled={!row.importable}
          onChange={(event) =>
            updateRow(index, {
              account_currency: event.target.value,
              ...(event.target.value === row.currency ? { transaction_amount: row.amount } : {}),
            })
          }
        >
          {currencyOptions.map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </Select>
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("transaction-amount")}>{t("statementImport.transactionAmount")}</Label>
        <Input
          id={fieldId("transaction-amount")}
          className={controlClass}
          type="number"
          step="0.01"
          min="0.01"
          value={row.transaction_amount}
          disabled={!row.importable}
          onChange={(event) => updateRow(index, { transaction_amount: event.target.value })}
        />
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("transaction-currency")}>{t("statementImport.transactionCurrency")}</Label>
        <Select
          id={fieldId("transaction-currency")}
          className={controlClass}
          value={row.currency.toUpperCase()}
          disabled={!row.importable}
          onChange={(event) =>
            updateRow(index, {
              currency: event.target.value,
              ...(event.target.value === row.account_currency ? { transaction_amount: row.amount } : {}),
            })
          }
        >
          {currencyOptions.map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </Select>
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("type")}>{t("statementImport.type")}</Label>
        <Select
          id={fieldId("type")}
          className={controlClass}
          value={row.type}
          disabled={!row.importable}
          onChange={(event) => updateRow(index, { type: event.target.value as TransactionType, category_id: null })}
        >
          <option value="income">{t("transactions.form.typeIncome")}</option>
          <option value="expense">{t("transactions.form.typeExpense")}</option>
        </Select>
      </div>
      <div className={fieldClass}>
        <Label className={labelClass} htmlFor={fieldId("category")}>{t("statementImport.category")}</Label>
        <Select
          id={fieldId("category")}
          className={controlClass}
          value={row.category_id ?? ""}
          disabled={!row.importable}
          onChange={(event) => updateRow(index, { category_id: event.target.value ? Number(event.target.value) : null })}
        >
          <option value="">{t("transactions.form.noCategory")}</option>
          {categories
            .filter((category) => category.kind === (row.type === "income" ? "income" : "expense"))
            .map((category) => (
              <option key={category.id} value={category.id}>{translateCategoryName(category.name)}</option>
            ))}
        </Select>
        {row.matched_rule && (
          <span className="mt-1 block text-xs text-text-muted">
            {t("statementImport.matchedRule", { name: row.matched_rule })}
          </span>
        )}
      </div>
      <div className={`${fieldClass} text-xs ${row.importable ? "text-success" : "text-warning"}`}>
        <span className={`block font-medium ${labelClass}`}>{t("statementImport.status")}</span>
        {preview.requires_row_confirmation || row.warning === BLOCKED_WARNING ? (
          <label className="flex min-h-11 cursor-pointer items-start gap-2 py-2">
            <input
              className="h-5 w-5 shrink-0"
              type="checkbox"
              checked={row.importable}
              onChange={(event) => updateRow(index, { importable: event.target.checked })}
            />
            <span>
              {t("statementImport.includeRow")}
              {row.warning && (
                <span className="mt-1 block text-warning">{localizedWarning(row.warning, language, t)}</span>
              )}
            </span>
          </label>
        ) : row.importable ? (
          t("statementImport.ready")
        ) : (
          localizedWarning(row.warning ?? "", language, t)
        )}
      </div>
    </div>
  );
}

type StatementReviewProps = {
  categories: Category[];
  currencyOptions: string[];
  document: LocalStatementDocument | null;
  language: "ru" | "en";
  preview: StatementPreview;
  rows: StatementRow[];
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  updateAccountAmount: (index: number, amount: string) => void;
  updateRow: (index: number, patch: Partial<StatementRow>) => void;
};

function DocumentPanel({
  document,
  t,
}: Pick<StatementReviewProps, "document" | "t">) {
  return (
    <div className="flex min-h-[360px] flex-col overflow-hidden rounded-xl border border-border bg-surface-2">
      <div className="flex items-center gap-2 border-b border-border p-3 text-sm font-medium">
        <FileText size={18} aria-hidden="true" />
        <span className="min-w-0 truncate">{document?.fileName ?? t("statementImport.documentUnavailable")}</span>
      </div>
      {!document ? (
        <p className="p-4 text-sm text-text-muted">{t("statementImport.documentUnavailable")}</p>
      ) : document.kind === "pdf" ? (
        <>
          <Suspense fallback={<p className="p-4 text-sm text-text-muted" role="status">{t("common.loading")}</p>}>
            <PdfPreview file={document.file} />
          </Suspense>
          <a
            className="m-3 inline-flex min-h-11 items-center justify-center rounded-lg border border-border px-4 text-sm font-medium hover:bg-surface-1"
            href={document.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("statementImport.openInNewTab")}
          </a>
        </>
      ) : document.kind === "image" ? (
        <div className="flex min-h-[360px] flex-1 items-start justify-center overflow-auto p-3">
          <img
            className="max-w-full object-contain"
            data-testid="statement-document"
            src={document.url}
            alt={t("statementImport.documentTitle")}
          />
        </div>
      ) : (
        <div className="grid flex-1 place-content-center gap-3 p-5 text-center">
          <p className="text-sm text-text-muted">{t("statementImport.documentFallback")}</p>
          <a
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-border px-4 text-sm font-medium hover:bg-surface-1"
            href={document.url}
            download={document.fileName}
          >
            {t("statementImport.openDocument")}
          </a>
        </div>
      )}
    </div>
  );
}

export function StatementReview({
  categories,
  currencyOptions,
  document,
  language,
  preview,
  rows,
  t,
  updateAccountAmount,
  updateRow,
}: StatementReviewProps) {
  const [mobileTab, setMobileTab] = useState<"transactions" | "document">("transactions");
  const [documentVisible, setDocumentVisible] = useState(true);

  const rowProps = { categories, currencyOptions, language, preview, t, updateAccountAmount, updateRow };

  return (
    <>
      {preview.warnings.map((warning) => (
        <p key={warning} className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          {localizedWarning(warning, language, t)}
        </p>
      ))}
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{t("statementImport.reviewTitle")}</h2>
        <Button
          className="hidden min-h-11 lg:inline-flex"
          variant="secondary"
          aria-controls="statement-document-panel"
          aria-expanded={documentVisible}
          onClick={() => setDocumentVisible((visible) => !visible)}
        >
          {documentVisible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
          {documentVisible ? t("statementImport.hideDocument") : t("statementImport.showDocument")}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:hidden" role="tablist" aria-label={t("statementImport.reviewViews")}>
        <Button
          id="statement-transactions-tab"
          className="min-h-11"
          variant={mobileTab === "transactions" ? "primary" : "secondary"}
          role="tab"
          aria-controls="statement-transactions-panel"
          aria-selected={mobileTab === "transactions"}
          tabIndex={mobileTab === "transactions" ? 0 : -1}
          data-review-tab="transactions"
          onClick={() => setMobileTab("transactions")}
        >
          {t("statementImport.transactionsTab")}
        </Button>
        <Button
          id="statement-document-tab"
          className="min-h-11"
          variant={mobileTab === "document" ? "primary" : "secondary"}
          role="tab"
          aria-controls="statement-document-panel"
          aria-selected={mobileTab === "document"}
          tabIndex={mobileTab === "document" ? 0 : -1}
          data-review-tab="document"
          onClick={() => setMobileTab("document")}
        >
          {t("statementImport.documentTab")}
        </Button>
      </div>

      <div
        className={`grid w-full min-w-0 max-w-full gap-4 ${documentVisible ? "lg:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]" : "lg:grid-cols-1"}`}
        data-testid="statement-review-layout"
      >
        <section
          id="statement-transactions-panel"
          className={`min-w-0 overflow-x-hidden ${mobileTab === "document" ? "hidden lg:block" : ""}`}
          style={{ contain: "inline-size paint" }}
          role="tabpanel"
          aria-labelledby="statement-transactions-tab"
        >
          <div
            className={`${documentVisible ? "hidden" : "hidden lg:block"} w-full min-w-0 max-w-full max-h-[65vh] overflow-auto rounded-lg border border-border`}
            data-testid="statement-review-table"
          >
            <div className="sticky top-0 grid min-w-[1180px] grid-cols-[130px_minmax(190px,1.6fr)_130px_120px_130px_120px_130px_minmax(170px,1fr)_170px] gap-2 bg-surface-2 p-2 text-left text-xs text-text-muted">
              <span>{t("transactions.form.dateLabel")}</span>
              <span>{t("statementImport.operation")}</span>
              <span>{t("transactions.form.amountLabel")}</span>
              <span>{t("statementImport.accountCurrency")}</span>
              <span>{t("statementImport.transactionAmount")}</span>
              <span>{t("statementImport.transactionCurrency")}</span>
              <span>{t("statementImport.type")}</span>
              <span>{t("statementImport.category")}</span>
              <span>{t("statementImport.status")}</span>
            </div>
            {rows.map((row, index) => <RowEditor key={index} {...rowProps} index={index} mobile={false} row={row} />)}
          </div>
          <div
            className={`grid gap-3 ${documentVisible ? "" : "lg:hidden"}`}
            data-testid="statement-review-cards"
          >
            {rows.map((row, index) => <RowEditor key={index} {...rowProps} index={index} mobile row={row} />)}
          </div>
        </section>

        {documentVisible && (
          <aside
            id="statement-document-panel"
            className={`min-w-0 ${mobileTab === "transactions" ? "hidden lg:block" : ""}`}
            role="tabpanel"
            aria-labelledby="statement-document-tab"
          >
            <DocumentPanel document={document} t={t} />
          </aside>
        )}
      </div>
    </>
  );
}
