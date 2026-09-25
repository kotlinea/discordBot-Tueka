import { createRegistry } from './catalog'
import { category as community } from './community/registry'
import { category as engagement } from './engagement/registry'
import { category as moderation } from './moderation/registry'
import { category as social } from './social/registry'
import { LifeBuoy } from 'lucide-react'

export const featureRegistry = createRegistry([community, engagement, moderation, social], [
  { id: 'server_operations', titleKey: 'nav.serverOperations', icon: LifeBuoy },
  community, engagement, moderation, social,
])
