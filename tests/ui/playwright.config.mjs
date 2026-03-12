import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..');
const port = process.env.UI_SMOKE_PORT || '8512';


export default defineConfig({
  testDir: __dirname,
  testMatch: ['**/*.spec.mjs'],
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
  },
  webServer: {
    command: `INTERVIEW_SMOKE_TEST=1 ./run-local.sh --server.headless true --server.port ${port}`,
    cwd: repoRoot,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
