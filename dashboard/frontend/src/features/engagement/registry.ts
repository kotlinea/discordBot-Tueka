import type { CategoryDefinition } from '../contracts'
import { feature as advanced_polls } from './advanced_polls.feature'
import { feature as suggestions } from './suggestions.feature'
import { feature as minigames } from './minigames.feature'

export const category: CategoryDefinition = {
  id: 'engagement', titleKey: 'nav.engagement',
  features: [advanced_polls, suggestions, minigames],
}

