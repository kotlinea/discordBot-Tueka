import { defineRuleFeature } from './ruleScreen'
import { MessageSquareWarning } from 'lucide-react'

export const feature = defineRuleFeature({
  id: 'anti_spam', defaultTrigger: 'message_rate',
  fields: {
    log_channel_id: { labelKey: 'settingsFields.log_channel_id' },
    immune_role_ids: { labelKey: 'settingsFields.immune_role_ids' },
    immune_user_ids: { labelKey: 'settingsFields.immune_user_ids' },
    immune_channel_ids: { labelKey: 'settingsFields.immune_channel_ids' },
  },
  titleKey: 'moderation.anti_spam', icon: MessageSquareWarning,
})
