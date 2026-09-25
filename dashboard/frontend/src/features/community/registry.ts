import type { CategoryDefinition } from '../contracts'
import { Users } from 'lucide-react'
import { feature as welcome } from './welcome.feature'
import { feature as autorole } from './autorole.feature'
import { feature as leveling } from './leveling.feature'
import { feature as reaction_roles } from './reaction_roles.feature'
import { feature as live_stats } from './live_stats.feature'
import { feature as temporary_voice } from './temporary_voice.feature'
import { feature as tickets } from './tickets.feature'

export const category: CategoryDefinition = {
  id: 'community', titleKey: 'nav.community', icon: Users,
  features: [tickets, reaction_roles, welcome, autorole, leveling, live_stats, temporary_voice],
}
