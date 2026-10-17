import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { ScheduleItem, SchedulePayload } from '../../../generated/api'
import type { FeatureScreenProps } from '../../contracts'
import type { Resource } from '../../../types'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../../components/forms/EditNotice'
import { ResourceSelect } from '../../../components/ResourcePicker'
import { Failure, Loading } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function localTime(seconds:number){
  const date=new Date(seconds*1000)
  return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)
}
const seconds=(value:string)=>value?Math.floor(new Date(value).getTime()/1000):0
type Draft=SchedulePayload&{revision:number}

export function ScheduleEditor({guildId,item,enabled,channels,onBusy}:{guildId:string;item?:ScheduleItem;enabled:boolean;channels:Resource[];onBusy?:(busy:boolean)=>void}){
  const {t}=useTranslation(['scheduling','common']);const qc=useQueryClient()
  const initial=useMemo<Draft>(()=>({kind:'message',title:'',body:'',color:0x5865F2,channel_id:null,run_at:Math.floor(Date.now()/60000)*60+600,interval_seconds:0,occurrences:1,revision:1}),[])
  const source=useMemo(()=>item?{...item.payload,revision:item.revision}:undefined,[item])
  const draft=useSettingsDraft<Draft>(source,initial,`${guildId}:${item?.id??'new'}`)
  const value=draft.draft
  const [key,setKey]=useState(()=>crypto.randomUUID())
  const save=useSaveMutation({mutationFn:()=>{
    const {revision,...payload}=value
    return item?request('PUT /api/v1/guilds/{guild_id}/schedules/items/{item_id}',`/guilds/${guildId}/schedules/items/${item.id}`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/schedules/items/{item_id}',{payload,revision})}):request('POST /api/v1/guilds/{guild_id}/schedules/items',`/guilds/${guildId}/schedules/items`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/schedules/items',{payload,request_key:key})})
  },onSuccess:async result=>{draft.accept(item?{...result.payload,revision:result.revision}:initial);setKey(crypto.randomUUID());await Promise.all([qc.invalidateQueries({queryKey:['scheduleItems',guildId]}),...(item?[qc.invalidateQueries({queryKey:['scheduleHistory',guildId,item.id]})]:[])])}})
  useUnsavedChanges(draft.dirty,save.isPending)
  useEffect(()=>{onBusy?.(draft.dirty||save.isPending);return()=>onBusy?.(false)},[draft.dirty,save.isPending,onBusy])
  const change=<K extends keyof Draft>(field:K,next:Draft[K])=>draft.setDraft({...value,[field]:next})
  return <form className={s.applicationSection} aria-label={item?`${t('scheduling.edit')} #${item.id}`:t('scheduling.create')} onSubmit={event=>{event.preventDefault();save.mutate()}}>
    <h2>{item?`${t('scheduling.edit')} #${item.id}`:t('scheduling.create')}</h2>
    <fieldset disabled={!enabled||save.isPending}>
      <label className={s.field}>{t('scheduling.kind')}<select value={value.kind} onChange={e=>draft.setDraft({...value,kind:e.target.value as Draft['kind'],interval_seconds:0,occurrences:1})}><option value="message">{t('scheduling.message')}</option><option value="event">{t('scheduling.event')}</option></select></label>
      <label className={s.field}>{t('scheduling.name')}<input maxLength={100} required={value.kind==='event'} value={value.title??''} onChange={e=>change('title',e.target.value)}/></label>
      <label className={s.field}>{t('scheduling.body')}<textarea maxLength={2000} required={!value.title?.trim()} value={value.body??''} onChange={e=>change('body',e.target.value)}/></label>
      <label className={s.field}>{t('scheduling.runAt')}<input required type="datetime-local" value={localTime(value.run_at)} onChange={e=>change('run_at',seconds(e.target.value))}/></label>
      {value.kind==='message'?<>
        <ResourceSelect label={t('scheduling.channel')} value={value.channel_id} items={channels} onChange={next=>change('channel_id',next?String(next):null)}/>
        <label className={s.field}>{t('scheduling.color')}<input type="color" value={`#${(value.color??0x5865F2).toString(16).padStart(6,'0')}`} onChange={e=>change('color',parseInt(e.target.value.slice(1),16))}/></label>
        <label className={s.field}>{t('scheduling.interval')}<select value={value.interval_seconds??0} onChange={e=>draft.setDraft({...value,interval_seconds:Number(e.target.value) as 0|86400|604800,occurrences:e.target.value==='0'?1:2})}><option value="0">{t('scheduling.once')}</option><option value="86400">{t('scheduling.daily')}</option><option value="604800">{t('scheduling.weekly')}</option></select></label>
        {Boolean(value.interval_seconds)&&<label className={s.field}>{t('scheduling.count')}<input type="number" min={1} max={365} required value={value.occurrences??1} onChange={e=>change('occurrences',Number(e.target.value))}/></label>}
      </>:<>
        <label className={s.field}>{t('scheduling.start')}<input required type="datetime-local" value={value.event_start?localTime(value.event_start):''} onChange={e=>change('event_start',seconds(e.target.value))}/></label>
        <label className={s.field}>{t('scheduling.end')}<input required type="datetime-local" value={value.event_end?localTime(value.event_end):''} onChange={e=>change('event_end',seconds(e.target.value))}/></label>
        <label className={s.field}>{t('scheduling.location')}<input required maxLength={100} value={value.event_location??''} onChange={e=>change('event_location',e.target.value)}/></label>
      </>}
    </fieldset>
    <EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>
    {save.error&&<Failure error={save.error}/>}
    <button type="submit" disabled={!enabled||!draft.dirty||save.isPending}>{t('scheduling.save')}</button>{' '}
    <button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();save.reset();setKey(crypto.randomUUID())}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}

export function ScheduleCard({guildId,item,enabled,channels}:{guildId:string;item:ScheduleItem;enabled:boolean;channels:Resource[]}){
  const {t,i18n}=useTranslation('scheduling');const qc=useQueryClient();const [expanded,setExpanded]=useState(false)
  const [editorBusy,setEditorBusy]=useState(false)
  const base=`/guilds/${guildId}/schedules/items/${item.id}`
  const detail=useQuery({queryKey:['scheduleHistory',guildId,item.id],enabled:expanded,queryFn:()=>request('GET /api/v1/guilds/{guild_id}/schedules/items/{item_id}/history',base+'/history')})
  const save=useSaveMutation({mutationFn:(job:number|null)=>job===null?request('POST /api/v1/guilds/{guild_id}/schedules/items/{item_id}/cancel',base+'/cancel',{body:encodeBody('POST /api/v1/guilds/{guild_id}/schedules/items/{item_id}/cancel',{revision:item.revision})}):request('POST /api/v1/guilds/{guild_id}/schedules/items/{item_id}/delivery/{job_id}/retry',base+`/delivery/${job}/retry`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/schedules/items/{item_id}/delivery/{job_id}/retry',{revision:item.revision})}),onSuccess:async()=>{await Promise.all([qc.invalidateQueries({queryKey:['scheduleItems',guildId]}),qc.invalidateQueries({queryKey:['scheduleHistory',guildId,item.id]})])}})
  const date=(n:number)=>new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(n*1000)
  return <section className={s.applicationSection}><h2>#{item.id} · {item.payload.title||t(`scheduling.${item.payload.kind}`)}</h2><p>{t(`scheduling.status.${item.status}`)} · {date(item.next_due)} · {t('scheduling.remaining')}: {item.remaining}</p>
    <p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{item.payload.body}</p>
    {item.payload.kind==='event'&&<p>{date(item.payload.event_start!)} — {date(item.payload.event_end!)} · {item.payload.event_location}</p>}
    <button aria-expanded={expanded} disabled={editorBusy} onClick={()=>setExpanded(!expanded)}>{t('scheduling.history')} #{item.id}</button>
    {expanded&&(detail.isLoading?<Loading/>:detail.error?<Failure error={detail.error} retry={()=>void detail.refetch()}/>:<>
      <ul>{detail.data?.delivery.map(job=><li key={job.id}>#{job.id} · {date(job.due_at)} · {job.status==='completed'?t('scheduling.delivered'):t(`scheduling.status.${job.status}`,{defaultValue:job.status})} · {job.discord_receipt_id??'—'}{job.status==='failed'&&<button disabled={!enabled||save.isPending||editorBusy||item.status==='cancelled'} onClick={()=>save.mutate(job.id)}>{t('scheduling.retry')} #{job.id}</button>}</li>)}</ul>
      <ol>{detail.data?.events.map(event=><li key={event.id}>{date(event.created_at)} · {event.actor_id} · {t(`scheduling.status.${event.event_type}`,{defaultValue:event.event_type})} {event.detail}</li>)}</ol>
      {((item.status==='scheduled'&&detail.data?.delivery.length===0)||editorBusy)&&<ScheduleEditor guildId={guildId} item={item} enabled={enabled&&item.status==='scheduled'} channels={channels} onBusy={setEditorBusy}/>}
    </>)}
    {item.status!=='cancelled'&&<button disabled={!enabled||save.isPending||editorBusy} onClick={()=>{if(confirm(t('scheduling.cancelConfirm')))save.mutate(null)}}>{t('scheduling.cancel')} #{item.id}</button>}{save.error&&<Failure error={save.error}/>}</section>
}

export default function Schedules({features}:FeatureScreenProps){
  const {guildId=''}=useParams();const {t}=useTranslation('scheduling');const [before,setBefore]=useState<number|undefined>()
  const query=useQuery({queryKey:['scheduleItems',guildId,before],queryFn:async()=>{
    const [items,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/schedules/items',`/guilds/${guildId}/schedules/items${before?`?before=${before}`:''}`),request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)])
    return {...items,channels:resources.channels.filter(c=>c.type===0)}
  }})
  const enabled=Boolean(features.find(f=>f.id==='scheduled_messages')?.enabled)
  if(query.isLoading)return <Loading/>
  if(query.error)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  const items=query.data?.items??[];const channels=query.data?.channels??[]
  return <main className={s.page}><h1>{t('scheduling.title')}</h1><p>{t('scheduling.help')}</p><p>{t('scheduling.warning')}</p>{!enabled&&<p>{t('scheduling.disabled')}</p>}
    <ScheduleEditor guildId={guildId} enabled={enabled} channels={channels}/>{!items.length&&<p>{t('scheduling.empty')}</p>}
    {items.map(item=><ScheduleCard key={item.id} guildId={guildId} item={item} enabled={enabled} channels={channels}/>)}
    {before&&<button onClick={()=>setBefore(undefined)}>{t('scheduling.latest')}</button>}{items.length===50&&<button onClick={()=>setBefore(items[items.length-1].id)}>{t('scheduling.older')}</button>}</main>
}
