import { defineRuleFeature } from './ruleScreen'
import { ShieldAlert } from 'lucide-react'

export const feature = defineRuleFeature({
  id: 'anti_raid', defaultTrigger: 'join_rate',
  fields: {
    log_channel_id: { labelKey: 'settingsFields.log_channel_id' },
    notify_channel_id: { labelKey: 'settingsFields.notify_channel_id' },
    default_lockdown_minutes: { labelKey: 'settingsFields.default_lockdown_minutes' },
    immune_role_ids: { labelKey: 'settingsFields.immune_role_ids' },
    immune_user_ids: { labelKey: 'settingsFields.immune_user_ids' },
    immune_channel_ids: { labelKey: 'settingsFields.immune_channel_ids' },
  },
  titleKey: 'moderation.anti_raid', icon: ShieldAlert,
})
