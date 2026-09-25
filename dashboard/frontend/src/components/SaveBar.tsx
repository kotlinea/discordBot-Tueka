import type { ReactNode } from 'react'
import { Save } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import s from '../styles/App.module.css'
import { Button } from './ui/Button'

export function SaveBar({ count, pending, error, onDiscard, onSave, title, disabled = false, form, actions, countLabel, inline = false, dirty = true }: {
  count?: number; pending: boolean; error?: unknown; onDiscard: () => void; onSave?: () => void;
  title?: string; disabled?: boolean; form?: string; actions?: ReactNode; countLabel?: string; inline?: boolean; dirty?: boolean
}) {
  const { t } = useTranslation('common')
  const label = dirty ? title || t('common.unsaved') : t('editing.noChanges')
  return <div className={inline ? s.dialogActions : s.saveBar} role="region" aria-label={label}>
    <div><strong>{label}</strong>{count !== undefined && <span>{countLabel || t('common.changeCount', { count })}</span>}</div>
    {Boolean(error) && <span role="alert">{error instanceof Error ? error.message : String(error)}</span>}
    <Button onClick={onDiscard} disabled={pending}>{t(dirty ? 'common.discard' : 'common.close')}</Button>
    {actions}
    <Button type={form ? 'submit' : 'button'} form={form} variant="primary" loading={pending} disabled={disabled || !dirty} onClick={onSave}>
      {!pending && <Save/>}{t('common.save')}
    </Button>
  </div>
}
