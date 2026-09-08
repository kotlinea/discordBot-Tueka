import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('documentation is responsive, searchable and accessible', async ({ page }, testInfo) => {
  await page.goto('./')
  await expect(page.getByRole('heading', { name: 'Tueka Docs' })).toBeVisible()
  await expect(page.getByRole('button', { name: /ドキュメントを検索/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)

  if (testInfo.project.name !== 'docs-desktop' && testInfo.project.name !== 'docs-768') {
    await page.locator('.VPNavBarHamburger').click()
    await expect(page.locator('.appearance-mobile select')).toBeVisible()
    await page.locator('.appearance-mobile select').selectOption('community')
    await expect(page.locator('html')).toHaveAttribute('data-appearance', 'community')
    await page.keyboard.press('Escape')
  } else {
    await expect(page.locator('.appearance-top select')).toBeVisible()
  }

  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze()
  expect(results.violations).toEqual([])
})

test('long feature pages do not overflow', async ({ page }) => {
  await page.goto('./features/tickets')
  await expect(page.getByRole('heading', { name: 'サポートチケット' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)
})
