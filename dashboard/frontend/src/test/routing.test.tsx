import { routeScreen } from './routeScreens'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { Suspense } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RegisteredFeatures } from '../routing/RegisteredFeatures'
import { StandaloneFeatures } from '../routing/StandaloneFeatures'
import { activeFeature, featureBreadcrumbs, paletteItems } from '../routing/catalog'
import { featureRegistry } from '../features/registry'
import '../i18n'

vi.mock('../features/DefaultSettings', () => ({ default: routeScreen('settings') }))
vi.mock('../features/community/welcome/Settings', () => ({ default: routeScreen('welcome') }))
vi.mock('../features/engagement/suggestions/Settings', () => ({ default: routeScreen('suggestions') }))
vi.mock('../features/community/reaction_roles/Overview', () => ({ ReactionRoleOverview: routeScreen('roles'), ReactionRoleSettingsPage: routeScreen('role-settings') }))
vi.mock('../features/community/reaction_roles/Groups', () => ({ ReactionRoleGroups: routeScreen('role-groups') }))
vi.mock('../features/community/reaction_roles/Events', () => ({ ReactionRoleEvents: routeScreen('role-events') }))
vi.mock('../features/community/reaction_roles/Editor', () => ({ ReactionRoleEditor: routeScreen('role-editor') }))
vi.mock('../features/moderation/Hub', () => ({ ModerationHub: routeScreen('moderation') }))
vi.mock('../features/moderation/RuleList', () => ({ RuleList: routeScreen('rules') }))
vi.mock('../features/moderation/RuleEditor', () => ({ RuleEditor: routeScreen('rule-editor') }))
vi.mock('../features/moderation/Infractions', () => ({ Infractions: routeScreen('infractions') }))
vi.mock('../features/moderation/Actions', () => ({ Actions: routeScreen('actions') }))
vi.mock('../features/moderation/Logs', () => ({ Logs: routeScreen('logs') }))
vi.mock('../features/social/Hub', () => ({ SocialHub: routeScreen('social') }))
vi.mock('../features/social/Provider', () => ({ SocialProviderPage: routeScreen('provider') }))
vi.mock('../features/community/tickets/Hub', () => ({ TicketHub: routeScreen('tickets') }))
vi.mock('../features/community/tickets/Inbox', () => ({ TicketInbox: routeScreen('inbox') }))
vi.mock('../features/community/tickets/Detail', () => ({ TicketDetail: routeScreen('ticket') }))
vi.mock('../features/community/tickets/Panels', () => ({ TicketPanels: routeScreen('panels') }))
vi.mock('../features/community/tickets/PanelEditor', () => ({ default: routeScreen('panel-editor') }))
vi.mock('../features/community/tickets/Settings', () => ({ TicketSettingsPage: routeScreen('ticket-settings') }))
vi.mock('../features/community/tickets/Archive', () => ({ TicketArchive: routeScreen('archive') }))
vi.mock('../features/community/tickets/Stats', () => ({ TicketStats: routeScreen('stats') }))
vi.mock('../features/community/tickets/Transcript', () => ({ TranscriptStandalone: routeScreen('transcript') }))
vi.mock('../features/community/tickets/Configuration', () => {
  return { TicketPanelMessages: routeScreen('panel-messages'), TicketForms: routeScreen('forms'), TicketTeams: routeScreen('teams'), TicketTags: routeScreen('tags') }
})

afterEach(cleanup)
beforeAll(async () => {
  for (const route of featureRegistry.routes) await featureRegistry.loadRoute(route.path)
  for (const category of featureRegistry.categories.filter(category => category.hub)) await featureRegistry.loadCategory(category.id)
  for (const feature of featureRegistry.features) for (const route of feature.standalone ?? []) await route.load()
})
async function mount(path: string, staffOnly = false) {
  await act(async () => { render(<MemoryRouter initialEntries={[path]}><Suspense fallback="Loading"><Routes>
    <Route path="/servers/:guildId/*" element={<RegisteredFeatures features={[]} staffOnly={staffOnly}/>}/>
    <Route path="*" element={<StandaloneFeatures/>}/>
  </Routes></Suspense></MemoryRouter>) })
}

describe('registered routes preserve direct links and parameters', () => {
  const paths: [string, Record<string, string>][] = [
    ['modules/welcome', { screen: 'welcome' }],
    ...['autorole', 'leveling', 'live_stats', 'temporary_voice', 'advanced_polls', 'minigames', 'moderation', 'automod', 'anti_spam', 'anti_raid', 'audit_log', 'trust_score', 'infractions', 'moderation_actions', 'moderation_logs', 'youtube_updates', 'twitch_updates', 'tiktok_updates', 'x_updates', 'instagram_updates'].map(id => [`modules/${id}`, { screen: 'settings', feature: id }] as [string, Record<string, string>]),
    ['moderation/audit_log', { screen: 'settings', feature: 'audit_log' }], ['moderation/trust_score', { screen: 'settings', feature: 'trust_score' }],
    ['modules/tickets', { screen: 'ticket-settings' }], ['modules/reaction_roles', { screen: 'roles' }], ['modules/suggestions', { screen: 'suggestions' }],
    ['suggestions', { screen: 'suggestions' }], ['reaction-roles', { screen: 'roles' }], ['reaction-roles/new', { screen: 'role-editor' }], ['reaction-roles/35', { screen: 'role-editor', configId: '35' }],
    ['reaction-roles/link-groups', { screen: 'role-groups' }], ['reaction-roles/events', { screen: 'role-events' }], ['reaction-roles/settings', { screen: 'role-settings' }],
    ['moderation', { screen: 'moderation' }], ['social', { screen: 'social' }],
    ...['automod', 'anti_spam', 'anti_raid'].flatMap(family => [
      [`moderation/${family}`, { screen: 'rules', family }], [`moderation/${family}/rules/new`, { screen: 'rule-editor', family }], [`moderation/${family}/rules/72`, { screen: 'rule-editor', family, ruleId: '72' }],
    ] as [string, Record<string, string>][]),
    ['moderation/infractions', { screen: 'infractions' }], ['moderation/moderation_actions', { screen: 'actions' }], ['moderation/moderation_logs', { screen: 'logs' }],
    ...['youtube', 'twitch', 'tiktok', 'x', 'instagram'].map(provider => [`social/${provider}`, { screen: 'provider', provider }] as [string, Record<string, string>]),
    ['tickets', { screen: 'tickets' }], ['tickets/inbox', { screen: 'inbox' }], ['tickets/inbox/23', { screen: 'ticket', ticketId: '23' }],
    ['tickets/panels', { screen: 'panels' }], ['tickets/panels/new', { screen: 'panel-editor' }], ['tickets/panels/4', { screen: 'panel-editor', panelId: '4' }],
    ['tickets/panel-messages', { screen: 'panel-messages' }], ['tickets/forms', { screen: 'forms' }], ['tickets/teams', { screen: 'teams' }], ['tickets/tags', { screen: 'tags' }], ['tickets/settings', { screen: 'ticket-settings' }], ['tickets/transcripts', { screen: 'archive' }], ['tickets/stats', { screen: 'stats' }],
  ]
  it.each(paths)('%s selects the correct lazy screen', async (path, expected) => {
    await mount(`/servers/123/${path}`)
    expect(JSON.parse((await screen.findByTestId('route')).textContent!)).toMatchObject({ ...expected, guildId: '123' })
  })
  it('keeps the standalone transcript URL and ID', async () => {
    await mount('/tickets/transcripts/678')
    expect(JSON.parse((await screen.findByTestId('route')).textContent!)).toMatchObject({ screen: 'transcript', transcriptId: '678' })
  })
  it('retains the reaction role unknown-child redirect', async () => {
    await mount('/servers/1/reaction-roles/unknown/child')
    expect(JSON.parse((await screen.findByTestId('route')).textContent!)).toMatchObject({ screen: 'roles', guildId: '1' })
  })
  it.each(['unknown', 'modules/unknown', 'social/unknown', 'moderation/unknown', 'moderation/automod/unknown', 'tickets/unknown'])('rejects unknown %s', async path => {
    await mount(`/servers/1/${path}`)
    expect(await screen.findByRole('heading', { name: 'ページが見つかりません' })).toBeInTheDocument()
  })
  it('resolves ticket detail for staff and hides manager-only screens', async () => {
    await mount('/servers/1/tickets/inbox/23', true)
    expect(await screen.findByTestId('route')).toHaveTextContent('ticket')
    cleanup()
    await mount('/servers/1/modules/welcome', true)
    expect(await screen.findByRole('heading', { name: 'ページが見つかりません' })).toBeInTheDocument()
  })
  it('builds nested breadcrumbs and palette paths from registrations', () => {
    const t = (key: string) => key
    expect(featureBreadcrumbs('/servers/1/moderation/anti_raid/rules/new', '1', [], t)).toEqual([
      { label: 'nav.moderation', to: '/servers/1/moderation' }, { label: 'moderation.anti_raid', to: '/servers/1/moderation/anti_raid' }, { label: 'common.create', to: undefined },
    ])
    expect(featureBreadcrumbs('/servers/1/tickets/panel-messages', '1', [], t).map(item => item.label)).toEqual(['nav.serverOperations', 'tickets.title', 'tickets.panelMessages'])
    expect(featureBreadcrumbs('/servers/1/social/youtube', '1', [], t).map(item => item.label)).toEqual(['nav.social', 'YouTube social.title'])
    expect(paletteItems('1', [], t).map(item => item.path)).toEqual(['/servers/1', '/servers/1/settings', '/servers/1/moderation', '/servers/1/social'])
    expect(activeFeature('/servers/1/tickets/inbox/4')?.screenKind).toBe('workspace')
    expect(featureRegistry.features.filter(item => item.access === 'ticket_staff').map(item => item.id)).toEqual(['tickets'])
  })
  it.each(['tickets/panels', 'tickets/panels/new', 'tickets/panels/4', 'tickets/forms', 'tickets/teams', 'tickets/panel-messages', 'tickets/tags', 'tickets/stats', 'tickets/settings', 'modules/tickets'])('blocks manager-only workspace path for staff: %s', async path => {
    await mount(`/servers/123/${path}`, true)
    expect(await screen.findByRole('heading', { name: 'ページが見つかりません' })).toBeInTheDocument()
    expect(screen.queryByTestId('route')).not.toBeInTheDocument()
  })
  it('keeps nested list breadcrumbs and intake grouping local to tickets', async () => {
    await mount('/servers/123/tickets/panels/4')
    await screen.findByTestId('route')
    expect(screen.getByRole('navigation', { name: '受付設定' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'フォーム' })).toHaveAttribute('href', '/servers/123/tickets/forms')
    expect(featureBreadcrumbs('/servers/123/tickets/inbox/23', '123', [], key => key)).toEqual([
      { label: 'nav.serverOperations', to: undefined },
      { label: 'tickets.title', to: '/servers/123/tickets' },
      { label: 'tickets.inbox', to: '/servers/123/tickets/inbox' },
      { label: '#23', to: undefined },
    ])
  })
})
