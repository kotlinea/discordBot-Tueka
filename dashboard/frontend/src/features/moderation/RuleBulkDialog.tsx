import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { request } from '../../api'
import type { Rule } from '../../types'
import { useConfiguration, configurationIssues } from '../../components/feature/ConfigurationState'
import { Failure } from '../../components/Feedback'
import { Button } from '../../components/ui/Button'
import s from '../../styles/App.module.css'

export function RuleBulkDialog({ rules, enabled, pending, error, conflict, missing, onConfirm, onClose, onRefresh }: {
  rules: Rule[]; enabled: boolean; pending: boolean; error: unknown; conflict: boolean; missing: boolean;
  onConfirm: () => void; onClose: () => void; onRefresh: () => void
}) {
  const { t } = useTranslation(['moderation','common']); const { guildId='' } = useParams()
  const { feature, features, fields } = useConfiguration()
  const resources = useQuery({queryKey:['resources',guildId],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)})
  const issues = configurationIssues(feature,features,resources.data,fields)
  const permissions = new Set<string>()
  const actionPermissions: Record<string,string> = { delete:'Manage Messages',purge:'Manage Messages',remove_reaction:'Manage Messages',timeout:'Moderate Members',untimeout:'Moderate Members',kick:'Kick Members',ban:'Ban Members',unban:'Ban Members',tempban:'Ban Members',softban:'Ban Members',lock:'Manage Channels',unlock:'Manage Channels',lockdown:'Manage Channels',unlockdown:'Manage Channels',notify:'Send Messages',log:'Send Messages' }
  for(const rule of rules) for(const action of rule.actions || []) {const permission=actionPermissions[String(action.type)];if(permission)permissions.add(permission)}
  const permissionBits: Record<string,bigint> = {'Manage Messages':1n<<13n,'Moderate Members':1n<<40n,'Kick Members':1n<<1n,'Ban Members':1n<<2n,'Manage Channels':1n<<4n,'Send Messages':1n<<11n}
  const bits=BigInt(resources.data?.bot_permissions || '0')
  const missingPermissions=resources.data ? [...permissions].filter(permission=>!(bits&8n)&&!(bits&permissionBits[permission])) : []
  const resourceMissing = resources.data && rules.some(rule => [rule.trigger_config,rule.conditions,rule.exemptions,...rule.actions].some(section =>
    Object.entries(section || {}).some(([key,value])=>{
      const options=/(?:channel|category)_ids?$/.test(key)?resources.data!.channels:/role_ids?$/.test(key)?resources.data!.roles:undefined
      return options && (Array.isArray(value)?value:[value]).filter(Boolean).some(id=>!options.some(item=>String(item.id)===String(id)))
    })))
  const requiredConfig:Record<string,string>={keyword:'keywords',regex:'patterns',domain:'domains',honeypot:'channel_ids'}
  const incomplete=rules.some(rule=>{const key=requiredConfig[rule.trigger_type];const value=rule.trigger_config?.[key];return !rule.name?.trim() || Boolean(key&&(!Array.isArray(value)||!value.length))})
  return <Dialog.Root open onOpenChange={open=>{if(!open&&!pending)onClose()}}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.dialog} onCloseAutoFocus={event=>{event.preventDefault();document.getElementById(enabled?'rule-enable':'rule-disable')?.focus()}}>
    <div className={s.dialogHead}><div><Dialog.Title>{t('operations.review')}</Dialog.Title><Dialog.Description>{t('operations.effect')}</Dialog.Description></div></div>
    <p><strong>{t(enabled?'operations.enable':'operations.disable')}</strong> · {t('operations.selected',{count:rules.length})}</p>
    <p>{t('operations.monitor',{count:rules.filter(rule=>rule.mode==='monitor').length})} / {t('operations.enforce',{count:rules.filter(rule=>rule.mode==='enforce').length})}</p>
    <ul>{rules.map(rule=><li key={rule.id}>{rule.name} — {t(`common.${rule.mode}`)}</li>)}</ul>
    <h3>{t('operations.requirements')}</h3><p>{[...permissions].join(', ') || t('operations.none')}</p>
    <h3>{t('operations.conditions')}</h3>
    {(!feature || resources.isLoading)&&<p>{t('operations.unknown')}</p>}
    {feature&&(!feature.enabled||issues.includes('parentOff'))&&<p role="status">{t('operations.stopped')}</p>}
    {issues.filter(issue=>issue!=='parentOff').map(issue=><p key={issue}>{t(`common:editing.${issue}`)}</p>)}
    {feature?.missing_permissions?.length ? <p>{feature.missing_permissions.join(', ')}</p>:null}
    {missingPermissions.length>0&&<p role="status">{t('moderation.permissions')}: {missingPermissions.join(', ')}</p>}
    {resourceMissing&&<p role="status">{t('operations.resourceMissing')}</p>}{incomplete&&<p role="status">{t('operations.required')}</p>}
    {resources.error&&<Failure error={resources.error} retry={()=>void resources.refetch()}/>}
    {Boolean(error)&&<Failure error={error}/>} {conflict&&<p role="status">{t('operations.conflict')}</p>}{missing&&<p role="status">{t('operations.missing')}</p>}
    <div className={s.dialogActions}><Button disabled={pending} onClick={onClose}>{t('operations.cancel')}</Button>{(conflict||missing)&&<Button disabled={pending} onClick={onRefresh}>{t('operations.refresh')}</Button>}<Button variant="primary" loading={pending} disabled={!rules.length||conflict||missing||Boolean(enabled&&(incomplete||resources.error||resources.isLoading))} onClick={onConfirm}>{t('operations.confirm')}</Button></div>
  </Dialog.Content></Dialog.Portal></Dialog.Root>
}
