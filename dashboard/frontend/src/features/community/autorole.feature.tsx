import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'autorole', category: 'community',
  path: 'modules/autorole', namespaces: ['common'],
  fields: {
    default_role_id: { labelKey: 'settingsFields.default_role_id' },
  },
})

