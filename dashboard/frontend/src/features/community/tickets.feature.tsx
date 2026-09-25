import { defineFeature } from '../defaults'
import { MessageSquareWarning } from 'lucide-react'

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'tickets', category: 'community',
  path: 'tickets', namespaces: ['tickets', 'common'], access: 'ticket_staff',
  nested: true, titleKey: 'tickets.title', icon: MessageSquareWarning,
  settingsPath: 'modules/tickets',
  settingsLoad: () => import('./tickets/Settings').then(module => ({ default: module.TicketSettingsPage })),
  breadcrumbs: (suffix, t) => suffix[0] ? [{ label: t(`tickets.${suffix[0] === 'panel-messages' ? 'panelMessages' : suffix[0]}`) }] : [],
  load: () => import('./tickets/Routes').then(module => ({ default: module.TicketRoutes })),
  standalone: [{ path: '/tickets/transcripts/:transcriptId', load: () => import('./tickets/Transcript').then(module => ({ default: module.TranscriptStandalone })) }],
})
