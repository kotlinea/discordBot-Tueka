import { useTranslation } from 'react-i18next'
import type { Resource } from "../types"
import s from "../styles/App.module.css"



export function selectedIds(value: unknown) { return Array.isArray(value) ? value.map(String) : value === null || value === undefined || value === '' ? [] : [String(value)] }

export function ResourceSelect({ label, value, items, multiple = false, onChange, hint, native = false }: { label: string; value: unknown; items: Resource[]; multiple?: boolean; hint?: string; native?: boolean; onChange: (value: unknown) => void }) {
  const { t } = useTranslation('common')
  const selected = new Set(selectedIds(value))
  if (multiple && !native) return <fieldset className={s.resourcePicker}><legend>{label}</legend><div className={s.resourcePickerActions}><button type="button" disabled={!items.length || selected.size === items.length} onClick={() => onChange(items.map(item => String(item.id)))}>{t('common.selectAll')}</button><button type="button" disabled={!items.length} onClick={() => onChange(items.map(item => String(item.id)).filter(id => !selected.has(id)))}>{t('common.invert')}</button></div><div className={s.resourceOptions}>{items.map(item => { const id = String(item.id); return <label key={id}><input type="checkbox" checked={selected.has(id)} onChange={() => onChange(selected.has(id) ? [...selected].filter(valueId => valueId !== id) : [...selected, id])}/><span>{item.name}</span></label> })}</div><small>{hint || (items.length ? t('common.selectedCount', { count: selected.size }) : t('common.noResources'))}</small></fieldset>
  return <label className={s.field}><span>{label}</span><select multiple={multiple} value={multiple ? [...selected] : selectedIds(value)[0] || ''} onChange={event => onChange(multiple ? Array.from(event.currentTarget.selectedOptions, item => item.value).filter(Boolean) : event.currentTarget.value || null)}><option value="">{t('common.notSet')}</option>{items.map(item => <option key={String(item.id)} value={String(item.id)}>{item.name}</option>)}</select><small>{hint || t(multiple ? 'common.multiSelectHelp' : 'common.serverSelect')}</small></label>
}
