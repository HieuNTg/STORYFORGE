import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: [
      "lib/**/*.test.ts",
      "lib/**/*.test.tsx",
      "stores/**/*.test.ts",
      "components/**/*.test.tsx",
    ],
  },
});
