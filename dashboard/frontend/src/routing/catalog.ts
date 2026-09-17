import { Shield, MessageSquareWarning, ShieldAlert, BookOpen, Gavel, FileText } from 'lucide-react'
import type { Feature, Guild } from '../types'

export const moderationItems = [
  ['automod', 'moderation.automod', Shield], ['anti_spam', 'moderation.anti_spam', MessageSquareWarning], ['anti_raid', 'moderation.anti_raid', ShieldAlert],
  ['infractions', 'moderation.infractions', BookOpen], ['moderation_actions', 'moderation.actions', Gavel], ['moderation_logs', 'moderation.logs', FileText],
] as const

export function featurePath(guildId:string, item:Feature) { if (item.id==='tickets') return `/servers/${guildId}/tickets`; if(item.id==='reaction_roles')return `/servers/${guildId}/reaction-roles`; if(item.id==='suggestions')return `/servers/${guildId}/suggestions`; if (item.category==='social') return `/servers/${guildId}/social/${item.id.replace('_updates','')}`; return item.parent==='moderation'?`/servers/${guildId}/moderation/${item.id}`:`/servers/${guildId}/modules/${item.id}` }

export function guildIcon(guild: Guild) { return guild.icon ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=96` : null }
