import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["tests/chat/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/chat/setup.ts"],
  },
});
