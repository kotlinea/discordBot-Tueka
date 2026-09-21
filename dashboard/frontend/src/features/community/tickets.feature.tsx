import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'tickets', category: 'community',
  path: 'tickets', namespaces: ['tickets', 'common'], access: 'ticket_staff',
  load: () => import('../tickets/Routes').then(module => ({ default: module.TicketRoutes })),
})

