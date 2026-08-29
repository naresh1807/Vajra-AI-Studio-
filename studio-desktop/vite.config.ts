import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri expects a fixed port and no clearScreen so its logs stay visible.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  worker: { format: "es" },
  build: { target: "es2021", outDir: "dist", chunkSizeWarningLimit: 4000 },
  optimizeDeps: { include: ["monaco-editor"] },
});
