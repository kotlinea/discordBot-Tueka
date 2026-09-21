import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'moderation_logs', category: 'moderation', parent: 'moderation',
  path: 'moderation/moderation_logs', namespaces: ['moderation', 'common'],
  load: () => import('./Logs').then(module => ({ default: module.Logs })),
})

