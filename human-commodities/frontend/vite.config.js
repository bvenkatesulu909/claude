import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev the console runs at http://localhost:5173/ and proxies /api → Flask.
// The production build is served by Flask under /app, so assets need base "/app/".
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/app/" : "/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5060",
    },
  },
}));
