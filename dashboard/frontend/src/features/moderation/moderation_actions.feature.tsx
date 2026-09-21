import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'moderation_actions', category: 'moderation', parent: 'moderation',
  path: 'moderation/moderation_actions', namespaces: ['moderation', 'common'],
  load: () => import('./Actions').then(module => ({ default: module.Actions })),
})

