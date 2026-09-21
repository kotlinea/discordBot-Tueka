import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'anti_raid', category: 'moderation', parent: 'moderation',
  path: 'moderation/anti_raid', namespaces: ['moderation', 'common'],
  load: () => import('./RuleList').then(module => ({ default: () => <module.RuleList family="anti_raid"/> })),
})

