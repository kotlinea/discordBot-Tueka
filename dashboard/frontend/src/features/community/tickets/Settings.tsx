import { useId } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request, encodeBody } from '../../../api'
import type { TicketSettings } from '../../../types'
import { Failure, Loading, SectionHead } from '../../../components/Feedback'
import { ResourceSelect } from '../../../components/ResourcePicker'
import { Toggle } from '../../../components/forms/Fields'
import { SaveBar } from '../../../components/SaveBar'
import { EditNotice } from '../../../components/forms/EditNotice'
import { useSettingsDraft } from '../../../components/forms/useSettingsDraft'
import { useUnsavedChanges } from '../../../components/forms/useUnsavedChanges'
import { useSaveMutation } from '../../../components/forms/useSaveMutation'
import s from '../../../styles/App.module.css'

export function TicketSettingsPage() {
  const { guildId = '' } = useParams()
  const { t } = useTranslation(['tickets', 'common'])
  const formId = useId()
  const qc = useQueryClient()
  const key = ['ticketSettings', guildId]
  const query = useQuery({ queryKey: key, queryFn: () => request('GET /api/v1/guilds/{guild_id}/tickets/settings', `/guilds/${guildId}/tickets/settings`) })
  const resources = useQuery({ queryKey: ['resources', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/resources', `/guilds/${guildId}/resources`) })
  const editor = useSettingsDraft<TicketSettings | null>(query.data, null, guildId)
  const { draft, setDraft } = editor
  const save = useSaveMutation({
    mutationFn: (value: TicketSettings) => request('PUT /api/v1/guilds/{guild_id}/tickets/settings', `/guilds/${guildId}/tickets/settings`, { body: encodeBody('PUT /api/v1/guilds/{guild_id}/tickets/settings', value) }),
    onSuccess: async value => {
      qc.setQueryData(key, value)
      editor.accept(value)
      await Promise.all([qc.invalidateQueries({ queryKey: key }), qc.invalidateQueries({ queryKey: ['features', guildId] }), qc.invalidateQueries({ queryKey: ['tickets', guildId] })])
    },
  })
  useUnsavedChanges(editor.dirty, save.isPending)
  if ((query.error && !query.data) || (resources.error && !resources.data)) return <main className={s.page}><Failure error={query.error || resources.error} retry={() => { void query.refetch(); void resources.refetch() }}/></main>
  if (!draft || resources.isLoading) return <Loading/>
  const channels = resources.data!.channels.filter(item => item.type === 0)
  const readError = query.error || resources.error
  return <main className={s.page}>
    <SectionHead title={t('tickets.settings')} description={t('tickets.settingsBody')}/>
    {readError && <Failure error={readError} retry={() => { void query.refetch(); void resources.refetch() }}/>}
    <EditNotice dirty={editor.dirty} changedRemotely={editor.changedRemotely} saved={save.isSuccess}/>
    <form id={formId} className={s.moduleForm} onSubmit={event => { event.preventDefault(); if (!readError) save.mutate(draft) }}>
      <fieldset className={s.moduleFields} disabled={save.isPending}>
        <Toggle label={t('tickets.enabled')} checked={draft.enabled} onChange={enabled => setDraft({ ...draft, enabled })}/>
        <div className={s.formGrid}>
          <label className={s.field}><span>{t('tickets.openLimit')}</span><input type="number" min={1} max={25} value={draft.open_limit} onChange={event => setDraft({ ...draft, open_limit: Number(event.target.value) })}/></label>
          <label className={s.field}><span>{t('tickets.retention')}</span><input type="number" min={1} max={3650} value={draft.transcript_retention_days} onChange={event => setDraft({ ...draft, transcript_retention_days: Number(event.target.value) })}/></label>
          <ResourceSelect label={t('tickets.logChannel')} value={draft.log_channel_id} items={channels} onChange={value => setDraft({ ...draft, log_channel_id: value ? String(value) : null })}/>
          <ResourceSelect label={t('tickets.transcriptChannel')} value={draft.transcript_channel_id} items={channels} onChange={value => setDraft({ ...draft, transcript_channel_id: value ? String(value) : null })}/>
        </div>
      </fieldset>
      {save.error && <Failure error={save.error}/>}
    </form>
    {editor.dirty && <SaveBar pending={save.isPending} disabled={Boolean(readError)} form={formId} onDiscard={() => { editor.discard(); save.reset() }}/>}
  </main>
}
