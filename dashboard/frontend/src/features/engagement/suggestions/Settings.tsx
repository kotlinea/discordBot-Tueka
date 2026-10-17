import { Failure, Loading, SectionHead, Status } from '../../../components/Feedback'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../../components/forms/EditNotice'
import { FieldErrors } from '../../../components/FieldErrors'
import { PermissionDiagnostics } from '../../../components/PermissionDiagnostics'
import { FormFieldsEditor } from '../../../components/forms/FormFieldsEditor'
import { constraints } from '../../../generated/api'
import { SuggestionReview } from './Review'
import { SaveBar } from '../../../components/SaveBar'
import { ResourceSelect } from '../../../components/ResourcePicker'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as Switch from '@radix-ui/react-switch'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, BookOpen, Lightbulb, Plus, Save, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

import { api, request, encodeBody } from "../../../api"
import type { Feature, Resource, SuggestionFormField, SuggestionItem, SuggestionSettings } from "../../../types"
import s from "../../../styles/App.module.css"

type SettingsResponse = Pick<Feature, 'enabled'|'revision'|'missing_permissions'|'docs_path'> & {settings:SuggestionSettings}
const newField = (label:string):SuggestionFormField => ({key:`field_${Date.now()}`,label,placeholder:'',style:'short',required:false,min_length:0,max_length:500})


function SingleResource({label,value,items,onChange}:{label:string;value:string|null;items:Resource[];onChange:(value:string|null)=>void}) { return <ResourceSelect label={label} value={value} items={items} onChange={next=>onChange(next as string|null)}/> }

function RolePicker({value,items,onChange}:{value:string[];items:Resource[];onChange:(value:string[])=>void}) { const {t}=useTranslation(['suggestions','common']);return <ResourceSelect label={t('suggestions.reviewRoles')} value={value} items={items} multiple onChange={next=>onChange(next as string[])} hint={t('suggestions.selected',{count:value.length})+' '+t('suggestions.reviewerHelp')}/> }

export default function Suggestions() {
  const {guildId=''}=useParams(); const {t,i18n}=useTranslation(['suggestions', 'common']); const qc=useQueryClient()
  const query=useQuery({queryKey:['suggestionsSettings',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/suggestions/settings", `/guilds/${guildId}/suggestions/settings`)})
  const resources=useQuery({queryKey:['resources',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/resources", `/guilds/${guildId}/resources`)})
  const items=useQuery({queryKey:['suggestionsItems',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/suggestions/items", `/guilds/${guildId}/suggestions/items?limit=20`),refetchInterval:10000})
  const editor=useSettingsDraft<SettingsResponse|null>(query.data,null,guildId);const {draft,setDraft,dirty}=editor
  const save=useSaveMutation({mutationFn:(value:SettingsResponse)=>request("PUT /api/v1/guilds/{guild_id}/suggestions/settings", `/guilds/${guildId}/suggestions/settings`, {method:'PUT',body:encodeBody("PUT /api/v1/guilds/{guild_id}/suggestions/settings", value)}),onSuccess:async value=>{qc.setQueryData(['suggestionsSettings',guildId],value);editor.accept(value);await Promise.all([qc.invalidateQueries({queryKey:['suggestionsSettings',guildId]}),qc.invalidateQueries({queryKey:['overview',guildId]}),qc.invalidateQueries({queryKey:['features',guildId]})])}})
  useUnsavedChanges(dirty,save.isPending)
  if((query.error&&!query.data)||(resources.error&&!resources.data))return <main className={s.page}><Failure error={query.error||resources.error} retry={()=>{void query.refetch();void resources.refetch()}}/></main>
  if(query.isLoading||resources.isLoading||!draft)return <Loading/>
  const settings=draft.settings; const textChannels=(resources.data?.channels||[]).filter(channel=>channel.type===0)
  const update=(values:Partial<SuggestionSettings>)=>setDraft({...draft,settings:{...settings,...values}})
  return <main className={s.page}>{(query.error||resources.error)&&<Failure error={query.error||resources.error} retry={()=>{void query.refetch();void resources.refetch()}}/>}<EditNotice dirty={dirty} changedRemotely={editor.changedRemotely} saved={save.isSuccess}/><SectionHead title={t('suggestions.title')} description={t('suggestions.subtitle')} actions={<a className={s.docsButton} href="/docs/features/suggestions" target="_blank" rel="noreferrer"><BookOpen/>{t('common.help','使い方')}</a>}/>
    {draft.missing_permissions.length>0&&<PermissionDiagnostics title={t('suggestions.permissions')} messages={draft.missing_permissions} blocking/>}
    <form id="suggestions-settings" className={s.moduleForm} onSubmit={event=>{event.preventDefault();if(!query.error&&!resources.error)save.mutate(draft)}}><fieldset disabled={save.isPending} className={s.moduleFields}>
      <section><h2>{t('suggestions.delivery')}</h2><label className={s.switchRow}><span><strong>{t('suggestions.enabled')}</strong></span><Switch.Root checked={draft.enabled} onCheckedChange={enabled=>setDraft({...draft,enabled})} className={s.switch}><Switch.Thumb/></Switch.Root></label><div className={s.formGrid}><SingleResource label={t('suggestions.channel')} value={settings.channel_id} items={textChannels} onChange={channel_id=>update({channel_id})}/><SingleResource label={t('suggestions.logChannel')} value={settings.log_channel_id} items={textChannels} onChange={log_channel_id=>update({log_channel_id})}/></div></section>
      <section><h2>{t('suggestions.review')}</h2><label className={s.switchRow}><span>{t('suggestions.discussion')}</span><Switch.Root aria-label={t('suggestions.discussion')} checked={Boolean(settings.discussion_enabled)} onCheckedChange={discussion_enabled=>update({discussion_enabled})} className={s.switch}><Switch.Thumb/></Switch.Root></label><RolePicker value={settings.review_role_ids} items={resources.data?.roles||[]} onChange={review_role_ids=>update({review_role_ids})}/><div className={s.formGrid}><label className={s.switchRow}><span><strong>{t('suggestions.voting')}</strong><small>{t('suggestions.votingHelp')}</small></span><Switch.Root checked={settings.allow_voting} onCheckedChange={allow_voting=>update({allow_voting})} className={s.switch}><Switch.Thumb/></Switch.Root></label><label className={s.switchRow}><span><strong>{t('suggestions.author')}</strong><small>{t('suggestions.authorHelp')}</small></span><Switch.Root checked={settings.show_author} onCheckedChange={show_author=>update({show_author})} className={s.switch}><Switch.Thumb/></Switch.Root></label></div></section>
      <section><div className={s.panelHead}><Lightbulb/><div><h2>{t('suggestions.form')}</h2><p>{t('suggestions.formHelp')}</p></div></div><label className={s.field}><span>{t('suggestions.formTitle')}</span><input maxLength={constraints.SuggestionSettings.form_title.maxLength} value={settings.form_title} onChange={event=>update({form_title:event.target.value})}/></label><FormFieldsEditor fields={settings.form_fields} onChange={form_fields=>update({form_fields})}/><button type="button" className={s.secondaryButton} disabled={settings.form_fields.length>=constraints.SuggestionSettings.form_fields.maxItems} onClick={()=>update({form_fields:[...settings.form_fields,newField(t('suggestions.additionalInfo'))]})}><Plus/>{t('suggestions.addField')}</button></section>
      {save.error&&<Failure error={save.error}/>}<button className={s.primaryButton} disabled={!dirty||save.isPending||Boolean(query.error||resources.error)||(draft.enabled&&!settings.channel_id)}><Save/>{t('common.save')}</button>
    </fieldset></form>
    <section><h2>{t('suggestions.recent')}</h2>{items.isLoading?<Loading/>:items.error?<Failure error={items.error} retry={()=>void items.refetch()}/>:items.data?.items.length?<div className={s.suggestionList}>{items.data.items.map(item=><article key={item.id}><div><strong>#{item.id} · {t(`suggestions.status.${item.status}`)}</strong><span>{Object.values(item.answers).find(Boolean)||'—'}</span></div><div><Status active={item.status==='approved'}>{t(`suggestions.status.${item.status}`)}</Status><small>👍 {item.upvotes} · 👎 {item.downvotes} · {new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium'}).format(item.created_at*1000)}</small></div><SuggestionReview guildId={guildId} item={item} enabled={query.data?.enabled??false}/></article>)}</div>:<p className={s.sectionCopy}>{t('suggestions.empty')}</p>}</section>
    {dirty&&<SaveBar title={t('suggestions.unsaved')} pending={save.isPending} disabled={Boolean(query.error||resources.error)||(draft.enabled&&!settings.channel_id)} onDiscard={()=>{editor.discard();save.reset()}} form="suggestions-settings"/>}
  </main>
}
