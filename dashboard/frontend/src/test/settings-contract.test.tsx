import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useSettingsDraft } from '../components/forms/useSettingsDraft'
import { useSaveMutation } from '../components/forms/useSaveMutation'
import { configurationIssues } from '../components/feature/ConfigurationState'
import type { Feature } from '../types'
import { feature as leveling } from '../features/community/leveling.feature'
import { SaveBar } from '../components/SaveBar'
import '../i18n'

afterEach(cleanup)

it('does not label a pristine dialog as unsaved or offer an enabled save', () => {
  render(<SaveBar inline dirty={false} pending={false} onDiscard={() => {}} onSave={() => {}}/>)
  expect(screen.getByRole('region', { name: '未保存の変更はありません' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '変更を保存' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '閉じる' })).toBeEnabled()
})

describe('settings draft contract', () => {
  const initial = { name: 'Original', revision: 1 }
  it('adopts clean refreshes, retains dirty values and revision, and discards to the latest source', () => {
    const { result, rerender } = renderHook(({ source, identity }) => useSettingsDraft(source, initial, identity), { initialProps: { source: initial, identity: '1' } })
    rerender({ source: { name: 'Refreshed', revision: 2 }, identity: '1' })
    expect(result.current.draft.revision).toBe(2)
    act(() => result.current.setDraft({ ...result.current.draft, name: 'Local' }))
    rerender({ source: { name: 'Remote', revision: 3 }, identity: '1' })
    expect(result.current.draft).toEqual({ name: 'Local', revision: 2 })
    expect(result.current.changedRemotely).toBe(true)
    act(() => result.current.discard())
    expect(result.current.draft).toEqual({ name: 'Remote', revision: 3 })
    expect(result.current.dirty).toBe(false)
    act(() => result.current.setDraft({ ...result.current.draft, name: 'Local again' }))
    rerender({ source: initial, identity: '2' })
    expect(result.current.draft).toEqual(initial)
    expect(result.current.dirty).toBe(false)
  })
  it('does not revert an accepted save to the old query snapshot', () => {
    const { result, rerender } = renderHook(() => useSettingsDraft(initial, initial, '1'))
    act(() => result.current.accept({ name: 'Saved', revision: 2 }))
    rerender()
    expect(result.current.draft).toEqual({ name: 'Saved', revision: 2 })
    expect(result.current.dirty).toBe(false)
  })
  it('preserves externally tracked changes such as pending deletions during refetch', () => {
    const { result, rerender } = renderHook(({ source, pending }) => useSettingsDraft(source, initial, '1', pending), { initialProps: { source: initial, pending: true } })
    rerender({ source: { name: 'Remote', revision: 2 }, pending: true })
    expect(result.current.draft).toEqual(initial)
    expect(result.current.dirty).toBe(true)
  })
})

describe('save submission contract', () => {
  it('guards same-tick duplicate submissions and permits retry after failure', async () => {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    let reject!: (error: Error) => void
    const mutationFn = vi.fn(() => new Promise<string>((_resolve, fail) => { reject = fail }))
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSaveMutation({ mutationFn }), { wrapper })
    act(() => { result.current.mutate(); result.current.mutate() })
    await waitFor(() => expect(mutationFn).toHaveBeenCalledTimes(1))
    await act(async () => reject(new Error('revision_conflict')))
    await waitFor(() => expect(result.current.isError).toBe(true))
    mutationFn.mockResolvedValue('saved')
    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mutationFn).toHaveBeenCalledTimes(2)
  })
})

describe('saved configuration and execution conditions', () => {
  const feature = (overrides: Partial<Feature> = {}): Feature => ({ id: 'child', category: 'community', parent: null, title: '', description: '', docs_path: '', enabled: true, revision: 1, fields: [], required_fields: [], required_bot_permissions: [], missing_permissions: [], settings: {}, ...overrides })
  it('keeps unknown metadata distinct from a disabled setting', () => {
    expect(configurationIssues(undefined, [])).toEqual(['unknown'])
    expect(configurationIssues(feature({ enabled: false }), [])).toEqual([])
    expect(configurationIssues(feature({ parent: 'absent' }), [])).toEqual(['unknown'])
  })
  it('reports disabled ancestors, missing permissions and required settings independently', () => {
    const child = feature({ parent: 'parent', required_fields: ['channel_id'], missing_permissions: ['manage_roles'] })
    expect(configurationIssues(child, [feature({ id: 'parent', enabled: false })])).toEqual(['parentOff', 'permissions', 'required'])
  })
  it('uses registered resource overrides for fields without conventional names', () => {
    const child = feature({ settings: { temp_voice_trigger_id: '123' } })
    expect(configurationIssues(child, [], { channels: [], roles: [] }, { temp_voice_trigger_id: { resource: 'voice' } })).toEqual(['resourceMissing'])
    expect(configurationIssues(child, [], { channels: [{ id: '123', name: 'Voice', type: 2 }], roles: [] }, { temp_voice_trigger_id: { resource: 'voice' } })).toEqual([])
  })
  it('checks references inside reward settings through the feature registration', () => {
    const child = feature({ settings: { text_role_rewards: ['5:123'], voice_role_rewards: ['10:456'] } })
    expect(configurationIssues(child, [], { channels: [], roles: [{ id: '123', name: 'Member' }] }, leveling.fields)).toEqual(['resourceMissing'])
  })
})
