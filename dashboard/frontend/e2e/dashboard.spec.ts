import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const session = { user: { id: '1', name: 'Moderator', avatar_url: 'https://cdn.discordapp.com/embed/avatars/0.png' }, csrf_token: 'csrf', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
const feature = (id: string, category: string, parent: string | null = null) => ({ id, category, parent, title: id, description: `${id} settings`, fields: [], required_fields: [], required_bot_permissions: [], enabled: true, settings: {}, revision: 1, missing_permissions: [] })

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: session }))
  await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Maple Server', icon: null }] } }))
  await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { guild_id: '1', features: [feature('moderation','moderation'), feature('automod','moderation','moderation'), feature('anti_spam','moderation','moderation'), feature('anti_raid','moderation','moderation'), feature('infractions','moderation','moderation'), feature('moderation_actions','moderation','moderation'), feature('moderation_logs','moderation','moderation'), feature('welcome','community')], resources: { channels: [], roles: [], bot_permissions: '8' }, moderation: { summary: {}, events: [], lockdown: null } } }))
})

test('overview is responsive and accessible', async ({ page }) => {
  await page.goto('/servers/1')
  await expect(page.getByRole('heading', { name: '概要' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['critical','serious'].includes(item.impact || ''))).toEqual([])
})
