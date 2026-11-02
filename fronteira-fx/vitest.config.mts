import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";


export default defineConfig({
  plugins: [react()],
  test: { include: ["src/**/*.test.ts", "src/**/*.test.tsx"], environment: "node" },
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
});
