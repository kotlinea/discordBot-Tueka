import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createInstance } from 'i18next'
import en from '../locales/en'
import ja from '../locales/ja'
import { Actions } from '../features/moderation/Actions'

vi.mock('../api', async importOriginal => {
  const original = await importOriginal<typeof import('../api')>()
  return { ...original, request: vi.fn(async () => ({ channels: [{id:'10',name:'Text',type:0},{id:'15',name:'Forum',type:15},{id:'20',name:'Voice',type:2}], roles: [] })) }
})
afterEach(cleanup)

describe('Manual moderation action duration', () => {
  it.each(['en','ja'])('enforces supported periods and channels without promising automatic unban in %s', async locale => {
    const i18n = createInstance()
    await i18n.init({ lng: locale, resources: { en, ja }, interpolation: { escapeValue: false } })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<I18nextProvider i18n={i18n}><QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/moderation/actions']}><Routes><Route path="/servers/:guildId/moderation/actions" element={<Actions/>}/></Routes></MemoryRouter></QueryClientProvider></I18nextProvider>)
    const timeout = await screen.findByRole('radio', { name: 'timeout' })
    fireEvent.click(timeout)
    const duration = screen.getByRole('spinbutton') as HTMLInputElement
    expect(duration).toHaveAttribute('max', '40320')
    fireEvent.change(duration, { target: { value: '40321' } })
    expect(duration.validity.rangeOverflow).toBe(true)
    fireEvent.click(screen.getByRole('radio', { name: 'lockdown' }))
    expect(screen.getByRole('spinbutton')).toHaveAttribute('max', '1440')
    fireEvent.click(screen.getByRole('radio', { name: 'ban' }))
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'lock' }))
    expect(await screen.findByRole('option',{name:'Forum'})).toBeInTheDocument()
    expect(screen.queryByRole('option',{name:'Voice'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio',{name:'purge'}))
    expect(screen.queryByRole('option',{name:'Forum'})).not.toBeInTheDocument()
    expect(screen.getByRole('option',{name:'Text'})).toBeInTheDocument()
    expect(screen.getByRole('spinbutton',{name:locale==='en'?'Count':'件数'})).toHaveAttribute('max','100')
    expect(screen.getByRole('button',{name:locale==='en'?'Queue action':'処置をキューへ追加'})).toBeInTheDocument()
  })
})
