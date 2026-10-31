import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { PollConfig, PollItem, Resource } from '../../../generated/api'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../../components/forms/EditNotice'
import { Failure } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

const fields=['counts','ranking','total','participants','ballots']
const modes=['anonymous','public','secret_winner','reveal_at_end','blind','custom'] as const
export const localTime=(n:number|null|undefined)=>n?new Date(n*1000-new Date(n*1000).getTimezoneOffset()*60000).toISOString().slice(0,16):''
const stamp=(value:string)=>value?Math.floor(new Date(value).getTime()/1000):null
export type PollDraft={config:PollConfig;channel_id:string;revision:number;closes_at:number|null;scheduled_at:number|null;duration_seconds:number|null}

export default function PollEditor({guildId,item,enabled,channels,roles,onSaved,onBusy}:{guildId:string;item?:PollItem;enabled:boolean;channels:Resource[];roles:Resource[];onSaved:()=>Promise<void>;onBusy?:(busy:boolean)=>void}){
 const {t}=useTranslation(['polls','common'])
 const initial=useMemo<PollDraft>(()=>({config:{question:'',description:'',options:['',''],emojis:['',''],max_choices:1,mode:'anonymous',ui:'buttons',allowed_roles:[],denied_roles:[],denied_users:[],color:0x5865f2},channel_id:'',revision:1,closes_at:null,scheduled_at:null,duration_seconds:null}),[])
 const source=useMemo<PollDraft|undefined>(()=>item?{config:item.config,channel_id:item.channel_id,revision:item.revision,closes_at:item.closes_at??null,scheduled_at:item.scheduled_at??null,duration_seconds:item.duration_seconds??null}:undefined,[item])
 const draft=useSettingsDraft(source,initial,`${guildId}:${item?.id??'new'}`)
 const value=draft.draft,c=value.config
 const [key,setKey]=useState(()=>crypto.randomUUID())
 const save=useSaveMutation({mutationFn:()=>item?request('PUT /api/v1/guilds/{guild_id}/polls/items/{poll_id}',`/guilds/${guildId}/polls/items/${item.id}`,{body:encodeBody('PUT /api/v1/guilds/{guild_id}/polls/items/{poll_id}',{config:c,revision:value.revision,closes_at:value.closes_at,scheduled_at:value.scheduled_at,duration_seconds:value.duration_seconds})}):request('POST /api/v1/guilds/{guild_id}/polls/items',`/guilds/${guildId}/polls/items`,{body:encodeBody('POST /api/v1/guilds/{guild_id}/polls/items',{config:c,channel_id:value.channel_id,request_key:key,closes_at:value.closes_at,scheduled_at:value.scheduled_at,duration_seconds:value.duration_seconds})}),onSuccess:async result=>{draft.accept(item?{...value,config:result.config,revision:result.revision}:initial);setKey(crypto.randomUUID());await onSaved()}})
 useUnsavedChanges(draft.dirty,save.isPending)
 useEffect(()=>{onBusy?.(draft.dirty||save.isPending);return()=>onBusy?.(false)},[draft.dirty,save.isPending,onBusy])
 const change=(values:Partial<PollConfig>)=>draft.setDraft({...value,config:{...c,...values}})
 const choice=(index:number,text:string)=>change({options:c.options.map((old,n)=>n===index?text:old)})
 const multiple=(event:React.ChangeEvent<HTMLSelectElement>)=>Array.from(event.target.selectedOptions,option=>option.value)
 return <form className={s.applicationSection} onSubmit={e=>{e.preventDefault();if(enabled)save.mutate()}} aria-label={t(item?'polls.edit':'polls.create')}>
  <h2>{t(item?'polls.edit':'polls.create')}</h2>
  <fieldset disabled={!enabled||save.isPending}>
   <label className={s.field}>{t('polls.question')}<textarea required maxLength={1024} value={c.question} onChange={e=>change({question:e.target.value})}/></label>
   <label className={s.field}>{t('polls.description')}<textarea maxLength={2000} value={c.description??''} onChange={e=>change({description:e.target.value})}/></label>
   {!item&&<label className={s.field}>{t('polls.channel')}<select required value={value.channel_id} onChange={e=>draft.setDraft({...value,channel_id:e.target.value})}><option value="">—</option>{channels.map(channel=><option key={channel.id} value={channel.id}>{channel.name}</option>)}</select></label>}
   {c.options.map((option,index)=><div key={index}>
    <label className={s.field}>{t('polls.option')} {index+1}<textarea required maxLength={256} value={option} onChange={e=>choice(index,e.target.value)}/></label>
    <label className={s.field}>{t('polls.emoji')} {index+1}<input maxLength={100} value={c.emojis?.[index]??''} onChange={e=>change({emojis:c.options.map((_,n)=>n===index?e.target.value:c.emojis?.[n]??'')})}/></label>
    <button type="button" disabled={c.options.length<=2} onClick={()=>change({options:c.options.filter((_,n)=>n!==index),emojis:(c.emojis??c.options.map(()=>'' )).filter((_,n)=>n!==index),max_choices:Math.min(c.max_choices??1,c.options.length-1)})}>{t('polls.removeOption')} {index+1}</button>
   </div>)}
   <button type="button" disabled={c.options.length>=25} onClick={()=>change({options:[...c.options,''],emojis:[...(c.emojis??c.options.map(()=>'')),'']})}>{t('polls.addOption')}</button>
   <label className={s.field}>{t('polls.maxChoices')}<input type="number" min={1} max={Math.min(20,c.options.length)} value={c.max_choices??1} onChange={e=>change({max_choices:Number(e.target.value)})}/></label>
   <label className={s.field}>{t('polls.mode')}<select value={c.mode??'anonymous'} onChange={e=>change({mode:e.target.value as PollConfig['mode']})}>{modes.map(mode=><option key={mode} value={mode}>{t(`polls.modes.${mode}`)}</option>)}</select></label>
   <p>{t('polls.privacy')}</p>
   {c.mode==='custom'&&(['open','closed'] as const).map(stage=><fieldset key={stage}><legend>{t(`polls.${stage}`)}</legend>{fields.map(field=><label className={s.field} key={field}>{t(`polls.disclosure.${field}`)}<select value={c.visibility?.[stage]?.[field]??'hidden'} onChange={e=>change({visibility:{open:{...c.visibility?.open},closed:{...c.visibility?.closed},[stage]:{...c.visibility?.[stage],[field]:e.target.value}}})}>{['everyone','admins','hidden'].map(level=><option key={level} value={level}>{t(`polls.levels.${level}`)}</option>)}</select></label>)}</fieldset>)}
   <label className={s.field}>{t('polls.ui')}<select value={c.options.length>20?'select':c.ui??'buttons'} disabled={c.options.length>20} onChange={e=>change({ui:e.target.value as 'buttons'|'select'})}><option value="buttons">{t('polls.buttons')}</option><option value="select">{t('polls.select')}</option></select></label>
   <label className={s.field}>{t('polls.buttonStyle')}<select value={c.button_style??'secondary'} onChange={e=>change({button_style:e.target.value as PollConfig['button_style']})}>{['primary','secondary','success','danger'].map(style=><option key={style} value={style}>{t(`polls.styles.${style}`)}</option>)}</select></label>
   <label className={s.field}>{t('polls.allowedRoles')}<select multiple value={c.allowed_roles??[]} onChange={e=>change({allowed_roles:multiple(e)})}>{roles.map(role=><option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
   <label className={s.field}>{t('polls.deniedRoles')}<select multiple value={c.denied_roles??[]} onChange={e=>change({denied_roles:multiple(e)})}>{roles.map(role=><option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
   <label className={s.field}>{t('polls.deniedUsers')}<input value={(c.denied_users??[]).join(',')} onChange={e=>change({denied_users:e.target.value.split(',').map(x=>x.trim()).filter(Boolean)})}/></label>
   <label className={s.field}>{t('polls.image')}<input type="url" maxLength={2048} value={c.image_url??''} onChange={e=>change({image_url:e.target.value||null})}/></label>
   <label className={s.field}>{t('polls.color')}<input type="color" value={`#${(c.color??0x5865f2).toString(16).padStart(6,'0')}`} onChange={e=>change({color:parseInt(e.target.value.slice(1),16)})}/></label>
   <label className={s.field}>{t('polls.cap')}<input type="number" min={1} max={1000000} value={c.max_participants??''} onChange={e=>change({max_participants:e.target.value?Number(e.target.value):null})}/></label>
   {(['announce_winner','pin_on_close','create_thread','remove_departed_votes'] as const).map(flag=><label key={flag}><input type="checkbox" checked={c[flag]??false} onChange={e=>change({[flag]:e.target.checked})}/>{t(`polls.automation.${flag}`)}</label>)}
   {(!item||['draft','scheduled'].includes(item.status))&&<><label className={s.field}>{t('polls.schedule')}<input type="datetime-local" value={localTime(value.scheduled_at)} onChange={e=>draft.setDraft({...value,scheduled_at:stamp(e.target.value)})}/></label><label className={s.field}>{t('polls.duration')}<input type="number" min={1} max={43200} value={value.duration_seconds?value.duration_seconds/60:''} onChange={e=>draft.setDraft({...value,duration_seconds:e.target.value?Number(e.target.value)*60:null,closes_at:null})}/></label></>}
   <label className={s.field}>{t('polls.deadline')}<input type="datetime-local" value={localTime(value.closes_at)} disabled={Boolean(value.duration_seconds)} onChange={e=>draft.setDraft({...value,closes_at:stamp(e.target.value)})}/></label>
  </fieldset>
  <details><summary>{t('polls.preview')}</summary><h3 style={{overflowWrap:'anywhere'}}>{c.question}</h3><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.description}</p><ol>{c.options.map((option,index)=><li key={index} style={{overflowWrap:'anywhere'}}>{c.emojis?.[index]} {option}</li>)}</ol>{c.image_url&&<img src={c.image_url} alt={t('polls.image')} style={{maxWidth:'100%'}}/>}<p>{t(`polls.modes.${c.mode??'anonymous'}`)} · {t('polls.maxChoices')}: {c.max_choices??1}</p></details>
  <EditNotice dirty={draft.dirty} changedRemotely={draft.changedRemotely} saved={save.isSuccess}/>
  {save.error&&<Failure error={save.error}/>}
  <button type="submit" disabled={!enabled||!draft.dirty||save.isPending}>{t('polls.save')}</button>{' '}<button type="button" disabled={!draft.dirty||save.isPending} onClick={()=>{draft.discard();save.reset();setKey(crypto.randomUUID())}}>{t('common.discard',{ns:'common'})}</button>
 </form>
}


