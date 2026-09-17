import type { Rule } from "../../types"
import type { ScopePolicy } from "../../components/AccessPolicy"



export type RuleForm = Rule & { keywordsText: string; allowText: string; patternsText: string; domainsText: string; limit: number; windowSeconds: number; channelPolicy: ScopePolicy; rolePolicy: ScopePolicy; scopeChannelIdsText: string; scopeRoleIdsText: string; previewContent: string }

export function toForm(rule: Rule): RuleForm { const config = rule.trigger_config || {}; const channelPolicy = String(rule.conditions?.channel_policy || ((rule.conditions?.channel_ids as unknown[])?.length ? 'only' : 'all_except')) as ScopePolicy; const rolePolicy = String(rule.conditions?.role_policy || ((rule.conditions?.required_role_ids as unknown[])?.length ? 'only' : 'all_except')) as ScopePolicy; return { ...rule, keywordsText: ((config.keywords as string[]) || []).join('\n'), allowText: ((config.allow_list as string[]) || []).join('\n'), patternsText: ((config.patterns as string[]) || []).join('\n'), domainsText: ((config.domains as string[]) || []).join('\n'), limit: Number(config.limit || 5), windowSeconds: Number(config.window_seconds || 10), channelPolicy, rolePolicy, scopeChannelIdsText: ((channelPolicy === 'only' ? rule.conditions?.channel_ids : rule.exemptions?.channel_ids) as Array<string|number> || []).join('\n'), scopeRoleIdsText: ((rolePolicy === 'only' ? rule.conditions?.required_role_ids : rule.exemptions?.role_ids) as Array<string|number> || []).join('\n'), previewContent: '' } }

export function lines(value: string) { return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean) }

export function ids(value: string) { return lines(value).filter(item => /^\d+$/.test(item)) }

export function fromForm(value: RuleForm): Rule { const trigger_config: Record<string, unknown> = {}; if (value.trigger_type === 'keyword') Object.assign(trigger_config, { keywords: lines(value.keywordsText), allow_list: lines(value.allowText), match: 'wildcard' }); else if (value.trigger_type === 'regex') Object.assign(trigger_config, { patterns: lines(value.patternsText) }); else if (value.trigger_type === 'domain') Object.assign(trigger_config, { domains: lines(value.domainsText), mode: 'blacklist' }); else Object.assign(trigger_config, { limit: Number(value.limit), window_seconds: Number(value.windowSeconds) }); const channelIds = ids(value.scopeChannelIdsText); const roleIds = ids(value.scopeRoleIdsText); return { ...value, trigger_config, conditions: { channel_policy: value.channelPolicy, role_policy: value.rolePolicy, channel_ids: value.channelPolicy === 'only' ? channelIds : [], required_role_ids: value.rolePolicy === 'only' ? roleIds : [] }, exemptions: { channel_ids: value.channelPolicy === 'all_except' ? channelIds : [], role_ids: value.rolePolicy === 'all_except' ? roleIds : [] }, actions: value.actions } }

export const RULE_ACTION_TYPES = ['delete','points','notify','dm','timeout','kick','ban','tempban','log'] as const

export function defaultAction(type: string): Record<string, unknown> { if (type === 'points') return { type, points: 1, expires_days: 30 }; if (type === 'timeout') return { type, duration_minutes: 10 }; if (type === 'tempban') return { type, duration_minutes: 1440 }; if (type === 'notify') return { type, message: '{user} さんのルール違反を検知しました: {reason}' }; if (type === 'dm') return { type, message: '{server}でルール違反を検知しました: {reason}' }; if (type === 'log') return { type, message: '{rule}: {reason}' }; return { type } }

export function actionConfigurable(type: string) { return ['points','notify','dm','timeout','tempban','log'].includes(type) }
