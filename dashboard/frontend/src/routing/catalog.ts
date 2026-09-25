import { matchPath, matchRoutes } from 'react-router-dom'
import type { Feature, Guild } from '../types'
import type { BreadcrumbItem } from '../app/Navigation'
import type { FeatureDefinition } from '../features/contracts'
import { featureRegistry } from '../features/registry'

export const dashboardNamespaces = [...new Set(['common' as const, ...featureRegistry.features.flatMap(feature => feature.namespaces), ...featureRegistry.categories.flatMap(category => category.hub?.namespaces ?? [])])]
export const categoryHubs = featureRegistry.categories.filter(category => category.hub)
export const presentationGroups = featureRegistry.presentationCategories

export function groupFeatures(categoryId: string, features: Feature[]) {
  const available = new Set(features.map(feature => feature.id))
  return featureRegistry.features.filter(feature => feature.presentationCategory === categoryId && available.has(feature.id))
}

export function featurePath(guildId: string, item: Pick<Feature, 'id'>) { return featureRegistry.path(guildId, item.id) }
export function guildIcon(guild: Guild) { return guild.icon ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=96` : null }
export function featurePattern(feature: FeatureDefinition) { return feature.path + (feature.nested ? '/*' : '') }
export function activeFeature(pathname: string) {
  return matchRoutes(featureRegistry.routes.map(feature => ({ path: `/servers/:guildId/${featurePattern(feature)}`, handle: feature })), pathname)?.at(-1)?.route.handle
}
export function featureLabel(definition: FeatureDefinition, features: Feature[], t: (key: string) => string) {
  return definition.label?.(t) ?? (definition.titleKey ? t(definition.titleKey) : features.find(item => item.id === definition.id)?.title ?? definition.id)
}

export function featureBreadcrumbs(pathname: string, guildId: string, features: Feature[], t: (key: string) => string): BreadcrumbItem[] {
  const definition = activeFeature(pathname)
  const category = definition ? featureRegistry.categories.find(item => item.id === definition.presentationCategory) : categoryHubs.find(item => matchPath(`/servers/:guildId/${item.hub!.path}`, pathname))
  const group = definition ? presentationGroups.find(item => item.id === definition.presentationCategory) : category
  const base = `/servers/${guildId}`
  const items: BreadcrumbItem[] = []
  if (group) {
    items.push({ label: t(group.titleKey), to: definition && category?.hub ? `${base}/${category.hub.path}` : undefined })
  }
  if (definition) {
    const owner = featureRegistry.get(definition.id)
    const page = owner.pages.find(page => `${owner.path}/${page.path}` === definition.path)
    const match = matchPath<string>(`/servers/:guildId/${featurePattern(definition)}`, pathname)
    const suffix = (match?.params['*'] ?? '').split('/').filter(Boolean)
    if (page) {
      items.push({ label: featureLabel(owner, features, t), to: `${base}/${owner.path}` })
      items.push({ label: t(page.titleKey), to: suffix.length ? `${base}/${definition.path}` : undefined })
      items.push(...(page.breadcrumbs?.(suffix, t) ?? []).map(item => ({ label: item.label, to: item.suffix ? `${base}/${definition.path}/${item.suffix}` : undefined })))
      return items
    }
    const children = definition.breadcrumbs?.(suffix, t) ?? []
    items.push({ label: featureLabel(definition, features, t), to: children.length ? `${base}/${definition.path}` : undefined })
    items.push(...children.map(item => ({ label: item.label, to: item.suffix ? `${featurePath(guildId, definition)}/${item.suffix}` : undefined })))
  }
  return items
}

export function paletteItems(guildId: string, features: Feature[], t: (key: string) => string): { title: string; path: string; category?: string }[] {
  return [
    { title: t('nav.overview'), path: `/servers/${guildId}` },
    { title: t('nav.settings'), path: `/servers/${guildId}/settings` },
    ...categoryHubs.map(category => ({ title: `${t(category.titleKey)} · ${t('nav.overview')}`, path: `/servers/${guildId}/${category.hub!.path}` })),
    ...presentationGroups.flatMap(group => groupFeatures(group.id, features).filter(feature => feature.inPalette !== false).map(feature => ({ title: featureLabel(feature, features, t), category: t(group.titleKey), path: featurePath(guildId, feature) }))),
  ]
}
