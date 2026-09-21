import type { CategoryDefinition } from '../contracts'
import { feature as youtube_updates } from './youtube_updates.feature'
import { feature as twitch_updates } from './twitch_updates.feature'
import { feature as tiktok_updates } from './tiktok_updates.feature'
import { feature as x_updates } from './x_updates.feature'
import { feature as instagram_updates } from './instagram_updates.feature'

export const category: CategoryDefinition = {
  id: 'social', titleKey: 'nav.social',
  features: [youtube_updates, twitch_updates, tiktok_updates, x_updates, instagram_updates],
}

