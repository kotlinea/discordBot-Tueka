import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRegistry } from '../features/catalog'
import { defineFeature } from '../features/defaults'
import { featureRegistry as original } from '../features/registry'
import type { CategoryDefinition } from '../features/contracts'
import type { Feature, Session } from '../types'
import '../i18n'

const probe = defineFeature({ id: 'g5_probe', category: 'community', fields: { text: { labelKey: 'G5 input' } } })
const custom = defineFeature({ id: 'g5_custom', category: 'g5_category', path: 'g5/custom',
  load: async () => ({ default: () => <h1>G5 dedicated screen</h1> }) })
const extra: CategoryDefinition = { id: 'g5_category', titleKey: 'G5 category', features: [custom] }
const metadata = (id: string, category: string): Feature => ({ id, category, parent: null, title: id,
  description: '', docs_path: '/docs/features/test', enabled: false, revision: 3, settings: { text: 'initial' },
  fields: ['text'], required_fields: [], required_bot_permissions: [], missing_permissions: [] })
const session: Session = { user: { id: '20', name: 'Test', avatar_url: '/test-avatar.png' }, csrf_token: 'test',
  preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 0 } }

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.doUnmock('../features/registry'); vi.doUnmock('../api') })

async function mount(mode: 'existing' | 'category' | 'removed', path: string) {
  vi.resetModules()
  const categories = original.categories.map(category => category.id === 'community' && mode === 'existing'
    ? { ...category, features: [...category.features, probe] } : category)
  const registry = createRegistry(mode === 'category' ? [...categories, extra] : categories)
  const feature = metadata(mode === 'category' ? custom.id : probe.id, mode === 'category' ? extra.id : probe.category)
  const features = mode === 'removed' ? [] : [feature]
  const request = vi.fn(async (_operation: string, endpoint: string, init?: RequestInit) => {
    if (endpoint === '/guilds') return { items: [{ id: '1', name: 'G5 guild', icon: null, access: 'admin' }] }
    if (endpoint.endsWith('/overview')) return { features, moderation: { summary: {}, events: [], lockdown: null } }
    if (endpoint.endsWith('/resources')) return { channels: [], roles: [] }
    if (init?.method === 'PUT') return { ...JSON.parse(String(init.body)), revision: 4 }
    throw new Error(`Unexpected request ${endpoint}`)
  })
  // Replace only the explicit registry export and the HTTP transport.
  vi.doMock('../features/registry', () => ({ featureRegistry: registry }))
  vi.doMock('../api', async importOriginal => ({ ...await importOriginal<typeof import('../api')>(), request }))
  const { Shell } = await import('../app/Shell')
  const routing = await import('../routing/catalog')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  await act(async () => { render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/servers/1/${path}`]}><Routes>
    <Route path="/servers/:guildId/*" element={<Shell session={session}/>}/>
  </Routes></MemoryRouter></QueryClientProvider>) })
  return { request, registry, routing, features }
}

describe('registration-only extension through the real Shell', () => {
  it('adds a feature to an existing category with default editing, navigation and saving', async () => {
    const { request, routing, features } = await mount('existing', 'modules/g5_probe')
    const input = await screen.findByRole('textbox', { name: 'G5 input' })
    expect(input).toHaveValue('initial')
    expect(within(screen.getByRole('navigation', { name: 'Dashboard' })).getByRole('link', { name: probe.id })).toHaveAttribute('href', '/servers/1/modules/g5_probe')
    expect(routing.featureBreadcrumbs('/servers/1/modules/g5_probe', '1', features, key => key).at(-1)?.label).toBe(probe.id)
    expect(routing.paletteItems('1', features, key => key)).toContainEqual({ title: probe.id, path: '/servers/1/modules/g5_probe' })
    fireEvent.change(input, { target: { value: 'saved through default' } })
    fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
    await waitFor(() => expect(request.mock.calls.some(([, , init]) => init?.method === 'PUT')).toBe(true))
    const saved = request.mock.calls.find(([, , init]) => init?.method === 'PUT')!
    expect(saved[1]).toBe('/guilds/1/modules/g5_probe')
    expect(JSON.parse(String(saved[2]?.body))).toMatchObject({ revision: 3, settings: { text: 'saved through default' } })
  })
  it('adds a category and a dedicated override without editing Shell or Router composition', async () => {
    const { routing, features } = await mount('category', custom.path)
    expect(await screen.findByRole('heading', { name: 'G5 dedicated screen' })).toBeInTheDocument()
    expect(screen.getByText('G5 category')).toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: 'Dashboard' })).getByRole('link', { name: custom.id })).toHaveAttribute('href', '/servers/1/g5/custom')
    expect(routing.paletteItems('1', features, key => key)).toContainEqual({ title: custom.id, path: '/servers/1/g5/custom' })
  })
  it.each(['modules/g5_probe', 'g5/custom'])('removing registration removes route and navigation for %s', async path => {
    const { registry, routing } = await mount('removed', path)
    expect(await screen.findByRole('heading', { name: 'ページが見つかりません' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /g5_probe|g5_custom/ })).not.toBeInTheDocument()
    expect(() => registry.get('g5_probe')).toThrow('Unknown feature')
    expect(routing.activeFeature(`/servers/1/${path}`)).toBeUndefined()
    expect(routing.paletteItems('1', [], key => key).some(item => item.path.includes('g5'))).toBe(false)
  })
})
