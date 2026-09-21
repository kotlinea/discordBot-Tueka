import { defineFeature } from '../defaults'
import { loadProvider } from './screens'

export const feature = defineFeature({
  id: 'twitch_updates', category: 'social',
  path: 'social/twitch', namespaces: ['social', 'common'],
  load: loadProvider,
})

