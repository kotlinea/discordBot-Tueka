import { defineRuleFeature } from './ruleScreen'
import { Shield } from 'lucide-react'

export const feature = defineRuleFeature({
  id: 'automod', defaultTrigger: 'keyword',
  fields: {
    log_channel_id: { labelKey: 'settingsFields.log_channel_id' },
    immune_role_ids: { labelKey: 'settingsFields.immune_role_ids' },
    immune_user_ids: { labelKey: 'settingsFields.immune_user_ids' },
    immune_channel_ids: { labelKey: 'settingsFields.immune_channel_ids' },
  },
  titleKey: 'moderation.automod', icon: Shield,
})
