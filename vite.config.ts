import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const configDir = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(
  configDir,
  "src/agent_foundations/viewer/static/chat",
);

export default defineConfig({
  plugins: [react()],
  root: "web/chat",
  base: "/chat-static/",
  build: {
    outDir,
    emptyOutDir: true,
  },
});
