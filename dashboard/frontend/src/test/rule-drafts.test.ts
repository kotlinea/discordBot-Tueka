import { expect, it } from 'vitest'
import { cloneDraft, fromForm, toForm } from '../features/moderation/ruleForm'
import type { Rule } from '../types'

const rule: Rule = { id: 15, revision: 7, guild_id: '1', family: 'anti_raid', event_type: 'member_join', name: 'New members', enabled: true, mode: 'monitor', priority: 50, stop_on_match: true, trigger_type: 'new_account_ratio', trigger_config: { limit: 12, window_seconds: 60, account_age_days: 5, percentage: 80 }, conditions: { channel_policy: 'only',channel_ids: ['123456789012345678'],category_ids: ['333333333333333333'],required_role_ids: ['555555555555555555'],minimum_account_age_days: 2,actor_kinds: ['human'] },exemptions:{user_ids:['999999999999999999']},actions:[{type:'log',message:'{rule}'}] }

it('duplicates a detached disabled draft without identity and keeps every domain setting',()=>{
  const copy=cloneDraft(rule)
  expect(copy).not.toHaveProperty('id');expect(copy).not.toHaveProperty('revision');expect(copy).not.toHaveProperty('guild_id')
  expect(copy.enabled).toBe(false)
  const value=fromForm(toForm(copy))
  expect(value.trigger_config).toEqual(rule.trigger_config)
  expect(value.conditions).toMatchObject(rule.conditions)
  expect(value.exemptions).toMatchObject(rule.exemptions)
  value.actions[0].message='changed'
  expect(rule.actions[0].message).toBe('{rule}')
})

it('edits thresholds without losing family-specific fields, resource IDs or revision',()=>{
  const form=toForm(rule);form.limit=20
  const value=fromForm(form)
  expect(value.trigger_config).toEqual({...rule.trigger_config,limit:20})
  expect(value.revision).toBe(7);expect(value.id).toBe(15);expect(value.enabled).toBe(true)
  expect(value).not.toHaveProperty('keywordsText')
  expect(value.conditions).toMatchObject(rule.conditions)
})

it('preserves keyword/domain policies and non-rate trigger options',()=>{
  for(const [trigger,config] of Object.entries({keyword:{keywords:['a'],match:'contains'},domain:{domains:['example.com'],mode:'block_all_except'},caps:{percentage:75,minimum_letters:8},honeypot:{channel_ids:['123456789012345678']}})) {
    const value=fromForm(toForm({...rule,trigger_type:trigger,trigger_config:config}))
    expect(value.trigger_config).toMatchObject(config)
    expect(value.trigger_config).not.toHaveProperty('limit')
  }
})
