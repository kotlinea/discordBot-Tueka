import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Shell } from '../app/Shell'
import { ApiError } from '../api'
import type { Session } from '../types'
import '../i18n'

vi.mock('../routing/RegisteredFeatures', () => ({ RegisteredFeatures: function Editor() {
  const [value, setValue] = useState('')
  return <input aria-label="Synthetic draft" value={value} onChange={event => setValue(event.target.value)}/>
} }))
vi.mock('../app/Preferences', () => ({ PreferencesDialog: () => null }))
vi.mock('../app/Navigation', () => ({ CommandPalette: () => null, Breadcrumbs: () => null }))
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it.each(['503', 'network'])('preserves the current editor when a background Guild-list refetch fails with cached data: %s', async failure => {
  const guilds = { items: [{ id: '1', name: 'Synthetic Guild', icon: null, access: 'admin' }] }
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['guilds'], guilds)
  client.setQueryData(['features', '1'], { items: [] })
  const session: Session = { user: { id: 'user1', name: 'Synthetic', avatar_url: '' }, csrf_token: 'fake', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
  vi.stubGlobal('fetch', vi.fn(async () => { if (failure === 'network') throw new TypeError('Synthetic transient outage'); return new Response(JSON.stringify({ message: 'Synthetic transient outage' }), { status: 503, headers: { 'content-type': 'application/json' } }) }))
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={<Shell session={session}/>}/></Routes></MemoryRouter></QueryClientProvider>)
  fireEvent.change(screen.getByLabelText('Synthetic draft'), { target: { value: 'Unsaved input' } })
  await act(async () => { await client.invalidateQueries({ queryKey: ['guilds'] }) })
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Synthetic transient outage'))
  expect(screen.getByLabelText('Synthetic draft')).toHaveValue('Unsaved input')
})


it.each([['guilds', 401], ['guilds', 403], ['features', 401], ['features', 403]] as const)('blocks a cached editor after %s authorization failure %i', async (query, status) => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['guilds'], { items: [{ id: '1', name: 'Synthetic Guild', icon: null, access: 'admin' }] })
  client.setQueryData(['features', '1'], { items: [] })
  const session: Session = { user: { id: 'user1', name: 'Synthetic', avatar_url: '' }, csrf_token: 'fake', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={<Shell session={session}/>}/></Routes></MemoryRouter></QueryClientProvider>)
  fireEvent.change(screen.getByLabelText('Synthetic draft'), { target: { value: 'Unsaved input' } })
  await act(async () => {
    await client.fetchQuery({ queryKey: query === 'guilds' ? ['guilds'] : ['features', '1'], staleTime: 0, queryFn: async () => { throw new ApiError(status, 'forbidden', 'Access lost') } }).catch(() => {})
  })
  // 403 blocks interaction but retains the draft for permission recovery; 401 still tears down the workspace.
  await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Synthetic draft' })).not.toBeInTheDocument())
  if (status === 403) {
    expect(screen.getByLabelText('Synthetic draft')).not.toBeVisible()
    expect(screen.getByLabelText('Synthetic draft')).toHaveValue('Unsaved input')
    expect(screen.getByLabelText('Synthetic draft').closest('[inert]')).toHaveAttribute('hidden')
  } else expect(screen.queryByLabelText('Synthetic draft')).not.toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Access lost')
})

it('blocks the current editor when a successful Guild-list refresh removes its membership', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['guilds'], { items: [{ id: '1', name: 'Synthetic Guild', icon: null, access: 'admin' }] })
  client.setQueryData(['features', '1'], { items: [] })
  const session: Session = { user: { id: 'user1', name: 'Synthetic', avatar_url: '' }, csrf_token: 'fake', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={<Shell session={session}/>}/></Routes></MemoryRouter></QueryClientProvider>)
  fireEvent.change(screen.getByLabelText('Synthetic draft'), { target: { value: 'Unsaved input' } })
  await act(async () => { client.setQueryData(['guilds'], { items: [] }) })
  await waitFor(() => expect(screen.queryByLabelText('Synthetic draft')).not.toBeInTheDocument())
  expect(screen.getByRole('heading', { name: 'ページが見つかりません' })).toBeInTheDocument()
})
