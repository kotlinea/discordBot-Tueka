import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'audit_log', category: 'moderation', parent: 'moderation',
  path: 'moderation/audit_log', namespaces: ['moderation', 'common'],
  settingsPath: 'modules/audit_log',
  fields: {
    management_channel_id: { labelKey: 'settingsFields.management_channel_id' },
    log_message: { labelKey: 'settingsFields.log_message' },
    log_voice: { labelKey: 'settingsFields.log_voice' },
    log_channel: { labelKey: 'settingsFields.log_channel' },
    log_member: { labelKey: 'settingsFields.log_member' },
    log_role: { labelKey: 'settingsFields.log_role' },
    log_server: { labelKey: 'settingsFields.log_server' },
  },
})
