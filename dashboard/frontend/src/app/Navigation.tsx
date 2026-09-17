import { useEffect, useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { BookOpen, ChevronRight, FileText, Gavel, MessageSquareWarning, Search, Shield, ShieldAlert } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { Feature, Guild } from "../types"
import s from "../styles/App.module.css"



import { moderationItems, featurePath, guildIcon } from '../routing/catalog'

export function CommandPalette({ guildId, features }: { guildId: string; features: Feature[] }) {
  const { t } = useTranslation(['moderation', 'social', 'common']); const navigate = useNavigate(); const [open, setOpen] = useState(false); const [term, setTerm] = useState('')
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setOpen(value => !value) } }; addEventListener('keydown', handler); return () => removeEventListener('keydown', handler) }, [])
  const items = useMemo(() => [{ title: t('nav.overview'), path: `/servers/${guildId}` }, { title: t('moderation.title'), path: `/servers/${guildId}/moderation` }, {title:t('social.title'),path:`/servers/${guildId}/social`}, ...features.filter(item => !['moderation'].includes(item.id)).map(item => ({ title: item.title, path: featurePath(guildId,item) }))].filter(item => item.title.toLocaleLowerCase().includes(term.toLocaleLowerCase())), [features, guildId, term, t])
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger asChild><button className={s.searchPill}><Search/><span>{t('nav.search')}</span><kbd>⌘ K</kbd></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.commandDialog} aria-describedby={undefined}><Dialog.Title className={s.srOnly}>{t('nav.search')}</Dialog.Title><div className={s.commandInput}><Search/><input autoFocus value={term} onChange={e => setTerm(e.target.value)} placeholder={t('nav.search')}/><kbd>Esc</kbd></div><div className={s.commandResults} aria-live="polite">{items.map(item => <button key={item.path} onClick={() => { navigate(item.path); setOpen(false); setTerm('') }}><span>{item.title}</span><ChevronRight/></button>)}{!items.length && <p>{t('common.noData')}</p>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>
}

export type BreadcrumbItem = { label: string; to?: string }

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return <nav className={s.breadcrumb} aria-label="パンくず"><ol>{items.map((item, index) => <li key={`${item.label}-${index}`}>{index > 0 && <ChevronRight aria-hidden="true"/>}{item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}</li>)}</ol></nav>
}
