import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'docs.spec.ts',
  use: { baseURL: 'http://127.0.0.1:4174/docs/', trace: 'retain-on-failure' },
  webServer: {
    command: 'npm --prefix ../../docs run preview -- --port 4174',
    url: 'http://127.0.0.1:4174/docs/',
    reuseExistingServer: false,
  },
  projects: [
    { name: 'docs-320', use: { ...devices['Desktop Chrome'], viewport: { width: 320, height: 720 } } },
    { name: 'docs-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 } } },
    { name: 'docs-414', use: { ...devices['Desktop Chrome'], viewport: { width: 414, height: 896 } } },
    { name: 'docs-768', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } } },
    { name: 'docs-desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
  ],
})
