import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev only: lets a second dev server point at a throwaway backend (used for end-to-end checks).
// Defaults to the normal backend on :8000.
const API_TARGET =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.API_TARGET ??
  "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Long multi-step user-flow tests got close to the 5s default when many files run in parallel; passing tests still finish as fast as before.
    testTimeout: 20000,
  },
  server: {
    port: 5173,
    proxy: {
      // Same-origin in dev → session cookie works without cross-site settings.
      "/api": { target: API_TARGET, changeOrigin: false },
      // The public progress page is served by the backend too, so the share link works from the dev address.
      "/share": { target: API_TARGET, changeOrigin: false },
    },
  },
});
