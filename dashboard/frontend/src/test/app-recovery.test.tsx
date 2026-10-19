import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { ApiError } from '../api'
import '../i18n'

vi.mock('../app/Shell', () => ({ Shell: function Editor() {
  const [value, setValue] = useState('')
  return <input aria-label="Synthetic draft" value={value} onChange={event => setValue(event.target.value)}/>
} }))
vi.mock('../app/Preferences', () => ({ applyPreferences: () => {} }))
afterEach(cleanup)

it.each(['503', 'network', '401', '403'])('handles session background failure %s with cached data', async failure => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['session'], { user: { id: 'user1', name: 'Synthetic', avatar_url: '' }, csrf_token: 'fake', preferences: { locale: 'ja', appearance: 'precision', color_scheme: 'light', navigation_collapsed: false, revision: 1 } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/servers/1/test']}><App/></MemoryRouter></QueryClientProvider>)
  fireEvent.change(await screen.findByLabelText('Synthetic draft'), { target: { value: 'Unsaved input' } })
  await act(async () => {
    await client.fetchQuery({ queryKey: ['session'], staleTime: 0, queryFn: async () => { throw failure === 'network' ? new TypeError('Synthetic failure') : new ApiError(Number(failure), 'failure', 'Synthetic failure') } }).catch(() => {})
  })
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Synthetic failure'))
  if (failure === '503' || failure === 'network') expect(screen.getByLabelText('Synthetic draft')).toHaveValue('Unsaved input')
  else expect(screen.queryByLabelText('Synthetic draft')).not.toBeInTheDocument()
})
