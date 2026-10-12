import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  timeout: 45000,
  workers: 1,
  use: {
    baseURL: process.env.E2E_URL || 'http://127.0.0.1:3120',
    viewport: { width: 1440, height: 1000 },
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  outputDir: '../logs/browser-tests',
});
