import { useId } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { ReactionRoleSettings } from '../../../types'
import { Failure } from '../../../components/Feedback'
import { ResourceSelect } from '../../../components/ResourcePicker'
import { Toggle } from '../../../components/forms/Fields'
import { SaveBar } from '../../../components/SaveBar'
import { EditNotice } from '../../../components/forms/EditNotice'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import s from '../../../styles/App.module.css'

export function SettingsDialog({ guildId, initial, onClose, onSaved }: { guildId: string; initial: ReactionRoleSettings; onClose: () => void; onSaved: () => void | Promise<void> }) {
  const formId=useId()
  const { t } = useTranslation(['reactionRoles', 'common'])
  const qc = useQueryClient()
  const editor = useSettingsDraft(initial, initial, guildId)
  const { draft, setDraft } = editor
  const resources = useQuery({ queryKey: ['resources', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/resources', `/guilds/${guildId}/resources`) })
  const save = useSaveMutation({ mutationFn: () => request('PUT /api/v1/guilds/{guild_id}/reaction-roles/settings', `/guilds/${guildId}/reaction-roles/settings`, { body: encodeBody('PUT /api/v1/guilds/{guild_id}/reaction-roles/settings', draft) }),
    onSuccess: async value => { editor.accept(value); await qc.invalidateQueries({ queryKey: ['features', guildId] }); allowLeave(); await onSaved() } })
  const allowLeave=useUnsavedChanges(editor.dirty, save.isPending)
  const close = () => { if (!save.isPending && (!editor.dirty || confirm(t('editing.discardConfirm')))) {allowLeave();onClose()} }
  return <Dialog.Root open onOpenChange={open => { if (!open) close() }}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.dialog}>
    <div className={s.dialogHead}><div><Dialog.Title>{t('reactionRoles.settings')}</Dialog.Title><Dialog.Description>{t('reactionRoles.settingsBody')}</Dialog.Description></div><Dialog.Close className={s.iconButton} disabled={save.isPending} aria-label={t('common.close')}><X/></Dialog.Close></div>
    {resources.error && <Failure error={resources.error} retry={() => void resources.refetch()}/>}
    <EditNotice dirty={editor.dirty} changedRemotely={editor.changedRemotely}/>
    <form id={formId} onSubmit={event=>{event.preventDefault();if(!resources.error&&!resources.isLoading)save.mutate()}}><fieldset className={s.moduleFields} disabled={save.isPending || resources.isLoading}>
      <Toggle label={t('reactionRoles.enabled')} checked={draft.enabled} onChange={enabled => setDraft({ ...draft, enabled })}/>
      <ResourceSelect label={t('reactionRoles.logChannel')} value={draft.log_channel_id} items={(resources.data?.channels ?? []).filter(item => item.type === 0)} onChange={value => setDraft({ ...draft, log_channel_id: value ? String(value) : null })}/>
      <Toggle label={t('reactionRoles.denialDm')} checked={draft.denial_dm} onChange={denial_dm => setDraft({ ...draft, denial_dm })}/>
      <label className={s.field}><span>{t('reactionRoles.dmCooldown')}</span><input type="number" min={30} max={86400} value={draft.denial_dm_cooldown_seconds} onChange={event => setDraft({ ...draft, denial_dm_cooldown_seconds: Number(event.target.value) })}/></label>
    </fieldset></form>
    {save.error && <Failure error={save.error}/>}
    <SaveBar inline dirty={editor.dirty} pending={save.isPending} disabled={!editor.dirty || Boolean(resources.error) || resources.isLoading} onDiscard={()=>{allowLeave();onClose()}} form={formId}/>
  </Dialog.Content></Dialog.Portal></Dialog.Root>
}
