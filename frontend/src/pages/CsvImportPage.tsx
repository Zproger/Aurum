import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useBulkCreateTransactions, useTransactionsForDuplicateCheck } from "@/hooks/useTransactions";
import { translateCategoryName } from "@/lib/categoryLabels";
import {
  AMOUNT_FORMATS,
  DATE_FORMATS,
  parseAmount,
  parseCsv,
  parseDateWithFormat,
  transactionDedupeKey,
  type AmountFormat,
  type DateFormat,
} from "@/lib/csv";
import { formatCurrency } from "@/lib/format";
import { ApiError } from "@/api/client";
import { useTranslation } from "@/lib/i18n";
import type { TransactionInput } from "@/types";

type Step = "upload" | "map" | "preview";

const NONE = "";

// WHATWG encoding labels TextDecoder understands. UTF-8 covers most modern
// exports; the rest are here because bank CSVs — especially older or
// Russian-bank ones — are routinely still in a legacy Windows codepage, and
// decoding those as UTF-8 silently turns every non-ASCII character into
// mojibake instead of failing loudly.
const ENCODINGS = ["utf-8", "windows-1251", "windows-1252", "koi8-r"] as const;
type Encoding = (typeof ENCODINGS)[number];

interface Mapping {
  date: string;
  amount: string;
  description: string;
  merchant: string;
  notes: string;
  category: string;
}

interface SkippedRow {
  row: number;
  reason: string;
}

export function CsvImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const bulkCreate = useBulkCreateTransactions();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [accountId, setAccountId] = useState("");
  const [step, setStep] = useState<Step>("upload");
  const [fileName, setFileName] = useState("");
  const [fileBuffer, setFileBuffer] = useState<ArrayBuffer | null>(null);
  const [encoding, setEncoding] = useState<Encoding>("utf-8");
  const [mapping, setMapping] = useState<Mapping>({ date: "", amount: "", description: "", merchant: "", notes: "", category: "" });
  const [dateFormat, setDateFormat] = useState<DateFormat>("YYYY-MM-DD");
  const [amountFormat, setAmountFormat] = useState<AmountFormat>("auto");
  const [includeDuplicates, setIncludeDuplicates] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [createdCount, setCreatedCount] = useState<number | null>(null);

  // Re-decoded whenever `encoding` changes, so picking a different encoding
  // on the map screen (because the auto-detected guess came out wrong)
  // re-parses the same upload without asking the user to re-select the file.
  const { headers, dataRows } = useMemo(() => {
    if (!fileBuffer) return { headers: [] as string[], dataRows: [] as string[][] };
    const text = new TextDecoder(encoding).decode(fileBuffer);
    const rows = parseCsv(text);
    if (rows.length < 2) return { headers: [] as string[], dataRows: [] as string[][] };
    const [headerRow, ...rest] = rows;
    return { headers: headerRow, dataRows: rest };
  }, [fileBuffer, encoding]);

  const categoryLookup = useMemo(() => {
    const map: Record<"income" | "expense", Map<string, number>> = { income: new Map(), expense: new Map() };
    for (const category of categories ?? []) {
      map[category.kind].set(category.name.trim().toLowerCase(), category.id);
      map[category.kind].set(translateCategoryName(category.name).trim().toLowerCase(), category.id);
    }
    return map;
  }, [categories]);

  function resolveType(amount: number): "income" | "expense" {
    return amount < 0 ? "expense" : "income";
  }

  /** First non-empty raw value under `headerName`, shown next to a mapping
   * dropdown so the user can confirm they picked the right column before
   * committing to a full preview — a bank's own header names (or a header
   * row that's just "Column1", "Column2"…) aren't always self-explanatory. */
  function sampleValue(headerName: string): string {
    if (!headerName) return "";
    const idx = headers.indexOf(headerName);
    if (idx < 0) return "";
    const row = dataRows.find((cells) => (cells[idx] ?? "").trim() !== "");
    return (row?.[idx] ?? "").trim();
  }

  // Bounds the duplicate-check query (see useTransactionsForDuplicateCheck
  // below) to the date range actually present in the file, instead of every
  // transaction ever recorded on the account.
  const dateBounds = useMemo(() => {
    if (step !== "preview" || !mapping.date) return null;
    const dateIdx = headers.indexOf(mapping.date);
    if (dateIdx < 0) return null;
    let min: string | null = null;
    let max: string | null = null;
    for (const cells of dataRows) {
      const iso = parseDateWithFormat(cells[dateIdx] ?? "", dateFormat);
      if (!iso) continue;
      if (min === null || iso < min) min = iso;
      if (max === null || iso > max) max = iso;
    }
    return min && max ? { min, max } : null;
  }, [step, headers, dataRows, mapping.date, dateFormat]);

  const existingTransactions = useTransactionsForDuplicateCheck(
    accountId ? Number(accountId) : null,
    dateBounds?.min ?? null,
    dateBounds?.max ?? null
  );

  // Keyed on date+type+amount+description — see lib/csv.ts's
  // transactionDedupeKey doc comment for why those fields and not an ID.
  const existingKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const tx of existingTransactions.data ?? []) {
      keys.add(transactionDedupeKey(tx.date, tx.type, tx.amount, tx.description));
    }
    return keys;
  }, [existingTransactions.data]);

  const { valid, skipped, duplicateCount } = useMemo(() => {
    if (step !== "preview") return { valid: [] as TransactionInput[], skipped: [] as SkippedRow[], duplicateCount: 0 };

    const dateIdx = headers.indexOf(mapping.date);
    const amountIdx = headers.indexOf(mapping.amount);
    const descIdx = headers.indexOf(mapping.description);
    const merchantIdx = mapping.merchant ? headers.indexOf(mapping.merchant) : -1;
    const notesIdx = mapping.notes ? headers.indexOf(mapping.notes) : -1;
    const categoryIdx = mapping.category ? headers.indexOf(mapping.category) : -1;

    const freshRows: TransactionInput[] = [];
    const duplicateRows: TransactionInput[] = [];
    const skippedRows: SkippedRow[] = [];

    dataRows.forEach((cells, index) => {
      const rowNumber = index + 2; // header is row 1
      const rawDate = cells[dateIdx] ?? "";
      const rawAmount = cells[amountIdx] ?? "";
      const rawDescription = (cells[descIdx] ?? "").trim();
      const rawMerchant = merchantIdx >= 0 ? (cells[merchantIdx] ?? "").trim() : "";
      const rawNotes = notesIdx >= 0 ? (cells[notesIdx] ?? "").trim() : "";
      const rawCategory = categoryIdx >= 0 ? (cells[categoryIdx] ?? "").trim() : "";

      const isoDate = parseDateWithFormat(rawDate, dateFormat);
      if (!isoDate) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorBadDate", { value: rawDate || "—" }) });
        return;
      }
      const amount = parseAmount(rawAmount, amountFormat);
      if (amount === null || amount === 0) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorBadAmount", { value: rawAmount || "—" }) });
        return;
      }
      const description = rawDescription || rawMerchant;
      if (!description) {
        skippedRows.push({ row: rowNumber, reason: t("transactions.import.errorNoDescription") });
        return;
      }

      const type = resolveType(amount);
      const categoryId = rawCategory ? categoryLookup[type].get(rawCategory.toLowerCase()) ?? null : null;

      const candidate: TransactionInput = {
        account_id: Number(accountId),
        category_id: categoryId,
        transfer_account_id: null,
        type,
        amount: Math.abs(amount).toFixed(2),
        description,
        merchant: rawMerchant || null,
        notes: rawNotes || null,
        date: isoDate,
      };

      const key = transactionDedupeKey(candidate.date, candidate.type, candidate.amount, candidate.description);
      if (existingKeys.has(key)) {
        duplicateRows.push(candidate);
      } else {
        freshRows.push(candidate);
      }
    });

    return {
      valid: includeDuplicates ? [...freshRows, ...duplicateRows] : freshRows,
      skipped: skippedRows,
      duplicateCount: duplicateRows.length,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, headers, dataRows, mapping, dateFormat, amountFormat, categoryLookup, accountId, existingKeys, includeDuplicates, t]);

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setParseError(null);

    const buffer = await file.arrayBuffer();
    // Invalid-UTF-8 byte sequences almost always mean a Cyrillic bank export
    // in the classic Windows codepage — a far better first guess than
    // staying on UTF-8 and showing every letter as mojibake. The user can
    // still override this from the dropdown on the next screen either way.
    let detectedEncoding: Encoding = "utf-8";
    try {
      new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    } catch {
      detectedEncoding = "windows-1251";
    }

    const rows = parseCsv(new TextDecoder(detectedEncoding).decode(buffer));
    if (rows.length < 2) {
      setParseError(t("transactions.import.errorEmptyFile"));
      return;
    }
    const [headerRow] = rows;
    setFileName(file.name);
    setFileBuffer(buffer);
    setEncoding(detectedEncoding);
    // Best-effort auto-mapping by common header names — the user can still
    // correct any of these on the next screen.
    const guess = (...candidates: string[]) =>
      headerRow.find((h) => candidates.includes(h.trim().toLowerCase())) ?? "";
    setMapping({
      date: guess("date", "дата"),
      amount: guess("amount", "сумма"),
      description: guess("description", "описание", "назначение платежа"),
      merchant: guess("merchant", "payee", "получатель"),
      notes: guess("notes", "заметка", "примечание"),
      category: guess("category", "категория"),
    });
    setAmountFormat("auto");
    setIncludeDuplicates(false);
    setStep("map");
  }

  function startOver() {
    setStep("upload");
    setFileName("");
    setFileBuffer(null);
    setEncoding("utf-8");
    setCreatedCount(null);
    setImportError(null);
  }

  async function handleImport() {
    setImportError(null);
    try {
      const result = await bulkCreate.mutateAsync(valid);
      setCreatedCount(result.created);
    } catch (error) {
      setImportError(error instanceof ApiError ? error.message : t("transactions.import.importError"));
    }
  }

  const mappingComplete = Boolean(mapping.date && mapping.amount && mapping.description);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Link
          to="/transactions"
          aria-label={t("common.back")}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-lg font-semibold text-text-primary">{t("transactions.import.title")}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("transactions.import.accountLabel")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Select value={accountId} onChange={(event) => setAccountId(event.target.value)} className="sm:w-72">
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
          <p className="mt-2 text-xs text-text-muted">{t("transactions.import.accountHint")}</p>
        </CardContent>
      </Card>

      {step === "upload" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.uploadTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-text-secondary">{t("transactions.import.uploadHint")}</p>
            <Button onClick={() => fileInputRef.current?.click()} disabled={!accountId}>
              <Upload size={16} />
              {t("transactions.import.chooseFile")}
            </Button>
            <input ref={fileInputRef} type="file" accept=".csv,text/csv" onChange={handleFileSelected} className="hidden" />
            {!accountId && <p className="text-xs text-text-muted">{t("transactions.import.pickAccountFirst")}</p>}
            {parseError && <p className="text-sm text-danger">{parseError}</p>}
          </CardContent>
        </Card>
      )}

      {step === "map" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.mapTitle")}</CardTitle>
            <span className="text-xs text-text-muted">{fileName}</span>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label htmlFor="map-encoding">{t("transactions.import.encodingLabel")}</Label>
              <Select id="map-encoding" value={encoding} onChange={(event) => setEncoding(event.target.value as Encoding)} className="sm:w-56">
                {ENCODINGS.map((enc) => (
                  <option key={enc} value={enc}>
                    {enc.toUpperCase()}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-text-muted">{t("transactions.import.encodingHint")}</p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="map-date">{t("transactions.import.dateColumnLabel")}</Label>
                <Select id="map-date" value={mapping.date} onChange={(event) => setMapping((prev) => ({ ...prev, date: event.target.value }))}>
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                {mapping.date && (
                  <p className="mt-1 text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.date) || "—" })}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="map-date-format">{t("transactions.import.dateFormatLabel")}</Label>
                <Select id="map-date-format" value={dateFormat} onChange={(event) => setDateFormat(event.target.value as DateFormat)}>
                  {DATE_FORMATS.map((format) => (
                    <option key={format} value={format}>
                      {format}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-amount">{t("transactions.import.amountColumnLabel")}</Label>
                <Select id="map-amount" value={mapping.amount} onChange={(event) => setMapping((prev) => ({ ...prev, amount: event.target.value }))}>
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-xs text-text-muted">{t("transactions.import.amountHint")}</p>
                {mapping.amount && (
                  <p className="text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.amount) || "—" })}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="map-amount-format">{t("transactions.import.amountFormatLabel")}</Label>
                <Select id="map-amount-format" value={amountFormat} onChange={(event) => setAmountFormat(event.target.value as AmountFormat)}>
                  {AMOUNT_FORMATS.map((format) => (
                    <option key={format} value={format}>
                      {t(`transactions.import.amountFormat.${format}`)}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="map-description">{t("transactions.import.descriptionColumnLabel")}</Label>
                <Select
                  id="map-description"
                  value={mapping.description}
                  onChange={(event) => setMapping((prev) => ({ ...prev, description: event.target.value }))}
                >
                  <option value={NONE} disabled>
                    {t("transactions.import.selectColumn")}
                  </option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                {mapping.description && (
                  <p className="mt-1 text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.description) || "—" })}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="map-merchant">{t("transactions.form.merchantLabel")}</Label>
                <Select id="map-merchant" value={mapping.merchant} onChange={(event) => setMapping((prev) => ({ ...prev, merchant: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                {mapping.merchant && (
                  <p className="mt-1 text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.merchant) || "—" })}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="map-notes">{t("transactions.form.notesLabel")}</Label>
                <Select id="map-notes" value={mapping.notes} onChange={(event) => setMapping((prev) => ({ ...prev, notes: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                {mapping.notes && (
                  <p className="mt-1 text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.notes) || "—" })}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="map-category">{t("transactions.form.categoryLabel")}</Label>
                <Select id="map-category" value={mapping.category} onChange={(event) => setMapping((prev) => ({ ...prev, category: event.target.value }))}>
                  <option value={NONE}>{t("transactions.import.notMapped")}</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-xs text-text-muted">{t("transactions.import.categoryHint")}</p>
                {mapping.category && (
                  <p className="text-xs text-text-muted">
                    {t("transactions.import.sampleValueLabel", { value: sampleValue(mapping.category) || "—" })}
                  </p>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={startOver}>
                {t("transactions.import.startOver")}
              </Button>
              <Button disabled={!mappingComplete} onClick={() => setStep("preview")}>
                {t("transactions.import.previewButton")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "preview" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("transactions.import.previewTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {createdCount !== null ? (
              <div className="space-y-3">
                <p className="text-sm text-success">{t("transactions.import.importSuccess", { count: createdCount })}</p>
                <Button onClick={() => navigate("/transactions")}>{t("transactions.import.goToTransactions")}</Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-text-secondary">
                  {t("transactions.import.summary", { valid: valid.length, skipped: skipped.length })}
                </p>

                {existingTransactions.isLoading && (
                  <p className="text-xs text-text-muted">{t("transactions.import.duplicateCheckLoading")}</p>
                )}

                {duplicateCount > 0 && (
                  <div className="flex items-start gap-2 rounded-lg border border-border bg-surface-2 p-3 text-xs text-text-muted">
                    <label className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={includeDuplicates}
                        onChange={(event) => setIncludeDuplicates(event.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
                      />
                      <span>
                        {t("transactions.import.duplicatesFound", { count: duplicateCount })}{" "}
                        {t("transactions.import.includeDuplicates")}
                      </span>
                    </label>
                  </div>
                )}

                {valid.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-surface-2 text-xs text-text-muted">
                        <tr>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.dateLabel")}</th>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.descriptionLabel")}</th>
                          <th className="px-3 py-2 font-medium">{t("transactions.form.categoryLabel")}</th>
                          <th className="px-3 py-2 text-right font-medium">{t("transactions.form.amountLabel")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gridline">
                        {valid.slice(0, 20).map((item, index) => (
                          <tr key={index}>
                            <td className="whitespace-nowrap px-3 py-1.5 text-text-secondary">{item.date}</td>
                            <td className="px-3 py-1.5 text-text-primary">{item.description}</td>
                            <td className="whitespace-nowrap px-3 py-1.5 text-text-secondary">
                              {categories?.find((c) => c.id === item.category_id)
                                ? translateCategoryName(categories.find((c) => c.id === item.category_id)!.name)
                                : "—"}
                            </td>
                            <td
                              className={`whitespace-nowrap px-3 py-1.5 text-right tabular-nums ${
                                item.type === "expense" ? "text-text-primary" : "text-success"
                              }`}
                            >
                              {item.type === "expense" ? "-" : "+"}
                              {formatCurrency(item.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {valid.length > 20 && (
                      <p className="border-t border-border px-3 py-2 text-xs text-text-muted">
                        {t("transactions.import.andMore", { count: valid.length - 20 })}
                      </p>
                    )}
                  </div>
                )}

                {skipped.length > 0 && (
                  <div className="max-h-40 overflow-y-auto rounded-lg border border-border bg-surface-2 p-3 text-xs text-text-muted">
                    {skipped.map((row) => (
                      <p key={row.row}>{t("transactions.import.skippedRow", { row: row.row, reason: row.reason })}</p>
                    ))}
                  </div>
                )}

                {importError && <p className="text-sm text-danger">{importError}</p>}

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="ghost" onClick={() => setStep("map")}>
                    {t("common.back")}
                  </Button>
                  <Button disabled={valid.length === 0 || bulkCreate.isPending} onClick={() => void handleImport()}>
                    {bulkCreate.isPending
                      ? t("common.saving")
                      : t("transactions.import.importButton", { count: valid.length })}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
