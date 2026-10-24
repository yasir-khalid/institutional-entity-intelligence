import { defineConfig, devices } from "@playwright/test";

function testPort(name: string, fallback: number) {
  const port = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error(`${name} must be a port between 1024 and 65535`);
  }
  return port;
}

const webPort = testPort("ER_E2E_WEB_PORT", 3100);
const apiPort = testPort("ER_E2E_API_PORT", 8100);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: { baseURL: `http://localhost:${webPort}`, trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    {
      command:
        `cd .. && uv run uvicorn --app-dir tests web_fixture:app --host 127.0.0.1 --port ${apiPort}`,
      url: `http://localhost:${apiPort}/api/coverage`,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      url: `http://localhost:${webPort}`,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${apiPort}` },
      reuseExistingServer: false,
    },
  ],
});
