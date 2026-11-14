import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { commitStatement, previewStatement } from "@/api/statementImports";
import { setLanguage } from "@/lib/i18n";
import { StatementImportPage } from "@/pages/StatementImportPage";
import type { StatementPreview, StatementRow } from "@/types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("@/api/statementImports", () => ({
  previewStatement: vi.fn(),
  commitStatement: vi.fn(),
}));

vi.mock("@/hooks/useAccounts", () => ({
  useAccounts: () => ({ data: [{ id: 7, name: "Everyday", currency: "KZT" }] }),
}));

vi.mock("@/hooks/useCategories", () => ({ useCategories: () => ({ data: [] }) }));
vi.mock("@/components/statements/PdfPreview", () => ({
  PdfPreview: ({ file }: { file: File }) => <div data-testid="statement-document" data-file={file.name} />,
}));

async function screenPdfPreview(container: HTMLElement): Promise<string | null> {
  // The preview is lazy-loaded; let the dynamic import settle.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  return container.querySelector('[data-testid="statement-document"]')?.getAttribute("data-file") ?? null;
}

const row = (overrides: Partial<StatementRow> = {}): StatementRow => ({
  source_row: "page 1, operation 1",
  external_id: "",
  date: "2026-01-02",
  type: "expense",
  amount: "12.34",
  account_currency: "KZT",
  currency: "KZT",
  transaction_amount: "12.34",
  description: "Sample purchase",
  details: null,
  purpose: "ordinary",
  security_symbol: null,
  category_id: null,
  importable: true,
  warning: null,
  matched_rule: null,
  ...overrides,
});

const preview = (overrides: Partial<StatementPreview> = {}): StatementPreview => ({
  provider: "sample_pdf",
  provider_label: "Sample PDF",
  file_name: "sample.pdf",
  rows: [row()],
  warnings: [],
  requires_row_confirmation: false,
  ...overrides,
});

function renderPage(initialEntry = "/transactions/import/statements?bank=kaspi") {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <QueryClientProvider client={client}>
          <StatementImportPage />
        </QueryClientProvider>
      </MemoryRouter>
    );
  });
  return { container, root };
}

async function upload(container: HTMLElement, file: File) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).not.toBeNull();
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  await act(async () => input?.dispatchEvent(new Event("change", { bubbles: true })));
}

function unmount(root: Root, container: HTMLElement) {
  act(() => root.unmount());
  container.remove();
}

beforeEach(() => {
  vi.mocked(previewStatement).mockResolvedValue(preview());
  vi.mocked(commitStatement).mockResolvedValue({ created: 1, duplicates: 0, ignored: 0 });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn((file: File) => `blob:local/${file.name}`),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

afterEach(() => {
  setLanguage("ru");
  vi.clearAllMocks();
  document.body.innerHTML = "";
});

describe("StatementImportPage document review", () => {
  it("creates a local URL and revokes it on replacement, unsupported transition, and unmount", async () => {
    setLanguage("en");
    const { container, root } = renderPage();

    await upload(container, new File(["pdf"], "first.pdf", { type: "application/pdf" }));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    // PDFs are drawn by pdf.js (mocked here) from the in-memory File, not framed.
    expect(await screenPdfPreview(container)).toBe("first.pdf");
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector<HTMLAnchorElement>('a[target="_blank"]')?.href).toContain("blob:local/first.pdf");

    await upload(container, new File(["image"], "second.png", { type: "image/png" }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:local/first.pdf");
    expect(container.querySelector<HTMLImageElement>('[data-testid="statement-document"]')?.src).toContain(
      "blob:local/second.png"
    );

    await upload(
      container,
      new File(["sheet"], "statement.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      })
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:local/second.png");
    expect(container.querySelector('[data-testid="statement-document"]')).toBeNull();
    expect(container.textContent).toContain("Inline preview is unavailable");
    expect(container.querySelector<HTMLAnchorElement>('a[download="statement.xlsx"]')?.href).toContain(
      "blob:local/statement.xlsx"
    );

    unmount(root, container);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:local/statement.xlsx");
  });

  it("fails closed for spoofed PDFs and script-capable SVG images", async () => {
    setLanguage("en");
    const { container, root } = renderPage();

    await upload(container, new File(["<script>parent.postMessage('x','*')</script>"], "spoofed.pdf", { type: "text/html" }));
    expect(container.querySelector('[data-testid="statement-document"]')).toBeNull();
    expect(container.textContent).toContain("Inline preview is unavailable");

    await upload(container, new File(["<svg xmlns='http://www.w3.org/2000/svg'/>"], "image.svg", { type: "image/svg+xml" }));
    expect(container.querySelector('[data-testid="statement-document"]')).toBeNull();
    expect(container.textContent).toContain("Inline preview is unavailable");

    unmount(root, container);
  });

  it("revokes the local document URL when the user cancels review", async () => {
    setLanguage("en");
    const { container, root } = renderPage();
    await upload(container, new File(["pdf"], "cancelled.pdf", { type: "application/pdf" }));

    const cancelButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "Cancel"
    );
    expect(cancelButton).toBeDefined();
    act(() => cancelButton?.click());

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:local/cancelled.pdf");
    expect(container.querySelector('[data-testid="statement-document"]')).toBeNull();

    unmount(root, container);
  });

  it("renders a desktop split, accessible document toggle, mobile tabs, and mobile review cards", async () => {
    setLanguage("en");
    const { container, root } = renderPage();
    await upload(container, new File(["pdf"], "sample.pdf", { type: "application/pdf" }));

    const layout = container.querySelector('[data-testid="statement-review-layout"]');
    expect(layout?.className).toContain("lg:grid-cols");
    const table = container.querySelector('[data-testid="statement-review-table"]');
    const cards = container.querySelector('[data-testid="statement-review-cards"]');
    expect(table?.className).toContain("hidden");
    expect(cards?.className).not.toContain("lg:hidden");

    const mobileCard = container.querySelector('[data-testid="statement-review-card"]');
    const linkedLabels = mobileCard?.querySelectorAll<HTMLLabelElement>("label[for]") ?? [];
    expect(linkedLabels).toHaveLength(8);
    for (const label of linkedLabels) {
      expect(container.querySelector(`[id="${label.htmlFor}"]`)).not.toBeNull();
    }

    const transactionsTab = container.querySelector<HTMLButtonElement>('[data-review-tab="transactions"]');
    const documentTab = container.querySelector<HTMLButtonElement>('[data-review-tab="document"]');
    expect(transactionsTab?.getAttribute("aria-selected")).toBe("true");
    expect(documentTab?.className).toContain("min-h-11");
    expect(transactionsTab?.getAttribute("aria-controls")).toBe("statement-transactions-panel");
    expect(documentTab?.getAttribute("aria-controls")).toBe("statement-document-panel");
    const transactionsPanel = container.querySelector<HTMLElement>("#statement-transactions-panel");
    expect(transactionsPanel?.getAttribute("role")).toBe("tabpanel");
    expect(transactionsPanel?.className).toContain("overflow-x-hidden");
    expect(transactionsPanel?.style.contain).toBe("inline-size paint");
    expect(container.querySelector("#statement-document-panel")?.getAttribute("role")).toBe("tabpanel");

    act(() => documentTab?.click());
    expect(documentTab?.getAttribute("aria-selected")).toBe("true");

    const toggle = container.querySelector<HTMLButtonElement>('[aria-controls="statement-document-panel"]');
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    act(() => toggle?.click());
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(table?.className).toContain("lg:block");
    expect(cards?.className).toContain("lg:hidden");

    unmount(root, container);
  });

  it("localizes known preview and row warnings instead of exposing backend English", async () => {
    setLanguage("ru");
    vi.mocked(previewStatement).mockResolvedValue(
      preview({
        warnings: ["Local OCR was used; review every row before importing"],
        rows: [row({ importable: false, warning: "Blocked amount is not a posted movement" })],
      })
    );
    const { container, root } = renderPage();
    await upload(container, new File(["pdf"], "sample.pdf", { type: "application/pdf" }));

    expect(container.textContent).toContain("Использовано локальное OCR");
    expect(container.textContent).toContain("Заблокированная сумма");
    expect(container.textContent).not.toContain("Local OCR was used");
    expect(container.textContent).not.toContain("Blocked amount");

    unmount(root, container);
  });

  it("imports a blocked Kaspi purchase by default and lets the user untick it", async () => {
    setLanguage("en");
    vi.mocked(previewStatement).mockResolvedValue(
      preview({
        rows: [row({ importable: true, warning: "Blocked amount awaiting confirmation; imported as spent" })],
      })
    );
    const { container, root } = renderPage();
    await upload(container, new File(["pdf"], "sample.pdf", { type: "application/pdf" }));

    expect(container.textContent).toContain("already left the balance");
    const checkbox = container.querySelector<HTMLInputElement>('[data-testid="statement-review-cards"] input[type="checkbox"]')!;
    expect(checkbox.checked).toBe(true);
    await act(async () => { checkbox.click(); });
    expect(container.querySelector<HTMLInputElement>('[data-testid="statement-review-cards"] input[type="checkbox"]')!.checked).toBe(false);

    unmount(root, container);
  });

  it("keeps OCR rows excluded until explicit confirmation and imports only after account mapping", async () => {
    setLanguage("en");
    vi.mocked(previewStatement).mockResolvedValue(
      preview({
        requires_row_confirmation: true,
        rows: [row({ importable: false, warning: "OCR row requires explicit confirmation" })],
      })
    );
    const { container, root } = renderPage();
    await upload(container, new File(["pdf"], "sample.pdf", { type: "application/pdf" }));

    const importButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "Import"
    );
    expect(importButton?.disabled).toBe(true);

    const confirmations = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    expect(confirmations.length).toBeGreaterThan(0);
    expect(Array.from(confirmations).every((checkbox) => !checkbox.checked)).toBe(true);
    act(() => confirmations[0]?.click());
    expect(importButton?.disabled).toBe(true);

    const accountSelect = Array.from(container.querySelectorAll("select")).find((select) =>
      Array.from(select.options).some((option) => option.textContent?.includes("Everyday"))
    );
    expect(accountSelect).toBeDefined();
    act(() => {
      if (!accountSelect) return;
      accountSelect.value = "7";
      accountSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(importButton?.disabled).toBe(false);

    await act(async () => importButton?.click());
    expect(commitStatement).toHaveBeenCalledTimes(1);
    expect(vi.mocked(commitStatement).mock.calls[0]?.[1][0]?.importable).toBe(true);

    unmount(root, container);
  });
});
