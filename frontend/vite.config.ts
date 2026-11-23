import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin in dev → session cookie works without cross-site settings.
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});
