import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'audit_log', category: 'moderation', parent: 'moderation',
  path: 'moderation/audit_log', namespaces: ['moderation', 'common'],
})

