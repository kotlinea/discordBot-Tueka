import {useEffect,useMemo} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {GiveawayItem} from '../../../types'
import {request,encodeBody} from '../../../api'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {useUnsavedChanges} from '../../../components/forms/useUnsavedChanges'
import {useSettingsDraft} from '../../../components/forms/useSettingsDraft'
import {EditNotice} from '../../../components/forms/EditNotice'
import {Failure,Loading} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

type Action='launch'|'close'|'cancel'|'reroll'
export function History({guildId,item,enabled,busy,onBusy}:{guildId:string;item:GiveawayItem;enabled:boolean;busy:boolean;onBusy:(value:boolean)=>void}){
  const {t,i18n}=useTranslation('giveaways');const qc=useQueryClient(),base=`/guilds/${guildId}/giveaways/${item.id}`
  const source=useMemo(()=>({reason:'',revision:item.revision}),[item.revision])
  const draft=useSettingsDraft(source,source,`${guildId}:${item.id}`),reason=draft.draft.reason
  const query=useQuery({queryKey:['giveawayHistory',guildId,item.id,item.revision],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/giveaways/{item_id}/history',base+'/history'),refetchInterval:q=>q.state.data&&(q.state.data.delivery.some(j=>['pending','retry','processing'].includes(j.status))||q.state.data.draw_jobs.some(j=>['retry','processing'].includes(j.status)))?5000:false})
  const save=useSaveMutation({mutationFn:async(action:Action|{id:number;draw:boolean})=>{
    if(typeof action==='object')return request('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/jobs/{job_id}/retry',base+`/jobs/${action.id}/retry?draw=${action.draw}`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/jobs/{job_id}/retry',{revision:item.revision})})
    if(action==='launch')return request('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/launch',base+'/launch',{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/launch',{revision:item.revision})})
    if(action==='close')return request('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/close',base+'/close',{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/close',{revision:draft.draft.revision,reason})})
    if(action==='cancel')return request('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/cancel',base+'/cancel',{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/cancel',{revision:draft.draft.revision,reason})})
    return request('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/reroll',base+'/reroll',{body:encodeBody('POST /api/v1/guilds/{guild_id}/giveaways/{item_id}/reroll',{revision:draft.draft.revision,reason})})
  },onSuccess:async()=>{draft.accept({reason:'',revision:item.revision});await Promise.all([qc.invalidateQueries({queryKey:['giveaways',guildId]}),qc.invalidateQueries({queryKey:['giveawayHistory',guildId,item.id]})])}})
  useUnsavedChanges(draft.dirty,save.isPending)
  useEffect(()=>{onBusy(draft.dirty||save.isPending);return()=>onBusy(false)},[draft.dirty,save.isPending,onBusy])
  const date=(v:number)=>new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(v*1000)
  const disabled=!enabled||busy||save.isPending||Boolean(query.error)
  const apply=(action:Action)=>{if(window.confirm(t('giveaways.confirm')))save.mutate(action)}
  return <section className={s.applicationSection} aria-label={t('giveaways.history')}><h2>{t('giveaways.history')}</h2><p>{t(`giveaways.status.${item.status}`)} · {date(item.ends_at)}</p>
    {item.message_id?<a href={`https://discord.com/channels/${guildId}/${item.config.channel_id}/${item.message_id}`} target="_blank" rel="noreferrer">{t('giveaways.receipt')}</a>:<p>{t(item.delivery_started?'giveaways.uncertain':'giveaways.awaiting')}</p>}
    {query.isLoading&&!query.data&&<Loading/>}{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}{save.error&&<Failure error={save.error}/>}
    <button disabled={save.isPending} onClick={()=>void Promise.all([qc.invalidateQueries({queryKey:['giveaways',guildId]}),query.refetch()])}>{t('giveaways.refresh')}</button>
    {item.status==='draft'&&<button disabled={disabled} onClick={()=>apply('launch')}>{t('giveaways.launch')}</button>}
    {item.status!=='cancelled'&&<label className={s.field}>{t('giveaways.reason')}<textarea disabled={disabled} maxLength={500} value={reason} onChange={e=>draft.setDraft({...draft.draft,reason:e.target.value})}/></label>}
    <EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>
    {draft.dirty&&<button disabled={save.isPending} onClick={()=>{draft.discard();save.reset()}}>{t('common.discard',{ns:'common'})}</button>}
    {item.status==='open'&&<button disabled={disabled||!reason.trim()} onClick={()=>apply('close')}>{t('giveaways.close')}</button>}
    {['draft','open','closing'].includes(item.status)&&<button disabled={disabled||!reason.trim()} onClick={()=>apply('cancel')}>{t('giveaways.cancel')}</button>}
    {item.status==='closed'&&item.config.kind==='giveaway'&&<button disabled={disabled||!reason.trim()||item.round_number>=20} onClick={()=>apply('reroll')}>{t('giveaways.reroll')}</button>}
    <h3>{t('giveaways.draws')}</h3>{!query.data?.draws.length&&<p>{t('giveaways.noDraws')}</p>}
    {query.data?.draws.map(draw=><article key={draw.id}><h4>{t('giveaways.round')} {draw.round_number}</h4><p>{t('giveaways.eligible')}: {draw.candidates.length} · {t('giveaways.excluded')}: {draw.excluded_count}</p><p>{t('giveaways.selected')}: {draw.winners.join(', ')||'—'}</p><p style={{overflowWrap:'anywhere'}}>{draw.reason} · {draw.actor_id} · {date(draw.created_at)}</p><code style={{overflowWrap:'anywhere'}}>{draw.candidate_hash}</code></article>)}
    {(['delivery','draw_jobs'] as const).map(kind=><div key={kind}><h3>{t(kind==='delivery'?'giveaways.delivery':'giveaways.drawJobs')}</h3><ul>{query.data?.[kind].map(job=><li key={job.id}>#{job.id} · {t(`giveaways.status.${job.status}`,{defaultValue:job.status})} {job.last_error}{job.status==='failed'&&<button disabled={disabled||Boolean(reason)} onClick={()=>save.mutate({id:job.id,draw:kind==='draw_jobs'})}>{t('giveaways.retry')} #{job.id}</button>}</li>)}</ul></div>)}
    <details><summary>{t('giveaways.entries')}</summary><ul>{query.data?.entries.map(entry=><li key={entry.user_id}>{entry.user_id} · {t(entry.active?'giveaways.active':'giveaways.withdrawn')}</li>)}</ul></details>
    <ol>{query.data?.events.map(event=><li style={{overflowWrap:'anywhere'}} key={event.id}>{date(event.created_at)} · {t(`giveaways.audit.${event.event_type}`,{defaultValue:event.event_type})} · {event.actor_id}{typeof event.detail.reason==='string'&&` · ${event.detail.reason}`}</li>)}</ol>
  </section>
}
