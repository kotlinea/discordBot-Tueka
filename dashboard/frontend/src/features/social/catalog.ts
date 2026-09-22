import { providers } from './registry'

export const socialNames: Record<string, string> = Object.fromEntries(providers.map(feature => [feature.provider.id, feature.provider.name]))
