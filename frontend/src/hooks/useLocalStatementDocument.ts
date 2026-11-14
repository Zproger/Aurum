import { useCallback, useEffect, useRef, useState } from "react";

export type LocalStatementDocument = {
  fileName: string;
  // Kept in memory so PDFs can be rendered from their bytes (no blob: fetch).
  file: File;
  kind: "pdf" | "image" | "unsupported";
  url: string;
};

const SAFE_INLINE_IMAGE_TYPES = new Set([
  "image/avif",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

function previewKind(file: File): LocalStatementDocument["kind"] {
  // Trust the browser-provided MIME type, not the extension. A renamed HTML
  // file must never become same-origin iframe content just because it ends in
  // .pdf, and script-capable SVG stays on the download-only fallback path.
  if (file.type === "application/pdf") return "pdf";
  if (SAFE_INLINE_IMAGE_TYPES.has(file.type)) return "image";
  return "unsupported";
}

export function useLocalStatementDocument() {
  const activeUrl = useRef<string | null>(null);
  const [document, setDocument] = useState<LocalStatementDocument | null>(null);

  const clearDocument = useCallback(() => {
    if (activeUrl.current) {
      URL.revokeObjectURL(activeUrl.current);
      activeUrl.current = null;
    }
    setDocument(null);
  }, []);

  const selectDocument = useCallback((file: File) => {
    if (activeUrl.current) URL.revokeObjectURL(activeUrl.current);
    const url = URL.createObjectURL(file);
    activeUrl.current = url;
    setDocument({ fileName: file.name, file, kind: previewKind(file), url });
  }, []);

  useEffect(
    () => () => {
      if (activeUrl.current) URL.revokeObjectURL(activeUrl.current);
    },
    []
  );

  return { document, selectDocument, clearDocument };
}
