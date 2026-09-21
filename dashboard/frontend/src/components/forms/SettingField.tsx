import { useTranslation } from 'react-i18next'
import { ResourceSelect } from '../ResourcePicker'
import { Toggle, Field } from './Fields'
import type { SettingFieldProps } from '../feature/ModuleSettings'
import s from '../../styles/App.module.css'

export type FieldOptions = { label: string; options?: { value: string; label: string }[]; template?: { variables: readonly string[]; maxLength: number; multiline?: boolean } }
export function SettingField({ name, value, channels, roles, onChange, label, options, template }: SettingFieldProps & FieldOptions) {
  const { t } = useTranslation('common')
  if (typeof value === 'boolean') return <Toggle label={label} checked={value} onChange={onChange}/>
  if (options) return <Field label={label}><select value={String(value ?? options[0]?.value ?? '')} onChange={event => onChange(event.currentTarget.value)}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
  if (name.endsWith('_channel_id')) return <ResourceSelect label={label} value={value} items={channels.filter(item => item.type !== 4)} onChange={onChange}/>
  if (name.endsWith('_role_id')) return <ResourceSelect label={label} value={value} items={roles} onChange={onChange}/>
  return <label className={s.field}><span>{label}</span>
    {template?.multiline ? <textarea value={String(value ?? '')} maxLength={template.maxLength} onChange={event => onChange(event.currentTarget.value)}/> : <input value={String(value ?? '')} maxLength={template?.maxLength} onChange={event => onChange(event.currentTarget.value)}/>}
    {template && <span className={s.templateHelp}><strong>{t('template.available')}</strong>{template.variables.map(variable => <span key={variable}><code>{`{${variable}}`}</code><span>{t(`template.variables.${variable}`)}</span></span>)}</span>}
  </label>
}
