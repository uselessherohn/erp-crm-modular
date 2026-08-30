import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
    // fileParallelism: false — los tests de integración *.integration.test.tsx
    // golpean un backend/Postgres real y COMPARTIDO (no hay fixtures aisladas
    // por archivo). Con paralelismo de archivos (default de Vitest), dos
    // suites que configuran el mismo document_account_mapping (clave única
    // company_id+document_type+role) corren a la vez y se pisan entre sí —
    // hallazgo real de la Fase 4 de accounting. Los tests unitarios puros no
    // se ven afectados por esta restricción; el costo es una suite un poco
    // más lenta a cambio de determinismo real.
    fileParallelism: false,
  },
});
