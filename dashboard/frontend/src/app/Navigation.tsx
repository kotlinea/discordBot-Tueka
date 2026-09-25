import { useEffect, useMemo, useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ChevronRight, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { Feature } from "../types"
import s from "../styles/App.module.css"



import { dashboardNamespaces, paletteItems } from '../routing/catalog'
import { focusPageHeading } from '../routing/focus'

export function CommandPalette({ guildId, features }: { guildId: string; features: Feature[] }) {
  const { t } = useTranslation(dashboardNamespaces); const navigate = useNavigate(); const [open, setOpen] = useState(false); const [term, setTerm] = useState('')
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setOpen(value => !value) } }; addEventListener('keydown', handler); return () => removeEventListener('keydown', handler) }, [])
  const chosen = useRef(false)
  const previousHeading = useRef<Element | null>(null)
  const stopFocus = useRef<() => void>(() => {})
  useEffect(() => () => stopFocus.current(), [])
  const items = useMemo(() => paletteItems(guildId, features, t).filter(item => (item.title + ' ' + (item.category ?? '')).toLocaleLowerCase().includes(term.toLocaleLowerCase())), [features, guildId, term, t])
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger asChild><button className={s.searchPill} aria-label={t('nav.search')}><Search/><span>{t('nav.search')}</span><kbd>⌘ K</kbd></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.commandDialog} aria-describedby={undefined} onCloseAutoFocus={event => { if (chosen.current) { event.preventDefault(); chosen.current = false; stopFocus.current(); requestAnimationFrame(() => { stopFocus.current = focusPageHeading(previousHeading.current) }) } }}><Dialog.Title className={s.srOnly}>{t('nav.search')}</Dialog.Title><div className={s.commandInput}><Search/><input aria-label={t('nav.search')} autoFocus value={term} onChange={e => setTerm(e.target.value)} placeholder={t('nav.search')}/><kbd>Esc</kbd></div><div className={s.commandResults} aria-live="polite">{items.map(item => <button key={item.path} onClick={() => { chosen.current = true; previousHeading.current = item.path !== window.location.pathname ? document.querySelector('[data-workspace] main h1') : null; navigate(item.path); setOpen(false); setTerm('') }}><span>{item.title}{item.category && <small>{item.category}</small>}</span><ChevronRight/></button>)}{!items.length && <p>{t('common.noData')}</p>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>
}

export type BreadcrumbItem = { label: string; to?: string }

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  const { t } = useTranslation('common')
  return <nav className={s.breadcrumb} aria-label={t('common.breadcrumbs')}><ol>{items.map((item, index) => <li key={`${item.label}-${index}`}>{index > 0 && <ChevronRight aria-hidden="true"/>}{item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current={index === items.length - 1 ? 'page' : undefined}>{item.label}</span>}</li>)}</ol></nav>
}
