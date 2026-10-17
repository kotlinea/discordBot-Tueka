import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { SuggestionItem } from '../../../types'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { Failure, Loading } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function SuggestionReview({guildId,item,enabled}:{guildId:string;item:SuggestionItem;enabled:boolean}) {
  const {t,i18n}=useTranslation(['suggestions','common']); const qc=useQueryClient()
  const [reason,setReason]=useState(''); const [history,setHistory]=useState(false)
  const [revision,setRevision]=useState<number|null>(null)
  const events=useQuery({queryKey:['suggestionEvents',guildId,item.id],enabled:history,
    queryFn:()=>request('GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/events',`/guilds/${guildId}/suggestions/items/${item.id}/events`)})
  const save=useSaveMutation({mutationFn:(status:'reviewing'|'approved'|'rejected'|'implemented')=>request(
    'POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/review',`/guilds/${guildId}/suggestions/items/${item.id}/review`,
    {method:'POST',body:encodeBody('POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/review',{status,reason,revision:revision??item.revision})}),
    onSuccess:async()=>{setReason('');setRevision(null); await Promise.all([qc.invalidateQueries({queryKey:['suggestionsItems',guildId]}),qc.invalidateQueries({queryKey:['suggestionEvents',guildId,item.id]})])}})
  useUnsavedChanges(Boolean(reason),save.isPending)
  const statuses:('reviewing'|'approved'|'rejected'|'implemented')[]=item.status==='approved'?['implemented']:['pending','reviewing'].includes(item.status)?['reviewing','approved','rejected']:[]
  return <section className={s.suggestionReview} aria-label={t('suggestions.reviewItem',{id:item.id})}>
    {item.review_reason&&<p>{t('suggestions.reason')}: {item.review_reason}</p>}
    {item.discussion_thread_id&&<a href={`https://discord.com/channels/${guildId}/${item.discussion_thread_id}`} target="_blank" rel="noreferrer">{t('suggestions.discussionOpen')}</a>}
    {(statuses.length>0||Boolean(reason))&&<><label className={s.field}><span>{t('suggestions.reason')}</span><textarea value={reason} maxLength={1000} disabled={save.isPending||!enabled||!statuses.length} onChange={e=>{if(revision===null)setRevision(item.revision);setReason(e.target.value)}}/></label>
      <div className={s.rowActions}>{statuses.map(status=><button key={status} disabled={!enabled||save.isPending||!reason.trim()||status===item.status} onClick={()=>save.mutate(status)}>{t(`suggestions.status.${status}`)}</button>)}
      <button disabled={save.isPending||!reason} onClick={()=>{setReason('');setRevision(null);save.reset()}}>{t('common.discard',{ns:'common'})}</button></div></>}
    {save.error&&<Failure error={save.error}/>}
    <button aria-expanded={history} onClick={()=>setHistory(!history)}>{t('suggestions.history')}</button>
    {history&&(events.isLoading?<Loading/>:events.error?<Failure error={events.error} retry={()=>void events.refetch()}/>:<ol>{events.data?.items.map(event=><li key={event.id}>
      <time>{new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(event.created_at*1000)}</time>{' '}
      {event.actor_id&&<span>{event.actor_id} · </span>}
      {event.event_type==='status_changed'?t(`suggestions.status.${String(event.detail.status)}`):t(`suggestions.event.${event.event_type}`,event.event_type)}{' '}
      {typeof event.detail.reason==='string'?event.detail.reason:''}
    </li>)}</ol>)}
  </section>
}
