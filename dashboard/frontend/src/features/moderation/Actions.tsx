import { useSaveMutation } from '../../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../../components/forms/useUnsavedChanges'
import { EditNotice } from '../../components/forms/EditNotice'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Gavel } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { Resource } from "../../types"
import s from "../../styles/App.module.css"
import { SectionHead, Failure } from "../../components/Feedback"
import { ResourceSelect } from "../../components/ResourcePicker"



export function Actions() {
  const { t } = useTranslation(['moderation', 'common']); const { guildId = '' } = useParams(); const [queued,setQueued] = useState(false)
  const resources = useQuery({ queryKey: ['resources', guildId], queryFn: () => request("GET /api/v1/guilds/{guild_id}/resources", `/guilds/${guildId}/resources`) })
  const form = useForm({ defaultValues: { action: 'warn', target_user_id: '', channel_id: '', reason: '', duration_minutes: 10, count: 10, confirmation: '', confirmed: false } })
  const action = form.watch('action'); const target = form.watch('target_user_id'); const destructive = ['ban','softban','lockdown'].includes(action)
  const mutation = useSaveMutation({ mutationFn: (value: Record<string,unknown>) => request("POST /api/v1/guilds/{guild_id}/moderation/actions", `/guilds/${guildId}/moderation/actions`, { method: 'POST', body: encodeBody("POST /api/v1/guilds/{guild_id}/moderation/actions", value) }), onSuccess: () => { setQueued(true); form.reset() } })
  useUnsavedChanges(form.formState.isDirty,mutation.isPending)
  return <main className={s.page}><SectionHead title={t('action.title')} description="処置を受け付け、順に実行します。"/><EditNotice dirty={form.formState.isDirty}/>{resources.error&&<Failure error={resources.error} retry={()=>void resources.refetch()}/>}<form className={s.actionForm} onSubmit={form.handleSubmit(value => {if(!resources.isLoading&&!resources.error)mutation.mutate(value)})}>
    <fieldset className={s.moduleFields} disabled={mutation.isPending||resources.isLoading}><div className={s.actionKind}>{['warn','timeout','untimeout','kick','ban','unban','softban','purge','lock','unlock','lockdown','unlockdown'].map(item => <label key={item}><input type="radio" value={item} {...form.register('action')}/><span>{item}</span></label>)}</div>
    <div className={s.formGrid}>{!['lockdown','unlockdown'].includes(action) && <label className={s.field}><span>{t('action.target')}</span><input inputMode="numeric" {...form.register('target_user_id')}/><small>対象ユーザーを指定する処置で入力してください。</small></label>}{['purge','lock','unlock'].includes(action) && <ResourceSelect label={t('action.channel')} value={form.watch('channel_id')} items={(resources.data?.channels || []).filter(item => item.type !== 4)} onChange={value => form.setValue('channel_id', String(value || ''), { shouldDirty: true })}/>}<label className={s.field}><span>{t('action.reason')}</span><textarea {...form.register('reason', { required: true, maxLength: 500 })}/><small>入力した理由はケースとログに保存されます。</small></label>{['timeout','ban','lockdown'].includes(action) && <label className={s.field}><span>{t('action.duration')}</span><input type="number" {...form.register('duration_minutes', { valueAsNumber: true })}/><small>自動解除するまでの期間</small></label>}{destructive && <label className={s.field}><span>確認入力</span><input autoComplete="off" {...form.register('confirmation', { required: true, validate: value => value === (action === 'lockdown' ? guildId : target) })}/><small><code>{action === 'lockdown' ? guildId : target || '対象ユーザーID'}</code> と入力してください。</small></label>}</div>
    <label className={s.confirmRow}><input type="checkbox" {...form.register('confirmed', { required: true })}/><span>{t('action.confirm')}</span></label>{mutation.error && <Failure error={mutation.error}/>} {queued && <div className={s.inlineSuccess} role="status"><Check/>{t('action.queued')}</div>}<button className={s.dangerButton} disabled={mutation.isPending||Boolean(resources.error)}><Gavel/>処置を実行</button>
  <button type="button" disabled={mutation.isPending||!form.formState.isDirty} onClick={()=>{form.reset();mutation.reset();setQueued(false)}}>{t('common.discard')}</button></fieldset></form></main>
}
