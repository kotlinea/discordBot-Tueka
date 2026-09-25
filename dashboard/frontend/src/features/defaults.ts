import type { FeatureDefinition, ScreenLoader } from './contracts'

/** No screen code is evaluated when the catalog is imported. */
export const loadModuleSettings: ScreenLoader = () => import('./DefaultSettings')

type Definition = Pick<FeatureDefinition, 'id' | 'category'> & Partial<Omit<FeatureDefinition, 'id' | 'category'>>

/** Start with the standard settings screen and override only a feature's needs. */
export function defineFeature(definition: Definition): FeatureDefinition {
  return Object.freeze({
    path: `modules/${definition.id}`,
    load: loadModuleSettings,
    access: 'manager',
    presentationCategory: definition.category,
    screenKind: 'settings',
    ...definition,
    namespaces: Object.freeze([...(definition.namespaces ?? ['common'])]),
    pages: Object.freeze((definition.pages ?? []).map(page => Object.freeze({ ...page }))),
  })
}
