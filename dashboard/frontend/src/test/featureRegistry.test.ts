import { describe, expect, it, vi } from 'vitest'
import { createRegistry } from '../features/catalog'
import type { CategoryDefinition, FeatureDefinition, FeaturePage, ScreenModule } from '../features/contracts'
import { defineFeature, loadModuleSettings } from '../features/defaults'
import { featureRegistry } from '../features/registry'
import baseline from './fixtures/feature_metadata.json'
import ja from '../locales/ja'
import en from '../locales/en'

const screen = () => null
const feature = (id = 'sample', overrides: Partial<FeatureDefinition> = {}) => defineFeature({ id, category: 'example', ...overrides })
const category = (...features: FeatureDefinition[]): CategoryDefinition => ({ id: 'example', titleKey: 'nav.example', features })
const page = (overrides: Partial<FeaturePage> = {}): FeaturePage => ({ id: 'inbox', path: 'inbox', titleKey: 'tickets.inbox', kind: 'navigation', access: 'manager', load: async () => ({ default: screen }), ...overrides })

describe('feature registration', () => {
  it('covers exactly the backend public catalog and retains existing navigation paths', () => {
    expect(featureRegistry.features.map(item => item.id).sort()).toEqual([...baseline.features.map(item => item.id),'applications'].sort())
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

  it('separates presentation categories from backend ownership and validates their references', () => {
    const source = feature('sample', { presentationCategory: 'operations' })
    const groups = [{ id: 'operations', titleKey: 'nav.operations' }]
    const registry = createRegistry([category(source)], groups)
    expect(registry.get('sample').category).toBe('example')
    expect(registry.get('sample').presentationCategory).toBe('operations')
    expect(registry.presentationCategories).toEqual(groups)
    expect(() => createRegistry([category(source)])).toThrow('Unknown presentation category')
    expect(() => createRegistry([], [...groups, ...groups])).toThrow('duplicate presentation category')
  })

  it('validates internal page routes, access and loaders before loading screens', () => {
    const register = (pages: FeaturePage[], overrides: Partial<FeatureDefinition> = {}) => createRegistry([category(feature('sample', { screenKind: 'workspace', pages, ...overrides }))])
    expect(() => register([page(), page()])).toThrow('duplicate page')
    expect(() => register([page(), page({ id: 'other', path: 'Inbox' })])).toThrow('Duplicate feature route')
    expect(() => register([page()], { screenKind: 'settings' })).toThrow('require workspace')
    expect(() => register([page({ access: 'ticket_staff' })])).toThrow('Invalid page access')
    expect(() => register([page({ load: undefined } as unknown as FeaturePage)])).toThrow('Missing screen loader')
    for (const path of ['', '../settings', '/outside', 'a//b', 'new?x', 'new#x', 'a\\b', '%2e%2e', ':id']) {
      expect(() => register([page({ path })]), path).toThrow()
    }
    expect(() => register([page()], { settingsPath: 'modules/sample/inbox' })).toThrow('Duplicate feature route')
    expect(() => createRegistry([category(feature('sample', { screenKind: 'workspace', pages: [page()] }), feature('other', { path: 'modules/sample/inbox' }))])).toThrow('Duplicate feature route')
  })

  it('loads declared pages once and keeps manager settings aliases separate from workspace navigation', async () => {
    const load = vi.fn(async () => ({ default: screen }))
    const registry = createRegistry([category(feature('sample', { screenKind: 'workspace', access: 'ticket_staff', pages: [page({ load })], settingsPath: 'sample/settings' }))])
    expect(load).not.toHaveBeenCalled()
    await Promise.all([registry.loadRoute('modules/sample/inbox'), registry.loadRoute('modules/sample/inbox')])
    expect(load).toHaveBeenCalledTimes(1)
    expect(registry.routes.find(route => route.path === 'sample/settings')).toMatchObject({ access: 'manager', screenKind: 'settings', pages: [] })
    expect(Object.isFrozen(registry.get('sample').pages[0])).toBe(true)
  })

  it('requires bilingual text for all registered presentation labels and page entries', () => {
    function translated(language: typeof ja | typeof en, key: string, scopes = Object.keys(language)) {
      return scopes.some(scope => {
        let value: unknown = language[scope as keyof typeof language]
        for (const part of key.split('.')) value = value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined
        return typeof value === 'string' && value.length > 0
      })
    }
    for (const language of [ja, en]) {
      expect(translated(language, 'missing.key')).toBe(false)
      for (const group of featureRegistry.presentationCategories) expect(translated(language, group.titleKey, ['common']), group.titleKey).toBe(true)
      for (const definition of featureRegistry.features) {
        const keys = [definition.titleKey, definition.homeTitleKey, ...definition.pages.flatMap(page => [page.titleKey, page.group?.titleKey]), ...Object.values(definition.fields ?? {}).map(field => field.labelKey)].filter((key): key is string => Boolean(key))
        definition.label?.(key => { keys.push(key); return key })
        for (const key of keys) expect(translated(language, key, [...definition.namespaces]), `${definition.id}: ${key}`).toBe(true)
      }
    }
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

  it('rejects inconsistent internal page groups and preserves nested page routing', () => {
    const pages = [
      { id: 'panels', path: 'panels', titleKey: 'tickets.panels', kind: 'navigation' as const, access: 'manager' as const, nested: true, group: { id: 'setup', titleKey: 'tickets.configuration' }, load: async () => ({ default: screen }) },
      { id: 'forms', path: 'forms', titleKey: 'tickets.forms', kind: 'navigation' as const, access: 'manager' as const, group: { id: 'setup', titleKey: 'tickets.configuration' }, load: async () => ({ default: screen }) },
    ]
    const registry = createRegistry([category(feature('sample', { screenKind: 'workspace', pages }))])
    expect(registry.routes.find(route => route.path.endsWith('/panels'))?.nested).toBe(true)
    expect(registry.routes.find(route => route.path.endsWith('/forms'))?.nested).toBe(false)
    expect(() => createRegistry([category(feature('sample', { screenKind: 'workspace', pages: [pages[0], { ...pages[1], group: { id: 'setup', titleKey: 'conflicting' } }] }))])).toThrow('Invalid page group')
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
      const source = baseline.features.find(item => item.id === definition.id)
      expect(Object.keys(definition.fields ?? {}).sort(), definition.id).toEqual([...(source?.fields??[])].sort())
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
    expect(() => createRegistry([{ ...category(feature('sample', { path: 'hub' })), hub: { path: 'hub', load, namespaces: ['common'] } }])).toThrow('Duplicate feature route')
    expect(() => createRegistry([category(feature('one', { standalone: [{ path: '/files/:id', load }] }), feature('two', { standalone: [{ path: '/files/:name', load }] }))])).toThrow('Duplicate standalone route')
    expect(load).not.toHaveBeenCalled()
  })

  it('rejects routes owned by the application before a feature can shadow them', () => {
    const load = vi.fn(async () => ({ default: screen }))
    expect(() => createRegistry([category(feature('sample', { path: 'Settings' }))])).toThrow('Duplicate feature route')
    expect(() => createRegistry([category(feature('sample', { settingsPath: 'settings' }))])).toThrow('Duplicate feature route')
    expect(() => createRegistry([{ ...category(), hub: { path: 'settings', load, namespaces: ['common'] } }])).toThrow('Duplicate feature route')
    for (const path of ['/servers', '/Servers/:id', '/servers/1/custom']) {
      expect(() => createRegistry([category(feature('sample', { standalone: [{ path, load }] }))])).toThrow('Reserved application route')
    }
    expect(load).not.toHaveBeenCalled()
  })
})
