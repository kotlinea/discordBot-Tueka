import { useTranslation } from 'react-i18next'
import { ResourceSelect } from '../ResourcePicker'
import { Toggle, Field } from './Fields'
import type { SettingFieldProps } from '../feature/ModuleSettings'
import s from '../../styles/App.module.css'

export type FieldOptions = { label: string; resource?: 'category' | 'channel' | 'text' | 'voice' | 'role'; references?: { kind: 'channel' | 'role'; ids: (value: unknown) => string[] }; options?: { value: string; label: string }[]; template?: { variables: readonly string[]; maxLength: number; multiline?: boolean } }
export function SettingField({ name, value, channels, roles, onChange, label, options, template, resource }: SettingFieldProps & FieldOptions) {
  const { t } = useTranslation('common')
  if (typeof value === 'boolean') return <Toggle label={label} checked={value} onChange={onChange}/>
  if (options) return <Field label={label}><select value={String(value ?? options[0]?.value ?? '')} onChange={event => onChange(event.currentTarget.value)}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field>
  const multiple = name.endsWith('_ids')
  const kind = resource ?? (/_category_ids?$/.test(name) ? 'category' : /_channel_ids?$/.test(name) ? 'channel' : /_role_ids?$/.test(name) ? 'role' : undefined)
  if (kind) return <ResourceSelect label={label} value={value} multiple={multiple} items={kind === 'role' ? roles : channels.filter(item => kind === 'category' ? item.type === 4 : kind === 'text' ? item.type === 0 : kind === 'voice' ? [2, 13].includes(item.type ?? -1) : item.type !== 4)} onChange={onChange}/>
  if (Array.isArray(value)) return <Field label={label}><textarea value={value.join('\n')} onChange={event => onChange(event.currentTarget.value.split('\n').map(line => line.trim()).filter(Boolean))}/></Field>
  return <label className={s.field}><span>{label}</span>
    {template?.multiline || (!template && /template|content|format/.test(name)) ? <textarea value={String(value ?? '')} maxLength={template?.maxLength} onChange={event => onChange(event.currentTarget.value)}/> : <input type={typeof value === 'number' ? 'number' : 'text'} value={String(value ?? '')} maxLength={template?.maxLength} onChange={event => onChange(typeof value === 'number' ? Number(event.currentTarget.value) : event.currentTarget.value)}/>}
    {template && <span className={s.templateHelp}><strong>{t('template.available')}</strong>{template.variables.map(variable => <span key={variable}><code>{`{${variable}}`}</code><span>{t(`template.variables.${variable}`)}</span></span>)}</span>}
  </label>
}
