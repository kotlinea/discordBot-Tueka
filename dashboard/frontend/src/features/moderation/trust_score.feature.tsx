import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'trust_score', category: 'moderation', parent: 'moderation',
  path: 'moderation/trust_score', namespaces: ['moderation', 'common'],
})

