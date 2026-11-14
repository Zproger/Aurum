import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n";

/**
 * Renders a statement PDF into canvases with pdf.js instead of the browser's
 * built-in viewer. The built-in viewer cannot be used here: the page's CSP
 * does not allow blob: frames, Chrome refuses PDFs in sandboxed frames, and
 * iOS Safari shows only the first page of an embedded PDF.
 *
 * The bytes come straight from the selected File, so nothing is fetched (the
 * CSP's connect-src stays 'self') and nothing leaves the browser. pdf.js runs
 * in a same-origin worker and pdf.js 6 no longer uses eval, so script-src stays strict.
 */
export function PdfPreview({ file }: { file: File }) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [pageCount, setPageCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let destroy: (() => Promise<void>) | null = null;
    const container = containerRef.current;
    setState("loading");
    setPageCount(0);

    (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
      const data = new Uint8Array(await file.arrayBuffer());
      const task = pdfjs.getDocument({ data });
      destroy = () => task.destroy();
      const pdf = await task.promise;
      if (cancelled || !container) return;
      setPageCount(pdf.numPages);
      container.replaceChildren();
      // The panel can be hidden (mobile "Transactions" tab) while this runs, so
      // render at least 600px wide and let CSS scale it; the pixel ratio is
      // capped so a long statement does not allocate huge canvases.
      const width = Math.max(container.clientWidth, 600);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      for (let number = 1; number <= pdf.numPages; number += 1) {
        const page = await pdf.getPage(number);
        if (cancelled) return;
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: (width / base.width) * ratio });
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.className = "block h-auto w-full bg-white shadow-card";
        canvas.setAttribute("aria-label", t("statementImport.pdfPage", { page: number, total: pdf.numPages }));
        canvas.setAttribute("role", "img");
        container.append(canvas);
        await page.render({ canvas, viewport }).promise;
        // The first page is enough to stop showing the spinner.
        if (number === 1 && !cancelled) setState("ready");
      }
    })().catch(() => {
      if (!cancelled) setState("error");
    });

    return () => {
      cancelled = true;
      void destroy?.();
    };
  }, [file, t]);

  return (
    <div className="flex min-h-[360px] flex-1 flex-col overflow-auto p-3" data-testid="statement-document">
      {state === "loading" && <p className="py-8 text-center text-sm text-text-muted" role="status">{t("common.loading")}</p>}
      {state === "error" && <p className="py-8 text-center text-sm text-danger" role="alert">{t("statementImport.pdfError")}</p>}
      {state === "ready" && pageCount > 1 && (
        <p className="mb-2 text-xs text-text-muted">{t("statementImport.pdfPages", { total: pageCount })}</p>
      )}
      <div ref={containerRef} className="grid gap-3" />
    </div>
  );
}
