import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider, useNavigate } from 'react-router-dom'
import { useUnsavedChanges } from '../components/forms/useUnsavedChanges'
import { NavigationGuard } from '../components/forms/NavigationGuard'
import '../i18n'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('protects browser back and imperative navigation, and allows an explicit successful-save redirect', async () => {
  // jsdom's AbortSignal is a different realm from Node's native Request.
  const NativeRequest = globalThis.Request
  vi.stubGlobal('Request', class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) { super(input, { ...init, signal: undefined }) }
  })
  vi.stubGlobal('confirm', vi.fn(() => false))
  function Editor() {
    const [dirty, setDirty] = useState(true)
    const [pending, setPending] = useState(false)
    const navigate = useNavigate()
    const allowLeave = useUnsavedChanges(dirty, pending)
    return <><h1>Editor</h1><button onClick={() => navigate('/other')}>Search result</button><button onClick={() => setPending(true)}>Saving</button><button onClick={() => { setDirty(false); allowLeave(); navigate('/other') }}>Saved</button></>
  }
  const router = createMemoryRouter([{ path: '/edit', element: <NavigationGuard><Editor/></NavigationGuard> }, { path: '/other', element: <h1>Other</h1> }], { initialEntries: ['/other', '/edit'] })
  render(<RouterProvider router={router}/>)
  await act(async () => { await router.navigate(-1) })
  expect(screen.getByRole('heading', { name: 'Editor' })).toBeInTheDocument()
  expect(window.confirm).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Search result' }))
  await waitFor(() => expect(window.confirm).toHaveBeenCalledTimes(2))
  expect(screen.getByRole('heading', { name: 'Editor' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Saving' }))
  vi.mocked(window.confirm).mockReturnValue(true)
  fireEvent.click(screen.getByRole('button', { name: 'Search result' }))
  expect(screen.getByRole('heading', { name: 'Editor' })).toBeInTheDocument()
  expect(window.confirm).toHaveBeenCalledTimes(2)
  fireEvent.click(screen.getByRole('button', { name: 'Saved' }))
  expect(await screen.findByRole('heading', { name: 'Other' })).toBeInTheDocument()
})
