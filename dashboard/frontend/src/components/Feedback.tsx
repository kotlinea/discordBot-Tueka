import { FieldErrors } from './FieldErrors'
import { AlertTriangle, CircleHelp, MoreHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import s from "../styles/App.module.css"



export function Loading() { const { t } = useTranslation(['common']); return <main className={s.centerState} aria-live="polite"><span className={s.spinner} aria-hidden="true"/><p>{t('common.loading')}</p></main> }

export function Failure({ error, retry }: { error: unknown; retry?: () => void }) { const { t } = useTranslation(['common']); const text = error instanceof Error ? error.message : String(error); return <div className={s.failure} role="alert"><AlertTriangle/><div><strong>{text}</strong><p>{t('common.checkAccess')}</p><FieldErrors error={error}/></div>{retry && <button className={s.secondaryButton} onClick={retry}>{t('common.retry')}</button>}</div> }

export function Empty({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) { return <div className={s.empty}><CircleHelp/><strong>{title}</strong><p>{body}</p>{action}</div> }

export function Status({ active, children }: { active: boolean; children: React.ReactNode }) { return <span className={active ? s.statusOn : s.statusOff}><span aria-hidden="true"/>{children}</span> }

export function SectionHead({ title, description, actions }: { title: string; description: string; actions?: React.ReactNode }) { return <header className={s.sectionHead}><div><h1>{title}</h1><p>{description}</p></div>{actions}</header> }

export function NotFound() { return <main className={s.centerState}><MoreHorizontal/><h1>ページが見つかりません</h1><Link className={s.primaryButton} to="/servers">サーバー一覧へ戻る</Link></main> }
