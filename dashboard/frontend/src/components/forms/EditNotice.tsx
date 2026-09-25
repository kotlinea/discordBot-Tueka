import { useTranslation } from 'react-i18next'
import s from '../../styles/App.module.css'

export function EditNotice({ dirty, changedRemotely = false, saved = false }: { dirty: boolean; changedRemotely?: boolean; saved?: boolean }) {
  const { t } = useTranslation('common')
  if (!dirty && !saved) return null
  return <p className={s.sectionCopy} role="status">{t(changedRemotely ? 'editing.remoteChanged' : dirty ? 'common.unsaved' : 'editing.saved')}</p>
}
