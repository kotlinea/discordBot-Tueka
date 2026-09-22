import { category } from './registry'

/** The category's feature registrations own labels, icons and hub order. */
export const moderationItems = category.features.filter(feature => feature.inHub).map(feature => [feature.id, feature.titleKey!, feature.icon!] as const)
