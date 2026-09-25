import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import baseline from '../src/test/fixtures/feature_metadata.json' with { type: 'json' }
import ja from '../src/locales/ja'
import en from '../src/locales/en'

for (const locale of ['ja', 'en'] as const) {
  const copy = locale === 'ja' ? ja : en
  test(`settings failures, discard, navigation and execution conditions (${locale})`, async ({ page }, info) => {
    test.setTimeout(90000)
    let settings = { enabled: true, revision: 1, open_limit: 3, transcript_retention_days: 30, log_channel_id: '999', transcript_channel_id: null }
    let readFailure = true
    let writeStatus = 409
    let writes = 0
    const features = baseline.features.map(feature => ({ ...feature, title: feature.id, description: '', enabled: feature.id !== 'moderation', settings: {}, revision: 1, missing_permissions: feature.id === 'automod' ? ['Manage Messages'] : [] }))
    await page.route('**/api/v1/session', route => route.fulfill({ json: { user: { id: '1', name: 'Reviewer' }, csrf_token: 'offline', preferences: { locale, appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } } }))
    await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'U3 fixture', access: 'manager' }] } }))
    await page.route('**/api/v1/guilds/1/**', async route => {
      const path = new URL(route.request().url()).pathname.split('/guilds/1/')[1]
      if (path === 'tickets/settings') {
        if (route.request().method() === 'PUT') {
          writes++
          if (writeStatus !== 200) return route.fulfill({ status: writeStatus, json: { detail: { code: 'rejected', message: `Rejected ${writeStatus}`, errors: [] } } })
          const value = route.request().postDataJSON()
          expect(value.revision).toBe(settings.revision)
          settings = { ...value, revision: settings.revision + 1 }
        } else if (readFailure) return route.fulfill({ status: 503, json: { detail: { code: 'unavailable', message: 'Read unavailable', errors: [] } } })
        return route.fulfill({ json: settings })
      }
      const data: Record<string, unknown> = {
        features: { items: features }, overview: { features, moderation: { summary: {}, events: [], lockdown: null } },
        resources: { channels: [{ id: '123', name: 'general', type: 0 }], roles: [], emojis: [], bot_permissions: '0' },
        tickets: { can_manage: true, summary: { open: 0, unclaimed: 0, closed_30d: 0 }, transcript_storage: { available: true } },
        'moderation/automod/rules': { items: [], next: null },
        'social/youtube/subscriptions': { available: false, items: [], limit: 5, events: ['video'], defaults: {}, variables: [] },
      }
      return route.fulfill({ json: data[path] ?? { items: [], next: null } })
    })
    await page.goto('/servers/1/tickets')
    const nav = page.getByRole('navigation', { name: copy.common.common.featureNavigation })
    await nav.getByRole('link', { name: copy.tickets.tickets.settings, exact: true }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Read unavailable' })).toBeVisible()
    readFailure = false
    await page.getByRole('button', { name: copy.common.common.retry, exact: true }).click()
    const limit = page.getByRole('spinbutton', { name: copy.tickets.tickets.openLimit })
    await expect(limit).toHaveValue('3')
    await expect(page.getByRole('combobox', { name: new RegExp(copy.tickets.tickets.logChannel) })).toHaveValue('999')
    await expect(page.locator('option[value="999"]')).toContainText(copy.common.editing.missingResource)
    await limit.fill('5')
    const save = page.getByRole('button', { name: copy.common.common.save, exact: true })
    for (const status of [403, 409, 422]) {
      writeStatus = status
      await save.click()
      await expect(page.getByRole('alert').filter({ hasText: `Rejected ${status}` })).toBeVisible()
      await expect(limit).toHaveValue('5')
    }
    // Browser Back and imperative search navigation both retain input on cancel.
    page.once('dialog', dialog => dialog.dismiss())
    await page.evaluate(() => history.back())
    await expect(page).toHaveURL(/\/tickets\/settings$/)
    await expect(limit).toHaveValue('5')
    await page.getByRole('button', { name: copy.common.nav.search, exact: true }).click()
    await page.getByRole('dialog').getByRole('textbox').fill('YouTube')
    page.once('dialog', dialog => dialog.dismiss())
    await page.getByRole('dialog').getByRole('button').first().click()
    await expect(page).toHaveURL(/\/tickets\/settings$/)
    await expect(limit).toHaveValue('5')
    await page.getByRole('button', { name: copy.common.common.discard, exact: true }).click()
    await expect(limit).toHaveValue('3')
    await limit.fill('6')
    writeStatus = 200
    await save.click()
    await expect(page.getByRole('region')).toHaveCount(0)
    expect(writes).toBe(4)
    await page.reload()
    await expect(limit).toHaveValue('6')
    await page.goto('/servers/1/moderation/automod')
    await expect(page.getByText(copy.common.editing.parentOff, { exact: true })).toBeVisible()
    await expect(page.getByText(copy.common.editing.permissions, { exact: true })).toBeVisible()
    await expect(page.getByText(copy.common.editing.noRules, { exact: true })).toBeVisible()
    await page.goto('/servers/1/social/youtube')
    await expect(page.getByText(copy.social.social.setupRequired, { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: copy.social.social.add, exact: true })).toBeDisabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    expect((await new AxeBuilder({ page }).analyze()).violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
    await page.screenshot({ path: info.outputPath(`settings-conditions-${locale}.png`), fullPage: true })
    if (info.project.name === 'desktop') {
      await page.setViewportSize({ width: 414, height: 896 })
      await page.goto('/servers/1/tickets/settings')
      await limit.fill('7')
      await expect(page.getByRole('region')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
      await page.screenshot({ path: info.outputPath(`settings-414-${locale}.png`), fullPage: true })
    }
  })
}
