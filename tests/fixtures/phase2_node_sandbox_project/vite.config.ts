import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: { entry: "src/math.ts", name: "math", formats: ["es"] },
    outDir: "dist",
    emptyOutDir: true,
  },
});
