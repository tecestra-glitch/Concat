import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Dados de demonstração só entram pelo cliente de API (`src/lib/api`): fora dele os componentes
  // usam `api.*(mode)` / hooks com o modo resolvido, para que `real`, `simulation` e `demo` nunca se misturem.
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/lib/api/demo-*", "**/demo-data", "**/demo-watch", "**/demo-graph", "**/demo-simulate"],
              message: "Dados de demonstração só entram pelo cliente de API (src/lib/api); fora dele use api.*(mode) ou os hooks de src/lib/queries.ts.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/lib/api/**", "src/test/**"],
    rules: { "no-restricted-imports": "off" },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
