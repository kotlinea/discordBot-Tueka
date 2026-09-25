import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import baseline from '../src/test/fixtures/feature_metadata.json' with { type: 'json' }
import ja from '../src/locales/ja'
import en from '../src/locales/en'

const metadata = (id: string, settings: Record<string, unknown> = {}) => ({ ...baseline.features.find(feature => feature.id === id)!, title: id, description: `${id} settings`, enabled: true, revision: 1, missing_permissions: [], settings })
const resources = { channels: [{ id: '123456789012345678', name: 'general', type: 0 }, { id: '123456789012345679', name: 'Voice', type: 2 }, { id: '123456789012345680', name: 'Category', type: 4 }], roles: [{ id: '123456789012345681', name: 'Member' }], bot_permissions: '8' }
async function session(page: Page, locale: 'ja' | 'en', access = 'manager') {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { user: { id: '1', name: 'Viewer', avatar_url: '' }, csrf_token: 'csrf', preferences: { locale, appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } } }))
  await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Example', icon: null, access }] } }))
  await page.route('**/api/v1/guilds/1/resources', route => route.fulfill({ json: resources }))
}
const failure = (status: number) => ({ status, json: { detail: { code: 'rejected', message: `Rejected ${status}`, errors: [] } } })

for (const locale of ['ja', 'en'] as const) {
  const copy = locale === 'ja' ? ja : en
  test(`feature-owned settings preserve types, failed input, disable and direct links (${locale})`, async ({ page }, info) => {
    // This case saves settings and opens every module URL; budget the whole multi-page journey.
    test.setTimeout(60000)
    await session(page, locale)
    let result = 200
    let leveling = metadata('leveling', { text_notification_channel_id: '123456789012345678', text_role_rewards: ['5:123456789012345681'], voice_enabled: false, voice_notification_channel_id: '123456789012345678', voice_role_rewards: [], voice_xp_per_minute: 2, voice_allow_solo: false, voice_allow_muted: false })
    const other = ['autorole', 'live_stats', 'temporary_voice', 'advanced_polls', 'minigames', 'moderation', 'automod', 'anti_spam', 'anti_raid', 'audit_log', 'trust_score'].map(id => metadata(id))
    const chunks: string[] = []
    page.on('request', request => { if (request.url().endsWith('.js')) chunks.push(request.url()) })
    await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { features: [leveling, ...other], moderation: { summary: {}, events: [], lockdown: null } } }))
    await page.route('**/api/v1/guilds/1/features', route => route.fulfill({ json: { items: [leveling, ...other] } }))
    await page.route('**/api/v1/guilds/1/modules/leveling', async route => {
      if (route.request().method() === 'PUT') {
        expect(route.request().headers()['x-csrf-token']).toBe('csrf')
        if (result !== 200) return route.fulfill(failure(result))
        const value = route.request().postDataJSON()
        expect(value.revision).toBe(leveling.revision)
        leveling = { ...leveling, ...value, revision: leveling.revision + 1 }
      }
      return route.fulfill({ json: leveling })
    })
    await page.goto('/servers/1/modules/leveling')
    const xp = page.getByRole('spinbutton', { name: copy.common.settingsFields.voice_xp_per_minute })
    await xp.focus()
    await page.keyboard.press('ControlOrMeta+A')
    await page.keyboard.type('8')
    const save = page.getByRole('button', { name: copy.common.common.save, exact: true })
    for (const status of [403, 409, 422]) {
      result = status
      await save.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('alert').filter({ hasText: `Rejected ${status}` }).first()).toBeVisible()
      await expect(xp).toHaveValue('8')
    }
    result = 200
    await save.click()
    await expect(page.getByRole('region')).toHaveCount(0)
    expect(leveling.settings.voice_xp_per_minute).toBe(8)
    expect(leveling.settings.text_role_rewards).toEqual(['5:123456789012345681'])
    await page.getByRole('switch', { name: copy.common.module.enable, exact: true }).click()
    await save.click()
    await expect(page.getByRole('region')).toHaveCount(0)
    await page.reload()
    await expect(xp).toHaveValue('8')
    await expect(page.getByRole('switch', { name: copy.common.module.enable, exact: true })).not.toBeChecked()
    expect(chunks.some(url => /\/(PanelEditor|RuleEditor|Provider)-/.test(url))).toBe(false)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    const audit = await new AxeBuilder({ page }).analyze()
    expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
    await page.screenshot({ path: info.outputPath(`leveling-${locale}.png`), fullPage: true })
    // All settings URLs are declared, including the existing rule-list settings links.
    for (const item of other) {
      const path = ['audit_log', 'trust_score'].includes(item.id) ? `moderation/${item.id}` : `modules/${item.id}`
      await page.goto(`/servers/1/${path}`)
      const title = item.id === 'automod' ? copy.moderation.moderation.automod : item.id === 'anti_spam' ? copy.moderation.moderation.anti_spam : item.id === 'anti_raid' ? copy.moderation.moderation.anti_raid : item.id
      await expect(page.getByRole('heading', { name: item.id, exact: true })).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'パンくず' })).toContainText(title)
    }
    await page.keyboard.press('ControlOrMeta+k')
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog').getByRole('button', { name: copy.social.social.title, exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.goto('/servers/1/modules/temporary_voice')
    const trigger = page.getByRole('combobox', { name: new RegExp(copy.common.settingsFields.temp_voice_trigger_id) })
    await expect(trigger.locator('option').filter({ hasText: 'Voice' })).toHaveCount(1)
    await expect(trigger.locator('option').filter({ hasText: 'general' })).toHaveCount(0)
    await expect(page.getByRole('textbox', { name: new RegExp(copy.common.settingsFields.temp_voice_name) })).toHaveAttribute('maxlength', '100')
    await page.goto('/servers/1/modules/live_stats')
    await expect(page.getByRole('textbox', { name: new RegExp(copy.common.settingsFields.stats_template) })).toHaveAttribute('maxlength', '90')
    await page.goto('/servers/1/modules/missing')
    await expect(page.getByRole('heading', { name: 'ページが見つかりません' })).toBeVisible()
  })

  test(`staff navigation avoids manager requests and preserves transcript links (${locale})`, async ({ page }) => {
    await session(page, locale, 'ticket_staff')
    let overviewRequests = 0
    let metadataRequests = 0
    await page.route('**/api/v1/guilds/1/features', route => { metadataRequests++; return route.fulfill(failure(403)) })
    await page.route('**/api/v1/guilds/1/overview', route => { overviewRequests++; return route.fulfill(failure(403)) })
    await page.route('**/api/v1/guilds/1/tickets', route => route.fulfill({ json: { can_manage: false, summary: { open: 0, unclaimed: 0, closed_30d: 0 }, transcript_storage: { available: true } } }))
    await page.route('**/api/v1/guilds/1/tickets/items*', route => route.fulfill({ json: { items: [], next: null } }))
    await page.goto('/servers/1')
    await expect(page).toHaveURL(/\/servers\/1\/tickets$/)
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.title, exact: true })).toBeVisible()
    const mobileNav = page.getByRole('button', { name: 'Navigation', exact: true })
    if (await mobileNav.isVisible()) {
      await mobileNav.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('dialog')).toBeVisible()
    }
    const nav = page.getByRole('navigation', { name: 'Dashboard' }).filter({ visible: true })
    await expect(nav.getByRole('link')).toHaveCount(1)
    await expect(nav.getByRole('link')).toHaveAttribute('href', '/servers/1/tickets')
    if (await page.getByRole('dialog').isVisible()) await page.keyboard.press('Escape')
    await page.goto('/servers/1/tickets/inbox')
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.inbox, exact: true })).toBeVisible()
    await page.goto('/servers/1/modules/welcome')
    await expect(page.getByRole('heading', { name: 'ページが見つかりません' })).toBeVisible()
    expect(overviewRequests).toBe(0)
    expect(metadataRequests).toBe(0)
    await page.route('**/api/v1/tickets/transcripts/678', route => route.fulfill({ json: { ticket: { id: 7, ticket_number: 23 }, messages: [], attachments: [], closed_at: 1700000000, close_reason: 'Resolved', feedback_enabled: false } }))
    await page.goto('/tickets/transcripts/678')
    await expect(page.getByRole('heading', { name: `${copy.tickets.tickets.transcript} · Ticket #23` })).toBeVisible()
    await page.route('**/api/v1/session', route => route.fulfill(failure(401)))
    await page.route('**/login', route => route.fulfill({ contentType: 'text/html', body: '<h1>Login</h1>' }))
    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible()
  })

  test(`direct workspace navigation uses independent metadata (${locale})`, async ({ page }, info) => {
    await session(page, locale)
    let overviewRequests = 0
    await page.route('**/api/v1/guilds/1/overview', route => { overviewRequests++; return route.fulfill(failure(503)) })
    await page.route('**/api/v1/guilds/1/features', route => route.fulfill({ json: { items: baseline.features.map(item => metadata(item.id)) } }))
    await page.route('**/api/v1/guilds/1/tickets', route => route.fulfill({ json: { can_manage: true, summary: { open: 0, unclaimed: 0, closed_30d: 0 }, transcript_storage: { available: true } } }))
    await page.goto('/servers/1/tickets')
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.title, exact: true })).toBeVisible()
    const menu = page.getByRole('button', { name: 'Navigation', exact: true })
    if (await menu.isVisible()) await menu.click()
    const nav = page.getByRole('navigation', { name: 'Dashboard' }).filter({ visible: true })
    await expect(nav.getByRole('link')).toHaveCount(baseline.features.length + 2)
    await expect(nav.locator('a[href="/servers/1/modules/welcome"]')).toBeVisible()
    await expect(nav.locator('a[href="/servers/1/moderation/automod"]')).toBeVisible()
    await expect(nav.locator('a[href="/servers/1/social/youtube"]')).toBeVisible()
    expect(overviewRequests).toBe(0)
    await page.screenshot({ path: info.outputPath(`registered-navigation-${locale}.png`), fullPage: true })
    if (await page.getByRole('dialog').isVisible()) await page.keyboard.press('Escape')
  })

  test(`registered social providers select their own presentation and endpoints (${locale})`, async ({ page }, info) => {
    await session(page, locale)
    await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { features: [], moderation: { summary: {}, events: [], lockdown: null } } }))
    await page.route('**/api/v1/guilds/1/features', route => route.fulfill({ json: { items: [] } }))
    for (const [provider, name] of [['youtube', 'YouTube'], ['twitch', 'Twitch'], ['tiktok', 'TikTok'], ['x', 'X'], ['instagram', 'Instagram']]) {
      let result = 409
      let body: Record<string, unknown> | undefined
      await page.route(`**/api/v1/guilds/1/social/${provider}/subscriptions`, async route => {
        if (route.request().method() === 'POST') {
          body = route.request().postDataJSON()
          if (result !== 200) return route.fulfill(failure(result))
          return route.fulfill({ json: { id: 1, ...body } })
        }
        return route.fulfill({ json: { items: [], available: true, events: ['post'], limit: 10, variables: [], defaults: {} } })
      })
      await page.goto(`/servers/1/social/${provider}`)
      await expect(page.getByRole('heading', { name: `${name} ${copy.social.social.title}`, exact: true })).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'パンくず' })).toContainText(`${name} ${copy.social.social.title}`)
      await page.getByRole('button', { name: copy.social.social.add, exact: true }).first().click()
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel(copy.social.social.account, { exact: true }).fill('sample')
      await dialog.getByRole('combobox', { name: new RegExp(copy.social.social.defaultChannel) }).selectOption('123456789012345678')
      await dialog.getByRole('button', { name: copy.common.common.save, exact: true }).click()
      await expect(dialog.getByRole('alert')).toContainText('Rejected 409')
      await expect(dialog.getByLabel(copy.social.social.account, { exact: true })).toHaveValue('sample')
      result = 200
      await dialog.getByRole('button', { name: copy.common.common.save, exact: true }).click()
      await expect(dialog).toHaveCount(0)
      expect(body).toMatchObject({ account: 'sample', channel_id: '123456789012345678', enabled: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    }
    const audit = await new AxeBuilder({ page }).analyze()
    expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
    await page.screenshot({ path: info.outputPath(`social-${locale}.png`), fullPage: true })
    await page.goto('/servers/1/social/missing')
    await expect(page.getByRole('heading', { name: 'ページが見つかりません' })).toBeVisible()
  })
}
