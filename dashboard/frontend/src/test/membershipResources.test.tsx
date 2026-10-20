import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { SettingField } from '../components/forms/SettingField'
import '../i18n'

afterEach(cleanup)
const channels = [
  { id: '10', name: 'Text', type: 0 }, { id: '11', name: 'Voice', type: 2 },
  { id: '12', name: 'Stage', type: 13 }, { id: '100', name: 'Category', type: 4 },
]
describe('shared resource field selection', () => {
  it.each([
    ['channel', ['Text', 'Voice', 'Stage']], ['voice', ['Voice', 'Stage']],
    ['category', ['Category']], ['role', ['Member']],
  ] as const)('preserves %s resources', (resource, names) => {
    render(<SettingField name="destination" value={null} channels={channels} roles={[{ id: '500', name: 'Member' }]} onChange={vi.fn()} label="Destination" resource={resource}/>)
    const picker = screen.getByRole('combobox', { name: /Destination/ })
    expect(within(picker).getAllByRole('option').slice(1).map(item => item.textContent)).toEqual(names)
  })
})
