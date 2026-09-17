import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { Activity, Bell, ChevronRight, LayoutDashboard, Menu, MessageSquareWarning, Settings, Shield, Users, X } from 'lucide-react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../api"
import type { Feature, Guild, ModerationEvent, Session } from "../types"
import s from "../styles/App.module.css"
import { Loading, Failure, NotFound } from "../components/Feedback"
import type { BreadcrumbItem } from "./Navigation"
import { socialNames } from "../features/social/catalog"
import { moderationItems, featurePath, guildIcon } from '../routing/catalog'
import { CommandPalette, Breadcrumbs } from "./Navigation"
import { DocsLink, AccountIdentity, LogoutButton } from "./Account"
import { PreferencesDialog } from "./Preferences"
import { lazy, Suspense } from 'react'

const ReactionRoles = lazy(() => import("../features/reaction-roles/Routes"))
const Suggestions = lazy(() => import("../features/suggestions/Settings"))
const GuildOverview = lazy(() => import("../features/guilds/Overview").then(module => ({ default: module.GuildOverview })))
const ModerationRoutes = lazy(() => import("../features/moderation/Routes").then(module => ({ default: module.ModerationRoutes })))
const SocialRoutes = lazy(() => import("../features/social/Routes").then(module => ({ default: module.SocialRoutes })))
const TicketRoutes = lazy(() => import("../features/tickets/Routes").then(module => ({ default: module.TicketRoutes })))
const ServerSettings = lazy(() => import("../features/guilds/Settings").then(module => ({ default: module.ServerSettings })))
const ModuleSettings = lazy(() => import("../features/modules/Settings").then(module => ({ default: module.ModuleSettings })))

export function Shell({ session }: { session: Session }) {
  const { guildId = '' } = useParams(); const { t } = useTranslation(['social', 'tickets', 'reactionRoles', 'suggestions', 'common']); const location = useLocation(); const [mobileOpen, setMobileOpen] = useState(false)
  const routeParts = location.pathname.split('/').filter(Boolean)
  const section = routeParts[2]
  const detail = routeParts[3]
  const ticketRoute = section === 'tickets'
  const guilds = useQuery({ queryKey: ['guilds'], queryFn: () => request("GET /api/v1/guilds", '/guilds') })
  const currentGuild = guilds.data?.items.find(item => item.id === guildId)
  const ticketOnly = currentGuild?.access === 'ticket_staff'
  const overview = useQuery({ queryKey: ['overview', guildId], queryFn: () => request("GET /api/v1/guilds/{guild_id}/overview", `/guilds/${guildId}/overview`), enabled: Boolean(guildId) && guilds.isSuccess && !ticketRoute && !ticketOnly })
  if (guilds.isLoading || (!ticketRoute && !ticketOnly && overview.isLoading)) return <Loading/>; if (guilds.error || (!ticketRoute && !ticketOnly && overview.error)) return <Failure error={guilds.error || overview.error}/>
  const features = overview.data?.features || []
  const categoryLinks = [
    ['community', t('nav.community'), Users], ['engagement', t('nav.engagement'), Activity],
  ] as const
  const breadcrumbItems: BreadcrumbItem[] = [{ label: 'Servers', to: '/servers' }]
  const hasGuildChild = Boolean(section)
  breadcrumbItems.push({ label: currentGuild?.name || guildId, to: hasGuildChild ? `/servers/${guildId}` : undefined })
  if (section === 'social') {
    breadcrumbItems.push({ label: t('nav.social'), to: detail ? `/servers/${guildId}/social` : undefined })
    if (detail) breadcrumbItems.push({ label: `${socialNames[detail] || detail} ${t('social.title')}` })
  } else if (section === 'tickets') {
    breadcrumbItems.push({ label: t('tickets.title'), to: detail ? `/servers/${guildId}/tickets` : undefined })
    if (detail) breadcrumbItems.push({ label: t(`tickets.${detail === 'panel-messages' ? 'panelMessages' : detail}`) })
  } else if (section === 'moderation') {
    breadcrumbItems.push({ label: t('nav.moderation'), to: detail ? `/servers/${guildId}/moderation` : undefined })
    if (detail) {
      const moderationKey = moderationItems.find(([id]) => id === detail)?.[1]
      const detailLabel = moderationKey ? t(moderationKey) : detail
      const hasRuleDetail = routeParts[4] === 'rules'
      breadcrumbItems.push({ label: detailLabel, to: hasRuleDetail ? `/servers/${guildId}/moderation/${detail}` : undefined })
      if (hasRuleDetail) breadcrumbItems.push({ label: routeParts[5] === 'new' ? t('common.create') : t('common.edit') })
    }
  } else if (section === 'settings') {
    breadcrumbItems.push({ label: t('nav.settings') })
  } else if (section === 'reaction-roles') {
    breadcrumbItems.push({ label: t('reactionRoles.title'), to: detail ? `/servers/${guildId}/reaction-roles` : undefined })
    if (detail) breadcrumbItems.push({ label: detail === 'new' ? t('common.create') : t('common.edit') })
  } else if (section === 'suggestions') {
    breadcrumbItems.push({ label: t('suggestions.title') })
  } else if (section === 'modules' && detail) {
    const feature = features.find(item => item.id === detail)
    breadcrumbItems.push({ label: feature?.title || detail })
  }
  const nav = <><a className={s.railBrand} href="/"><span>T</span><strong>Tueka</strong></a><nav aria-label="Dashboard">{ticketOnly?<NavLink to={`/servers/${guildId}/tickets`}><MessageSquareWarning/>{t('tickets.title')}</NavLink>:<><NavLink end to={`/servers/${guildId}`}><LayoutDashboard/>{t('nav.overview')}</NavLink><NavLink to={`/servers/${guildId}/moderation`}><Shield/>{t('nav.moderation')}</NavLink><NavLink to={`/servers/${guildId}/social`}><Bell/>{t('nav.social')}</NavLink><NavLink to={`/servers/${guildId}/settings`}><Settings/>{t('nav.settings')}</NavLink>{categoryLinks.map(([category,label,Icon]) => <div className={s.navGroup} key={category}><p><Icon/>{label}</p>{features.filter(item => item.category === category && !item.parent).map(item => <NavLink key={item.id} to={featurePath(guildId,item)}>{item.title}</NavLink>)}</div>)}</>}</nav></>
  return <div className={`${s.shell} ${session.preferences.navigation_collapsed ? s.shellCollapsed : ''}`}><aside className={s.rail}>{nav}</aside><Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.mobileNav} aria-describedby={undefined}><Dialog.Title className={s.srOnly}>Navigation</Dialog.Title><Dialog.Close className={s.mobileClose}><X/></Dialog.Close>{nav}</Dialog.Content></Dialog.Portal></Dialog.Root><div className={s.workspace}><header className={s.topbar}><button className={s.mobileMenu} onClick={() => setMobileOpen(true)} aria-label="Navigation"><Menu/></button><Link to="/servers" className={s.guildSelector}>{currentGuild && guildIcon(currentGuild) ? <img src={guildIcon(currentGuild)!} alt=""/> : <span>{currentGuild?.name.slice(0, 1)}</span>}<strong>{currentGuild?.name}</strong><ChevronRight/></Link>{!ticketOnly&&<CommandPalette guildId={guildId} features={features}/>}<div className={s.topActions}><DocsLink/><PreferencesDialog session={session}/><AccountIdentity session={session}/><LogoutButton/></div></header><Breadcrumbs items={breadcrumbItems}/><Suspense fallback={<Loading/>}><Routes><Route index element={ticketOnly?<Navigate to={`/servers/${guildId}/tickets`} replace/>:<GuildOverview features={features} moderation={overview.data?.moderation || {summary:{},events:[],lockdown:null}}/>} /><Route path="moderation/*" element={<ModerationRoutes features={features}/>} /><Route path="social/*" element={<SocialRoutes/>}/><Route path="tickets/*" element={<TicketRoutes/>}/><Route path="reaction-roles/*" element={<ReactionRoles/>}/><Route path="suggestions" element={<Suggestions/>}/><Route path="settings" element={<ServerSettings features={features}/>} /><Route path="modules/:moduleId" element={<ModuleSettings features={features}/>} /><Route path="*" element={<NotFound/>}/></Routes></Suspense></div></div>
}
