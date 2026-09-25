import { Gavel } from 'lucide-react'
import { defineFeature } from '../defaults'

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'moderation_actions', category: 'moderation', parent: 'moderation',
  path: 'moderation/moderation_actions', namespaces: ['moderation', 'common'],
  settingsPath: 'modules/moderation_actions',
  load: () => import('./Actions').then(module => ({ default: module.Actions })),
  titleKey: 'moderation.actions', icon: Gavel, inHub: true,
})
