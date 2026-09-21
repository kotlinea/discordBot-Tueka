import { defineFeature } from '../defaults'
import { loadProvider } from './screens'

export const feature = defineFeature({
  id: 'x_updates', category: 'social',
  path: 'social/x', namespaces: ['social', 'common'],
  load: loadProvider,
})

