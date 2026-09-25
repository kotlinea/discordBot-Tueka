import { BookOpen } from 'lucide-react'
import { defineFeature } from '../defaults'

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'infractions', category: 'moderation', parent: 'moderation',
  path: 'moderation/infractions', namespaces: ['moderation', 'common'],
  settingsPath: 'modules/infractions',
  fields: {
    point_thresholds: { labelKey: 'settingsFields.point_thresholds' },
    log_channel_id: { labelKey: 'settingsFields.log_channel_id' },
  },
  load: () => import('./Infractions').then(module => ({ default: module.Infractions })),
  titleKey: 'moderation.infractions', icon: BookOpen, inHub: true,
})
