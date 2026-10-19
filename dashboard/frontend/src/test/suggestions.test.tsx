import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from "../locales/en"
import ja from "../locales/ja"
import Suggestions from "../features/engagement/suggestions/Settings"
import { api } from "../api"

vi.mock('../api', async importOriginal => { const original = await importOriginal<typeof import('../api')>(); const api = vi.fn(); return { ...original, api, request: (_operation: string, path: string, init?: RequestInit) => api(path, init), encodeBody: (_operation: string, body: unknown) => JSON.stringify(body) } })
const request = vi.mocked(api)
const initial = () => ({ enabled: true, revision: 1, missing_permissions: [], docs_path: '', settings: {
  channel_id: '10', log_channel_id: null, review_role_ids: [], allow_voting: true, show_author: true,
  form_title: 'Ideas', form_fields: [{ key: 'idea', label: 'Idea', placeholder: '', style: 'paragraph', required: true, min_length: 1, max_length: 100 }],
} })
async function mount(locale = 'en') {
  const i18n = createInstance()
  await i18n.init({ lng: locale, resources: { en, ja }, interpolation: { escapeValue: false } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/suggestions']}><Routes><Route path="/servers/:guildId/suggestions" element={<Suggestions/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
  return client
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  request.mockReset()
  request.mockImplementation(async path => {
    if (path.endsWith('/resources')) return { channels: [{ id: '10', name: 'Ideas', type: 0 }], roles: [] }
    if (path.includes('/items')) return { items: [] }
    return initial()
  })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Suggestions settings', () => {
  it.each(['en','ja'])('reviews with a reason, preserves edits on conflict, and reads history in %s', async locale => {
    const text=(locale==='en'?en:ja).suggestions.suggestions
    const item={id:1,author_id:'20',message_id:'100',status:'approved',answers:{idea:'Guide'},upvotes:1,downvotes:0,reviewer_id:'30',created_at:1000,revision:2,review_reason:'Useful',discussion_thread_id:'100'}
    request.mockImplementation(async(path,init)=>{
      if(init?.method==='POST')throw new Error('revision_conflict')
      if(path.endsWith('/events'))return {items:[{id:1,actor_id:'30',event_type:'status_changed',detail:{status:'approved',reason:'History reason'},created_at:1000}]}
      if(path.includes('/items'))return {items:[item]}
      if(path.endsWith('/resources'))return {channels:[],roles:[]}
      return initial()
    })
    const client=await mount(locale)
    const input=await screen.findByRole('textbox',{name:text.reason})
    const button=screen.getByRole('button',{name:text.status.implemented})
    expect(button).toBeDisabled()
    fireEvent.change(input,{target:{value:'Released'}})
    await act(async()=>{client.setQueryData(['suggestionsItems','1'],{items:[{...item,revision:3}]})})
    fireEvent.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent('revision_conflict')
    expect(input).toHaveValue('Released')
    const call=request.mock.calls.find(([,init])=>init?.method==='POST')
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({revision:2,status:'implemented',reason:'Released'})
    fireEvent.click(screen.getByRole('button',{name:text.history}))
    expect(await screen.findByText(/History reason/)).toBeInTheDocument()
    expect(screen.getByRole('link',{name:text.discussionOpen})).toHaveAttribute('href','https://discord.com/channels/1/100')
    await act(async()=>{client.setQueryData(['suggestionsItems','1'],{items:[{...item,status:'implemented',revision:4}]})})
    expect(input).toHaveValue('Released')
    await waitFor(()=>expect(input).toBeDisabled())
    fireEvent.click(screen.getByRole('button',{name:(locale==='en'?en:ja).common.common.discard}))
    expect(screen.queryByRole('textbox',{name:text.reason})).not.toBeInTheDocument()
  })
  it('shows an initial settings failure instead of loading forever', async () => {
    request.mockRejectedValue(new Error('Settings unavailable'))
    await mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Settings unavailable')
  })
  it.each([['en', 'Move up', 'Additional information'], ['ja', '上へ', '追加情報']])('localizes field controls in %s', async (locale, label, fieldLabel) => {
    await mount(locale)
    expect(await screen.findByRole('button', { name: label })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: (locale === 'en' ? en : ja).suggestions.suggestions.addField }))
    expect(screen.getByDisplayValue(fieldLabel)).toBeInTheDocument()
  })
  it('saves disabling without a channel and restores the server response', async () => {
    const client = await mount()
    fireEvent.click(await screen.findByRole('switch', { name: 'Enable Suggestions' }))
    fireEvent.change(screen.getByRole('combobox', { name: /^Suggestion channel/ }), { target: { value: '' } })
    let saved = initial()
    request.mockImplementation(async (path, init) => {
      if (init?.method === 'PUT') { saved = { ...initial(), ...JSON.parse(String(init.body)), revision: 2 }; return saved }
      if (path.endsWith('/settings')) return saved
      if (path.endsWith('/resources')) return { channels: [], roles: [] }
      return { items: [] }
    })
    const buttons = screen.getAllByRole('button', { name: 'Save changes' })
    fireEvent.click(buttons[buttons.length - 1])
    await waitFor(() => expect(request).toHaveBeenCalledWith('/guilds/1/suggestions/settings', expect.objectContaining({ method: 'PUT' })))
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
    expect(client.getQueryData(['suggestionsSettings', '1'])).toMatchObject({ enabled: false, revision: 2, settings: { channel_id: null } })
  })
  it('preserves local edits after a background refresh and a failed save', async () => {
    const client = await mount()
    const input = await screen.findByRole('textbox', { name: 'Form title' })
    fireEvent.change(input, { target: { value: 'Local edit' } })
    await act(async () => { client.setQueryData(['suggestionsSettings', '1'], { ...initial(), revision: 2 }) })
    expect(input).toHaveValue('Local edit')
    request.mockRejectedValue(new Error('revision_conflict'))
    fireEvent.click(screen.getAllByRole('button', { name: 'Save changes' })[0])
    expect(await screen.findByRole('alert')).toHaveTextContent('revision_conflict')
    expect(input).toHaveValue('Local edit')
    const write = request.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(write?.[1]?.body)).revision).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(input).toHaveValue('Ideas')
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
})
