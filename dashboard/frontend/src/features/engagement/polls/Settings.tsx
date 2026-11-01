import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody, isTransientQueryError } from '../../../api'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../../components/forms/EditNotice'
import { Failure, Loading } from '../../../components/Feedback'
import type { PollSettingsItem, Resource } from '../../../generated/api'
import s from '../../../styles/App.module.css'

const permissions=['view','manage','view_votes','manage_votes','settings','weights']
export function SettingsEditor({guildId,source,roles,rights}:{guildId:string;source:PollSettingsItem;roles:Resource[];rights:string[]}){
 const {t}=useTranslation(['polls','common']),qc=useQueryClient()
 const initial=useMemo(()=>source,[])
 const draft=useSettingsDraft(source,initial,guildId)
 const value=draft.draft
 const save=useSaveMutation({mutationFn:()=>request('PUT /api/v1/guilds/{guild_id}/polls/settings',`/guilds/${guildId}/polls/settings`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/polls/settings',value)}),onSuccess:async result=>{draft.accept(result);await qc.invalidateQueries({queryKey:['pollSettings',guildId]})}})
 useUnsavedChanges(draft.dirty,save.isPending)
 const settings=value.settings
 return <form className={s.applicationSection} onSubmit={e=>{e.preventDefault();save.mutate()}}>
  <fieldset disabled={save.isPending}>
   <label><input type="checkbox" disabled={!rights.includes('settings')} checked={value.enabled??false} onChange={e=>draft.setDraft({...value,enabled:e.target.checked})}/>{t('polls.enabled')}</label>
   <label className={s.field}>{t('polls.retention')}<input type="number" min={1} max={365} disabled={!rights.includes('settings')} value={settings.retention_days??90} onChange={e=>draft.setDraft({...value,settings:{...settings,retention_days:Number(e.target.value)}})}/></label>
   {roles.map(role=><fieldset key={role.id}><legend>{role.name}</legend>
    <label className={s.field}>{t('polls.weight')}<input type="number" min={1} max={100} disabled={!rights.includes('weights')} value={settings.role_weights?.[role.id]??1} onChange={e=>draft.setDraft({...value,settings:{...settings,role_weights:{...settings.role_weights,[role.id]:Number(e.target.value)}}})}/></label>
    {permissions.map(permission=><label key={permission}><input type="checkbox" disabled={!rights.includes('permissions')} checked={settings.role_permissions?.[role.id]?.includes(permission)??false} onChange={e=>{const old=settings.role_permissions?.[role.id]??[];draft.setDraft({...value,settings:{...settings,role_permissions:{...settings.role_permissions,[role.id]:e.target.checked?[...old,permission]:old.filter(p=>p!==permission)}}})}}/>{t(`polls.permissions.${permission}`)}</label>)}
   </fieldset>)}
  </fieldset>
  <EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>
  {save.error&&<Failure error={save.error}/>}
  <button disabled={!draft.dirty||save.isPending} type="submit">{t('polls.save')}</button>{' '}<button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();save.reset()}}>{t('common.discard',{ns:'common'})}</button>
 </form>
}

export default function Settings(){
 const {guildId=''}=useParams();const {t}=useTranslation('polls')
 const query=useQuery({queryKey:['pollSettings',guildId],queryFn:async()=>{
  const [source,resources,caps,history]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/polls/settings',`/guilds/${guildId}/polls/settings`),request('GET /api/v1/guilds/{guild_id}/polls/resources',`/guilds/${guildId}/polls/resources`),request('GET /api/v1/guilds/{guild_id}/polls/capabilities',`/guilds/${guildId}/polls/capabilities`),request('GET /api/v1/guilds/{guild_id}/polls/settings/history',`/guilds/${guildId}/polls/settings/history`)])
  return {source,roles:resources.roles,caps,history:history.items}
 }})
 if(query.isLoading)return <Loading/>
 if(query.error&&(!query.data||!isTransientQueryError(query.error)))return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
 return <main className={s.page}><h1>{t('polls.settings')}</h1><p>{t('polls.weightHelp')}</p>{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}<SettingsEditor guildId={guildId} source={query.data!.source} roles={query.data!.roles} rights={query.error?[]:query.data!.caps.permissions}/><h2>{t('polls.history')}</h2><ol>{query.data!.history.map(event=><li key={event.id}>{new Date(event.created_at*1000).toLocaleString()} · {event.actor_id} · {event.event_type}</li>)}</ol></main>
}
