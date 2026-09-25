import { matchPath } from 'react-router-dom'
import type { Feature, Guild } from '../types'
import type { BreadcrumbItem } from '../app/Navigation'
import type { FeatureDefinition } from '../features/contracts'
import { featureRegistry } from '../features/registry'

export const dashboardNamespaces = [...new Set(['common' as const, ...featureRegistry.features.flatMap(feature => feature.namespaces), ...featureRegistry.categories.flatMap(category => category.hub?.namespaces ?? [])])]
export const categoryHubs = featureRegistry.categories.filter(category => category.hub)
export const categoryGroups = featureRegistry.categories.filter(category => !category.hub)
export const presentationGroups = featureRegistry.presentationCategories

export function groupFeatures(categoryId: string, features: Feature[]) {
  const available = new Set(features.map(feature => feature.id))
  return featureRegistry.features.filter(feature => feature.presentationCategory === categoryId && available.has(feature.id))
}

export function featurePath(guildId: string, item: Pick<Feature, 'id'>) { return featureRegistry.path(guildId, item.id) }
export function guildIcon(guild: Guild) { return guild.icon ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=96` : null }
export function featurePattern(feature: FeatureDefinition) { return feature.path + (feature.nested ? '/*' : '') }
export function activeFeature(pathname: string) {
  return featureRegistry.routes.find(feature => !feature.nested && matchPath(`/servers/:guildId/${feature.path}`, pathname))
    ?? featureRegistry.routes.find(feature => matchPath(`/servers/:guildId/${featurePattern(feature)}`, pathname))
}
export function featureLabel(definition: FeatureDefinition, features: Feature[], t: (key: string) => string) {
  return definition.label?.(t) ?? (definition.titleKey ? t(definition.titleKey) : features.find(item => item.id === definition.id)?.title ?? definition.id)
}

export function featureBreadcrumbs(pathname: string, guildId: string, features: Feature[], t: (key: string) => string): BreadcrumbItem[] {
  const definition = activeFeature(pathname)
  const category = definition ? featureRegistry.categories.find(item => item.id === definition.category) : categoryHubs.find(item => matchPath(`/servers/:guildId/${item.hub!.path}`, pathname))
  const base = `/servers/${guildId}`
  const items: BreadcrumbItem[] = []
  if (category?.hub && (!definition || definition.path.startsWith(`${category.hub.path}/`))) {
    items.push({ label: t(category.titleKey), to: definition ? `${base}/${category.hub.path}` : undefined })
  }
  if (definition) {
    const owner = featureRegistry.get(definition.id)
    const page = owner.pages.find(page => `${owner.path}/${page.path}` === definition.path)
    const match = matchPath<string>(`/servers/:guildId/${featurePattern(definition)}`, pathname)
    const suffix = (match?.params['*'] ?? '').split('/').filter(Boolean)
    const children = page ? [{ label: t(page.titleKey) }] : definition.breadcrumbs?.(suffix, t) ?? []
    items.push({ label: featureLabel(definition, features, t), to: children.length ? `${base}/${page ? owner.path : definition.path}` : undefined })
    items.push(...children.map(item => ({ label: item.label, to: item.suffix ? `${featurePath(guildId, definition)}/${item.suffix}` : undefined })))
  }
  return items
}

export function paletteItems(guildId: string, features: Feature[], t: (key: string) => string) {
  return [
    { title: t('nav.overview'), path: `/servers/${guildId}` },
    ...categoryHubs.map(category => ({ title: t(category.hub!.paletteKey), path: `/servers/${guildId}/${category.hub!.path}` })),
    ...features.filter(feature => featureRegistry.get(feature.id).inPalette !== false).map(feature => ({ title: feature.title, path: featurePath(guildId, feature) })),
  ]
}
