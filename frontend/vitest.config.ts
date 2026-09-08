import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Separate from vite.config.ts (the app config) since the unit tests here
// are plain-function tests over lib/ logic — no dev server, no proxy, no
// React plugin needed, so pulling in the app's own config would just be
// dead weight. Still needs jsdom, not plain "node": lib/i18n.ts reads
// localStorage at module load time (readInitialLanguage), which doesn't
// exist as a Node global.
export default defineConfig({
  resolve: {
    // Mirrors tsconfig.app.json's "@/*" path mapping — Vite/Vitest don't
    // read tsconfig paths on their own, this is TypeScript-only otherwise.
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
  },
});
