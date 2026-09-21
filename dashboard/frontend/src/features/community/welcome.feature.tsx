import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'welcome', category: 'community',
  path: 'modules/welcome', namespaces: ['common'],
  load: () => import('./welcome/Settings'),
})
