import type { CategoryDefinition, FeatureDefinition, ScreenLoader, ScreenModule } from './contracts'
import { loadModuleSettings } from './defaults'

const identifier = /^[a-z][a-z0-9_]*$/
const namespaces = new Set(['common', 'moderation', 'tickets', 'reactionRoles', 'social', 'suggestions'])

export function createRegistry(categories: readonly CategoryDefinition[]) {
  const categoryIds = new Set<string>()
  const features = new Map<string, FeatureDefinition>()
  // Shell owns the guild settings route outside feature composition.
  const routes = new Set<string>(['settings'])
  const standaloneRoutes = new Set<string>()
  function registerRoute(path: string, owner: string) {
    if (!path || path.startsWith('/') || /[?#*]/.test(path) || path.split('/').some(part => !part || part === '.' || part === '..')) throw new Error(`Invalid route: ${owner}`)
    const shape = path.toLowerCase().replace(/:[^/]+/g, ':_')
    if (routes.has(shape)) throw new Error(`Duplicate feature route: ${path}`)
    routes.add(shape)
  }
  for (const category of categories) {
    if (!identifier.test(category.id) || categoryIds.has(category.id) || !category.titleKey) throw new Error(`Invalid or duplicate category: ${category.id}`)
    categoryIds.add(category.id)
    if (category.hub) {
      registerRoute(category.hub.path, category.id)
      if (typeof category.hub.load !== 'function') throw new Error(`Missing screen loader: ${category.id}`)
      if (!category.hub.namespaces.length || category.hub.namespaces.some(value => !namespaces.has(value))) throw new Error(`Unknown namespace: ${category.id}`)
    }
    for (const feature of category.features) {
      if (!identifier.test(feature.id) || features.has(feature.id)) throw new Error(`Invalid or duplicate feature: ${feature.id}`)
      if (feature.category !== category.id) throw new Error(`Unregistered category: ${feature.id}`)
      if (typeof feature.load !== 'function') throw new Error(`Missing screen loader: ${feature.id}`)
      if (!feature.namespaces.length || feature.namespaces.some(value => !namespaces.has(value))) throw new Error(`Unknown namespace: ${feature.id}`)
      if (!['manager', 'ticket_staff'].includes(feature.access)) throw new Error(`Unknown display access: ${feature.id}`)
      // React Router defaults to case-insensitive matching; parameter names are not distinct routes.
      registerRoute(feature.path, feature.id)
      if (feature.settingsPath) {
        registerRoute(feature.settingsPath, feature.id)
        if (feature.settingsLoad !== undefined && typeof feature.settingsLoad !== 'function') throw new Error(`Missing settings loader: ${feature.id}`)
      }
      for (const route of feature.standalone ?? []) {
        if (!route.path.startsWith('/') || /[?#*]/.test(route.path) || route.path.slice(1).split('/').some(part => !part || part === '.' || part === '..')) throw new Error(`Invalid standalone route: ${feature.id}`)
        const shape = route.path.toLowerCase().replace(/:[^/]+/g, ':_')
        if (shape === '/servers' || shape.startsWith('/servers/')) throw new Error(`Reserved application route: ${route.path}`)
        if (standaloneRoutes.has(shape)) throw new Error(`Duplicate standalone route: ${route.path}`)
        if (typeof route.load !== 'function') throw new Error(`Missing screen loader: ${feature.id}`)
        standaloneRoutes.add(shape)
      }
      features.set(feature.id, Object.freeze({ ...feature, namespaces: Object.freeze([...feature.namespaces]) }))
    }
  }
  for (const feature of features.values()) {
    const seen = new Set([feature.id])
    let parent = feature.parent
    while (parent !== undefined) {
      const target = features.get(parent)
      if (!target) throw new Error(`Unknown parent: ${feature.id}`)
      if (seen.has(parent)) throw new Error(`Cyclic feature parent: ${feature.id}`)
      if (target.category !== feature.category) throw new Error(`Parent belongs to another category: ${feature.id}`)
      seen.add(parent)
      parent = target.parent
    }
  }
  const pending = new Map<ScreenLoader, Promise<ScreenModule>>()
  const screenRoutes: FeatureDefinition[] = [...features.values()].flatMap(feature => [feature, ...(feature.settingsPath ? [{ ...feature, path: feature.settingsPath, nested: false, load: feature.settingsLoad ?? loadModuleSettings, access: 'manager' as const, overview: true, breadcrumbs: undefined }] : [])])
  function get(id: string) {
    const feature = features.get(id)
    if (!feature) throw new Error(`Unknown feature: ${id}`)
    return feature
  }
  function loadScreen(loader: ScreenLoader, id: string): Promise<ScreenModule> {
    let result = pending.get(loader)
    if (!result) {
      result = Promise.resolve().then(loader).then(module => {
        if (typeof module?.default !== 'function') throw new Error(`Invalid screen module: ${id}`)
        return module
      }).catch(error => { pending.delete(loader); throw error })
      pending.set(loader, result)
    }
    return result
  }
  return Object.freeze({
    categories: Object.freeze(categories.map(category => Object.freeze({ ...category, features: Object.freeze(category.features.map(feature => get(feature.id))) }))),
    features: Object.freeze([...features.values()]), get,
    routes: Object.freeze(screenRoutes),
    load: (id: string) => loadScreen(get(id).load, id),
    loadRoute: (path: string) => {
      const route = screenRoutes.find(route => route.path === path)
      if (!route) throw new Error(`Unknown screen route: ${path}`)
      return loadScreen(route.load, route.id)
    },
    loadCategory: (id: string) => {
      const hub = categories.find(category => category.id === id)?.hub
      if (!hub) throw new Error(`Unknown category screen: ${id}`)
      return loadScreen(hub.load, id)
    },
    path: (guildId: string, id: string) => `/servers/${encodeURIComponent(guildId)}/${get(id).path}`,
  })
}
