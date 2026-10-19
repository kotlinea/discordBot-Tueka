import {useEffect,useMemo,useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import {request,encodeBody} from '../../../api'
import type {SuggestionItem,SuggestionSettings} from '../../../types'
import {useSettingsDraft} from '../../../components/forms/useSettingsDraft'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {useUnsavedChanges} from '../../../components/forms/useUnsavedChanges'
import {EditNotice} from '../../../components/forms/EditNotice'
import {Failure} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function LabelsEditor({guildId,item,settings,enabled,onBusy}:{guildId:string;item:SuggestionItem;settings:SuggestionSettings;enabled:boolean;onBusy:(busy:boolean)=>void}){
  const {t}=useTranslation(['suggestions','common']);const qc=useQueryClient()
  const source=useMemo(()=>({category:item.category??'',tags:item.tags??[],revision:item.revision}),[item])
  const draft=useSettingsDraft(source,source,`${guildId}:${item.id}`)
  const value=draft.draft
  const save=useSaveMutation({mutationFn:()=>request('POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/labels',`/guilds/${guildId}/suggestions/items/${item.id}/labels`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/labels',value)}),onSuccess:async result=>{
    draft.accept({category:result.category??'',tags:result.tags??[],revision:result.revision})
    await Promise.all([qc.invalidateQueries({queryKey:['suggestionsItems',guildId]}),qc.invalidateQueries({queryKey:['roadmapDetail',guildId,item.id]}),qc.invalidateQueries({queryKey:['suggestionEvents',guildId,item.id]})])
  }})
  useUnsavedChanges(draft.dirty,save.isPending)
  useEffect(()=>{onBusy(draft.dirty||save.isPending);return()=>onBusy(false)},[draft.dirty,save.isPending,onBusy])
  const categories=[...new Set([...(settings.categories??[]),...(value.category?[value.category]:[])])]
  const tags=[...new Set([...(settings.tags??[]),...value.tags])]
  return <form aria-label={t('suggestions.editLabels')} onSubmit={e=>{e.preventDefault();save.mutate()}}><h3>{t('suggestions.editLabels')}</h3><fieldset disabled={!enabled||save.isPending}>
    <label className={s.field}>{t('suggestions.category')}<select value={value.category} onChange={e=>draft.setDraft({...value,category:e.target.value})}><option value="">{t('suggestions.notSet')}</option>{categories.map(name=><option key={name} value={name}>{name}</option>)}</select></label>
    <fieldset><legend>{t('suggestions.tags')}</legend>{tags.map(name=><label key={name}><input type="checkbox" checked={value.tags.includes(name)} onChange={e=>draft.setDraft({...value,tags:e.target.checked?[...value.tags,name]:value.tags.filter(v=>v!==name)})}/>{name}</label>)}</fieldset>
  </fieldset><EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>{save.error&&<Failure error={save.error}/>}
    <button disabled={!enabled||!draft.dirty||save.isPending}>{t('common.save',{ns:'common'})}</button><button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();save.reset()}}>{t('common.discard',{ns:'common'})}</button></form>
}

export function MergeEditor({guildId,item,enabled,onBusy}:{guildId:string;item:SuggestionItem;enabled:boolean;onBusy:(busy:boolean)=>void}){
  const {t}=useTranslation(['suggestions','common']);const qc=useQueryClient()
  const [targetId,setTargetId]=useState(''),[reason,setReason]=useState('')
  const [revision,setRevision]=useState<number|null>(null),[target,setTarget]=useState<SuggestionItem|null>(null)
  const lookup=useSaveMutation({mutationFn:()=>{setTarget(null);return request('GET /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}',`/guilds/${guildId}/suggestions/items/${Number(targetId)}`)},onSuccess:setTarget})
  const save=useSaveMutation({mutationFn:()=>{
    if(!target)throw new Error(t('suggestions.lookupTarget'))
    return request('POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/merge',`/guilds/${guildId}/suggestions/items/${item.id}/merge`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/merge',{target_id:target.id,target_revision:target.revision,revision:revision??item.revision,reason})})
  },onSuccess:async()=>{clear();await Promise.all([qc.invalidateQueries({queryKey:['suggestionsItems',guildId]}),qc.invalidateQueries({queryKey:['roadmapDetail',guildId]}),qc.invalidateQueries({queryKey:['suggestionEvents',guildId]})])}})
  const pending=lookup.isPending||save.isPending,dirty=Boolean(targetId||reason)
  useUnsavedChanges(dirty,pending)
  useEffect(()=>{onBusy(dirty||pending);return()=>onBusy(false)},[dirty,pending,onBusy])
  const capture=()=>{if(revision===null)setRevision(item.revision)}
  const clear=()=>{setTargetId('');setReason('');setRevision(null);setTarget(null);lookup.reset()}
  return <form aria-label={t('suggestions.merge')} onSubmit={e=>{e.preventDefault();save.mutate()}}><h3>{t('suggestions.merge')}</h3><p>{t('suggestions.mergeHelp')}</p>
    <fieldset disabled={!enabled||pending||item.status==='merged'}><label className={s.field}>{t('suggestions.mergeTarget')}<input type="number" min={1} value={targetId} onChange={e=>{capture();setTargetId(e.target.value);setTarget(null);lookup.reset();save.reset()}}/></label>
      <button type="button" disabled={!Number.isSafeInteger(Number(targetId))||Number(targetId)<=0||Number(targetId)===item.id} onClick={()=>lookup.mutate()}>{t('suggestions.lookupTarget')}</button>
      {target&&<p>#{target.id} · {t(`suggestions.status.${target.status}`)} · {Object.values(target.answers).find(Boolean)}</p>}
      <label className={s.field}>{t('suggestions.mergeReason')}<textarea required maxLength={1000} value={reason} onChange={e=>{capture();setReason(e.target.value)}}/></label>
    </fieldset>{(lookup.error||save.error)&&<Failure error={lookup.error||save.error}/>}
    <button disabled={!enabled||pending||!reason.trim()||!target||target.id===item.id||Boolean(target.merged_into)||target.status==='delivery_failed'||target.status==='merged'||item.status==='merged'}>{t('suggestions.merge')}</button><button type="button" disabled={pending||!dirty} onClick={()=>{clear();save.reset()}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}
