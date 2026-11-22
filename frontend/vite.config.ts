import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// `E2E_API_PORT` lets a second light stack run next to one on :8000 (parallel worktrees).
const API = `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`;

const CHUNKS: { name: string; test: RegExp }[] = [
  { name: "react", test: /node_modules[\\/](react|react-dom|react-router|react-router-dom)[\\/]/ },
  // Recharts and its state/scale deps, only fetched with the trend chart.
  {
    name: "charts",
    test: /node_modules[\\/](recharts|victory-vendor|d3-[a-z-]+|@reduxjs|react-redux|immer|reselect|es-toolkit|decimal\.js-light)[\\/]/,
  },
];

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: {
      "/api": { target: API, changeOrigin: true },
      "/socket.io": { target: API, ws: true, changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rolldownOptions: {
      output: {
        // Strip stray console/debugger from production bundles (dev keeps them for the eslint rule).
        minify: { compress: { dropConsole: true, dropDebugger: true } },
        codeSplitting: { groups: CHUNKS },
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
