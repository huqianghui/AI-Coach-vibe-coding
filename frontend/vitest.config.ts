/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "rt-client": path.resolve(__dirname, "./src/test/__mocks__/rt-client.ts"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    testTimeout: 15_000,
    setupFiles: ["./src/test/setup.ts"],
    server: {
      deps: {
        // Allow mocking rt-client which may not be installed locally
        inline: ["rt-client"],
      },
    },
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      // Vitest 3.2 on Windows compares /C:/... tested URLs with C:/...
      // glob results and otherwise merges duplicate empty reports.
      all: false,
      reporter: ["text", "text-summary", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/**/*.d.ts",
        "src/vite-env.d.ts",
        "src/main.tsx",
        "src/types/**",
        "src/components/ui/dropdown-menu.tsx",
        "src/components/ui/select.tsx",
        "src/components/ui/form.tsx",
      ],
      // TODO: raise to 95 per project testing standard once coverage improves
      // (measured baseline recorded in 29-10-SUMMARY.md: Stmts 71.87%, Branches
      // 82.31%, Funcs 70.33%, Lines 71.87% as of Phase 29's final verification sweep)
      thresholds: {
        statements: 71,
        branches: 82,
        functions: 70,
        lines: 71,
      },
    },
  },
});
