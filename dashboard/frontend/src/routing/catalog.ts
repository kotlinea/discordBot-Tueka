import { Shield, MessageSquareWarning, ShieldAlert, BookOpen, Gavel, FileText } from 'lucide-react'
import type { Feature, Guild } from '../types'
import { featureRegistry } from '../features/registry'

export const moderationItems = [
  ['automod', 'moderation.automod', Shield], ['anti_spam', 'moderation.anti_spam', MessageSquareWarning], ['anti_raid', 'moderation.anti_raid', ShieldAlert],
  ['infractions', 'moderation.infractions', BookOpen], ['moderation_actions', 'moderation.actions', Gavel], ['moderation_logs', 'moderation.logs', FileText],
] as const

export function featurePath(guildId: string, item: Feature) { return featureRegistry.path(guildId, item.id) }

export function guildIcon(guild: Guild) { return guild.icon ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=96` : null }
