import {useParams} from 'react-router-dom'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {InsightsSettings,Resource} from '../../../types'
import {request,encodeBody} from '../../../api'
import {ResourceSelect} from '../../../components/ResourcePicker'
import {useSettingsDraft} from '../../../components/forms/useSettingsDraft'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {useUnsavedChanges} from '../../../components/forms/useUnsavedChanges'
import {EditNotice} from '../../../components/forms/EditNotice'
import {Failure,Loading} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

const initial:InsightsSettings={enabled:false,settings:{channel_ids:[],retention_days:30,track_members:true},revision:0}
export function SettingsEditor({guildId,source,channels}:{guildId:string;source:InsightsSettings;channels:Resource[]}){
  const {t}=useTranslation(['insights','common']);const qc=useQueryClient()
  const draft=useSettingsDraft(source,initial,guildId),value=draft.draft
  const save=useSaveMutation({mutationFn:()=>request('PUT /api/v1/guilds/{guild_id}/insights/settings',`/guilds/${guildId}/insights/settings`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/insights/settings',value)}),onSuccess:async result=>{draft.accept(result);await Promise.all([qc.invalidateQueries({queryKey:['insights',guildId]}),qc.invalidateQueries({queryKey:['features',guildId]})])}})
  useUnsavedChanges(draft.dirty,save.isPending)
  return <form className={s.applicationSection} aria-label={t('insights.settings')} onSubmit={e=>{e.preventDefault();save.mutate()}}><h2>{t('insights.settings')}</h2><p>{t('insights.settingsHelp')}</p>
    <fieldset disabled={save.isPending}>
      <label><input type="checkbox" checked={value.enabled} onChange={e=>draft.setDraft({...value,enabled:e.target.checked})}/>{t('insights.enabled')}</label>
      <ResourceSelect label={t('insights.channels')} multiple items={channels.filter(c=>[0,2,5,13,15,16].includes(c.type??-1))} value={value.settings.channel_ids} onChange={v=>draft.setDraft({...value,settings:{...value.settings,channel_ids:v as string[]}})}/><small>{t('insights.channelHelp')}</small>
      <label><input type="checkbox" checked={value.settings.track_members} onChange={e=>draft.setDraft({...value,settings:{...value.settings,track_members:e.target.checked}})}/>{t('insights.members')}</label>
      <label className={s.field}>{t('insights.retention')}<input type="number" required min={1} max={365} value={value.settings.retention_days} onChange={e=>draft.setDraft({...value,settings:{...value.settings,retention_days:Number(e.target.value)}})}/><small>{t('insights.retentionHelp')}</small></label>
    </fieldset><EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>{save.error&&<Failure error={save.error}/>}
    <button disabled={!draft.dirty||save.isPending||(value.settings.channel_ids?.length??0)>25}>{t('common.save',{ns:'common'})}</button><button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();save.reset()}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}

export default function Settings(){
  const {guildId=''}=useParams();const {t}=useTranslation('insights')
  const query=useQuery({queryKey:['insights',guildId,'settings'],queryFn:async()=>{const [module,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/insights/settings',`/guilds/${guildId}/insights/settings`),request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)]);return {module,...resources}}})
  if(!query.data)return <main className={s.page}>{query.error?<Failure error={query.error} retry={()=>void query.refetch()}/>:<Loading/>}</main>
  return <main className={s.page}><h1>{t('insights.title')}</h1><button disabled={query.isFetching} onClick={()=>void query.refetch()}>{t('insights.refresh')}</button>{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}<SettingsEditor guildId={guildId} source={query.data.module} channels={query.data.channels}/></main>
}
