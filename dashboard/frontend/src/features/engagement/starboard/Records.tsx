import {useEffect,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {StarboardItem} from '../../../types'
import {request,encodeBody} from '../../../api'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {Failure,Loading} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function Records({guildId,board,enabled,busy,onBusy}:{guildId:string;board:StarboardItem;enabled:boolean;busy:boolean;onBusy:(value:boolean)=>void}){
  const {t,i18n}=useTranslation('starboard');const qc=useQueryClient();const [before,setBefore]=useState<number|undefined>()
  const base=`/guilds/${guildId}/starboard/boards/${board.id}`
  const query=useQuery({queryKey:['starboardRecords',guildId,board.id,before],queryFn:async()=>{
    const [items,history]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/entries',base+`/entries${before?`?before=${before}`:''}`),request('GET /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/history',base+'/history')]);return {...items,history}
  }})
  const retry=useSaveMutation({mutationFn:({id,source}:{id:number;source:boolean})=>source?request('POST /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/source-jobs/{job_id}/retry',base+`/source-jobs/${id}/retry`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/source-jobs/{job_id}/retry',{revision:board.revision})}):request('POST /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/delivery/{job_id}/retry',base+`/delivery/${id}/retry`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/starboard/boards/{board_id}/delivery/{job_id}/retry',{revision:board.revision})}),onSuccess:()=>qc.invalidateQueries({queryKey:['starboardRecords',guildId]})})
  useEffect(()=>{onBusy(retry.isPending);return()=>onBusy(false)},[retry.isPending,onBusy])
  if(query.isLoading&&!query.data)return <Loading/>
  if(query.error&&!query.data)return <Failure error={query.error} retry={()=>void query.refetch()}/>
  const rows=query.data?.items??[],history=query.data?.history
  const disabled=!enabled||busy||retry.isPending||Boolean(query.error)
  const date=(value:number)=>new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(value*1000)
  return <section className={s.applicationSection} aria-label={t('starboard.records')}><h2>{t('starboard.records')}</h2>
    {query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}{retry.error&&<Failure error={retry.error}/>}
    {!rows.length&&<p>{t('starboard.noRecords')}</p>}
    {rows.map(item=><article key={item.id} className={s.applicationSection}><h3>#{item.id} · {item.score} · {t(item.desired?'starboard.eligible':'starboard.below')}</h3><p style={{overflowWrap:'anywhere',whiteSpace:'pre-wrap'}}>{item.snapshot.content}</p><a href={`https://discord.com/channels/${guildId}/${item.source_channel_id}/${item.source_message_id}`} target="_blank" rel="noreferrer">{t('starboard.source')}</a><p>{date(item.expires_at)}</p></article>)}
    {before&&<button disabled={busy||retry.isPending} onClick={()=>setBefore(undefined)}>{t('starboard.latest')}</button>}{rows.length===50&&<button disabled={busy||retry.isPending} onClick={()=>setBefore(rows[rows.length-1].id)}>{t('starboard.older')}</button>}
    <h2>{t('starboard.history')}</h2>
    <ul>{history?.publications.map(publication=><li key={publication.id}>#{publication.entry_id} · {publication.removed?t('starboard.withdrawn'):publication.message_id?<a href={`https://discord.com/channels/${guildId}/${publication.target_channel_id}/${publication.message_id}`} target="_blank" rel="noreferrer">{t('starboard.publication')}</a>:t('starboard.uncertain')}</li>)}</ul>
    <ul aria-label={t('starboard.history')}>{history?.delivery.map(job=><li key={job.id}>#{job.id} · {t(`starboard.status.${job.status}`,{defaultValue:job.status})} {job.last_error}{job.status==='failed'&&<button disabled={disabled} onClick={()=>retry.mutate({id:job.id,source:false})}>{t('starboard.retry')} #{job.id}</button>}</li>)}</ul>
    <h3>{t('starboard.sourceJobs')}</h3><ul aria-label={t('starboard.sourceJobs')}>{history?.source_fetches.map(job=><li key={job.id}>#{job.id} · {t(`starboard.status.${job.status}`,{defaultValue:job.status})} {job.last_error}{job.retry_actor_id&&<span> · {job.retry_actor_id}</span>}{job.status==='failed'&&<button disabled={disabled} onClick={()=>retry.mutate({id:job.id,source:true})}>{t('starboard.retry')} #{job.id}</button>}</li>)}</ul>
    <ol>{history?.events.map(event=><li key={event.id}>{date(event.created_at)} · {t(`starboard.event.${event.event_type}`,{defaultValue:event.event_type})}{event.actor_id!=='0'&&<span> · {event.actor_id}</span>}</li>)}</ol>
  </section>
}
