import type { CategoryDefinition } from '../contracts'
import { Shield } from 'lucide-react'
import { feature as moderation } from './moderation.feature'
import { feature as automod } from './automod.feature'
import { feature as anti_spam } from './anti_spam.feature'
import { feature as anti_raid } from './anti_raid.feature'
import { feature as infractions } from './infractions.feature'
import { feature as moderation_actions } from './moderation_actions.feature'
import { feature as moderation_logs } from './moderation_logs.feature'
import { feature as audit_log } from './audit_log.feature'
import { feature as trust_score } from './trust_score.feature'

export const category: CategoryDefinition = {
  id: 'moderation', titleKey: 'nav.moderation', icon: Shield,
  hub: { path: 'moderation', namespaces: ['moderation', 'common'], load: () => import('./Hub').then(module => ({ default: module.ModerationHub })) },
  features: [moderation, automod, anti_spam, anti_raid, infractions, moderation_actions, moderation_logs, audit_log, trust_score],
}
