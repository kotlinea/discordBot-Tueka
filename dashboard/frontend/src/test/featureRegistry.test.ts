import { describe, expect, it, vi } from 'vitest'
import { createRegistry } from '../features/catalog'
import type { CategoryDefinition, FeatureDefinition, ScreenModule } from '../features/contracts'
import { defineFeature, loadModuleSettings } from '../features/defaults'
import { featureRegistry } from '../features/registry'
import baseline from './fixtures/feature_metadata.json'
import ja from '../locales/ja'
import en from '../locales/en'

const screen = () => null
const feature = (id = 'sample', overrides: Partial<FeatureDefinition> = {}) => defineFeature({ id, category: 'example', ...overrides })
const category = (...features: FeatureDefinition[]): CategoryDefinition => ({ id: 'example', titleKey: 'nav.example', features })

describe('feature registration', () => {
  it('covers exactly the backend public catalog and retains existing navigation paths', () => {
    expect(featureRegistry.features.map(item => item.id).sort()).toEqual(baseline.features.map(item => item.id).sort())
    for (const source of baseline.features) {
      const target = featureRegistry.get(source.id)
      expect(target.category).toBe(source.category)
      expect(target.parent).toBe('parent' in source ? source.parent : undefined)
      const path = source.id === 'tickets' ? 'tickets'
        : source.id === 'reaction_roles' ? 'reaction-roles'
        : source.id === 'suggestions' ? 'suggestions'
        : source.category === 'social' ? `social/${source.id.replace('_updates', '')}`
        : 'parent' in source && source.parent === 'moderation' ? `moderation/${source.id}` : `modules/${source.id}`
      expect(featureRegistry.path('123', source.id)).toBe(`/servers/123/${path}`)
      for (const language of [ja, en]) {
        for (const namespace of target.namespaces) expect(language[namespace]).toBeDefined()
      }
    }
    for (const item of featureRegistry.categories) {
      const key = item.id as keyof typeof ja.common.nav
      expect(ja.common.nav[key]).toBeTruthy()
      expect(en.common.nav[key]).toBeTruthy()
    }
  })

  it('starts from default settings and permits a dedicated screen override without eagerly loading it', async () => {
    expect(feature().load).toBe(loadModuleSettings)
    expect(feature().path).toBe('modules/sample')
    const load = vi.fn(async () => ({ default: screen }))
    const registry = createRegistry([category(feature('custom', { load, path: 'custom', access: 'ticket_staff' }))])
    expect(load).not.toHaveBeenCalled()
    await registry.load('custom')
    expect(load).toHaveBeenCalledTimes(1)
    expect(registry.get('custom').access).toBe('ticket_staff')
  })

  it('rejects duplicate categories, features and mismatched category references', () => {
    expect(() => createRegistry([category(), category()])).toThrow('duplicate category')
    expect(() => createRegistry([category(feature(), feature())])).toThrow('duplicate feature')
    expect(() => createRegistry([category(feature('sample', { category: 'missing' }))])).toThrow('Unregistered category')
    expect(() => createRegistry([category(feature('../bad'))])).toThrow('Invalid or duplicate feature')
  })

  it('rejects missing, cyclic and cross-category parents', () => {
    expect(() => createRegistry([category(feature('sample', { parent: 'missing' }))])).toThrow('Unknown parent')
    expect(() => createRegistry([category(feature('sample', { parent: 'sample' }))])).toThrow('Cyclic')
    expect(() => createRegistry([category(feature('first', { parent: 'second' }), feature('second', { parent: 'first' }))])).toThrow('Cyclic')
    expect(() => createRegistry([category(feature('sample', { parent: 'foreign' })),
      { id: 'other', titleKey: 'nav.other', features: [feature('foreign', { category: 'other' })] }])).toThrow('another category')
  })

  it('rejects equivalent parameter routes and case-insensitive route collisions', () => {
    expect(() => createRegistry([category(feature('one', { path: 'items/:id' }), feature('two', { path: 'items/:name' }))])).toThrow('Duplicate feature route')
    expect(() => createRegistry([category(feature('one', { path: 'Items' }), feature('two', { path: 'items' }))])).toThrow('Duplicate feature route')
    for (const path of ['/absolute', '../outside', 'bad?query', 'bad//path', '']) {
      expect(() => createRegistry([category(feature('sample', { path }))])).toThrow('Invalid route')
    }
  })

  it('rejects missing loaders, missing namespaces and unknown lookups', () => {
    expect(() => createRegistry([category({ ...feature(), load: undefined } as unknown as FeatureDefinition)])).toThrow('Missing screen loader')
    expect(() => createRegistry([category(feature('sample', { namespaces: [] }))])).toThrow('Unknown namespace')
    expect(() => featureRegistry.get('missing')).toThrow('Unknown feature')
  })

  it('initializes a shared screen once even across concurrent feature requests', async () => {
    const load = vi.fn(async () => ({ default: screen }))
    const registry = createRegistry([category(feature('one', { load }), feature('two', { load }))])
    const modules = await Promise.all([registry.load('one'), registry.load('two'), registry.load('one')])
    expect(load).toHaveBeenCalledTimes(1)
    expect(modules[0]).toBe(modules[1])
  })

  it('rejects a missing module export and permits retry after a loader failure', async () => {
    const load = vi.fn<() => Promise<ScreenModule>>()
      .mockResolvedValueOnce({} as ScreenModule)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ default: screen })
    const registry = createRegistry([category(feature('sample', { load }))])
    await expect(registry.load('sample')).rejects.toThrow('Invalid screen module')
    await expect(registry.load('sample')).rejects.toThrow('offline')
    await expect(registry.load('sample')).resolves.toEqual({ default: screen })
    expect(load).toHaveBeenCalledTimes(3)
  })

  it('resolves every real screen binding', async () => {
    for (const item of featureRegistry.features) {
      const module = await featureRegistry.load(item.id)
      expect(typeof module.default, item.id).toBe('function')
    }
    for (const category of featureRegistry.categories.filter(item => item.hub)) {
      expect(typeof (await featureRegistry.loadCategory(category.id)).default).toBe('function')
    }
    for (const feature of featureRegistry.features) {
      for (const route of feature.standalone ?? []) expect(typeof (await route.load()).default).toBe('function')
    }
  })

  it('declares every default settings field with bilingual presentation owned by that feature', () => {
    for (const definition of featureRegistry.features.filter(item => item.load === loadModuleSettings || (item.settingsPath && !item.settingsLoad))) {
      const source = baseline.features.find(item => item.id === definition.id)!
      expect(Object.keys(definition.fields ?? {}).sort(), definition.id).toEqual([...source.fields].sort())
      for (const field of Object.values(definition.fields ?? {})) {
        for (const language of [ja, en]) {
          const key = field.labelKey.replace('settingsFields.', '') as keyof typeof language.common.settingsFields
          expect(language.common.settingsFields[key], field.labelKey).toBeTruthy()
        }
      }
    }
  })

  it('rejects category hub and standalone route collisions before screen loading', () => {
    const load = vi.fn(async () => ({ default: screen }))
    expect(() => createRegistry([{ ...category(feature('sample', { path: 'hub' })), hub: { path: 'hub', load, namespaces: ['common'], paletteKey: 'nav.example' } }])).toThrow('Duplicate feature route')
    expect(() => createRegistry([category(feature('one', { standalone: [{ path: '/files/:id', load }] }), feature('two', { standalone: [{ path: '/files/:name', load }] }))])).toThrow('Duplicate standalone route')
    expect(load).not.toHaveBeenCalled()
  })
})
