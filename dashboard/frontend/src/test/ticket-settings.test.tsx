import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { request, ApiError } from '../api'
import { TicketSettingsPage } from '../features/community/tickets/Settings'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
const api = vi.mocked(request)
const initial = () => ({ enabled: true, revision: 1, open_limit: 3, transcript_retention_days: 30, log_channel_id: null, transcript_channel_id: null })
let persisted = initial()
async function mount() {
  const i18n = createInstance()
  await i18n.init({ lng: 'en', resources: { en, ja } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/tickets/settings']}><Routes><Route path="/servers/:guildId/tickets/settings" element={<TicketSettingsPage/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
  return client
}
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  persisted = initial()
  api.mockReset()
  api.mockImplementation(async (operation, path, options) => {
    if (path.endsWith('/resources')) return { channels: [], roles: [] } as never
    if (operation.startsWith('PUT')) persisted = { ...JSON.parse(String(options?.body)), revision: persisted.revision + 1 }
    return persisted as never
  })
})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})

describe('Ticket settings share the editing contract', () => {
  it.each([403, 409, 422])('preserves the original revision and input after %s and discards to the refreshed value', async status => {
    const client = await mount()
    const limit = await screen.findByRole('spinbutton', { name: en.tickets.tickets.openLimit })
    fireEvent.change(limit, { target: { value: '5' } })
    await act(async () => { client.setQueryData(['ticketSettings', '1'], { ...initial(), revision: 2, open_limit: 7 }) })
    api.mockRejectedValue(new ApiError(status, 'rejected', `Rejected ${status}`))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(`Rejected ${status}`)
    expect(limit).toHaveValue(5)
    expect(JSON.parse(String(api.mock.calls.find(([operation]) => operation.startsWith('PUT'))?.[2]?.body))).toMatchObject({ revision: 1, open_limit: 5 })
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(limit).toHaveValue(7)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('disables edits and duplicate saves while pending, then refetches the saved settings', async () => {
    await mount()
    const limit = await screen.findByRole('spinbutton', { name: en.tickets.tickets.openLimit })
    fireEvent.change(limit, { target: { value: '5' } })
    let finish!: () => void
    api.mockImplementation(async (operation, path, options) => {
      if (path.endsWith('/resources')) return { channels: [], roles: [] } as never
      if (operation.startsWith('PUT')) {
        persisted = { ...JSON.parse(String(options?.body)), revision: 2 }
        await new Promise<void>(resolve => { finish = resolve })
      }
      return persisted as never
    })
    const save = screen.getByRole('button', { name: 'Save changes' })
    fireEvent.click(save)
    fireEvent.click(save)
    await waitFor(() => expect(save).toBeDisabled())
    expect(limit).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Discard changes' })).toBeDisabled()
    await act(async () => finish())
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
    expect(limit).toHaveValue(5)
    expect(api.mock.calls.filter(([operation]) => operation.startsWith('PUT'))).toHaveLength(1)
    expect(api.mock.calls.filter(([operation]) => operation.startsWith('GET') && operation.endsWith('/settings'))).toHaveLength(2)
  })
  it('shows a failed initial read and recovers through retry', async () => {
    api.mockRejectedValue(new Error('Unavailable'))
    await mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable')
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    api.mockImplementation(async (_operation, path) => (path.endsWith('/resources') ? { channels: [], roles: [] } : initial()) as never)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('spinbutton', { name: en.tickets.tickets.openLimit })).toHaveValue(3)
  })
})
