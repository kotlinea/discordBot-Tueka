import { useEffect, useMemo, useRef, useState } from 'react'
import * as Switch from '@radix-ui/react-switch'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, BookOpen, Lightbulb, Plus, Save, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

import { api } from './api'
import type { Feature, Resource, SuggestionFormField, SuggestionItem, SuggestionSettings } from './types'
import s from './styles/App.module.css'

type SettingsResponse = Pick<Feature, 'enabled'|'revision'|'missing_permissions'|'docs_path'> & {settings:SuggestionSettings}
const newField = (label:string):SuggestionFormField => ({key:`field_${Date.now()}`,label,placeholder:'',style:'short',required:false,min_length:0,max_length:500})

function Loading() { const {t}=useTranslation();return <div className={s.centerState} aria-live="polite"><span className={s.spinner}/><p>{t('common.loading')}</p></div> }
function Failure({error}:{error:unknown}) { const {t}=useTranslation();return <div className={s.failure} role="alert"><div><strong>{error instanceof Error?error.message:String(error)}</strong><p>{t('suggestions.checkInput')}</p></div></div> }
function SectionHead({title,description,actions}:{title:string;description:string;actions?:React.ReactNode}) { return <header className={s.sectionHead}><div><h1>{title}</h1><p>{description}</p></div>{actions}</header> }
function Status({active,children}:{active:boolean;children:React.ReactNode}) { return <span className={active?s.statusOn:s.statusOff}><span aria-hidden="true"/>{children}</span> }

function SingleResource({label,value,items,onChange}:{label:string;value:string|null;items:Resource[];onChange:(value:string|null)=>void}) {
  const {t}=useTranslation();return <label className={s.field}><span>{label}</span><select value={value||''} onChange={event=>onChange(event.target.value||null)}><option value="">{t('suggestions.notSet')}</option>{items.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><small>{t('suggestions.serverSelect')}</small></label>
}

function RolePicker({value,items,onChange}:{value:string[];items:Resource[];onChange:(value:string[])=>void}) {
  const {t}=useTranslation();const selected=new Set(value)
  return <fieldset className={s.resourcePicker}><legend>{t('suggestions.reviewRoles')}</legend><div className={s.resourcePickerActions}><button type="button" onClick={()=>onChange(items.map(item=>item.id))} disabled={!items.length||selected.size===items.length}>{t('suggestions.selectAll')}</button><button type="button" onClick={()=>onChange(items.map(item=>item.id).filter(id=>!selected.has(id)))} disabled={!items.length}>{t('suggestions.invert')}</button></div><div className={s.resourceOptions}>{items.map(item=><label key={item.id}><input type="checkbox" checked={selected.has(item.id)} onChange={()=>onChange(selected.has(item.id)?value.filter(id=>id!==item.id):[...value,item.id])}/><span>{item.name}</span></label>)}</div><small>{t('suggestions.selected',{count:selected.size})} {t('suggestions.reviewerHelp')}</small></fieldset>
}

export default function Suggestions() {
  const {guildId=''}=useParams(); const {t,i18n}=useTranslation(); const qc=useQueryClient()
  const query=useQuery({queryKey:['suggestionsSettings',guildId],queryFn:()=>api<SettingsResponse>(`/guilds/${guildId}/suggestions/settings`)})
  const resources=useQuery({queryKey:['resources',guildId],queryFn:()=>api<{channels:Resource[];roles:Resource[]}>(`/guilds/${guildId}/resources`)})
  const items=useQuery({queryKey:['suggestionsItems',guildId],queryFn:()=>api<{items:SuggestionItem[]}>(`/guilds/${guildId}/suggestions/items?limit=20`),refetchInterval:10000})
  const [draft,setDraft]=useState<SettingsResponse|null>(null)
  const previous=useRef<{guildId:string;data:SettingsResponse|undefined}>({guildId,data:undefined})
  useEffect(()=>{
    const old=previous.current
    if(query.data)setDraft(current=>old.guildId!==guildId||!current||JSON.stringify(current)===JSON.stringify(old.data)?structuredClone(query.data!):current)
    else if(old.guildId!==guildId)setDraft(null)
    previous.current={guildId,data:query.data}
  },[guildId,query.data])
  const dirty=useMemo(()=>Boolean(draft&&query.data&&JSON.stringify(draft)!==JSON.stringify(query.data)),[draft,query.data])
  useEffect(()=>{if(!dirty)return;const guard=(event:BeforeUnloadEvent)=>{event.preventDefault()};addEventListener('beforeunload',guard);return()=>removeEventListener('beforeunload',guard)},[dirty])
  const save=useMutation({mutationFn:(value:SettingsResponse)=>api<SettingsResponse>(`/guilds/${guildId}/suggestions/settings`,{method:'PUT',body:JSON.stringify(value)}),onSuccess:value=>{qc.setQueryData(['suggestionsSettings',guildId],value);setDraft(structuredClone(value));void qc.invalidateQueries({queryKey:['overview',guildId]})}})
  if(query.error||resources.error)return <main className={s.page}><Failure error={query.error||resources.error}/></main>
  if(query.isLoading||resources.isLoading||!draft)return <Loading/>
  const settings=draft.settings; const textChannels=(resources.data?.channels||[]).filter(channel=>channel.type===0)
  const update=(values:Partial<SuggestionSettings>)=>setDraft({...draft,settings:{...settings,...values}})
  const updateField=(index:number,values:Partial<SuggestionFormField>)=>update({form_fields:settings.form_fields.map((field,i)=>i===index?{...field,...values}:field)})
  const moveField=(index:number,direction:-1|1)=>{const target=index+direction;if(target<0||target>=settings.form_fields.length)return;const next=[...settings.form_fields];[next[index],next[target]]=[next[target],next[index]];update({form_fields:next})}
  return <main className={s.page}><SectionHead title={t('suggestions.title')} description={t('suggestions.subtitle')} actions={<a className={s.docsButton} href="/docs/features/suggestions" target="_blank" rel="noreferrer"><BookOpen/>{t('common.help','使い方')}</a>}/>
    {draft.missing_permissions.length>0&&<div className={s.failure} role="alert"><div><strong>{t('suggestions.permissions')}</strong><p>{draft.missing_permissions.join(' · ')}</p></div></div>}
    <form id="suggestions-settings" className={s.moduleForm} onSubmit={event=>{event.preventDefault();save.mutate(draft)}}>
      <section><h2>{t('suggestions.delivery')}</h2><label className={s.switchRow}><span><strong>{t('suggestions.enabled')}</strong></span><Switch.Root checked={draft.enabled} onCheckedChange={enabled=>setDraft({...draft,enabled})} className={s.switch}><Switch.Thumb/></Switch.Root></label><div className={s.formGrid}><SingleResource label={t('suggestions.channel')} value={settings.channel_id} items={textChannels} onChange={channel_id=>update({channel_id})}/><SingleResource label={t('suggestions.logChannel')} value={settings.log_channel_id} items={textChannels} onChange={log_channel_id=>update({log_channel_id})}/></div></section>
      <section><h2>{t('suggestions.review')}</h2><RolePicker value={settings.review_role_ids} items={resources.data?.roles||[]} onChange={review_role_ids=>update({review_role_ids})}/><div className={s.formGrid}><label className={s.switchRow}><span><strong>{t('suggestions.voting')}</strong><small>{t('suggestions.votingHelp')}</small></span><Switch.Root checked={settings.allow_voting} onCheckedChange={allow_voting=>update({allow_voting})} className={s.switch}><Switch.Thumb/></Switch.Root></label><label className={s.switchRow}><span><strong>{t('suggestions.author')}</strong><small>{t('suggestions.authorHelp')}</small></span><Switch.Root checked={settings.show_author} onCheckedChange={show_author=>update({show_author})} className={s.switch}><Switch.Thumb/></Switch.Root></label></div></section>
      <section><div className={s.panelHead}><Lightbulb/><div><h2>{t('suggestions.form')}</h2><p>{t('suggestions.formHelp')}</p></div></div><label className={s.field}><span>{t('suggestions.formTitle')}</span><input maxLength={45} value={settings.form_title} onChange={event=>update({form_title:event.target.value})}/></label><ol className={s.suggestionFields}>{settings.form_fields.map((field,index)=><li key={`${field.key}-${index}`} className={s.suggestionField}><div className={s.suggestionFieldHead}><strong>{index+1}. {field.label||t('suggestions.unnamed')}</strong><div><button type="button" aria-label={t('suggestions.moveUp')} disabled={index===0} onClick={()=>moveField(index,-1)}><ArrowUp/></button><button type="button" aria-label={t('suggestions.moveDown')} disabled={index===settings.form_fields.length-1} onClick={()=>moveField(index,1)}><ArrowDown/></button><button type="button" aria-label={t('suggestions.removeField')} disabled={settings.form_fields.length===1} onClick={()=>update({form_fields:settings.form_fields.filter((_,i)=>i!==index)})}><Trash2/></button></div></div><div className={s.formGrid}><label className={s.field}><span>{t('suggestions.label')}</span><input required maxLength={45} value={field.label} onChange={event=>updateField(index,{label:event.target.value})}/></label><label className={s.field}><span>{t('suggestions.placeholder')}</span><input maxLength={100} value={field.placeholder} onChange={event=>updateField(index,{placeholder:event.target.value})}/></label><label className={s.field}><span>{t('suggestions.inputType')}</span><select value={field.style} onChange={event=>updateField(index,{style:event.target.value as SuggestionFormField['style']})}><option value="short">{t('suggestions.short')}</option><option value="paragraph">{t('suggestions.paragraph')}</option></select></label><label className={s.field}><span>{t('suggestions.maxLength')}</span><input type="number" min={1} max={4000} value={field.max_length} onChange={event=>updateField(index,{max_length:Number(event.target.value)})}/></label></div><label className={s.confirmRow}><input type="checkbox" checked={field.required} onChange={event=>updateField(index,{required:event.target.checked,min_length:event.target.checked?Math.max(1,field.min_length):0})}/><span>{t('suggestions.required')}</span></label></li>)}</ol><button type="button" className={s.secondaryButton} disabled={settings.form_fields.length>=5} onClick={()=>update({form_fields:[...settings.form_fields,newField(t('suggestions.additionalInfo'))]})}><Plus/>{t('suggestions.addField')}</button></section>
      {save.error&&<Failure error={save.error}/>}<button className={s.primaryButton} disabled={!dirty||save.isPending||(draft.enabled&&!settings.channel_id)}><Save/>{t('common.save')}</button>
    </form>
    <section><h2>{t('suggestions.recent')}</h2>{items.isLoading?<Loading/>:items.error?<Failure error={items.error}/>:items.data?.items.length?<div className={s.suggestionList}>{items.data.items.map(item=><article key={item.id}><div><strong>#{item.id} · {t(`suggestions.status.${item.status}`)}</strong><span>{Object.values(item.answers).find(Boolean)||'—'}</span></div><div><Status active={item.status==='approved'}>{t(`suggestions.status.${item.status}`)}</Status><small>👍 {item.upvotes} · 👎 {item.downvotes} · {new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium'}).format(item.created_at*1000)}</small></div></article>)}</div>:<p className={s.sectionCopy}>{t('suggestions.empty')}</p>}</section>
    {dirty&&<div className={s.saveBar} role="region" aria-label={t('suggestions.unsaved')}><div><strong>{t('suggestions.unsaved')}</strong></div><button type="button" className={s.secondaryButton} onClick={()=>setDraft(structuredClone(query.data!))}>{t('common.discard')}</button><button className={s.primaryButton} disabled={save.isPending||(draft.enabled&&!settings.channel_id)} type="submit" form="suggestions-settings"><Save/>{t('common.save')}</button></div>}
  </main>
}
