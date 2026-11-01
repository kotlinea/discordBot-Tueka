import { useCallback, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody, isTransientQueryError } from '../../../api'
import type { PollItem, Operations, Resource } from '../../../generated/api'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { Failure, Loading } from '../../../components/Feedback'
import Editor from './Editor'
import s from '../../../styles/App.module.css'
type PollAction = Operations['POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/actions']['body']['action']

function Card({guildId,item,permissions,enabled,channels,roles,refresh,onBusy}:{guildId:string;item:PollItem;permissions:string[];enabled:boolean;channels:Resource[];roles:Resource[];refresh:()=>Promise<void>;onBusy:(id:number,busy:boolean)=>void}){
 const {t}=useTranslation('polls');const [editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[target,setTarget]=useState(''),[deadline,setDeadline]=useState('')
 const [historyOpen,setHistoryOpen]=useState(false)
 const [removeUser,setRemoveUser]=useState('')
 const history=useQuery({queryKey:['pollHistory',guildId,item.id],enabled:historyOpen,queryFn:()=>request('GET /api/v1/guilds/{guild_id}/polls/items/{poll_id}/history',`/guilds/${guildId}/polls/items/${item.id}/history`)})
 const action=useSaveMutation({mutationFn:(kind:PollAction)=>request('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/actions',`/guilds/${guildId}/polls/items/${item.id}/actions`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/actions',{action:kind,revision:item.revision,request_key:crypto.randomUUID(),channel_id:target||null,closes_at:deadline?Math.floor(new Date(deadline).getTime()/1000):null})}),onSuccess:refresh})
 const exporting=useSaveMutation({mutationFn:(format:string)=>request('GET /api/v1/guilds/{guild_id}/polls/items/{poll_id}/export',`/guilds/${guildId}/polls/items/${item.id}/export?format=${format}`).then(blob=>{const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`poll-${item.id}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})})
 const retry=useSaveMutation({mutationFn:(job:number)=>request('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/delivery/{job_id}/retry',`/guilds/${guildId}/polls/items/${item.id}/delivery/${job}/retry`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/delivery/{job_id}/retry',{revision:item.revision})}),onSuccess:refresh})
 const remove=useSaveMutation({mutationFn:()=>request('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/votes/remove',`/guilds/${guildId}/polls/items/${item.id}/votes/remove`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/polls/items/{poll_id}/votes/remove',{revision:item.revision,user_id:removeUser})}),onSuccess:refresh})
 const editorBusy=useCallback((dirty:boolean)=>{setBusy(dirty);onBusy(item.id,dirty)},[onBusy,item.id])
 const manage=permissions.includes('manage'),blocked=busy||action.isPending||retry.isPending||remove.isPending
 const perform=(kind:PollAction)=>{if(kind!=='delete'||confirm(t('polls.deleteConfirm')))action.mutate(kind)}
 return <section className={s.applicationSection}>
  <h2 style={{overflowWrap:'anywhere'}}>#{item.id} · {item.config.question}</h2><p>{t(`polls.status.${item.status}`,{defaultValue:item.status})} · {t(`polls.modes.${item.config.mode??'anonymous'}`)}</p>
  <p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{item.config.description}</p>
  {item.closes_at&&<p>{t('polls.deadline')}: {new Date(item.closes_at*1000).toLocaleString()}</p>}
  <ol>{item.config.options.map((option,index)=><li key={index} style={{overflowWrap:'anywhere'}}>{option}{item.counts&&` · ${item.counts[index]}`}{item.weighted_counts&&<>{` (${t('polls.weight')}: ${item.weighted_counts[index]})`} <meter min={0} max={Math.max(1,...item.weighted_counts)} value={item.weighted_counts[index]} aria-label={option}/></>}{item.ranking&&` · #${item.ranking[index]}`}</li>)}</ol>
  {item.total!==undefined&&item.total!==null&&<p>{t('polls.total')}: {item.total} · {t('polls.selections')}: {item.selections}</p>}
  {item.participants&&<details><summary>{t('polls.disclosure.participants')}</summary><p>{item.participants.join(', ')}</p></details>}
  {item.ballots&&<details><summary>{t('polls.disclosure.ballots')}</summary><ul>{item.ballots.map(ballot=><li key={ballot.user_id}>{ballot.user_id} · {ballot.choices.map(n=>n+1).join(', ')} · {t('polls.weight')}: {ballot.weight}</li>)}</ul></details>}
  {manage&&<fieldset disabled={blocked}>
   {item.status==='draft'&&<button disabled={!enabled} onClick={()=>perform('launch')}>{t('polls.launch')}</button>}
   {item.status==='open'&&<button onClick={()=>perform('close')}>{t('polls.close')}</button>}
   {item.status==='closed'&&<><label className={s.field}>{t('polls.newDeadline')}<input type="datetime-local" value={deadline} onChange={e=>setDeadline(e.target.value)}/></label><button disabled={!enabled} onClick={()=>perform('reopen')}>{t('polls.reopen')}</button></>}
   {(item.status==='draft'||item.status==='scheduled')&&<button onClick={()=>perform('cancel')}>{t('polls.cancel')}</button>}
   {item.message_id&&['open','closed'].includes(item.status)&&<><label className={s.field}>{t('polls.moveChannel')}<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">—</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><button disabled={!enabled||!target} onClick={()=>perform('move')}>{t('polls.move')}</button></>}
   <button disabled={!enabled} onClick={()=>perform('copy')}>{t('polls.copy')}</button>
   {item.status!=='deleted'&&<button onClick={()=>perform('delete')}>{t('polls.delete')}</button>}
   {!editing&&<button disabled={!enabled||['deleted','cancelled','publishing'].includes(item.status)} onClick={()=>setEditing(true)}>{t('polls.edit')}</button>}
  </fieldset>}
  {['csv','json'].map(format=><button key={format} disabled={exporting.isPending} onClick={()=>exporting.mutate(format)}>{t('polls.export')} {format.toUpperCase()}</button>)}
  {permissions.includes('manage_votes')&&<fieldset disabled={blocked}><label className={s.field}>{t('polls.removeVoteUser')}<input inputMode="numeric" value={removeUser} onChange={e=>setRemoveUser(e.target.value)}/></label><button disabled={!removeUser} onClick={()=>{if(confirm(t('polls.removeVoteConfirm')))remove.mutate()}}>{t('polls.removeVote')}</button></fieldset>}
  <button disabled={blocked} aria-expanded={historyOpen} onClick={()=>setHistoryOpen(!historyOpen)}>{t('polls.history')}</button>
  {historyOpen&&history.isLoading&&<Loading/>}{historyOpen&&history.error&&<Failure error={history.error} retry={()=>void history.refetch()}/>}
  {historyOpen&&history.data&&<><ol>{history.data.events.map(e=><li key={e.id}>{new Date(e.created_at*1000).toLocaleString()} · {e.event_type} · {e.actor_id??'—'}</li>)}</ol><ul>{history.data.delivery.map(job=><li key={job.id}>#{job.id} · {job.action} · {t(`polls.status.${job.status}`,{defaultValue:job.status})} · {job.last_error??''}{manage&&job.status==='failed'&&<button disabled={!enabled||blocked} onClick={()=>retry.mutate(job.id)}>{t('polls.retry')}</button>}</li>)}</ul></>}
  {action.error&&<Failure error={action.error}/>} {exporting.error&&<Failure error={exporting.error}/>}
  {retry.error&&<Failure error={retry.error}/>} {remove.error&&<Failure error={remove.error}/>}
  {editing&&<Editor guildId={guildId} item={item} enabled={enabled&&manage&&!action.isPending} channels={channels} roles={roles} onSaved={refresh} onBusy={editorBusy}/>}
 </section>
}

export default function Polls(){
 const {guildId=''}=useParams();const {t}=useTranslation('polls'),qc=useQueryClient()
 const [before,setBefore]=useState<number|undefined>(),[editors,setEditors]=useState<Record<number,boolean>>({})
 const onBusy=useCallback((id:number,busy:boolean)=>setEditors(old=>old[id]===busy?old:{...old,[id]:busy}),[])
 const createBusy=useCallback((busy:boolean)=>onBusy(0,busy),[onBusy])
 const query=useQuery({queryKey:['pollItems',guildId,before],queryFn:async()=>{
  const [caps,items,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/polls/capabilities',`/guilds/${guildId}/polls/capabilities`),request('GET /api/v1/guilds/{guild_id}/polls/items',`/guilds/${guildId}/polls/items${before?`?before=${before}`:''}`),request('GET /api/v1/guilds/{guild_id}/polls/resources',`/guilds/${guildId}/polls/resources`)])
  return {caps,items:items.items,channels:resources.channels.filter(c=>c.type===0||c.type===5),roles:resources.roles}
 }})
 const refresh=useCallback(async()=>{await Promise.all([qc.invalidateQueries({queryKey:['pollItems',guildId]}),qc.invalidateQueries({queryKey:['pollHistory',guildId]})])},[qc,guildId])
 if(query.isLoading)return <Loading/>
 if(query.error&&(!query.data||!isTransientQueryError(query.error)))return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
 const data=query.data!;const busy=Object.values(editors).some(Boolean)
 return <main className={s.page}><h1>{t('polls.title')}</h1><p>{t('polls.help')}</p>{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>} {!data.caps.enabled&&<p>{t('polls.disabled')}</p>}
  {data.caps.permissions.includes('manage')&&<Editor guildId={guildId} enabled={data.caps.enabled&&!query.error} channels={data.channels} roles={data.roles} onSaved={refresh} onBusy={createBusy}/>}
  {!data.items.length&&<p>{t('polls.empty')}</p>}
  {data.items.map(item=><Card key={item.id} guildId={guildId} item={item} permissions={query.error?[]:data.caps.permissions} enabled={data.caps.enabled&&!query.error} channels={data.channels} roles={data.roles} refresh={refresh} onBusy={onBusy}/>)}
  {before&&<button disabled={busy} onClick={()=>setBefore(undefined)}>{t('polls.latest')}</button>}{data.items.length===50&&<button disabled={busy} onClick={()=>setBefore(data.items.at(-1)!.id)}>{t('polls.older')}</button>}
 </main>
}
