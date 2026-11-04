import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/**", ".vercel/**", "coverage/**"] },
  ...tseslint.configs.strict,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
