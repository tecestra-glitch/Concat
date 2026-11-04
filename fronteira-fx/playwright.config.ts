import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PORT ?? 3100);
// Segundo servidor, com o login próprio ligado (e2e/login). Hash e segredo são só de teste.
const LOGIN_PORT = PORT + 1;
const LOGIN_ENV = {
  FX_SITE_PASSWORD_HASH: "scrypt$32768$8$1$h4mmTmvbLm47tY2vAYICUA==$cnkfwUwfTKUQFL0XjqyiOfTub0rqNPFwAbxdFScvbBY=",
  FX_SESSION_SECRET: "segredo-somente-do-e2e-com-mais-de-trinta-e-dois-caracteres",
  FX_BASIC_AUTH: "",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never", outputFolder: "dev/playwright-report" }]],
  outputDir: "dev/test-results",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure", colorScheme: "dark" },
  webServer: [
    {
      command: `pnpm exec next start -p ${PORT}`,
      url: `http://localhost:${PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `pnpm exec next start -p ${LOGIN_PORT}`,
      url: `http://localhost:${LOGIN_PORT}/entrar`,
      // Sempre novo: a contagem de tentativas vive na memória do processo.
      reuseExistingServer: false,
      timeout: 120_000,
      env: LOGIN_ENV,
    },
  ],
  projects: [
    { name: "desktop-1440", testIgnore: /login\//, use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet-1024", testIgnore: /login\//, use: { ...devices["Desktop Chrome"], viewport: { width: 1024, height: 768 } } },
    { name: "mobile-390", testIgnore: /login\//, use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } } },
    {
      name: "login-390",
      testMatch: /login\/.*\.spec\.ts/,
      fullyParallel: false,
      workers: 1,
      use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${LOGIN_PORT}`, viewport: { width: 390, height: 844 } },
    },
  ],
});
