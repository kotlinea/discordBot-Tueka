import { useCallback, useEffect, useState } from 'react'
import { Link,useParams } from 'react-router-dom'
import { useQuery,useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request,encodeBody } from '../../../api'
import type { AppealItem } from '../../../generated/api'
import type { FeatureScreenProps } from '../../contracts'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { Failure,Loading } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function Conversation({guildId,item,enabled,onBusy}:{guildId:string;item:AppealItem;enabled:boolean;onBusy?:(id:number,busy:boolean)=>void}){
  const {t,i18n}=useTranslation(['appeals','common']);const qc=useQueryClient()
  const [expanded,setExpanded]=useState(false)
  const [content,setContent]=useState(''),[reason,setReason]=useState(''),[ticket,setTicket]=useState('')
  const [revision,setRevision]=useState<number|null>(null)
  const detail=useQuery({queryKey:['appealDetail',guildId,item.id],enabled:expanded,queryFn:()=>request('GET /api/v1/guilds/{guild_id}/appeals/items/{item_id}',`/guilds/${guildId}/appeals/items/${item.id}`)})
  const base=`/guilds/${guildId}/appeals/items/${item.id}`
  const currentRevision=revision??item.revision
  const save=useSaveMutation({mutationFn:async(action:string)=>{
    if(action==='reply')return request('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/reply',base+'/reply',{body:encodeBody('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/reply',{content,revision:currentRevision})})
    if(action==='ticket')return request('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/ticket',base+'/ticket',{body:encodeBody('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/ticket',{ticket_id:Number(ticket),revision:currentRevision})})
    if(action.startsWith('retry:'))return request('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/delivery/{job_id}/retry',base+`/delivery/${action.slice(6)}/retry`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/delivery/{job_id}/retry',{revision:currentRevision})})
    return request('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/review',base+'/review',{body:encodeBody('POST /api/v1/guilds/{guild_id}/appeals/items/{item_id}/review',{status:action as 'reviewing'|'accepted'|'rejected'|'closed',reason,revision:currentRevision})})
  },onSuccess:async()=>{setContent('');setReason('');setTicket('');setRevision(null);await Promise.all([qc.invalidateQueries({queryKey:['appealItems',guildId]}),qc.invalidateQueries({queryKey:['appealDetail',guildId,item.id]})])}})
  const dirty=Boolean(content||reason||ticket);useUnsavedChanges(dirty,save.isPending)
  useEffect(()=>{onBusy?.(item.id,dirty||save.isPending);return()=>onBusy?.(item.id,false)},[item.id,dirty,save.isPending,onBusy])
  const capture=()=>{if(revision===null)setRevision(item.revision)}
  const clear=()=>{setContent('');setReason('');setTicket('');setRevision(null);save.reset()}
  const open=['open','reviewing'].includes(item.status)
  const date=(n:number)=>new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(n*1000)
  return <section className={s.applicationSection} aria-label={`#${item.id}`}><h2>#{item.id} · {item.kind==='appeal'?t('appeals.case'):t('appeals.title')} · {t(`appeals.status.${item.status}`)}</h2>
    <p>{t('appeals.author')}: {item.author_id} · {date(item.created_at)}</p>
    {item.case_id&&<p>{t('appeals.case')} #{item.case_id} · {item.case_action} · <Link to={`/servers/${guildId}/moderation/infractions`}>{t('appeals.case')}</Link></p>}
    {item.application_id&&<p><Link to={`/servers/${guildId}/applications/review`}>{t('appeals.application')} #{item.application_id}</Link></p>}
    {item.ticket_id&&<p><Link to={`/servers/${guildId}/tickets/inbox/${item.ticket_id}`}>{t('appeals.ticket')} #{item.ticket_id}</Link></p>}
    <button aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{t('appeals.open')} #{item.id}</button>
    {expanded&&(detail.isLoading?<Loading/>:detail.error?<Failure error={detail.error} retry={()=>void detail.refetch()}/>:<>
      <ol>{detail.data?.messages.map(message=><li key={message.id}><p>{message.staff?t('appeals.staff'):t('appeals.author')} · {message.actor_id} · {date(message.created_at)}</p><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{message.content}</p></li>)}</ol>
      {(open||dirty)&&<fieldset disabled={!enabled||save.isPending||!open}>
        <label className={s.field}>{t('appeals.message')}<textarea maxLength={2000} value={content} onChange={e=>{capture();setContent(e.target.value)}}/></label><button disabled={!content.trim()||Boolean(reason||ticket)} onClick={()=>save.mutate('reply')}>{t('appeals.send')}</button>
        <label className={s.field}>{t('appeals.reason')}<textarea maxLength={1000} value={reason} onChange={e=>{capture();setReason(e.target.value)}}/></label><p>{t('appeals.outcome')}</p>
        {(['reviewing','accepted','rejected','closed'] as const).map(status=><button key={status} disabled={!reason.trim()||item.status===status||Boolean(content||ticket)} onClick={()=>save.mutate(status)}>{t(`appeals.status.${status}`)}</button>)}
        <label className={s.field}>{t('appeals.ticketId')}<input type="number" min={1} value={ticket} onChange={e=>{capture();setTicket(e.target.value)}}/></label><button disabled={!Number.isSafeInteger(Number(ticket))||Number(ticket)<=0||Boolean(content||reason)} onClick={()=>save.mutate('ticket')}>{t('appeals.link')}</button>
      </fieldset>}
      <button disabled={!dirty||save.isPending} onClick={clear}>{t('common.discard',{ns:'common'})}</button>
      <h3>{t('appeals.delivery')}</h3><ul>{detail.data?.delivery.map(job=><li key={job.id}>#{job.id} · {t(`appeals.status.${job.status}`,{defaultValue:job.status})} · {job.attempts}{job.status==='failed'&&<button disabled={!enabled||save.isPending||dirty} onClick={()=>save.mutate(`retry:${job.id}`)}>{t('appeals.retry')} #{job.id}</button>}</li>)}</ul>
      <h3>{t('appeals.history')}</h3><ol>{detail.data?.events.map(event=><li key={event.id}>{date(event.created_at)} · {event.actor_id} · {t(`appeals.status.${event.event_type}`,{defaultValue:event.event_type})} · {event.reason}</li>)}</ol>
    </>)}{save.error&&<Failure error={save.error}/>}</section>
}

export default function Inbox({features}:FeatureScreenProps){
  const {guildId=''}=useParams();const {t}=useTranslation('appeals');const [before,setBefore]=useState<number|undefined>()
  const [editors,setEditors]=useState<Record<number,boolean>>({})
  const onBusy=useCallback((id:number,busy:boolean)=>setEditors(old=>old[id]===busy?old:{...old,[id]:busy}),[])
  const busy=Object.values(editors).some(Boolean)
  const query=useQuery({queryKey:['appealItems',guildId,before],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/appeals/items',`/guilds/${guildId}/appeals/items${before?`?before=${before}`:''}`)})
  const enabled=Boolean(features.find(f=>f.id==='appeals')?.enabled)
  if(query.isLoading)return <Loading/>
  if(query.error&&!query.data)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  const items=query.data?.items??[]
  return <main className={s.page}><h1>{t('appeals.title')}</h1>{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}<p>{t('appeals.private')}</p>{!enabled&&<p>{t('appeals.disabled')}</p>}{!items.length&&<p>{t('appeals.empty')}</p>}
    {items.map(item=><Conversation key={item.id} guildId={guildId} item={item} enabled={enabled&&!query.error} onBusy={onBusy}/>)}
    {before&&<button disabled={busy} onClick={()=>setBefore(undefined)}>{t('appeals.latest')}</button>}{items.length===50&&<button disabled={busy} onClick={()=>setBefore(items[items.length-1].id)}>{t('appeals.older')}</button>}</main>
}
