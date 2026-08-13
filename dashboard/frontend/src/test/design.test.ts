// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import ja from '../locales/ja'
import en from '../locales/en'

const tokens = readFileSync(new URL('../../../../tokens.css', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../styles/App.module.css', import.meta.url), 'utf8')
const globals = readFileSync(new URL('../styles/app.css', import.meta.url), 'utf8')

function keys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object') return [prefix]
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key))
}

describe('dashboard design system', () => {
  it('defines every appearance and color scheme as semantic tokens', () => {
    expect(tokens).toContain('[data-appearance="community"]')
    expect(tokens).toContain('[data-appearance="atmosphere"]')
    expect(tokens).toContain('[data-color-scheme="dark"]')
    expect(tokens).toContain('--color-accent-ink')
  })

  it('keeps component styles token-driven and motion-specific', () => {
    expect(styles).not.toMatch(/#[0-9a-f]{3,8}/i)
    expect(styles).not.toContain('transition-all')
    expect(globals).toContain('prefers-reduced-motion')
  })

  it('keeps Japanese and English translation keys aligned', () => {
    expect(keys(ja).sort()).toEqual(keys(en).sort())
  })
})
