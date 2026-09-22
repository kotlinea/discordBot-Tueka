import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'trust_score', category: 'moderation', parent: 'moderation',
  path: 'moderation/trust_score', namespaces: ['moderation', 'common'],
  settingsPath: 'modules/trust_score',
  fields: {
    trust_retention_days: { labelKey: 'settingsFields.trust_retention_days' },
    trust_flag_threshold: { labelKey: 'settingsFields.trust_flag_threshold' },
  },
})
