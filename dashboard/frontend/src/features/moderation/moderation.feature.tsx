import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'moderation', category: 'moderation',
  path: 'modules/moderation', namespaces: ['common'],
  titleKey: 'nav.moderationSettings',
  fields: {
    default_log_channel_id: { labelKey: 'settingsFields.default_log_channel_id' },
    immune_role_ids: { labelKey: 'settingsFields.immune_role_ids' },
    immune_user_ids: { labelKey: 'settingsFields.immune_user_ids' },
    immune_channel_ids: { labelKey: 'settingsFields.immune_channel_ids' },
    evidence_excluded_channel_ids: { labelKey: 'settingsFields.evidence_excluded_channel_ids' },
    evidence_retention_days: { labelKey: 'settingsFields.evidence_retention_days' },
    exclude_bots: { labelKey: 'settingsFields.exclude_bots' },
    exclude_webhooks: { labelKey: 'settingsFields.exclude_webhooks' },
  },
})
