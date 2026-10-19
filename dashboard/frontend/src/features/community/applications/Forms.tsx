import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { ApplicationForm, Operations } from '../../../generated/api'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../../components/forms/EditNotice'
import { Failure, Loading } from '../../../components/Feedback'
import { ResourceSelect } from '../../../components/ResourcePicker'
import type { Resource } from '../../../types'
import s from '../../../styles/App.module.css'
type ApplicationFormInput = Operations['POST /api/v1/guilds/{guild_id}/applications/forms']['body']

const initial:ApplicationFormInput={title:'',description:'',enabled:false,fields:[{key:'answer',label:'',style:'paragraph',required:true,min_length:1,max_length:1000}],required_role_ids:[],denied_role_ids:[],account_age_days:0,member_age_days:0,cooldown_seconds:3600,retention_days:30}

export function FormEditor({guildId,item,roles=[]}:{guildId:string;item?:ApplicationForm;roles?:Resource[]}) {
  const {t}=useTranslation(['applications','common']);const qc=useQueryClient()
  const draft=useSettingsDraft<ApplicationFormInput>(item,initial,`${guildId}:${item?.id??'new'}`)
  const value=draft.draft
  const save=useSaveMutation({mutationFn:()=>item?request('PUT /api/v1/guilds/{guild_id}/applications/forms/{form_id}',`/guilds/${guildId}/applications/forms/${item.id}`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/applications/forms/{form_id}',value)}):request('POST /api/v1/guilds/{guild_id}/applications/forms',`/guilds/${guildId}/applications/forms`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/applications/forms',value)}),
    onSuccess:async result=>{draft.accept(item?result:initial);await qc.invalidateQueries({queryKey:['applicationForms',guildId]})}})
  useUnsavedChanges(draft.dirty,save.isPending)
  const change=<K extends keyof ApplicationFormInput>(key:K,next:ApplicationFormInput[K])=>draft.setDraft({...value,[key]:next})
  return <form className={s.applicationSection} onSubmit={e=>{e.preventDefault();save.mutate()}} aria-label={item?`${t('applications.edit')} #${item.id}`:t('applications.create')}>
    <h2>{item?`${t('applications.edit')} #${item.id}`:t('applications.create')}</h2>
    <fieldset disabled={save.isPending}>
      <label className={s.field}>{t('applications.formTitle')}<input required maxLength={45} value={value.title} onChange={e=>change('title',e.target.value)}/></label>
      <label className={s.field}>{t('applications.description')}<textarea maxLength={2000} value={value.description??''} onChange={e=>change('description',e.target.value)}/></label>
      <label><input type="checkbox" checked={value.enabled??false} onChange={e=>change('enabled',e.target.checked)}/>{t('applications.accepting')}</label>
      <h3>{t('applications.questions')}</h3>
      {value.fields.map((field,i)=><fieldset key={i}><legend>{t('applications.question',{n:i+1})}</legend>
        <label className={s.field}>{t('applications.key')}<input required pattern="[a-z][a-z0-9_]{0,39}" value={field.key} onChange={e=>change('fields',value.fields.map((f,n)=>n===i?{...f,key:e.target.value}:f))}/></label>
        <label className={s.field}>{t('applications.label')}<input required maxLength={45} value={field.label} onChange={e=>change('fields',value.fields.map((f,n)=>n===i?{...f,label:e.target.value}:f))}/></label>
        <label className={s.field}>{t('applications.style')}<select value={field.style} onChange={e=>change('fields',value.fields.map((f,n)=>n===i?{...f,style:e.target.value as 'short'|'paragraph'}:f))}><option value="short">{t('applications.short')}</option><option value="paragraph">{t('applications.paragraph')}</option></select></label>
        <label><input type="checkbox" checked={field.required??true} onChange={e=>change('fields',value.fields.map((f,n)=>n===i?{...f,required:e.target.checked}:f))}/>{t('applications.required')}</label>
        {(['min_length','max_length'] as const).map(key=><label className={s.field} key={key}>{t(`applications.${key}`)}<input type="number" min={key==='min_length'?0:1} max={4000} required value={field[key]??(key==='min_length'?1:1000)} onChange={e=>change('fields',value.fields.map((f,n)=>n===i?{...f,[key]:Number(e.target.value)}:f))}/></label>)}
        <button type="button" disabled={value.fields.length<=1} onClick={()=>change('fields',value.fields.filter((_,n)=>n!==i))}>{t('applications.removeQuestion')}</button>
      </fieldset>)}
      <button type="button" disabled={value.fields.length>=5} onClick={()=>change('fields',[...value.fields,{key:`answer_${value.fields.length+1}`,label:'',style:'paragraph',required:true,min_length:1,max_length:1000}])}>{t('applications.addQuestion')}</button>
      <h3>{t('applications.policy')}</h3>
      {(['required_role_ids','denied_role_ids'] as const).map(key=><ResourceSelect key={key} label={t(`applications.${key}`)} multiple items={roles} value={value[key]??[]} onChange={ids=>change(key,ids as string[])}/>)}
      {(['account_age_days','member_age_days','cooldown_seconds','retention_days'] as const).map(key=><label className={s.field} key={key}>{t(`applications.${key}`)}<input required type="number" min={key==='retention_days'?1:0} max={key==='cooldown_seconds'?2592000:key==='retention_days'?365:3650} value={value[key]??0} onChange={e=>change(key,Number(e.target.value))}/></label>)}
    </fieldset>
    <EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>
    {save.error&&<Failure error={save.error}/>}
    <button type="submit" disabled={!draft.dirty||save.isPending}>{t('common.save',{ns:'common'})}</button>{' '}
    <button type="button" disabled={save.isPending||!draft.dirty} onClick={()=>{draft.discard();save.reset()}}>{t('common.discard',{ns:'common'})}</button>
  </form>
}

export default function Forms(){
  const {guildId=''}=useParams();const {t}=useTranslation('applications')
  const query=useQuery({queryKey:['applicationForms',guildId],queryFn:async()=>{
    const [forms,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/applications/forms',`/guilds/${guildId}/applications/forms`),request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)])
    return {...forms,roles:resources.roles}
  }})
  if(query.isLoading)return <Loading/>
  if(query.error)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  return <main className={s.page}><h1>{t('applications.title')}</h1><p>{t('applications.help')}</p>
    {!query.data?.items.length&&<p>{t('applications.emptyForms')}</p>}
    {query.data?.items.map(item=><details key={item.id}><summary>#{item.id} {item.title}</summary><FormEditor guildId={guildId} item={item} roles={query.data.roles}/></details>)}<FormEditor guildId={guildId} roles={query.data?.roles}/></main>
}
