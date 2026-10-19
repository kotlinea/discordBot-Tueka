import {useState} from 'react'
import {useParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import {request} from '../../../api'
import type {SuggestionItem,SuggestionSettings} from '../../../types'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {Failure,Loading} from '../../../components/Feedback'
import {SuggestionReview} from './Review'
import {LabelsEditor,MergeEditor} from './RoadmapEditors'
import s from '../../../styles/App.module.css'

const states=['pending','reviewing','approved','implemented','rejected','merged','delivery_failed'] as const
export default function Roadmap(){
  const {guildId=''}=useParams();const {t}=useTranslation(['suggestions','common'])
  const [category,setCategory]=useState(''),[tag,setTag]=useState(''),[status,setStatus]=useState(''),[before,setBefore]=useState<number|undefined>()
  const [selected,setSelected]=useState<SuggestionItem|null>(null)
  const [labelsBusy,setLabelsBusy]=useState(false),[mergeBusy,setMergeBusy]=useState(false),[reviewBusy,setReviewBusy]=useState(false)
  const settings=useQuery({queryKey:['suggestionsSettings',guildId],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/suggestions/settings',`/guilds/${guildId}/suggestions/settings`)})
  const items=useQuery({queryKey:['suggestionsItems',guildId,'roadmap',category,tag,status,before],queryFn:()=>{
    const params=new URLSearchParams({limit:'50'});if(category)params.set('category',category);if(tag)params.set('tag',tag);if(status)params.set('status',status);if(before)params.set('before',String(before))
    return request('GET /api/v1/guilds/{guild_id}/suggestions/items',`/guilds/${guildId}/suggestions/items?${params}`)
  }})
  const detail=useQuery({queryKey:['roadmapDetail',guildId,selected?.id],enabled:Boolean(selected),queryFn:()=>request('GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}',`/guilds/${guildId}/suggestions/items/${selected!.id}`)})
  const open=useSaveMutation({mutationFn:(id:number)=>request('GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}',`/guilds/${guildId}/suggestions/items/${id}`),onSuccess:setSelected})
  const busy=labelsBusy||mergeBusy||reviewBusy||open.isPending
  if(settings.isLoading||items.isLoading)return <Loading/>
  if(settings.error&&!settings.data||items.error&&!items.data)return <main className={s.page}><Failure error={settings.error||items.error} retry={()=>{void settings.refetch();void items.refetch()}}/></main>
  const enabled=Boolean(settings.data?.enabled)&&!settings.error&&!items.error,config=settings.data!.settings as SuggestionSettings,rows=items.data?.items??[]
  const current=detail.data?.id===selected?.id?detail.data:selected
  const choose=(item:SuggestionItem)=>{if(!busy)setSelected(item)}
  return <main className={s.page}><h1>{t('suggestions.roadmap')}</h1><p>{t('suggestions.boardHelp',{count:rows.length})}</p>{!enabled&&<p>{t('suggestions.boardDisabled')}</p>}
    {(settings.error||items.error)&&<Failure error={settings.error||items.error} retry={()=>{void settings.refetch();void items.refetch()}}/>}
    <fieldset disabled={busy}><legend>{t('suggestions.filters')}</legend>
      <label className={s.field}>{t('suggestions.category')}<select value={category} onChange={e=>{setCategory(e.target.value);setBefore(undefined)}}><option value="">{t('suggestions.all')}</option>{(config.categories??[]).map(v=><option key={v} value={v}>{v}</option>)}</select></label>
      <label className={s.field}>{t('suggestions.tags')}<select value={tag} onChange={e=>{setTag(e.target.value);setBefore(undefined)}}><option value="">{t('suggestions.all')}</option>{(config.tags??[]).map(v=><option key={v} value={v}>{v}</option>)}</select></label>
      <label className={s.field}>{t('suggestions.boardStatus')}<select value={status} onChange={e=>{setStatus(e.target.value);setBefore(undefined)}}><option value="">{t('suggestions.all')}</option>{states.map(v=><option key={v} value={v}>{t(`suggestions.status.${v}`)}</option>)}</select></label>
    </fieldset>{open.error&&<Failure error={open.error}/>}
    {current&&<section className={s.applicationSection} aria-label={t('suggestions.selectedSuggestion',{id:current.id})}><h2>#{current.id} · {t(`suggestions.status.${current.status}`)}</h2>
      <button disabled={busy} onClick={()=>setSelected(null)}>{t('suggestions.closeEditor')}</button>
      {detail.error&&<Failure error={detail.error} retry={()=>void detail.refetch()}/>}
      {Object.entries(current.answers).map(([key,value])=><p key={key} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{value}</p>)}
      {current.merged_into&&<button disabled={busy} onClick={()=>open.mutate(current.merged_into!)}>{t('suggestions.openCanonical',{id:current.merged_into})}</button>}
      <LabelsEditor key={`labels:${current.id}`} guildId={guildId} item={current} settings={config} enabled={enabled&&!mergeBusy&&!reviewBusy&&!detail.error} onBusy={setLabelsBusy}/>
      <MergeEditor key={`merge:${current.id}`} guildId={guildId} item={current} enabled={enabled&&!labelsBusy&&!reviewBusy&&!detail.error} onBusy={setMergeBusy}/>
      <SuggestionReview key={`review:${current.id}`} guildId={guildId} item={current} enabled={enabled&&!labelsBusy&&!mergeBusy&&!detail.error} onBusy={setReviewBusy}/>
    </section>}
    <div className={s.roadmapGrid}>{states.filter(v=>!status||status===v).map(state=><section key={state} className={s.roadmapColumn} aria-label={t(`suggestions.status.${state}`)}><h2>{t(`suggestions.status.${state}`)}</h2>
      {rows.filter(item=>item.status===state).map(item=><article key={item.id} className={s.applicationSection}><h3>#{item.id}</h3><p style={{overflowWrap:'anywhere'}}>{Object.values(item.answers).find(Boolean)}</p><p>{item.category} · {(item.tags??[]).join(' · ')}</p><p>👍 {item.upvotes} · 👎 {item.downvotes}</p><button disabled={busy} onClick={()=>choose(item)}>{t('suggestions.openSuggestion',{id:item.id})}</button></article>)}
    </section>)}</div>{!rows.length&&<p>{t('suggestions.empty')}</p>}
    {before&&<button disabled={busy} onClick={()=>setBefore(undefined)}>{t('suggestions.latest')}</button>}{rows.length===50&&<button disabled={busy} onClick={()=>setBefore(rows[rows.length-1].id)}>{t('suggestions.older')}</button>}</main>
}
