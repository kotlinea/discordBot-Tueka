import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { request, ApiError } from '../api'
import { RuleList } from '../features/moderation/RuleList'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('reports partial deletion and retries only the remaining rule with its original revision', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.stubGlobal('confirm', vi.fn(() => true))
  const api = vi.mocked(request)
  let items = [{ id: 1, name: 'First', revision: 3, enabled: false, stop_on_match: false, trigger_type: 'keyword', mode: 'monitor' }, { id: 2, name: 'Second', revision: 4, enabled: false, stop_on_match: false, trigger_type: 'keyword', mode: 'monitor' }]
  let rejectSecond = true
  api.mockImplementation(async (operation, path) => {
    if (operation.startsWith('DELETE')) {
      const id = Number(path.split('/').at(-1))
      if (id === 2 && rejectSecond) throw new ApiError(409, 'revision_conflict', 'Second changed')
      items = items.filter(item => item.id !== id)
      return undefined as never
    }
    return { items, next: null } as never
  })
  const i18n = createInstance()
  await i18n.init({ lng: 'en', resources: { en, ja }, fallbackNS: 'common', react: { nsMode: 'fallback' } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/moderation/automod']}><Routes><Route path="/servers/:guildId/moderation/automod" element={<RuleList family="automod"/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
  for (const name of ['First', 'Second']) {
    const row = (await screen.findByText(name)).closest('[role="row"]') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'Mark for deletion' }))
  }
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Second changed')
  expect(screen.queryByText('First')).not.toBeInTheDocument()
  expect(screen.getByText('Second')).toBeInTheDocument()
  expect(screen.getByText(en.common.editing.partialDeleted.replace('{{count}}', '1'))).toBeInTheDocument()
  rejectSecond = false
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await waitFor(() => expect(screen.queryByText('Second')).not.toBeInTheDocument())
  const deletes = api.mock.calls.filter(([operation]) => operation.startsWith('DELETE'))
  expect(deletes.map(([, path]) => path.split('/').at(-1))).toEqual(['1', '2', '2'])
  expect(deletes.map(([, , options]) => options?.headers)).toEqual([{ 'if-match': '3' }, { 'if-match': '4' }, { 'if-match': '4' }])
  expect(items).toEqual([])
})
