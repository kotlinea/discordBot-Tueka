import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'infractions', category: 'moderation', parent: 'moderation',
  path: 'moderation/infractions', namespaces: ['moderation', 'common'],
  load: () => import('./Infractions').then(module => ({ default: module.Infractions })),
})

