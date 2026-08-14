import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const session = { user: { id: '1', name: 'Moderator', avatar_url: 'https://cdn.discordapp.com/embed/avatars/0.png' }, csrf_token: 'csrf', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
const feature = (id: string, category: string, parent: string | null = null) => ({ id, category, parent, title: id, description: `${id} settings`, fields: [], required_fields: [], required_bot_permissions: [], enabled: true, settings: {}, revision: 1, missing_permissions: [] })
const welcome = { ...feature('welcome','community'), title: '入退室', fields: ['welcome_enabled','welcome_channel_id','welcome_format','welcome_content'], settings: { welcome_enabled: false, welcome_channel_id: null, welcome_format: 'text', welcome_content: '' } }
const reactionRoles = { ...feature('reaction_roles','community'), title: 'リアクションロール', fields: ['reaction_role_channel_id','reaction_role_ids'], settings: { reaction_role_channel_id: null, reaction_role_ids: [] } }

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: session }))
  await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Maple Server', icon: null }] } }))
  await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { guild_id: '1', features: [feature('moderation','moderation'), feature('automod','moderation','moderation'), feature('anti_spam','moderation','moderation'), feature('anti_raid','moderation','moderation'), feature('infractions','moderation','moderation'), feature('moderation_actions','moderation','moderation'), feature('moderation_logs','moderation','moderation'), welcome, reactionRoles], resources: { channels: [], roles: [], bot_permissions: '8' }, moderation: { summary: {}, events: [], lockdown: null } } }))
  await page.route('**/api/v1/guilds/1/resources', route => route.fulfill({ json: { channels: [{ id: '123456789012345678', name: '一般', type: 0 }], roles: [{ id: '123456789012345679', name: 'メンバー' }, { id: '123456789012345680', name: '通知' }], bot_permissions: '8' } }))
})

test('resource selections preserve snowflake IDs and module labels are Japanese', async ({ page }) => {
  let saved: Record<string, any> | undefined
  await page.route('**/api/v1/guilds/1/modules/reaction_roles', async route => {
    saved = route.request().postDataJSON()
    await route.fulfill({ json: reactionRoles })
  })
  await page.goto('/servers/1/modules/reaction_roles')
  await page.getByLabel('パネル投稿先').selectOption('123456789012345678')
  await page.getByLabel('メンバー').check()
  await page.getByLabel('通知').check()
  await page.getByRole('region', { name: 'Unsaved changes' }).getByRole('button', { name: '変更を保存' }).click()
  await expect.poll(() => saved).toBeTruthy()
  expect(saved?.settings.reaction_role_channel_id).toBe('123456789012345678')
  expect(saved?.settings.reaction_role_ids).toEqual(['123456789012345679', '123456789012345680'])

  await page.goto('/servers/1/modules/welcome')
  await expect(page.getByText('ウェルカムメッセージ', { exact: true })).toBeVisible()
  await expect(page.getByLabel('ウェルカム送信先')).toBeVisible()
  await expect(page.getByLabel('ウェルカム表示形式')).toBeVisible()
})

test('overview is responsive and accessible', async ({ page }) => {
  await page.goto('/servers/1')
  await expect(page.getByRole('heading', { name: '概要' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['critical','serious'].includes(item.impact || ''))).toEqual([])
})
