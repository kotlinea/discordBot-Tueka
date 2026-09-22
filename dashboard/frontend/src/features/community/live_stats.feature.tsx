import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'live_stats', category: 'community',
  path: 'modules/live_stats', namespaces: ['common'],
  fields: {
    stats_channel_id: { labelKey: 'settingsFields.stats_channel_id' },
    stats_template: { labelKey: 'settingsFields.stats_template', template: { variables: ['members', 'humans', 'bots', 'roles'], maxLength: 90 } },
  },
})

