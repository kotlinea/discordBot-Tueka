import type { CategoryDefinition } from '../contracts'
import { Bell } from 'lucide-react'
import { feature as youtube_updates } from './youtube_updates.feature'
import { feature as twitch_updates } from './twitch_updates.feature'
import { feature as tiktok_updates } from './tiktok_updates.feature'
import { feature as x_updates } from './x_updates.feature'
import { feature as instagram_updates } from './instagram_updates.feature'

export const providers = [youtube_updates, twitch_updates, tiktok_updates, x_updates, instagram_updates]
export const category: CategoryDefinition = {
  id: 'social', titleKey: 'nav.social', icon: Bell,
  hub: { path: 'social', namespaces: ['social', 'common'], load: () => import('./Hub').then(module => ({ default: module.SocialHub })) },
  features: providers,
}
