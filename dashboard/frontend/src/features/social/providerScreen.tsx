import { defineFeature } from '../defaults'

export interface ProviderPresentation { id: string; name: string; unofficial?: boolean; accountPlaceholder?: string }

export function defineProvider(provider: ProviderPresentation) {
  return {
    ...defineFeature({
      screenKind: 'workspace',
      id: `${provider.id}_updates`, category: 'social', path: `social/${provider.id}`,
      settingsPath: `modules/${provider.id}_updates`,
      namespaces: ['social', 'common'],
      label: t => `${provider.name} ${t('social.title')}`,
      load: () => import('./Provider').then(module => ({ default: () => <module.SocialProviderPage presentation={provider}/> })),
    }),
    provider,
  }
}
