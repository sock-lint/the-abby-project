import { defineConfig } from '@playwright/test';
import { requireCheck } from './scripts/live-checks-contract.mjs';

// The wrapper owns the private result file, exclusive account lock and hard
// time limit. Do not run this config directly with Playwright CLI overrides.
requireCheck(process.env.ABBY_LIVE_GUARDED_RUN === '1' && process.env.ABBY_LIVE_OUTPUT_DIRECTORY);

export default defineConfig({
  testDir: './e2e/live-smoke',
  testMatch: '**/*.pw.js',
  workers: 1,
  retries: 0,
  timeout: 150_000,
  globalTimeout: 170_000,
  expect: { timeout: 12_000 },
  outputDir: process.env.ABBY_LIVE_OUTPUT_DIRECTORY,
  reporter: [['./e2e/live-smoke/quiet-reporter.js']],
  use: {
    browserName: 'chromium',
    headless: true,
    serviceWorkers: 'block',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    ignoreHTTPSErrors: false,
    acceptDownloads: false,
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
    actionTimeout: 12_000,
    navigationTimeout: 15_000,
  },
});
