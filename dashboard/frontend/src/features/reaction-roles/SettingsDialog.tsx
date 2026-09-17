

import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Switch from '@radix-ui/react-switch'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Save, X } from 'lucide-react'

import { useTranslation } from 'react-i18next'
import { request, encodeBody } from "../../api"

import type { ReactionRoleSettings } from "../../types"
import s from "../../styles/App.module.css"
import { Failure } from '../../components/Feedback'

export function SettingsDialog({guildId,initial,onClose,onSaved}:{guildId:string;initial:ReactionRoleSettings;onClose:()=>void;onSaved:()=>void}){
  const {t}=useTranslation(['tickets', 'reactionRoles', 'common']);const [draft,setDraft]=useState(initial);const resources=useQuery({queryKey:['resources',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/resources", `/guilds/${guildId}/resources`)});const save=useMutation({mutationFn:()=>request("PUT /api/v1/guilds/{guild_id}/reaction-roles/settings", `/guilds/${guildId}/reaction-roles/settings`, {method:'PUT',body:encodeBody("PUT /api/v1/guilds/{guild_id}/reaction-roles/settings", draft)}),onSuccess:onSaved})
  return <Dialog.Root open onOpenChange={open=>{if(!open)onClose()}}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.dialog}><div className={s.dialogHead}><div><Dialog.Title>{t('reactionRoles.settings')}</Dialog.Title><Dialog.Description>{t('reactionRoles.settingsBody')}</Dialog.Description></div><Dialog.Close className={s.iconButton}><X/></Dialog.Close></div><label className={s.switchRow}><span><strong>{t('reactionRoles.enabled')}</strong></span><Switch.Root checked={draft.enabled} onCheckedChange={enabled=>setDraft({...draft,enabled})} className={s.switch}><Switch.Thumb/></Switch.Root></label><label className={s.field}><span>{t('reactionRoles.logChannel')}</span><select value={draft.log_channel_id||''} onChange={e=>setDraft({...draft,log_channel_id:e.target.value||null})}><option value="">{t('reactionRoles.notSet')}</option>{resources.data?.channels.filter(item=>item.type===0).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className={s.switchRow}><span><strong>{t('reactionRoles.denialDm')}</strong></span><Switch.Root checked={draft.denial_dm} onCheckedChange={denial_dm=>setDraft({...draft,denial_dm})} className={s.switch}><Switch.Thumb/></Switch.Root></label><label className={s.field}><span>{t('reactionRoles.dmCooldown')}</span><input type="number" min={30} max={86400} value={draft.denial_dm_cooldown_seconds} onChange={e=>setDraft({...draft,denial_dm_cooldown_seconds:Number(e.target.value)})}/></label>{save.error&&<Failure error={save.error}/>}<div className={s.dialogActions}><Dialog.Close className={s.secondaryButton}>{t('common.discard')}</Dialog.Close><button className={s.primaryButton} disabled={save.isPending} onClick={()=>save.mutate()}><Save/>{t('common.save')}</button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
}
