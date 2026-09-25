import { defineFeature } from '../defaults'

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'reaction_roles', category: 'community',
  presentationCategory: 'server_operations', homeTitleKey: 'reactionRoles.messages',
  path: 'reaction-roles', namespaces: ['reactionRoles', 'common'],
  nested: true, titleKey: 'reactionRoles.title',
  settingsPath: 'modules/reaction_roles',
  settingsLoad: () => import('./reaction_roles/Routes').then(module => ({ default: module.ReactionRoleSettingsAlias })),
  breadcrumbs: (suffix, t) => suffix[0] ? [{ label: t(suffix[0] === 'new' ? 'common.create' : 'common.edit') }] : [],
  load: () => import('./reaction_roles/Routes'),
  pages: [
    { id: 'groups', path: 'link-groups', titleKey: 'reactionRoles.linkGroups', kind: 'navigation', access: 'manager', load: () => import('./reaction_roles/Groups').then(module => ({ default: module.ReactionRoleGroups })) },
    { id: 'events', path: 'events', titleKey: 'reactionRoles.audit', kind: 'navigation', access: 'manager', load: () => import('./reaction_roles/Events').then(module => ({ default: module.ReactionRoleEvents })) },
    { id: 'settings', path: 'settings', titleKey: 'reactionRoles.settings', kind: 'navigation', access: 'manager', load: () => import('./reaction_roles/Overview').then(module => ({ default: module.ReactionRoleSettingsPage })) },
    { id: 'create', path: 'new', titleKey: 'reactionRoles.create', kind: 'action', access: 'manager', load: () => import('./reaction_roles/Editor').then(module => ({ default: module.ReactionRoleEditor })) },
  ],
})
