import { Link, matchPath, NavLink, useLocation, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { FeatureDefinition } from '../features/contracts'
import { featureRegistry } from '../features/registry'
import s from '../styles/App.module.css'

export function WorkspaceNavigation({ definition, staffOnly }: { definition: FeatureDefinition; staffOnly: boolean }) {
  const { guildId = '' } = useParams()
  const { pathname } = useLocation()
  const { t } = useTranslation([...definition.namespaces])
  const pages = definition.pages.filter(page => !staffOnly || page.access === 'ticket_staff')
  if (!pages.length) return null
  const base = featureRegistry.path(guildId, definition.id)
  const active = pages.find(page => matchPath(`${base}/${page.path}${page.nested ? '/*' : ''}`, pathname))
  const seenGroups = new Set<string>()
  const primary = pages.filter(page => {
    if (!page.group) return true
    if (seenGroups.has(page.group.id)) return false
    seenGroups.add(page.group.id)
    return true
  })
  return <div className={s.featureNavigation}>
    <nav aria-label={t('common.featureNavigation')}>
      <Link className={s.secondaryButton} to={base} aria-current={!active ? 'page' : undefined}>{t(definition.homeTitleKey ?? 'nav.overview')}</Link>
      {primary.map(page => page.group
        ? <Link key={page.group.id} className={s.secondaryButton} to={`${base}/${page.path}`} aria-current={active?.group?.id === page.group.id ? 'page' : undefined}>{t(page.group.titleKey)}</Link>
        : <NavLink key={page.id} end={!page.nested} className={page.kind === 'action' ? s.primaryButton : s.secondaryButton} to={`${base}/${page.path}`}>{t(page.titleKey)}</NavLink>)}
    </nav>
    {active?.group && <nav aria-label={t(active.group.titleKey)}>
      {pages.filter(page => page.group?.id === active.group!.id).map(page => <NavLink key={page.id} end={!page.nested} className={s.secondaryButton} to={`${base}/${page.path}`}>{t(page.titleKey)}</NavLink>)}
    </nav>}
  </div>
}
