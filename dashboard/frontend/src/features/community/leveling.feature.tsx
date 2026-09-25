import { defineFeature } from '../defaults'

const rewardRoles = { kind: 'role' as const, ids: (value: unknown) => Array.isArray(value) ? value.map(item => String(item).split(':')[1]).filter(Boolean) : [] }

export const feature = defineFeature({
  id: 'leveling', category: 'community',
  path: 'modules/leveling', namespaces: ['common'],
  fields: {
    text_notification_channel_id: { labelKey: 'settingsFields.text_notification_channel_id' },
    text_role_rewards: { labelKey: 'settingsFields.text_role_rewards', references: rewardRoles },
    voice_enabled: { labelKey: 'settingsFields.voice_enabled' },
    voice_notification_channel_id: { labelKey: 'settingsFields.voice_notification_channel_id' },
    voice_role_rewards: { labelKey: 'settingsFields.voice_role_rewards', references: rewardRoles },
    voice_xp_per_minute: { labelKey: 'settingsFields.voice_xp_per_minute' },
    voice_allow_solo: { labelKey: 'settingsFields.voice_allow_solo' },
    voice_allow_muted: { labelKey: 'settingsFields.voice_allow_muted' },
  },
})
