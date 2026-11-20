/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.MNEMOS_API ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom", "react-router-dom"] } },
    },
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
