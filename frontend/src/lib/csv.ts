// Minimal RFC4180-ish CSV parser — handles quoted fields (with embedded
// delimiters/newlines, "" as an escaped quote) and auto-detects comma vs
// semicolon as the delimiter (many EU bank exports use ";"). No dependency
// pulled in for this; bank CSV exports don't need more than this covers.
export function parseCsv(text: string): string[][] {
  const firstLine = text.slice(0, text.search(/\r?\n/) === -1 ? text.length : text.search(/\r?\n/));
  const commaCount = (firstLine.match(/,/g) ?? []).length;
  const semicolonCount = (firstLine.match(/;/g) ?? []).length;
  const delimiter = semicolonCount > commaCount ? ";" : ",";

  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      row.push(field);
      field = "";
    } else if (char === "\r") {
      // skip — \n (below) closes the row
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((cells) => !(cells.length === 1 && cells[0].trim() === ""));
}

export const DATE_FORMATS = ["YYYY-MM-DD", "DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY"] as const;
export type DateFormat = (typeof DATE_FORMATS)[number];

const DATE_PATTERNS: Record<DateFormat, { regex: RegExp; order: ["y" | "m" | "d", "y" | "m" | "d", "y" | "m" | "d"] }> = {
  "YYYY-MM-DD": { regex: /^(\d{4})-(\d{1,2})-(\d{1,2})$/, order: ["y", "m", "d"] },
  "DD.MM.YYYY": { regex: /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/, order: ["d", "m", "y"] },
  "DD/MM/YYYY": { regex: /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/, order: ["d", "m", "y"] },
  "MM/DD/YYYY": { regex: /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/, order: ["m", "d", "y"] },
  "DD-MM-YYYY": { regex: /^(\d{1,2})-(\d{1,2})-(\d{4})$/, order: ["d", "m", "y"] },
};

/** Parses `raw` per `format`, returning an ISO "YYYY-MM-DD" string, or null
 * if it doesn't match the pattern or isn't a real calendar date (e.g. Feb 30
 * round-trips to Mar 2, which this catches by re-checking the parts). */
export function parseDateWithFormat(raw: string, format: DateFormat): string | null {
  const { regex, order } = DATE_PATTERNS[format];
  const match = raw.trim().match(regex);
  if (!match) return null;

  const parts: Record<"y" | "m" | "d", number> = { y: 0, m: 0, d: 0 };
  order.forEach((key, index) => {
    parts[key] = Number(match[index + 1]);
  });
  const { y: year, m: month, d: day } = parts;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;

  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;

  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export const AMOUNT_FORMATS = ["auto", "dot-decimal", "comma-decimal"] as const;
export type AmountFormat = (typeof AMOUNT_FORMATS)[number];

/** Parses a bank-export amount string. `format` lets the user resolve what
 * "auto" can't: a single "," or "." with nothing else in the string is
 * genuinely ambiguous (thousands separator vs. decimal mark) — there's no
 * way to tell "1,234" (one thousand two hundred thirty-four) from "1,234"
 * (one point two three four) without knowing the exporting bank's locale.
 * "auto" keeps the historical last-separator-wins heuristic for that case
 * (e.g. "1.234,56" and "1,234.56" both resolve correctly since both
 * separators are present), but no longer corrupts amounts that have
 * *multiple* thousands separators and no decimal part at all (e.g.
 * "1,234,567" or "1.234.567") — a number can have at most one decimal
 * point, so 2+ occurrences of the same separator can only be thousands
 * grouping. */
export function parseAmount(raw: string, format: AmountFormat = "auto"): number | null {
  let value = raw.trim().replace(/[\s ]/g, "");
  if (!value) return null;

  if (format === "dot-decimal") {
    value = value.replace(/,/g, "");
  } else if (format === "comma-decimal") {
    value = value.replace(/\./g, "").replace(",", ".");
  } else {
    const commaCount = (value.match(/,/g) ?? []).length;
    const dotCount = (value.match(/\./g) ?? []).length;
    if (commaCount > 0 && dotCount > 0) {
      value = value.lastIndexOf(",") > value.lastIndexOf(".") ? value.replace(/\./g, "").replace(",", ".") : value.replace(/,/g, "");
    } else if (commaCount > 1) {
      value = value.replace(/,/g, "");
    } else if (commaCount === 1) {
      value = value.replace(",", ".");
    } else if (dotCount > 1) {
      value = value.replace(/\./g, "");
    }
  }

  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

/** Stable key for spotting a re-imported bank export that overlaps a
 * previous one — see pages/CsvImportPage.tsx's duplicate check. Matches on
 * date + type + amount (2dp) + description, the same fields the API
 * actually stores, so it works whether the "existing" side comes from a
 * Transaction or the "candidate" side from a freshly parsed CSV row. */
export function transactionDedupeKey(date: string, type: string, amount: number | string, description: string): string {
  const normalizedAmount = typeof amount === "number" ? amount : Number(amount);
  return `${date}|${type}|${normalizedAmount.toFixed(2)}|${description.trim().toLowerCase()}`;
}
