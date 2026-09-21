import { useEffect, useId } from 'react'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen } from 'lucide-react'
import { request, encodeBody } from '../../api'
import type { Feature, Resource } from '../../types'
import { Loading, NotFound, SectionHead, Failure } from '../Feedback'
import { PermissionDiagnostics } from '../PermissionDiagnostics'
import { Toggle } from '../forms/Fields'
import { SaveBar } from '../SaveBar'
import s from '../../styles/App.module.css'

export interface SettingFieldProps { name: string; value: unknown; channels: Resource[]; roles: Resource[]; onChange: (value: unknown) => void }
type Value = Pick<Feature, 'enabled' | 'settings' | 'revision'>
type Props = { feature?: Feature; renderField: (props: SettingFieldProps) => ReactNode; title?: string; description?: string; actions?: ReactNode }
const groupFor = (field: string) => field.includes('enabled') ? 0 : field.includes('role') || field.includes('allow') ? 2 : field.includes('channel') || field.includes('notification') || field.includes('log') ? 3 : 1

export function ModuleSettings({ feature, renderField, title, description, actions }: Props) {
  const { guildId = '' } = useParams()
  const { t } = useTranslation('common')
  const formId = useId()
  const queryClient = useQueryClient()
  const resources = useQuery({ queryKey: ['resources', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/resources', `/guilds/${guildId}/resources`) })
  const form = useForm<Value>({ defaultValues: feature && { enabled: feature.enabled, settings: feature.settings, revision: feature.revision } })
  useEffect(() => {
    if (feature && !form.formState.isDirty && feature.revision > form.getValues('revision')) {
      form.reset({ enabled: feature.enabled, settings: feature.settings, revision: feature.revision })
    }
  }, [feature, form])
  const save = useMutation({
    mutationFn: (value: Value) => request('PUT /api/v1/guilds/{guild_id}/modules/{module_id}', `/guilds/${guildId}/modules/${feature!.id}`, { method: 'PUT', body: encodeBody('PUT /api/v1/guilds/{guild_id}/modules/{module_id}', value) }),
    onSuccess: async value => {
      form.reset(value)
      await queryClient.invalidateQueries({ queryKey: ['overview', guildId] })
    },
  })
  if (!feature) return <NotFound/>
  if (resources.isLoading) return <Loading/>
  if (resources.error) return <Failure error={resources.error} retry={() => resources.refetch()}/>
  const groups = ['state', 'basic', 'targets', 'notifications', 'permissions'] as const
  return <main className={s.page}>
    <SectionHead title={title ?? feature.title} description={description ?? feature.description} actions={actions ?? <a className={s.docsButton} href={feature.docs_path} aria-label={t('module.guide')} target="_blank" rel="noopener noreferrer"><BookOpen/><span>{t('module.guide')}</span></a>}/>
    <PermissionDiagnostics title={t('module.permissions')} messages={feature.missing_permissions}/>
    <form id={formId} className={s.moduleForm} onSubmit={form.handleSubmit(value => save.mutate(value))}>
      <fieldset disabled={save.isPending} className={s.moduleFields}>
        {groups.map((group, index) => {
          const fields = feature.fields.filter(field => groupFor(field) === index)
          if (index > 0 && !fields.length) return null
          return <section key={group}><h2>{t(`module.${group}`)}</h2>
            {index === 0 && <Toggle label={t('module.enable')} checked={form.watch('enabled')} onChange={value => form.setValue('enabled', value, { shouldDirty: true })}/>}
            <div className={s.formGrid}>{fields.map(name => <div key={name}>{renderField({ name, value: form.watch(`settings.${name}`), channels: resources.data?.channels ?? [], roles: resources.data?.roles ?? [], onChange: value => form.setValue(`settings.${name}`, value, { shouldDirty: true }) })}</div>)}</div>
          </section>
        })}
      </fieldset>
      {save.error && <Failure error={save.error}/>}
    </form>
    {form.formState.isDirty && <SaveBar count={1} pending={save.isPending} error={save.error} form={formId} onDiscard={() => { form.reset(); save.reset() }}/>}
  </main>
}
