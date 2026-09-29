import { defineFeature } from '../defaults'
import type { FeatureDefinition } from '../contracts'

/** Rule families share their editor, while each feature owns its initial trigger. */
export function defineRuleFeature({ defaultTrigger, ...definition }: Pick<FeatureDefinition, 'id' | 'titleKey' | 'icon' | 'fields'> & { defaultTrigger: string }) {
  return defineFeature({
    screenKind: 'workspace',
    category: 'moderation', parent: 'moderation',
    path: `moderation/${definition.id}`, settingsPath: `modules/${definition.id}`,
    namespaces: ['moderation', 'common'], nested: true, inHub: true,
    homeTitleKey: 'operations.back',
    pages: [{ id: 'create', path: 'rules/new', titleKey: 'operations.create', kind: 'action', access: 'manager',
      load: () => import('./RuleEditor').then(module => ({ default: () => <module.RuleEditor family={definition.id} defaultTrigger={defaultTrigger}/> })) }],
    breadcrumbs: (suffix, t) => suffix[0] === 'rules' ? [{ label: t(suffix[1] === 'new' ? 'common.create' : 'common.edit') }] : [],
    load: () => import('./RuleRoutes').then(module => ({ default: () => <module.default family={definition.id} defaultTrigger={defaultTrigger}/> })),
    ...definition,
  })
}
