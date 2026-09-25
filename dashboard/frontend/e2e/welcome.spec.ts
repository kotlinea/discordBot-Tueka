import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import ja from '../src/locales/ja'
import en from '../src/locales/en'

for (const locale of ['ja', 'en'] as const) {
  test(`registered welcome saves, retains failed edits and disables in ${locale}`, async ({ page }, testInfo) => {
    const copy = (locale === 'ja' ? ja : en).common
    let feature = { id: 'welcome', category: 'community', parent: null, title: '入退室', description: '', docs_path: '/docs/features/welcome', enabled: true, revision: 1, fields: ['welcome_enabled', 'welcome_channel_id', 'welcome_format', 'welcome_content', 'leave_enabled', 'leave_channel_id', 'leave_format', 'leave_content'], required_fields: [], required_bot_permissions: [], missing_permissions: [], settings: { welcome_enabled: true, welcome_channel_id: '123456789012345678', welcome_format: 'text', welcome_content: 'Hello {user}', leave_enabled: false, leave_channel_id: null, leave_format: 'text', leave_content: 'Bye {user}' } }
    let failure = 0
    let writes = 0
    await page.route('**/api/v1/session', route => route.fulfill({ json: { user: { id: '1', name: 'Manager', avatar_url: '' }, csrf_token: 'csrf', preferences: { locale, appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } } }))
    await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Example', icon: null }] } }))
    await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { guild_id: '1', features: [feature], moderation: { summary: {}, events: [], lockdown: null } } }))
    await page.route('**/api/v1/guilds/1/features', route => route.fulfill({ json: { items: [feature] } }))
    await page.route('**/api/v1/guilds/1/resources', route => route.fulfill({ json: { channels: [{ id: '123456789012345678', name: 'welcome', type: 0 }], roles: [], bot_permissions: '8' } }))
    await page.route('**/api/v1/guilds/1/modules/welcome', async route => {
      if (route.request().method() === 'PUT') {
        writes++
        expect(route.request().headers()['x-csrf-token']).toBe('csrf')
        if (failure) { await route.fulfill({ status: failure, json: { detail: { code: 'rejected', message: `Rejected ${failure}`, errors: [] } } }); return }
        const body = route.request().postDataJSON()
        expect(body.revision).toBe(feature.revision)
        feature = { ...feature, ...body, revision: feature.revision + 1 }
      }
      await route.fulfill({ json: feature })
    })
    await page.goto('/servers/1/modules/welcome')
    const content = page.getByRole('textbox', { name: new RegExp(copy.welcome.fields.welcome_content) })
    await expect(page.getByRole('heading', { level: 1, name: copy.welcome.title })).toBeVisible()
    await content.fill('Edited {displayname}')
    const save = page.getByRole('button', { name: copy.common.save, exact: true })
    for (const status of [403, 409, 422]) {
      failure = status
      await save.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('alert').filter({ hasText: `Rejected ${status}` }).first()).toBeVisible()
      await expect(content).toHaveValue('Edited {displayname}')
      await expect(save).toBeEnabled()
    }
    failure = 0
    await save.click()
    await expect(page.getByRole('region', { name: copy.common.unsaved })).toHaveCount(0)
    expect(writes).toBe(4)
    await page.reload()
    await expect(content).toHaveValue('Edited {displayname}')
    await page.getByRole('switch', { name: copy.module.enable, exact: true }).click()
    await save.click()
    await expect(page.getByRole('region', { name: copy.common.unsaved })).toHaveCount(0)
    await page.reload()
    await expect(page.getByRole('switch', { name: copy.module.enable, exact: true })).not.toBeChecked()
    await expect(content).toHaveValue('Edited {displayname}')
    expect(feature.settings.welcome_channel_id).toBe('123456789012345678')
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    const audit = await new AxeBuilder({ page }).analyze()
    expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`welcome-${locale}.png`), fullPage: true })
    if (testInfo.project.name === 'desktop') {
      await page.setViewportSize({ width: 414, height: 896 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
      await page.screenshot({ path: testInfo.outputPath(`welcome-${locale}-414.png`), fullPage: true })
    }
    await page.goto('/servers/1/modules/missing')
    await expect(page.getByRole('heading', { name: 'ページが見つかりません' })).toBeVisible()
  })
}
