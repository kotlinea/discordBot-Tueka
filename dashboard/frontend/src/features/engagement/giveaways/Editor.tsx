import {useEffect,useMemo,useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {GiveawayConfig,GiveawayItem,Resource} from '../../../types'
import {request,encodeBody} from '../../../api'
import {ResourceSelect} from '../../../components/ResourcePicker'
import {useSettingsDraft} from '../../../components/forms/useSettingsDraft'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {useUnsavedChanges} from '../../../components/forms/useUnsavedChanges'
import {EditNotice} from '../../../components/forms/EditNotice'
import {Failure} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

type Draft=GiveawayConfig&{revision:number}
export function Editor({guildId,item,enabled,channels,roles,onBusy,onCreated}:{guildId:string;item?:GiveawayItem;enabled:boolean;channels:Resource[];roles:Resource[];onBusy:(busy:boolean)=>void;onCreated:(item:GiveawayItem)=>void}){
  const {t}=useTranslation(['giveaways','common']);const qc=useQueryClient()
  const initial=useMemo<Draft>(()=>({kind:'giveaway',title:'',description:'',channel_id:'',ends_at:Math.floor(Date.now()/1000)+3600,winner_count:1,capacity:1000,required_role_ids:[],denied_role_ids:[],min_account_days:0,min_member_days:0,retention_days:30,revision:1}),[])
  const source=useMemo(()=>item?{...item.config,revision:item.revision}:undefined,[item])
  const draft=useSettingsDraft(source,initial,`${guildId}:${item?.id??'new'}`);const value=draft.draft
  const [nonce,setNonce]=useState(()=>crypto.randomUUID())
  const save=useSaveMutation({mutationFn:()=>{
    const {revision,...config}=value
    return item?request('PUT /api/v1/guilds/{guild_id}/giveaways/{item_id}',`/guilds/${guildId}/giveaways/${item.id}`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/giveaways/{item_id}',{config,revision})}):request('POST /api/v1/guilds/{guild_id}/giveaways',`/guilds/${guildId}/giveaways`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways',{config,request_key:nonce})})
  },onSuccess:async result=>{draft.accept({...result.config,revision:result.revision});await qc.invalidateQueries({queryKey:['giveaways',guildId]});if(!item)onCreated(result)}})
  useUnsavedChanges(draft.dirty,save.isPending)
  useEffect(()=>{onBusy(draft.dirty||save.isPending);return()=>onBusy(false)},[draft.dirty,save.isPending,onBusy])
  const change=<K extends keyof Draft>(key:K,next:Draft[K])=>draft.setDraft({...value,[key]:next})
  const localTime=new Date(value.ends_at*1000-new Date(value.ends_at*1000).getTimezoneOffset()*60000).toISOString().slice(0,16)
  const locked=Boolean(item&&item.status!=='draft')
  return <form className={s.applicationSection} aria-label={item?`${t('giveaways.edit')} #${item.id}`:t('giveaways.create')} onSubmit={e=>{e.preventDefault();save.mutate()}}><h2>{item?`${t('giveaways.edit')} #${item.id}`:t('giveaways.create')}</h2>
    {locked&&<p>{t('giveaways.locked')}</p>}
    <fieldset disabled={!enabled||locked||save.isPending}>
      <label className={s.field}>{t('giveaways.name')}<input required maxLength={120} value={value.title} onChange={e=>change('title',e.target.value)}/></label>
      <label className={s.field}>{t('giveaways.description')}<textarea maxLength={2000} value={value.description} onChange={e=>change('description',e.target.value)}/></label>
      <label className={s.field}>{t('giveaways.kind')}<select value={value.kind} onChange={e=>draft.setDraft({...value,kind:e.target.value as 'giveaway'|'event',winner_count:e.target.value==='event'?0:1})}><option value="giveaway">{t('giveaways.giveaway')}</option><option value="event">{t('giveaways.event')}</option></select></label>
      <ResourceSelect label={t('giveaways.channel')} items={channels.filter(c=>[0,5].includes(c.type??-1))} value={value.channel_id} onChange={v=>change('channel_id',String(v??''))}/>
      <label className={s.field}>{t('giveaways.deadline')}<input required type="datetime-local" value={localTime} onChange={e=>{if(e.target.value)change('ends_at',Math.floor(new Date(e.target.value).getTime()/1000))}}/></label>
      {value.kind==='giveaway'&&<label className={s.field}>{t('giveaways.winners')}<input type="number" required min={1} max={20} value={value.winner_count} onChange={e=>change('winner_count',Number(e.target.value))}/></label>}
      <label className={s.field}>{t('giveaways.capacity')}<input type="number" required min={1} max={1000} value={value.capacity} onChange={e=>change('capacity',Number(e.target.value))}/></label>
      <ResourceSelect label={t('giveaways.requiredRoles')} items={roles} multiple value={value.required_role_ids} onChange={v=>change('required_role_ids',v as string[])}/>
      <ResourceSelect label={t('giveaways.deniedRoles')} items={roles} multiple value={value.denied_role_ids} onChange={v=>change('denied_role_ids',v as string[])}/>
      <label className={s.field}>{t('giveaways.accountDays')}<input type="number" required min={0} max={3650} value={value.min_account_days} onChange={e=>change('min_account_days',Number(e.target.value))}/></label>
      <label className={s.field}>{t('giveaways.memberDays')}<input type="number" required min={0} max={3650} value={value.min_member_days} onChange={e=>change('min_member_days',Number(e.target.value))}/></label>
      <label className={s.field}>{t('giveaways.retention')}<input type="number" required min={1} max={365} value={value.retention_days} onChange={e=>change('retention_days',Number(e.target.value))}/><small>{t('giveaways.retentionHelp')}</small></label>
    </fieldset><EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>{save.error&&<Failure error={save.error}/>}
    <button disabled={!enabled||locked||!draft.dirty||save.isPending||!value.title.trim()||!value.channel_id}>{t('common.save',{ns:'common'})}</button><button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();if(!item)setNonce(crypto.randomUUID());save.reset()}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}
