import { defineFeature } from '../defaults'
import { loadProvider } from './screens'

export const feature = defineFeature({
  id: 'youtube_updates', category: 'social',
  path: 'social/youtube', namespaces: ['social', 'common'],
  load: loadProvider,
})

