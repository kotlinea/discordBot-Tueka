import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'automod', category: 'moderation', parent: 'moderation',
  path: 'moderation/automod', namespaces: ['moderation', 'common'],
  load: () => import('./RuleList').then(module => ({ default: () => <module.RuleList family="automod"/> })),
})

