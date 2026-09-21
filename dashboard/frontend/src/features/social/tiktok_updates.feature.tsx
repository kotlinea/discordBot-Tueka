import { defineFeature } from '../defaults'
import { loadProvider } from './screens'

export const feature = defineFeature({
  id: 'tiktok_updates', category: 'social',
  path: 'social/tiktok', namespaces: ['social', 'common'],
  load: loadProvider,
})

