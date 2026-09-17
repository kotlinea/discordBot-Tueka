import type { Resource } from "../types"
import s from "../styles/App.module.css"
import { ResourceSelect } from "./ResourcePicker"
import { useTranslation } from 'react-i18next'



export type ScopePolicy = 'only' | 'all_except'

export function PolicyChoice<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void
}) {
  return <div className={s.policyToggle} role="group" aria-label={label}>
    {options.map(option => <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>
}

export function ScopePolicyPicker({ label, policy, value, items, onPolicyChange, onChange }: { label: string; policy: ScopePolicy; value: string[]; items: Resource[]; onPolicyChange: (value: ScopePolicy) => void; onChange: (value: unknown) => void }) { const {t}=useTranslation('common'); return <section className={s.scopePolicy}><div><h3>{label}</h3><PolicyChoice label={t('common.scopePolicy',{label})} value={policy} onChange={onPolicyChange} options={[{value:'all_except',label:t('common.excludeSelected')},{value:'only',label:t('common.onlySelected')}]}/><p>{policy === 'all_except' ? t('common.excludeHelp') : t('common.onlyHelp')}</p></div><ResourceSelect label={policy === 'all_except' ? t('common.excludedItems') : t('common.includedItems')} value={value} items={items} multiple onChange={onChange}/></section> }
