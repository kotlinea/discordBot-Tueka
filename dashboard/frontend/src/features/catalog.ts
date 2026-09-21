import type { CategoryDefinition, FeatureDefinition, ScreenLoader, ScreenModule } from './contracts'

const identifier = /^[a-z][a-z0-9_]*$/
const namespaces = new Set(['common', 'moderation', 'tickets', 'reactionRoles', 'social', 'suggestions'])

export function createRegistry(categories: readonly CategoryDefinition[]) {
  const categoryIds = new Set<string>()
  const features = new Map<string, FeatureDefinition>()
  const routes = new Set<string>()
  for (const category of categories) {
    if (!identifier.test(category.id) || categoryIds.has(category.id) || !category.titleKey) throw new Error(`Invalid or duplicate category: ${category.id}`)
    categoryIds.add(category.id)
    for (const feature of category.features) {
      if (!identifier.test(feature.id) || features.has(feature.id)) throw new Error(`Invalid or duplicate feature: ${feature.id}`)
      if (feature.category !== category.id) throw new Error(`Unregistered category: ${feature.id}`)
      if (typeof feature.load !== 'function') throw new Error(`Missing screen loader: ${feature.id}`)
      if (!feature.namespaces.length || feature.namespaces.some(value => !namespaces.has(value))) throw new Error(`Unknown namespace: ${feature.id}`)
      if (!['manager', 'ticket_staff'].includes(feature.access)) throw new Error(`Unknown display access: ${feature.id}`)
      if (!feature.path || feature.path.startsWith('/') || /[?#]/.test(feature.path) || feature.path.split('/').some(part => !part || part === '.' || part === '..')) throw new Error(`Invalid route: ${feature.id}`)
      // React Router defaults to case-insensitive matching; parameter names are not distinct routes.
      const shape = feature.path.toLowerCase().replace(/:[^/]+/g, ':_')
      if (routes.has(shape)) throw new Error(`Duplicate feature route: ${feature.path}`)
      routes.add(shape)
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
  function get(id: string) {
    const feature = features.get(id)
    if (!feature) throw new Error(`Unknown feature: ${id}`)
    return feature
  }
  function load(id: string): Promise<ScreenModule> {
    const loader = get(id).load
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
    features: Object.freeze([...features.values()]), get, load,
    path: (guildId: string, id: string) => `/servers/${encodeURIComponent(guildId)}/${get(id).path}`,
  })
}
