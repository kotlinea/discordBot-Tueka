import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'temporary_voice', category: 'community',
  path: 'modules/temporary_voice', namespaces: ['common'],
  fields: {
    temp_voice_trigger_id: { labelKey: 'settingsFields.temp_voice_trigger_id', resource: 'voice' },
    temp_voice_category_id: { labelKey: 'settingsFields.temp_voice_category_id' },
    temp_voice_name: { labelKey: 'settingsFields.temp_voice_name', template: { variables: ['member'], maxLength: 100 } },
  },
})

