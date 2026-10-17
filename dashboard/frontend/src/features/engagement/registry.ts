import type { CategoryDefinition } from '../contracts'
import { Activity } from 'lucide-react'
import { feature as advanced_polls } from './advanced_polls.feature'
import { feature as suggestions } from './suggestions.feature'
import { feature as minigames } from './minigames.feature'
import { feature as scheduled_messages } from './scheduled_messages.feature'

export const category: CategoryDefinition = {
  id: 'engagement', titleKey: 'nav.engagement', icon: Activity,
  features: [advanced_polls, suggestions, minigames, scheduled_messages],
}
