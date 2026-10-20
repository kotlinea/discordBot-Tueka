import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import { FormEditor } from '../features/community/applications/Forms'
import { request } from '../api'
import type { ApplicationForm } from '../generated/api'

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('removes a middle question then adds a question with a unique key and saves', async () => {
  const form: ApplicationForm = { id: 1, guild_id: '1', revision: 2, created_at: 1, updated_at: 1,
    title: 'Synthetic form', enabled: true, retention_days: 30, fields: ['answer', 'answer_2', 'answer_3'].map(key =>
      ({ key, label: key, style: 'paragraph' as const, required: true, min_length: 1, max_length: 1000 })) }
  vi.mocked(request).mockResolvedValue(form)
  const i18n = createInstance()
  await i18n.init({ lng: 'en', resources: { en }, interpolation: { escapeValue: false } })
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter>
    <FormEditor guildId="1" item={form}/>
  </MemoryRouter></QueryClientProvider></I18nextProvider>)
  const text = en.applications.applications
  fireEvent.click(screen.getAllByRole('button', { name: text.removeQuestion })[1])
  fireEvent.click(screen.getByRole('button', { name: text.addQuestion }))
  const keys = screen.getAllByRole('textbox', { name: text.key }).map(input => (input as HTMLInputElement).value)
  expect(new Set(keys).size).toBe(keys.length)
  const labels = screen.getAllByRole('textbox', { name: text.label })
  fireEvent.change(labels[labels.length - 1], { target: { value: 'Added question' } })
  fireEvent.click(screen.getByRole('button', { name: en.common.common.save }))
  await waitFor(() => expect(request).toHaveBeenCalledOnce())
  const body = JSON.parse(String(vi.mocked(request).mock.calls[0][2]?.body))
  expect(new Set(body.fields.map((field: { key: string }) => field.key)).size).toBe(3)
  expect(body.revision).toBe(2)
  expect(body.fields.map((field: { label: string }) => field.label)).toEqual(['answer', 'answer_3', 'Added question'])
})
