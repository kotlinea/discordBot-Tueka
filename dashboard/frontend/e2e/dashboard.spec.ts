import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const session = { user: { id: '1', name: 'Moderator', avatar_url: 'https://cdn.discordapp.com/embed/avatars/0.png' }, csrf_token: 'csrf', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
const feature = (id: string, category: string, parent: string | null = null) => ({ id, category, parent, title: id, description: `${id} settings`, fields: [], required_fields: [], required_bot_permissions: [], enabled: true, settings: {}, revision: 1, missing_permissions: [] })
const welcome = { ...feature('welcome','community'), title: '入退室', fields: ['welcome_enabled','welcome_channel_id','welcome_format','welcome_content'], settings: { welcome_enabled: false, welcome_channel_id: null, welcome_format: 'text', welcome_content: '' } }
const reactionRoles = { ...feature('reaction_roles','community'), title: 'リアクションロール', fields: ['reaction_role_channel_id','reaction_role_ids'], settings: { reaction_role_channel_id: null, reaction_role_ids: [] } }
const rule = (id: number, name: string) => ({ id, guild_id: 1, family: 'automod', event_type: 'message_create', name, enabled: true, mode: 'enforce', priority: id * 10, stop_on_match: false, trigger_type: 'keyword', trigger_config: { keywords: ['bad'], allow_list: [], match: 'wildcard' }, conditions: { channel_policy: 'all_except', role_policy: 'all_except', channel_ids: [], required_role_ids: [] }, exemptions: { channel_ids: [], role_ids: [] }, actions: [{ type: 'delete' }, { type: 'log', message: '{rule}: {reason}' }], revision: 1 })

test('suggestions save bar validates and persists edits', async ({ page }) => {
  let writes = 0
  let settings = { ...feature('suggestions', 'engagement'), settings: {
    channel_id: '123456789012345678', log_channel_id: null, review_role_ids: [], allow_voting: true, show_author: true,
    form_title: 'Ideas', form_fields: [{ key: 'idea', label: 'Idea', placeholder: '', style: 'paragraph', required: true, min_length: 1, max_length: 100 }],
  } }
  await page.route('**/api/v1/guilds/1/suggestions/items*', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/guilds/1/suggestions/settings', async route => {
    if (route.request().method() === 'PUT') { writes++; settings = { ...route.request().postDataJSON(), revision: settings.revision + 1 } }
    await route.fulfill({ json: settings })
  })
  await page.goto('/servers/1/suggestions')
  const label = page.locator('#suggestions-settings input[required]').first()
  await label.fill('')
  const saveBar = page.getByRole('region').filter({ has: page.getByRole('button', { name: '変更を保存' }) })
  await saveBar.getByRole('button', { name: '変更を保存' }).click()
  expect(await label.evaluate((element: HTMLInputElement) => element.validity.valueMissing)).toBe(true)
  expect(writes).toBe(0)
  await label.fill('Updated idea')
  await saveBar.getByRole('button', { name: '変更を保存' }).click()
  await expect.poll(() => writes).toBe(1)
  await expect(saveBar).toHaveCount(0)
  await page.reload()
  await expect(label).toHaveValue('Updated idea')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  const audit = await new AxeBuilder({ page }).analyze()
  expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
})

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: session }))
  await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Maple Server', icon: null }] } }))
  await page.route('**/api/v1/guilds/1/overview', route => route.fulfill({ json: { guild_id: '1', features: [feature('moderation','moderation'), feature('automod','moderation','moderation'), feature('anti_spam','moderation','moderation'), feature('anti_raid','moderation','moderation'), feature('infractions','moderation','moderation'), feature('moderation_actions','moderation','moderation'), feature('moderation_logs','moderation','moderation'), feature('tickets','community'), welcome, reactionRoles], resources: { channels: [], roles: [], bot_permissions: '8' }, moderation: { summary: {}, events: [], lockdown: null } } }))
  await page.route('**/api/v1/guilds/1/resources', route => route.fulfill({ json: { channels: [{ id: '123456789012345678', name: '一般', type: 0 }, { id: '123456789012345681', name: 'サポート', type: 4 }], roles: [{ id: '123456789012345679', name: 'メンバー' }, { id: '123456789012345680', name: '通知' }], emojis: [{ id: '123456789012345682', name: 'ticket', animated: false }], bot_permissions: '8' } }))
})

test('resource selections preserve snowflake IDs and module labels are Japanese', async ({ page }) => {
  let saved: Record<string, any> | undefined
  const suggestionSettings = { ...feature('suggestions','engagement'), settings: {
    channel_id: null, log_channel_id: null, review_role_ids: [], allow_voting: true, show_author: true,
    form_title: 'Ideas', form_fields: [{ key: 'idea', label: 'Idea', placeholder: '', style: 'paragraph', required: true, min_length: 1, max_length: 100 }],
  } }
  await page.route('**/api/v1/guilds/1/suggestions/items*', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/guilds/1/suggestions/settings', async route => {
    if (route.request().method() === 'PUT') saved = route.request().postDataJSON()
    await route.fulfill({ json: saved ? { ...saved, revision: 2 } : suggestionSettings })
  })
  await page.goto('/servers/1/suggestions')
  await page.getByRole('combobox', { name: /^提案の投稿チャンネル/ }).selectOption('123456789012345678')
  await page.getByRole('checkbox', { name: 'メンバー', exact: true }).check()
  await page.getByRole('checkbox', { name: '通知', exact: true }).check()
  await page.getByRole('region', { name: '未保存の変更があります' }).getByRole('button', { name: '変更を保存' }).click()
  await expect.poll(() => saved).toBeTruthy()
  expect(saved?.settings.channel_id).toBe('123456789012345678')
  expect(saved?.settings.review_role_ids).toEqual(['123456789012345679', '123456789012345680'])

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

test('rule scope uses one policy and action options open in a dialog', async ({ page }) => {
  await page.route('**/api/v1/guilds/1/moderation/automod/rules', route => route.fulfill({ json: { items: [], trigger_types: ['keyword'] } }))
  await page.goto('/servers/1/moderation/automod/rules/new')
  await page.getByRole('button', { name: /適用範囲・例外/ }).click()
  const channels = page.getByRole('heading', { name: 'チャンネル' }).locator('..').locator('..')
  await channels.getByRole('button', { name: '選択したものだけ対象' }).click()
  await expect(page.getByRole('button', { name: '次へ' })).toBeDisabled()
  await channels.getByRole('button', { name: 'すべて選択' }).click()
  await expect(page.getByRole('button', { name: '次へ' })).toBeEnabled()
  await page.getByRole('button', { name: '次へ' }).click()
  await page.getByRole('button', { name: '警告ポイント' }).click()
  await page.getByRole('button', { name: '警告ポイントを設定' }).click()
  await expect(page.getByLabel('加算ポイント')).toHaveValue('1')
  await page.getByRole('button', { name: 'キャンセル' }).click()
  await page.getByRole('button', { name: 'モデレーションログを設定' }).click()
  await expect(page.getByRole('dialog')).toContainText('{reason}')
})

test('rule order and stop behavior are saved from the list', async ({ page }) => {
  let saved: Record<string, any> | undefined
  await page.route('**/api/v1/guilds/1/moderation/automod/rules**', async route => {
    if (route.request().method() === 'PUT') { saved = route.request().postDataJSON(); await route.fulfill({ json: { items: [] } }); return }
    await route.fulfill({ json: { items: [rule(1, 'first'), rule(2, 'second')], trigger_types: ['keyword'] } })
  })
  await page.goto('/servers/1/moderation/automod')
  await page.getByRole('button', { name: 'firstを下へ' }).click()
  await page.getByRole('switch').first().click()
  await page.getByRole('region', { name: 'Unsaved changes' }).getByRole('button', { name: '変更を保存' }).click()
  await expect.poll(() => saved).toBeTruthy()
  expect(saved?.items.map((item: Record<string, unknown>) => item.id)).toEqual([2, 1])
  expect(saved?.items[0].stop_on_match).toBe(true)
})

test('social account registration only requires an account and Discord channel', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  const template = { content: '', title: '{title}', description: '{account}\n{url}', color: '#5865F2', url: '{url}', thumbnail_url: '{avatar}', image_url: '{thumbnail}', footer: '{platform}' }
  let saved: Record<string, any> | undefined
  await page.route('**/api/v1/guilds/1/social/youtube/subscriptions', async route => {
    if (route.request().method() === 'POST') { saved = route.request().postDataJSON(); await route.fulfill({ status: 201, json: { id: 1 } }); return }
    await route.fulfill({ json: { items: [], available: true, events: ['video','live_start','live_end'], limit: 10, variables: ['account','title','url'], defaults: { video: template, live_start: template, live_end: template } } })
  })
  await page.goto('/servers/1/social/youtube')
  const breadcrumb = page.getByRole('navigation', { name: 'パンくず' })
  await expect(breadcrumb.getByRole('link', { name: 'Servers' })).toHaveAttribute('href', '/servers')
  await expect(breadcrumb.getByRole('link', { name: 'Maple Server' })).toHaveAttribute('href', '/servers/1')
  await expect(breadcrumb.getByRole('link', { name: '通知・ソーシャル' })).toHaveAttribute('href', '/servers/1/social')
  await expect(breadcrumb.locator('[aria-current="page"]')).toHaveText('YouTube 通知・ソーシャル')
  await page.getByRole('button', { name: 'アカウントを追加' }).first().click()
  await page.getByLabel('アカウントID／ハンドル').fill('UCExample')
  await page.getByLabel('既定の通知チャンネル').selectOption('123456789012345678')
  await page.getByRole('button', { name: '通知Embedを編集' }).click()
  await expect(page.getByRole('dialog').last()).toContainText('{account}')
  await page.getByRole('button', { name: '閉じる' }).last().click()
  await page.getByRole('button', { name: '変更を保存' }).click()
  await expect.poll(() => saved).toBeTruthy()
  expect(saved?.account).toBe('UCExample')
  expect(saved?.channel_id).toBe('123456789012345678')
  expect(saved?.events).toEqual(['video','live_start','live_end'])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)
})

test('ticket panel editor keeps one draft across six responsive tabs', async ({ page }) => {
  let saved: Record<string, any> | undefined
  const team = { id: 7, name: 'Support', role_ids: ['123456789012345680'], user_ids: [], manager_user_ids: [], notification_channel_id: null, on_call_user_ids: [], revision: 1 }
  await page.route('**/api/v1/guilds/1/tickets/teams', route => route.fulfill({ json: { items: [team] } }))
  await page.route('**/api/v1/guilds/1/tickets/forms', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/guilds/1/tickets/panel-messages', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/guilds/1/tickets/panels/bundles', async route => {
    saved = route.request().postDataJSON()
    await route.fulfill({ status: 201, json: { ...saved, panel: { ...saved?.panel, id: 9, revision: 1 }, deployment: { ...saved?.deployment, id: 3, panel_ids: [9], revision: 1 }, deployments: [] } })
  })
  await page.route('**/api/v1/guilds/1/tickets/panels/preview', route => route.fulfill({ json: { panel_message: { title: 'サポートチケット', description: '下のボタンからお問い合わせください。', content: '' }, button: { style: 'primary', label: 'チケットを作成', emoji: '' }, welcome_message: { title: 'ようこそ', description: '受付しました', fields: [] } } }))
  await page.goto('/servers/1/tickets/panels/new')
  await page.getByLabel('設定名').fill('請求サポート')
  await page.getByLabel('サポートチーム').selectOption('7')
  await page.getByLabel('チケットカテゴリー').selectOption('123456789012345681')
  const mobileTabs = page.locator('select').filter({ has: page.locator('option[value="panel"]') })
  if (await mobileTabs.isVisible()) await mobileTabs.selectOption('panel')
  else await page.getByRole('tab', { name: 'パネル' }).click()
  await page.getByLabel('設置名').fill('問い合わせ窓口')
  await page.getByLabel('パネルチャンネル').selectOption('123456789012345678')
  await expect(page.getByRole('region', { name: '未保存の変更があります' })).toContainText('2タブ変更')
  await page.getByRole('region', { name: '未保存の変更があります' }).getByRole('button', { name: 'プレビュー' }).click()
  await expect(page.getByRole('dialog')).toContainText('サポートチケット')
  await page.getByRole('dialog').getByRole('button').first().click()
  await page.getByRole('region', { name: '未保存の変更があります' }).getByRole('button', { name: '保存' }).click()
  await expect.poll(() => saved).toBeTruthy()
  expect(saved?.panel.name).toBe('請求サポート')
  expect(saved?.panel.category_id).toBe('123456789012345681')
  expect(saved?.deployment.channel_id).toBe('123456789012345678')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(item => ['critical','serious'].includes(item.impact || ''))).toEqual([])
})
