import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'suggestions', category: 'engagement',
  path: 'suggestions', namespaces: ['suggestions', 'common'],
  load: () => import('../suggestions/Settings'),
})

