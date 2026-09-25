import { FileText } from 'lucide-react'
import { defineFeature } from '../defaults'

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'moderation_logs', category: 'moderation', parent: 'moderation',
  path: 'moderation/moderation_logs', namespaces: ['moderation', 'common'],
  settingsPath: 'modules/moderation_logs',
  fields: { log_channel_id: { labelKey: 'settingsFields.log_channel_id' } },
  load: () => import('./Logs').then(module => ({ default: module.Logs })),
  titleKey: 'moderation.logs', icon: FileText, inHub: true,
})
