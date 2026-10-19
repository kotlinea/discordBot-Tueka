import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { ApplicationItem } from '../../../generated/api'
import type { FeatureScreenProps } from '../../contracts'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { Failure, Loading } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function ReviewItem({guildId,item,enabled}:{guildId:string;item:ApplicationItem;enabled:boolean}){
  const {t,i18n}=useTranslation(['applications','common']);const qc=useQueryClient()
  const [reason,setReason]=useState('');const [revision,setRevision]=useState<number|null>(null)
  const [history,setHistory]=useState(false)
  const events=useQuery({queryKey:['applicationEvents',guildId,item.id],enabled:history,queryFn:()=>request('GET /api/v1/guilds/{guild_id}/applications/items/{item_id}/events',`/guilds/${guildId}/applications/items/${item.id}/events`)})
  const save=useSaveMutation({mutationFn:(status:'reviewing'|'approved'|'rejected')=>request('POST /api/v1/guilds/{guild_id}/applications/items/{item_id}/review',`/guilds/${guildId}/applications/items/${item.id}/review`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/applications/items/{item_id}/review',{status,reason,revision:revision??item.revision})}),onSuccess:async()=>{setReason('');setRevision(null);await Promise.all([qc.invalidateQueries({queryKey:['applicationsItems',guildId]}),qc.invalidateQueries({queryKey:['applicationEvents',guildId,item.id]})])}})
  useUnsavedChanges(Boolean(reason),save.isPending)
  const open=['pending','reviewing'].includes(item.status)
  return <section className={s.applicationSection} aria-label={`#${item.id}`}><h2>#{item.id} {item.snapshot.title}</h2>
    <p>{t('applications.author')}: {item.author_id} · {t(`applications.status.${item.status}`)}</p>
    <dl>{item.snapshot.fields.map(field=><div key={field.key}><dt>{field.label}</dt><dd style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{item.answers[field.key]||'—'}</dd></div>)}</dl>
    {(open||reason)&&<><label className={s.field}>{t('applications.reason')}<textarea maxLength={1000} value={reason} disabled={!enabled||save.isPending||!open} onChange={e=>{if(revision===null)setRevision(item.revision);setReason(e.target.value)}}/></label>
      {(['reviewing','approved','rejected'] as const).map(status=><button key={status} disabled={!enabled||!open||status===item.status||!reason.trim()||save.isPending} onClick={()=>save.mutate(status)}>{t(`applications.status.${status}`)}</button>)}
      <button disabled={!reason||save.isPending} onClick={()=>{setReason('');setRevision(null);save.reset()}}>{t('common.discard',{ns:'common'})}</button></>}
    {save.error&&<Failure error={save.error}/>}
    <button aria-expanded={history} onClick={()=>setHistory(!history)}>{t('applications.history')}</button>
    {history&&(events.isLoading?<Loading/>:events.error?<Failure error={events.error} retry={()=>void events.refetch()}/>:<ol>{events.data?.items.map(event=><li key={event.id}><time dateTime={new Date(event.created_at*1000).toISOString()}>{new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(event.created_at*1000)}</time>{' · '}{event.actor_id} · {t(`applications.status.${event.event_type}`,{defaultValue:event.event_type})} · {event.reason}</li>)}</ol>)}
  </section>
}

export default function Review({features}:FeatureScreenProps){
  const {guildId=''}=useParams();const {t}=useTranslation('applications')
  const enabled=Boolean(features.find(f=>f.id==='applications')?.enabled)
  const [before,setBefore]=useState<number|undefined>()
  const query=useQuery({queryKey:['applicationsItems',guildId,before],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/applications/items',`/guilds/${guildId}/applications/items${before?`?before=${before}`:''}`)})
  if(query.isLoading)return <Loading/>
  if(query.error)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  const items=query.data?.items??[]
  return <main className={s.page}><h1>{t('applications.review')}</h1><p>{t('applications.private')}</p>{!enabled&&<p>{t('applications.disabled')}</p>}
    {!items.length&&<p>{t('applications.emptyItems')}</p>}{items.map(item=><ReviewItem key={item.id} guildId={guildId} item={item} enabled={enabled}/>)}
    {before&&<button onClick={()=>setBefore(undefined)}>{t('applications.latest')}</button>}
    {items.length===50&&<button onClick={()=>setBefore(items[items.length-1].id)}>{t('applications.older')}</button>}</main>
}
