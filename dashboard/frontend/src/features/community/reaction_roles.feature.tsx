import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'reaction_roles', category: 'community',
  path: 'reaction-roles', namespaces: ['reactionRoles', 'common'],
  load: () => import('../reaction-roles/Routes'),
})

