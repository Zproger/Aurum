import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "@/lib/i18n";

const getDocument = vi.fn();
vi.mock("pdfjs-dist", () => ({ GlobalWorkerOptions: { workerSrc: "" }, getDocument: (...args: unknown[]) => getDocument(...args) }));

const { PdfPreview } = await import("./PdfPreview");

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root | null = null;
let container: HTMLDivElement | null = null;

function fakePdf(pages: number) {
  const page = {
    getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
    render: vi.fn(() => ({ promise: Promise.resolve() })),
  };
  return { numPages: pages, getPage: vi.fn(async () => page), page };
}

async function render(file: File) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => { root?.render(<PdfPreview file={file} />); });
  // Let the async load and the per-page renders settle.
  for (let i = 0; i < 5; i += 1) await act(async () => { await Promise.resolve(); });
  return container;
}

beforeEach(() => {
  setLanguage("en");
  getDocument.mockReset();
  // jsdom has no canvas implementation; rendering is mocked, sizing is enough.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.restoreAllMocks();
});

const pdfFile = () => new File(["%PDF-1.7"], "statement.pdf", { type: "application/pdf" });

it("renders every page from the file's own bytes, without fetching a URL", async () => {
  const pdf = fakePdf(2);
  getDocument.mockReturnValue({ promise: Promise.resolve(pdf), destroy: vi.fn(async () => {}) });

  const view = await render(pdfFile());

  const [{ data }] = getDocument.mock.calls[0] as [{ data: Uint8Array; url?: string }];
  expect(data).toBeInstanceOf(Uint8Array);
  expect(getDocument.mock.calls[0][0]).not.toHaveProperty("url");
  expect(view.querySelectorAll("canvas")).toHaveLength(2);
  expect(view.querySelector("canvas")?.getAttribute("aria-label")).toBe("Page 1 of 2");
  expect(view.textContent).toContain("Pages: 2");
  expect(pdf.page.render).toHaveBeenCalledTimes(2);
});

it("shows an honest error when the PDF cannot be read", async () => {
  getDocument.mockReturnValue({ promise: Promise.reject(new Error("broken")), destroy: vi.fn(async () => {}) });

  const view = await render(pdfFile());

  expect(view.querySelector('[role="alert"]')?.textContent).toContain("Could not display the PDF");
  expect(view.querySelector("canvas")).toBeNull();
});

it("stops loading when the preview is closed", async () => {
  const destroy = vi.fn(async () => {});
  getDocument.mockReturnValue({ promise: new Promise(() => {}), destroy });

  await render(pdfFile());
  act(() => root?.unmount());
  root = null;

  expect(destroy).toHaveBeenCalled();
});
