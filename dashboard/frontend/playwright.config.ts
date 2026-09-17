import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  testIgnore: 'docs.spec.ts',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  webServer: { command: 'npx vite build --base / --outDir node_modules/.cache/playwright-dist && npx vite preview --base / --outDir node_modules/.cache/playwright-dist --host 127.0.0.1 --port 4173', port: 4173, timeout: 120000, reuseExistingServer: false },
  projects: [
    { name: 'mobile-320', use: { ...devices['Desktop Chrome'], viewport: { width: 320, height: 720 } } },
    { name: 'mobile-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 } } },
    { name: 'tablet-768', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
  ],
})
