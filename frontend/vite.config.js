import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме фронтенд живёт на :5173 и проксирует /api на FastAPI (:8000),
// чтобы не настраивать CORS в бэкенде. В проде статика раздаётся FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});