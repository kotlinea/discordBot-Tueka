import { defineFeature } from '../defaults'
import { loadProvider } from './screens'

export const feature = defineFeature({
  id: 'instagram_updates', category: 'social',
  path: 'social/instagram', namespaces: ['social', 'common'],
  load: loadProvider,
})

