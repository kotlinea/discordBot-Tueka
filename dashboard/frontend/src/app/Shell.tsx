import { lazy, Suspense, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, LayoutDashboard, Menu, Settings, X } from 'lucide-react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request } from '../api'
import type { Session } from '../types'
import s from '../styles/App.module.css'
import { Loading, Failure, NotFound } from '../components/Feedback'
import type { BreadcrumbItem } from './Navigation'
import { dashboardNamespaces, featureBreadcrumbs, featureLabel, featurePath, groupFeatures, guildIcon, presentationGroups } from '../routing/catalog'
import { featureRegistry } from '../features/registry'
import { RegisteredFeatures } from '../routing/RegisteredFeatures'
import { CommandPalette, Breadcrumbs } from './Navigation'
import { DocsLink, AccountIdentity, LogoutButton } from './Account'
import { PreferencesDialog } from './Preferences'

const GuildOverview = lazy(() => import('./guilds/Overview').then(module => ({ default: module.GuildOverview })))
const ServerSettings = lazy(() => import('./guilds/Settings').then(module => ({ default: module.ServerSettings })))
const staffFeatures = featureRegistry.features.filter(feature => feature.access === 'ticket_staff')

export function Shell({ session }: { session: Session }) {
  const { guildId = '' } = useParams()
  const { t } = useTranslation(dashboardNamespaces)
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const guilds = useQuery({ queryKey: ['guilds'], queryFn: () => request('GET /api/v1/guilds', '/guilds') })
  const currentGuild = guilds.data?.items.find(item => item.id === guildId)
  const staffOnly = currentGuild?.access === 'ticket_staff'
  const base = `/servers/${guildId}`
  const needsOverview = location.pathname.replace(/\/$/, '') === base && !staffOnly
  const overview = useQuery({ queryKey: ['overview', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/overview', `/guilds/${guildId}/overview`), enabled: Boolean(currentGuild) && needsOverview })
  const metadata = useQuery({ queryKey: ['features', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/features', `/guilds/${guildId}/features`), enabled: Boolean(currentGuild) && !staffOnly })
  if (guilds.isLoading) return <Loading/>
  if (guilds.error) return <Failure error={guilds.error}/>
  if (!currentGuild) return <NotFound/>
  if ((!staffOnly && metadata.isLoading) || (needsOverview && overview.isLoading)) return <Loading/>
  if ((!staffOnly && metadata.error) || (needsOverview && overview.error)) return <Failure error={metadata.error || overview.error}/>
  const features = staffOnly ? [] : metadata.data?.items || []
  const hasGuildChild = location.pathname.replace(/\/$/, '') !== base
  const breadcrumbItems: BreadcrumbItem[] = [
    { label: 'Servers', to: '/servers' },
    { label: currentGuild?.name || guildId, to: hasGuildChild ? base : undefined },
    ...(location.pathname === `${base}/settings` ? [{ label: t('nav.settings') }] : featureBreadcrumbs(location.pathname, guildId, features, t)),
  ]
  const nav = <>
    <a className={s.railBrand} href="/"><span>T</span><strong>Tueka</strong></a>
    <nav aria-label="Dashboard">{staffOnly ? staffFeatures.map(feature => {
      const Icon = feature.icon
      return <NavLink key={feature.id} to={featurePath(guildId, feature)}>{Icon && <Icon/>}{featureLabel(feature, features, t)}</NavLink>
    }) : <>
      <NavLink end to={base}><LayoutDashboard/>{t('nav.overview')}</NavLink>
      <NavLink to={`${base}/settings`}><Settings/>{t('nav.settings')}</NavLink>
      {presentationGroups.map(category => {
        const Icon = category.icon
        const items = groupFeatures(category.id, features)
        return items.length ? <div className={s.navGroup} key={category.id}><p>{Icon && <Icon/>}{t(category.titleKey)}</p>{items.map(item => <NavLink key={item.id} to={featurePath(guildId, item)}>{featureLabel(item, features, t)}</NavLink>)}</div> : null
      })}
    </>}</nav>
  </>
  return <div className={`${s.shell} ${session.preferences.navigation_collapsed ? s.shellCollapsed : ''}`}>
    <aside className={s.rail}>{nav}</aside>
    <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.mobileNav} aria-describedby={undefined}><Dialog.Title className={s.srOnly}>Navigation</Dialog.Title><Dialog.Close className={s.mobileClose}><X/></Dialog.Close>{nav}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <div className={s.workspace}>
      <header className={s.topbar}>
        <button className={s.mobileMenu} onClick={() => setMobileOpen(true)} aria-label="Navigation"><Menu/></button>
        <Link to="/servers" className={s.guildSelector}>{currentGuild && guildIcon(currentGuild) ? <img src={guildIcon(currentGuild)!} alt=""/> : <span>{currentGuild?.name.slice(0, 1)}</span>}<strong>{currentGuild?.name}</strong><ChevronRight/></Link>
        {!staffOnly && <CommandPalette guildId={guildId} features={features}/>}
        <div className={s.topActions}><DocsLink/><PreferencesDialog session={session}/><AccountIdentity session={session}/><LogoutButton/></div>
      </header>
      <Breadcrumbs items={breadcrumbItems}/>
      <Suspense fallback={<Loading/>}><Routes>
        <Route index element={staffOnly ? (staffFeatures[0] ? <Navigate to={featurePath(guildId, staffFeatures[0])} replace/> : <NotFound/>) : <GuildOverview features={features} moderation={overview.data?.moderation || { summary: {}, events: [], lockdown: null }}/>}/>
        {!staffOnly && <Route path="settings" element={<ServerSettings features={features}/>}/>}
        <Route path="*" element={<RegisteredFeatures features={features} staffOnly={staffOnly}/>}/>
      </Routes></Suspense>
    </div>
  </div>
}
