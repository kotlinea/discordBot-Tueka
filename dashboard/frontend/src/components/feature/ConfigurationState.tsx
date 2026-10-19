import { createContext, useContext } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { request } from '../../api'
import type { Feature, Resource } from '../../types'
import type { FieldOptions } from '../forms/SettingField'
import { selectedIds } from '../ResourcePicker'
import { Failure } from '../Feedback'
import s from '../../styles/App.module.css'

type ResourceFields = Readonly<Record<string, Pick<FieldOptions, 'resource' | 'references'>>>
export const ConfigurationContext = createContext<{ feature?: Feature; features: Feature[]; fields?: ResourceFields }>({ features: [] })
export const useConfiguration = () => useContext(ConfigurationContext)

export function configurationIssues(feature: Feature | undefined, features: Feature[], resources?: { channels: Resource[]; roles: Resource[] }, fields?: ResourceFields) {
  if (!feature) return ['unknown']
  const reasons = new Set<string>()
  let parent = feature.parent
  const seen = new Set<string>()
  while (parent && !seen.has(parent)) {
    seen.add(parent)
    const item = features.find(item => item.id === parent)
    if (!item) { reasons.add('unknown'); break }
    if (!item.enabled) reasons.add('parentOff')
    parent = item.parent
  }
  if (feature.missing_permissions?.length) reasons.add('permissions')
  if (feature.required_fields?.some(name => {
    const value = feature.settings[name]
    return value == null || value === '' || (Array.isArray(value) && !value.length)
  })) reasons.add('required')
  if (resources) for (const [name, value] of Object.entries(feature.settings)) {
    const references = fields?.[name]?.references
    const kind = references?.kind ?? fields?.[name]?.resource ?? (/(?:channel|category)_ids?$/.test(name) ? 'channel' : /role_ids?$/.test(name) ? 'role' : undefined)
    const items = kind === 'role' ? resources.roles : kind ? resources.channels : undefined
    if (items && (references ? references.ids(value) : selectedIds(value)).some(id => !items.some(item => String(item.id) === id))) reasons.add('resourceMissing')
  }
  return [...reasons]
}

export function ConfigurationState() {
  const { feature, features, fields } = useConfiguration()
  const { guildId = '' } = useParams()
  const { t } = useTranslation('common')
  const resources = useQuery({ queryKey: ['resources', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/resources', `/guilds/${guildId}/resources`) })
  const issues = configurationIssues(feature, features, resources.data, fields)
  return <aside className={s.configurationState} aria-label={t('editing.savedState')}>
    <strong>{t(feature ? feature.enabled ? 'editing.on' : 'editing.off' : 'editing.unknown')}</strong>
    {feature?.maturity&&<span>{t('featureMaturity.label')}: {t(`featureMaturity.${feature.maturity}`)}</span>}
    <span>{t('editing.configurationOnly')}</span>
    {resources.isLoading && <p role="status">{t('common.loading')}</p>}
    {resources.error && <Failure error={resources.error} retry={() => void resources.refetch()}/>}
    {issues.length > 0 && <ul>{issues.map(reason => <li key={reason}>{t(`editing.${reason}`)}</li>)}</ul>}
  </aside>
}
