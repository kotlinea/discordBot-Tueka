import {useEffect,useMemo,useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {StarboardConfig,StarboardItem,Resource} from '../../../types'
import {request,encodeBody} from '../../../api'
import {ResourceSelect} from '../../../components/ResourcePicker'
import {useSettingsDraft} from '../../../components/forms/useSettingsDraft'
import {useSaveMutation} from '../../../components/forms/useSaveMutation'
import {useUnsavedChanges} from '../../../components/forms/useUnsavedChanges'
import {EditNotice} from '../../../components/forms/EditNotice'
import {Failure} from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

type Draft=StarboardConfig&{revision:number}
export function BoardEditor({guildId,item,enabled,channels,onBusy,onCreated}:{guildId:string;item?:StarboardItem;enabled:boolean;channels:Resource[];onBusy:(value:boolean)=>void;onCreated:(item:StarboardItem)=>void}){
  const {t}=useTranslation(['starboard','common']);const qc=useQueryClient()
  const initial=useMemo<Draft>(()=>({name:'',enabled:false,target_channel_id:'',source_channel_ids:[],excluded_channel_ids:[],emoji:'⭐',threshold:3,retention_days:30,revision:1}),[])
  const source=useMemo(()=>item?{...item.config,revision:item.revision}:undefined,[item])
  const [extraSource,setExtraSource]=useState(''),[extraExcluded,setExtraExcluded]=useState('')
  const [requestKey,setRequestKey]=useState(()=>crypto.randomUUID())
  const extraDirty=Boolean(extraSource||extraExcluded)
  const draft=useSettingsDraft(source,initial,`${guildId}:${item?.id??'new'}`,extraDirty);const value=draft.draft
  const save=useSaveMutation({mutationFn:()=>{
    const {revision,...config}=value
    return item?request('PUT /api/v1/guilds/{guild_id}/starboard/boards/{board_id}',`/guilds/${guildId}/starboard/boards/${item.id}`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/starboard/boards/{board_id}',{config,revision})}):request('POST /api/v1/guilds/{guild_id}/starboard/boards',`/guilds/${guildId}/starboard/boards`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/starboard/boards',{config,request_key:requestKey})})
  },onSuccess:async result=>{draft.accept({...result.config,revision:result.revision});await Promise.all([qc.invalidateQueries({queryKey:['starboards',guildId]}),qc.invalidateQueries({queryKey:['starboardRecords',guildId]})]);if(!item)onCreated(result)}})
  useUnsavedChanges(draft.dirty,save.isPending)
  useEffect(()=>{onBusy(draft.dirty||save.isPending);return()=>onBusy(false)},[draft.dirty,save.isPending,onBusy])
  const change=<K extends keyof Draft>(key:K,next:Draft[K])=>draft.setDraft({...value,[key]:next})
  const add=(key:'source_channel_ids'|'excluded_channel_ids',text:string,clear:()=>void)=>{change(key,[...new Set([...(value[key]??[]),text.trim()])]);clear()}
  return <form className={s.applicationSection} aria-label={item?`${t('starboard.edit')} #${item.id}`:t('starboard.create')} onSubmit={e=>{e.preventDefault();if(!extraDirty)save.mutate()}}><h2>{item?`${t('starboard.edit')} #${item.id}`:t('starboard.create')}</h2>
    <fieldset disabled={!enabled||save.isPending}>
      <label className={s.field}>{t('starboard.name')}<input required maxLength={80} value={value.name} onChange={e=>change('name',e.target.value)}/></label>
      <label><input type="checkbox" checked={value.enabled} onChange={e=>change('enabled',e.target.checked)}/>{t('starboard.boardEnabled')}</label><p>{t('starboard.boardOff')}</p>
      <ResourceSelect label={t('starboard.target')} items={channels.filter(c=>[0,5,10,11,12].includes(c.type??-1))} value={value.target_channel_id} onChange={v=>change('target_channel_id',String(v??''))}/>
      <ResourceSelect label={t('starboard.sources')} items={channels} multiple value={value.source_channel_ids} onChange={v=>change('source_channel_ids',v as string[])}/>
      <label className={s.field}>{t('starboard.extraSource')}<input inputMode="numeric" maxLength={22} value={extraSource} onChange={e=>setExtraSource(e.target.value)}/></label><button type="button" aria-label={`${t('starboard.add')} · ${t('starboard.extraSource')}`} disabled={!/^[0-9]+$/.test(extraSource)||(value.source_channel_ids?.length??0)>=25} onClick={()=>add('source_channel_ids',extraSource,()=>setExtraSource(''))}>{t('starboard.add')}</button>
      <ResourceSelect label={t('starboard.excluded')} items={channels} multiple value={value.excluded_channel_ids} onChange={v=>change('excluded_channel_ids',v as string[])}/>
      <label className={s.field}>{t('starboard.extraExcluded')}<input inputMode="numeric" maxLength={22} value={extraExcluded} onChange={e=>setExtraExcluded(e.target.value)}/></label><button type="button" aria-label={`${t('starboard.add')} · ${t('starboard.extraExcluded')}`} disabled={!/^[0-9]+$/.test(extraExcluded)||(value.excluded_channel_ids?.length??0)>=25} onClick={()=>add('excluded_channel_ids',extraExcluded,()=>setExtraExcluded(''))}>{t('starboard.add')}</button>
      <label className={s.field}>{t('starboard.emoji')}<input required maxLength={80} value={value.emoji} onChange={e=>change('emoji',e.target.value)}/><small>{t('starboard.emojiHelp')}</small></label>
      <label className={s.field}>{t('starboard.threshold')}<input type="number" required min={1} max={100} value={value.threshold} onChange={e=>change('threshold',Number(e.target.value))}/></label>
      <label className={s.field}>{t('starboard.retention')}<input type="number" required min={1} max={365} value={value.retention_days} onChange={e=>change('retention_days',Number(e.target.value))}/><small>{t('starboard.retentionHelp')}</small></label>
    </fieldset><EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>{save.error&&<><Failure error={save.error}/><button type="button" disabled={save.isPending} onClick={()=>void qc.invalidateQueries({queryKey:['starboards',guildId]})}>{t('starboard.refresh')}</button></>}
    <button disabled={!enabled||!draft.dirty||extraDirty||save.isPending||!value.name.trim()||!value.target_channel_id||!value.source_channel_ids.length}>{t('common.save',{ns:'common'})}</button><button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();setExtraSource('');setExtraExcluded('');if(!item)setRequestKey(crypto.randomUUID());save.reset()}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}
