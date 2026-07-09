import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import istanbul from "vite-plugin-istanbul";
import path from "path";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(process.env.INSTRUMENT_COVERAGE === "true"
      ? [
          istanbul({
            include: "src/**/*",
            exclude: ["node_modules", "e2e", "dist"],
            extension: [".ts", ".tsx"],
            requireEnv: false,
            forceBuildInstrument: false,
          }),
        ]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
