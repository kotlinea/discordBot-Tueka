import { Suspense, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { RegisteredFeatures } from '../routing/RegisteredFeatures'
import { Button } from '../components/ui/Button'
import { EmbedEditor } from '../components/editors/EmbedEditor'
import { api, ApiError } from '../api'
import type { Feature, TicketEmbed } from '../types'

vi.mock('../api', async importOriginal => {
  const original = await importOriginal<typeof import('../api')>()
  const api = vi.fn()
  return { ...original, api, request: (_operation: string, path: string, init?: RequestInit) => api(path, init), encodeBody: (_operation: string, body: unknown) => JSON.stringify(body) }
})
const request = vi.mocked(api)
const initial = (): Feature => ({ id: 'welcome', category: 'community', parent: null, title: '入退室', description: '', docs_path: '/docs/features/welcome', enabled: true, revision: 2, fields: ['welcome_enabled', 'welcome_channel_id', 'welcome_format', 'welcome_content'], required_fields: [], required_bot_permissions: [], missing_permissions: [], settings: { welcome_enabled: true, welcome_channel_id: '10', welcome_format: 'text', welcome_content: 'Hello {user}' } })
async function mount(locale = 'en', feature = initial()) {
  const i18n = createInstance()
  await i18n.init({ lng: locale, resources: { en, ja }, interpolation: { escapeValue: false } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const tree = (value: Feature) => <I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/modules/welcome']}><Link to="/servers/2/modules/welcome">Other server</Link><Suspense fallback="Loading"><Routes><Route path="/servers/:guildId/*" element={<RegisteredFeatures features={[value]}/>}/></Routes></Suspense></MemoryRouter></QueryClientProvider></I18nextProvider>
  const view = render(tree(feature))
  return { client, update: (value: Feature) => view.rerender(tree(value)) }
}
beforeEach(() => {
  vi.stubGlobal('confirm', vi.fn(() => true))
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  request.mockReset()
  request.mockImplementation(async (_path, init) => init?.method === 'PUT' ? { ...JSON.parse(String(init.body)), revision: 3 } : { channels: [{ id: '10', name: 'Welcome', type: 0 }], roles: [] })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('registered welcome settings', () => {
  it('refreshes clean data but preserves edits, and isolates drafts when changing servers', async () => {
    const mounted = await mount()
    const content = await screen.findByRole('textbox', { name: /Welcome content/ })
    mounted.update({ ...initial(), revision: 3, settings: { ...initial().settings, welcome_content: 'Refreshed' } })
    await waitFor(() => expect(content).toHaveValue('Refreshed'))
    fireEvent.change(content, { target: { value: 'Local draft' } })
    mounted.update({ ...initial(), revision: 4, settings: { ...initial().settings, welcome_content: 'Other server content' } })
    expect(content).toHaveValue('Local draft')
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    fireEvent.click(screen.getByRole('link', { name: 'Other server' }))
    expect(content).toHaveValue('Local draft')
    fireEvent.click(screen.getByRole('link', { name: 'Other server' }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Welcome content/ })).toHaveValue('Other server content'))
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
  it.each([['en', 'Welcome content'], ['ja', 'ウェルカム本文']])('loads the registered screen and fields in %s', async (locale, label) => {
    await mount(locale)
    expect(await screen.findByRole('textbox', { name: new RegExp(label) })).toHaveValue('Hello {user}')
  })
  it('saves the current revision and uses the returned revision for the next edit', async () => {
    await mount()
    const content = await screen.findByRole('textbox', { name: /Welcome content/ })
    fireEvent.change(content, { target: { value: 'Updated' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
    expect(JSON.parse(String(request.mock.calls.find(([, init]) => init?.method === 'PUT')?.[1]?.body)).revision).toBe(2)
    fireEvent.click(screen.getByRole('switch', { name: 'Enable feature' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
    const last = request.mock.calls.filter(([, init]) => init?.method === 'PUT').at(-1)!
    expect(JSON.parse(String(last[1]?.body))).toMatchObject({ enabled: false, revision: 3, settings: { welcome_content: 'Updated' } })
  })
  it.each([403, 409, 422])('retains input and dirty state after HTTP %s until explicit discard', async status => {
    await mount()
    const content = await screen.findByRole('textbox', { name: /Welcome content/ })
    fireEvent.change(content, { target: { value: 'Keep my edit' } })
    request.mockRejectedValue(new ApiError(status, 'rejected', 'Save rejected'))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0))
    expect(content).toHaveValue('Keep my edit')
    expect(screen.getByRole('region')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(content).toHaveValue('Hello {user}')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('shared controls', () => {
  it('preserves form submission, ref, aria and loading semantics', () => {
    const submit = vi.fn(event => event.preventDefault())
    const ref = { current: null as HTMLButtonElement | null }
    const { rerender } = render(<><form id="sample" onSubmit={submit}><input required aria-label="Required"/></form><Button type="submit" form="sample" ref={ref} aria-label="Save">Save</Button></>)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Required'), { target: { value: 'ready' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).toHaveBeenCalledTimes(1)
    expect(ref.current).toBe(screen.getByRole('button'))
    rerender(<Button loading aria-label="Save">Save</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
  it('uses caller constraints and variables and emits embed edits without saving', async () => {
    const i18n = createInstance()
    await i18n.init({ lng: 'en', resources: { en, ja } })
    const value: TicketEmbed = { color: '#5865F2', title: '', title_url: '', description: '', image_url: '', thumbnail_url: '', author: { enabled: false, name: '', icon_url: '', url: '' }, footer: { enabled: false, text: '', icon_url: '', timestamp: false }, fields: [] }
    const changed = vi.fn()
    function Editor() {
      const [embed, set] = useState(value)
      return <EmbedEditor title="Message" value={embed} onChange={next => { changed(next); set(next) }} variables={['{sample}']} limits={{ title: 12, description: 40, authorName: 10, footerText: 10, fields: 1, fieldName: 8, fieldValue: 20 }}/>
    }
    render(<I18nextProvider i18n={i18n}><Editor/></I18nextProvider>)
    expect(screen.getByLabelText('Title')).toHaveAttribute('maxlength', '12')
    expect(screen.getByText('{sample}')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Example' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add field' }))
    expect(screen.getByRole('button', { name: 'Add field' })).toBeDisabled()
    expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({ title: 'Example', fields: [{ name: '', value: '', inline: false }] })
    expect(request).not.toHaveBeenCalled()
  })
})
