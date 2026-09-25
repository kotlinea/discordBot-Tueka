import { expect, test } from '@playwright/test'
import baseline from '../src/test/fixtures/feature_metadata.json' with { type: 'json' }

// Render the real application with deterministic, offline HTTP data for the UX inventory.
test('UX inventory captures manager and staff workspaces', async ({ page }, info) => {
  test.setTimeout(60000)
  let staff = false
  const features = baseline.features.map(feature => ({ ...feature, title: feature.id, description: feature.id, enabled: false, settings: {}, revision: 1, missing_permissions: [] }))
  await page.route('**/api/v1/session', route => route.fulfill({ json: { user: { id: '1', name: 'UX review', avatar_url: '' }, csrf_token: 'offline', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } } }))
  await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Inventory fixture', icon: null, access: staff ? 'ticket_staff' : 'manager' }] } }))
  await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { features, moderation: { summary: {}, events: [], lockdown: null } } }))
  await page.route('**/api/v1/guilds/1/features', route => route.fulfill({ json: { items: features } }))
  await page.route('**/api/v1/guilds/1/resources', route => route.fulfill({ json: { channels: [], roles: [], emojis: [], bot_permissions: '8' } }))
  await page.route('**/api/v1/guilds/1/tickets', route => route.fulfill({ json: { can_manage: !staff, summary: { open: 0, unclaimed: 0, closed_30d: 0 }, transcript_storage: { available: true } } }))
  await page.route('**/api/v1/guilds/1/tickets/items*', route => route.fulfill({ json: { items: [], next: null } }))
  await page.route('**/api/v1/guilds/1/tickets/settings', route => route.fulfill({ json: { enabled: false, revision: 1, open_limit: 3, transcript_retention_days: 30, log_channel_id: null, transcript_channel_id: null } }))
  await page.route('**/api/v1/guilds/1/reaction-roles', route => route.fulfill({ json: { settings: { enabled: false, revision: 0, log_channel_id: null, denial_dm: true, denial_dm_cooldown_seconds: 300 }, items: [], summary: { active: 0, pending: 0, failed: 0, scheduled: 0 }, recoveries: [] } }))
  await page.route('**/api/v1/guilds/1/reaction-roles/events*', route => route.fulfill({ json: { items: [], next: null } }))
  await page.route('**/api/v1/guilds/1/reaction-roles/link-groups', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/guilds/1/moderation/automod/rules', route => route.fulfill({ json: { items: [], trigger_types: ['keyword'] } }))
  for (const [path, heading, name] of [
    ['settings', 'サーバー設定', 'server-settings'],
    ['tickets', 'チケット', 'tickets'],
    ['reaction-roles', 'リアクションロール', 'reaction-roles'],
    ['moderation/automod', 'AutoMod', 'rules'],
  ]) {
    if (path === 'tickets') await page.locator('main a[href="/servers/1/tickets"]').click()
    else await page.goto(`/servers/1/${path}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true })
    if (path === 'tickets') {
      await page.locator('main a[href$="/inbox"]').first().click()
      await expect(page).toHaveURL(/\/tickets\/inbox$/)
      await page.goBack()
      await page.locator('main a[href$="/settings"]').click()
      await expect(page.getByRole('heading', { name: '設定', exact: true })).toBeVisible()
      await page.goBack()
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    }
    if (info.project.name === 'desktop') {
      await page.setViewportSize({ width: 414, height: 896 })
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: info.outputPath(`${name}-414.png`), fullPage: true })
      await page.setViewportSize({ width: 1440, height: 1000 })
    }
  }
  const mobile = page.getByRole('button', { name: 'Navigation', exact: true })
  if (await mobile.isVisible()) await mobile.click()
  await page.screenshot({ path: info.outputPath('manager-navigation.png'), fullPage: true })
  if (await mobile.isVisible()) await page.keyboard.press('Escape')
  staff = true
  await page.goto('/servers/1')
  await expect(page).toHaveURL(/\/tickets$/)
  await expect(page.getByRole('heading', { name: 'チケット', exact: true })).toBeVisible()
  await expect(page.locator('main a[href$="/settings"]')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('staff-tickets.png'), fullPage: true })
  await page.locator('main a[href$="/inbox"]').first().click()
  await expect(page).toHaveURL(/\/tickets\/inbox$/)
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'チケット', exact: true })).toBeVisible()
})
