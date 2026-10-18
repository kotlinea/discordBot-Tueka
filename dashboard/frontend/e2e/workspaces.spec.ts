import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import baseline from '../src/test/fixtures/feature_metadata.json' with { type: 'json' }
import ja from '../src/locales/ja'
import en from '../src/locales/en'

for (const locale of ['ja', 'en'] as const) {
  const copy = locale === 'ja' ? ja : en
  test(`workspace placement, internal navigation and staff boundaries (${locale})`, async ({ page }, info) => {
    test.setTimeout(90000)
    let staff = false
    let ticketSettings = { enabled: false, revision: 1, open_limit: 3, transcript_retention_days: 30, log_channel_id: null, transcript_channel_id: null }
    let rrSettings = { enabled: false, revision: 0, log_channel_id: null, denial_dm: true, denial_dm_cooldown_seconds: 300 }
    const writes: string[] = []
    const forbidden: string[] = []
    const features = [...baseline.features,{id:'applications',category:'community',docs_path:'/docs/features/applications',fields:[],required_fields:[],required_bot_permissions:[]},{id:'appeals',category:'moderation',docs_path:'/docs/features/appeals',fields:['retention_days'],required_fields:[],required_bot_permissions:[]},{id:'scheduled_messages',category:'engagement',docs_path:'/docs/features/scheduled-messages',fields:['retention_days'],required_fields:[],required_bot_permissions:[]},{id:'starboard',category:'engagement',docs_path:'/docs/features/starboard',fields:[],required_fields:[],required_bot_permissions:[]},{id:'giveaways',category:'engagement',docs_path:'/docs/features/giveaways',fields:[],required_fields:[],required_bot_permissions:[]},{id:'insights',category:'community',docs_path:'/docs/features/insights',fields:[],required_fields:[],required_bot_permissions:[]}].map(feature => ({ ...feature, title: feature.id, description: '', enabled: false, settings: {}, revision: 1, missing_permissions: [] }))
    await page.route('**/api/v1/session', route => route.fulfill({ json: { user: { id: '1', name: 'Reviewer', avatar_url: '' }, csrf_token: 'offline', preferences: { locale, appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } } }))
    await page.route('**/api/v1/guilds', route => route.fulfill({ json: { items: [{ id: '1', name: 'Workspace fixture', icon: null, access: staff ? 'ticket_staff' : 'manager' }] } }))
    await page.route('**/api/v1/guilds/1/**', route => {
      const path = new URL(route.request().url()).pathname.split('/guilds/1/')[1]
      if (staff && !['tickets', 'tickets/items', 'tickets/items/7'].includes(path)) forbidden.push(path)
      if (route.request().method() === 'PUT') {
        writes.push(path)
        expect(route.request().headers()['x-csrf-token']).toBe('offline')
        if (path === 'tickets/settings') {
          ticketSettings = { ...route.request().postDataJSON(), revision: ticketSettings.revision + 1 }
          return route.fulfill({ json: ticketSettings })
        }
        if (path === 'reaction-roles/settings') {
          rrSettings = { ...route.request().postDataJSON(), revision: rrSettings.revision + 1 }
          return route.fulfill({ json: rrSettings })
        }
        throw new Error(`Unexpected write: ${path}`)
      }
      const data: Record<string, unknown> = {
        features: { items: features },
        overview: { features, moderation: { summary: {}, events: [], lockdown: null } },
        resources: { channels: [{ id: '123456789012345678', name: 'general', type: 0 }], roles: [{ id: '123456789012345679', name: 'Member' }], emojis: [], bot_permissions: '8' },
        tickets: { can_manage: !staff, summary: { open: 0, unclaimed: 0, closed_30d: 1 }, transcript_storage: { available: true } },
        'tickets/items': { items: [{ id: 7, ticket_number: 42, status: 'closed', mode: 'channel', created_at: 1700000000 }], next: null },
        'tickets/items/7': { ticket: { id: 7, ticket_number: 42, status: 'closed', mode: 'channel', revision: 1 }, messages: [], transcript: null },
        'tickets/settings': ticketSettings,
        'reaction-roles': { settings: rrSettings, items: [], summary: { active: 0, pending: 0, failed: 0, scheduled: 0 }, recoveries: [] },
      }
      return route.fulfill({ json: data[path] ?? { items: [], next: null } })
    })
    await page.goto('/servers/1/settings')
    await expect(page.getByRole('heading', { name: copy.common.nav.settings, exact: true })).toBeVisible()
    await expect(page.locator('main')).toContainText('Workspace fixture')
    await expect(page.locator('main a[href*="/modules/"]')).toHaveCount(0)
    const guildLink = page.locator('header').getByRole('link', { name: 'Workspace fixture' })
    const guildBounds = (await guildLink.boundingBox())!
    const searchBounds = (await page.getByRole('button', { name: copy.common.nav.search, exact: true }).boundingBox())!
    expect(guildBounds.width).toBeGreaterThanOrEqual(44)
    expect(guildBounds.height).toBeGreaterThanOrEqual(44)
    expect(guildBounds.x + guildBounds.width).toBeLessThanOrEqual(searchBounds.x)
    const menu = page.getByRole('button', { name: 'Navigation', exact: true })
    if (await menu.isVisible()) await menu.click()
    const nav = page.getByRole('navigation', { name: 'Dashboard' }).filter({ visible: true })
    // Independent acceptance table: one main entry for every public feature.
    const groups = [
      [copy.common.nav.serverOperations, ['tickets', 'reaction-roles', 'applications']],
      [copy.common.nav.community, ['modules/welcome', 'modules/autorole', 'modules/leveling', 'modules/live_stats', 'modules/temporary_voice','insights']],
      [copy.common.nav.engagement, ['modules/advanced_polls', 'suggestions', 'modules/minigames', 'schedules', 'starboard', 'giveaways']],
      [copy.common.nav.moderation, ['modules/moderation', 'moderation/automod', 'moderation/anti_spam', 'moderation/anti_raid', 'moderation/infractions', 'moderation/moderation_actions', 'moderation/moderation_logs', 'moderation/audit_log', 'moderation/trust_score','appeals']],
      [copy.common.nav.social, ['social/youtube', 'social/twitch', 'social/tiktok', 'social/x', 'social/instagram']],
    ] as const
    await expect(nav.getByRole('link')).toHaveCount(32)
    for (const [name, paths] of groups) {
      const links = nav.getByRole('group', { name, exact: true }).getByRole('link')
      expect(await links.evaluateAll(nodes => nodes.map(node => node.getAttribute('href')))).toEqual(paths.map(path => `/servers/1/${path}`))
    }
    for (const link of await nav.getByRole('link').all()) expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    await page.screenshot({ path: info.outputPath(`navigation-${locale}.png`), fullPage: true })
    await nav.getByRole('link', { name: copy.tickets.tickets.title, exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const ticketHeading = page.getByRole('heading', { name: copy.tickets.tickets.title, exact: true })
    await expect(ticketHeading).toBeVisible()
    if (await menu.isVisible()) await expect(ticketHeading).toBeFocused()
    const internal = page.getByRole('navigation', { name: copy.common.common.featureNavigation })
    await expect(internal.getByRole('link')).toHaveCount(6)
    await internal.getByRole('link', { name: copy.tickets.tickets.configuration, exact: true }).click()
    await expect(page).toHaveURL(/\/tickets\/panels$/)
    const intake = page.getByRole('navigation', { name: copy.tickets.tickets.configuration, exact: true })
    await expect(intake.getByRole('link')).toHaveCount(5)
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.panels, exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`ticket-intake-${locale}.png`), fullPage: true })
    await intake.getByRole('link', { name: copy.tickets.tickets.forms, exact: true }).click()
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.forms, exact: true })).toBeVisible()
    await page.goBack()
    await page.getByRole('link', { name: copy.tickets.tickets.createPanel, exact: true }).first().click()
    await expect(page).toHaveURL(/\/tickets\/panels\/new$/)
    await page.getByRole('link', { name: copy.tickets.tickets.backToPanels, exact: true }).click()
    await expect(page).toHaveURL(/\/tickets\/panels$/)
    await internal.getByRole('link', { name: copy.tickets.tickets.transcripts, exact: true }).click()
    await page.getByRole('link', { name: /Ticket #42/ }).click()
    await expect(page).toHaveURL(/\/tickets\/inbox\/7$/)
    await expect(page.getByRole('heading', { name: 'Ticket #42', exact: true })).toBeVisible()
    await page.getByRole('navigation', { name: copy.common.common.breadcrumbs }).getByRole('link', { name: copy.tickets.tickets.inbox, exact: true }).click()
    await expect(page).toHaveURL(/\/tickets\/inbox$/)
    await internal.getByRole('link', { name: copy.tickets.tickets.settings, exact: true }).click()
    await page.getByRole('spinbutton', { name: copy.tickets.tickets.openLimit }).fill('4')
    await page.getByRole('button', { name: copy.common.common.save, exact: true }).click()
    await expect.poll(() => ticketSettings.open_limit).toBe(4)
    await internal.getByRole('link', { name: copy.common.nav.overview, exact: true }).click()
    await expect(ticketHeading).toBeVisible()

    await page.getByRole('button', { name: copy.common.nav.search, exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('textbox').fill(copy.common.nav.serverOperations)
    await expect(dialog.getByRole('button')).toHaveCount(3)
    await dialog.getByRole('button', { name: new RegExp(copy.reactionRoles.reactionRoles.title) }).click()
    const rrHeading = page.getByRole('heading', { name: copy.reactionRoles.reactionRoles.title, exact: true })
    await expect(rrHeading).toBeFocused()
    for (const name of [copy.reactionRoles.reactionRoles.linkGroups, copy.reactionRoles.reactionRoles.audit]) {
      await internal.getByRole('link', { name, exact: true }).click()
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
    }
    await internal.getByRole('link', { name: copy.reactionRoles.reactionRoles.settings, exact: true }).click()
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page).toHaveURL(/\/reaction-roles$/)
    await internal.getByRole('link', { name: copy.reactionRoles.reactionRoles.settings, exact: true }).click()
    await dialog.getByRole('spinbutton', { name: copy.reactionRoles.reactionRoles.dmCooldown }).fill('600')
    await dialog.getByRole('button', { name: copy.common.common.save, exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page).toHaveURL(/\/reaction-roles$/)
    expect(rrSettings.denial_dm_cooldown_seconds).toBe(600)
    expect(writes).toEqual(['tickets/settings', 'reaction-roles/settings'])
    await internal.getByRole('link', { name: copy.reactionRoles.reactionRoles.create, exact: true }).click()
    await expect(page).toHaveURL(/\/reaction-roles\/new$/)
    await page.getByRole('link', { name: copy.reactionRoles.reactionRoles.back, exact: true }).click()
    await expect(page).toHaveURL(/\/reaction-roles$/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    expect((await new AxeBuilder({ page }).analyze()).violations.filter(item => ['critical', 'serious'].includes(item.impact || ''))).toEqual([])
    await page.screenshot({ path: info.outputPath(`reaction-roles-${locale}.png`), fullPage: true })
    await page.goto('/servers/1/modules/tickets')
    await expect(page).toHaveURL(/\/tickets\/settings$/)
    await expect(page.getByRole('heading', { name: copy.tickets.tickets.settings, exact: true })).toBeVisible()
    await expect(page.getByRole('spinbutton', { name: copy.tickets.tickets.openLimit })).toHaveValue('4')
    await page.goto('/servers/1/modules/reaction_roles')
    await expect(page).toHaveURL(/\/reaction-roles$/)
    await expect(rrHeading).toBeVisible()

    staff = true
    await page.goto('/servers/1')
    await expect(ticketHeading).toBeVisible()
    await expect(internal.getByRole('link')).toHaveCount(3)
    await internal.getByRole('link', { name: copy.tickets.tickets.transcripts, exact: true }).click()
    await page.getByRole('link', { name: /Ticket #42/ }).click()
    await expect(page.getByRole('heading', { name: 'Ticket #42', exact: true })).toBeVisible()
    for (const path of ['tickets/panels/new', 'tickets/forms', 'tickets/settings', 'modules/tickets']) {
      await page.goto(`/servers/1/${path}`)
      await expect(page.getByRole('heading', { name: 'ページが見つかりません' })).toBeVisible()
    }
    expect(forbidden).toEqual([])
  })
}
