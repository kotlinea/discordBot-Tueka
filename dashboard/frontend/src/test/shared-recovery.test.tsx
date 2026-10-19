import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useSettingsDraft } from '../components/forms/useSettingsDraft'
import { useSaveMutation } from '../components/forms/useSaveMutation'
import { api, ApiError } from '../api'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const initial = { name: 'Original', revision: 1 }

describe('D20a shared draft recovery', () => {
  it('adopts a known remote revision after the user manually returns to the original value', () => {
    const { result, rerender } = renderHook(({ source }) => useSettingsDraft(source, initial, 'guild1'), { initialProps: { source: initial } })
    act(() => result.current.setDraft({ name: 'Local', revision: 1 }))
    const remote = { name: 'Remote', revision: 2 }
    rerender({ source: remote })
    expect(result.current.draft).toEqual({ name: 'Local', revision: 1 })
    expect(result.current.changedRemotely).toBe(true)
    act(() => result.current.setDraft(initial))
    expect(result.current.dirty).toBe(false)
    expect(result.current.draft).toEqual(remote)
  })
  it('resets draft and revision for a different Guild identity', () => {
    const { result, rerender } = renderHook(({ source, identity }) => useSettingsDraft(source, initial, identity), { initialProps: { source: initial, identity: 'guild1' } })
    act(() => result.current.setDraft({ name: 'Local', revision: 1 }))
    const second = { name: 'Other Guild', revision: 8 }
    rerender({ source: second, identity: 'guild2' })
    expect(result.current.draft).toEqual(second)
    expect(result.current.dirty).toBe(false)
  })
  it.each([403, 409, 422])('retains input and revision after a delayed %i response and permits retry', async status => {
    let finish!: (value: Response) => void
    const fetchMock = vi.fn(() => new Promise<Response>(resolve => { finish = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result } = renderHook(() => {
      const editor = useSettingsDraft(initial, initial, 'guild1')
      const save = useSaveMutation({ mutationFn: (value: typeof initial) => api<typeof initial>('/fake', { method: 'PUT', body: JSON.stringify(value) }), onSuccess: value => editor.accept(value) })
      return { editor, save }
    }, { wrapper })
    act(() => result.current.editor.setDraft({ name: 'Local', revision: 1 }))
    act(() => { result.current.save.mutate(result.current.editor.draft); result.current.save.mutate(result.current.editor.draft) })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await act(async () => finish(new Response(JSON.stringify({ code: 'test_failure', message: 'Synthetic failure' }), { status, headers: { 'content-type': 'application/json' } })))
    await waitFor(() => expect(result.current.save.isError).toBe(true))
    expect(result.current.save.error).toBeInstanceOf(ApiError)
    expect(result.current.editor.draft).toEqual({ name: 'Local', revision: 1 })
    expect(result.current.editor.dirty).toBe(true)
    act(() => result.current.save.mutate(result.current.editor.draft))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await act(async () => finish(new Response(JSON.stringify({ name: 'Local', revision: 2 }), { headers: { 'content-type': 'application/json' } })))
    await waitFor(() => expect(result.current.save.isSuccess).toBe(true))
    expect(result.current.editor.draft).toEqual({ name: 'Local', revision: 2 })
    expect(result.current.editor.dirty).toBe(false)
  })
})


it('accepts a successful save without reverting to a deferred pre-save query snapshot', () => {
  const { result, rerender } = renderHook(({ source }) => useSettingsDraft(source, initial, '1'), { initialProps: { source: initial } })
  act(() => result.current.setDraft({ name: 'Local', revision: 1 }))
  const remote = { name: 'Remote', revision: 2 }
  rerender({ source: remote })
  const saved = { name: 'Saved', revision: 3 }
  act(() => result.current.accept(saved))
  rerender({ source: remote })
  expect(result.current.draft).toEqual(saved)
  expect(result.current.dirty).toBe(false)
})

it('keeps remote updates while externally dirty and applies the latest one when that work clears', () => {
  const { result, rerender } = renderHook(({ source, pending }) => useSettingsDraft(source, initial, '1', pending), { initialProps: { source: initial, pending: true } })
  const remote = { name: 'Remote', revision: 2 }
  rerender({ source: remote, pending: true })
  expect(result.current.draft).toEqual(initial)
  rerender({ source: remote, pending: false })
  expect(result.current.draft).toEqual(remote)
})

it('discards to the latest remote snapshot and clears the deferred refresh', () => {
  const { result, rerender } = renderHook(({ source }) => useSettingsDraft(source, initial, '1'), { initialProps: { source: initial } })
  act(() => result.current.setDraft({ name: 'Local', revision: 1 }))
  rerender({ source: { name: 'Remote', revision: 2 } })
  const latest = { name: 'Latest', revision: 3 }
  rerender({ source: latest })
  act(() => result.current.discard())
  expect(result.current.draft).toEqual(latest)
  expect(result.current.dirty).toBe(false)
})

