import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'reaction_roles', category: 'community',
  path: 'reaction-roles', namespaces: ['reactionRoles', 'common'],
  nested: true, titleKey: 'reactionRoles.title',
  settingsPath: 'modules/reaction_roles',
  settingsLoad: () => import('./reaction_roles/Overview').then(module => ({ default: module.ReactionRoleOverview })),
  breadcrumbs: (suffix, t) => suffix[0] ? [{ label: t(suffix[0] === 'new' ? 'common.create' : 'common.edit') }] : [],
  load: () => import('./reaction_roles/Routes'),
})
