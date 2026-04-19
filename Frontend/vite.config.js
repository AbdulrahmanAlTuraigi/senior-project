import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  logLevel: "error", // Suppress warnings, only show errors
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // When running `npm run dev`, proxy API calls to the Flask server.
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  plugins: [react()],
});