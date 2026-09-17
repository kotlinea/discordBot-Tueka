import type { ReactNode } from 'react'
import { Save } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import s from '../styles/App.module.css'

export function SaveBar({ count, pending, error, onDiscard, onSave, title, disabled = false, form, actions, countLabel }: {
  count?: number; pending: boolean; error?: unknown; onDiscard: () => void; onSave?: () => void;
  title?: string; disabled?: boolean; form?: string; actions?: ReactNode; countLabel?: string
}) {
  const { t } = useTranslation('common')
  const label = title || t('common.unsaved')
  return <div className={s.saveBar} role="region" aria-label={label}>
    <div><strong>{label}</strong>{count !== undefined && <span>{countLabel || t('common.changeCount', { count })}</span>}</div>
    {Boolean(error) && <span role="alert">{error instanceof Error ? error.message : String(error)}</span>}
    <button type="button" className={s.secondaryButton} onClick={onDiscard} disabled={pending}>{t('common.discard')}</button>
    {actions}
    <button type={form ? 'submit' : 'button'} form={form} className={s.primaryButton} disabled={pending || disabled} onClick={onSave}>
      {pending ? <span className={s.spinner}/> : <Save/>}{t('common.save')}
    </button>
  </div>
}
