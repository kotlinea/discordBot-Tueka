import { defineFeature } from '../defaults'
import { MessageSquareWarning } from 'lucide-react'

const configuration = { id: 'configuration', titleKey: 'tickets.configuration' }

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'tickets', category: 'community',
  presentationCategory: 'server_operations',
  path: 'tickets', namespaces: ['tickets', 'common'], access: 'ticket_staff',
  titleKey: 'tickets.title', icon: MessageSquareWarning,
  settingsPath: 'modules/tickets',
  settingsLoad: () => import('./tickets/Routes').then(module => ({ default: module.TicketSettingsAlias })),
  load: () => import('./tickets/Hub').then(module => ({ default: module.TicketHub })),
  pages: [
    { id: 'inbox', path: 'inbox', titleKey: 'tickets.inbox', kind: 'navigation', access: 'ticket_staff', nested: true, load: () => import('./tickets/Routes').then(module => ({ default: module.TicketInboxRoutes })), breadcrumbs: suffix => suffix[0] ? [{ label: `#${suffix[0]}` }] : [] },
    { id: 'panels', path: 'panels', titleKey: 'tickets.panels', group: configuration, kind: 'navigation', access: 'manager', nested: true, load: () => import('./tickets/Routes').then(module => ({ default: module.TicketPanelRoutes })), breadcrumbs: (suffix, t) => suffix[0] ? [{ label: t(suffix[0] === 'new' ? 'tickets.createPanel' : 'common.edit') }] : [] },
    { id: 'panel_messages', path: 'panel-messages', titleKey: 'tickets.panelMessages', group: configuration, kind: 'navigation', access: 'manager', load: () => import('./tickets/Configuration').then(module => ({ default: module.TicketPanelMessages })) },
    { id: 'forms', path: 'forms', titleKey: 'tickets.forms', group: configuration, kind: 'navigation', access: 'manager', load: () => import('./tickets/Configuration').then(module => ({ default: module.TicketForms })) },
    { id: 'teams', path: 'teams', titleKey: 'tickets.teams', group: configuration, kind: 'navigation', access: 'manager', load: () => import('./tickets/Configuration').then(module => ({ default: module.TicketTeams })) },
    { id: 'tags', path: 'tags', titleKey: 'tickets.tags', group: configuration, kind: 'navigation', access: 'manager', load: () => import('./tickets/Configuration').then(module => ({ default: module.TicketTags })) },
    { id: 'transcripts', path: 'transcripts', titleKey: 'tickets.transcripts', kind: 'navigation', access: 'ticket_staff', load: () => import('./tickets/Archive').then(module => ({ default: module.TicketArchive })) },
    { id: 'stats', path: 'stats', titleKey: 'tickets.stats', kind: 'navigation', access: 'manager', load: () => import('./tickets/Stats').then(module => ({ default: module.TicketStats })) },
    { id: 'settings', path: 'settings', titleKey: 'tickets.settings', kind: 'navigation', access: 'manager', load: () => import('./tickets/Settings').then(module => ({ default: module.TicketSettingsPage })) },
  ],
  standalone: [{ path: '/tickets/transcripts/:transcriptId', load: () => import('./tickets/Transcript').then(module => ({ default: module.TranscriptStandalone })) }],
})
