import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ModuleSettings } from '../components/feature/ModuleSettings'
import type { Feature } from '../types'
import '../i18n'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
it('adopts the latest Module revision when manual edits return to a clean form', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['resources', '1'], { channels: [], roles: [] })
  const initial: Feature = { id: 'test', category: 'community', parent: null, title: 'Test', description: '', docs_path: '', enabled: false, revision: 1, fields: ['name'], required_fields: [], required_bot_permissions: [], missing_permissions: [], settings: { name: 'Original' } }
  const tree = (feature: Feature) => <QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><Routes><Route path="/servers/:guildId/*" element={<ModuleSettings feature={feature} renderField={({ value, onChange }) => <input aria-label="Module value" value={String(value)} onChange={event => onChange(event.target.value)}/>}/>}/></Routes></MemoryRouter></QueryClientProvider>
  const { rerender } = render(tree(initial))
  fireEvent.change(screen.getByLabelText('Module value'), { target: { value: 'Local' } })
  rerender(tree({ ...initial, revision: 2, settings: { name: 'Remote' } }))
  expect(screen.getByLabelText('Module value')).toHaveValue('Local')
  fireEvent.change(screen.getByLabelText('Module value'), { target: { value: 'Original' } })
  await waitFor(() => expect(screen.getByLabelText('Module value')).toHaveValue('Remote'))
})
