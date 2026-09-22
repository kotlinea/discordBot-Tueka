import { Activity, ChevronRight, Gauge, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { Feature, ModerationEvent } from "../../types"
import s from "../../styles/App.module.css"
import { SectionHead, Status } from "../../components/Feedback"
import { PermissionNotice, FeatureNavRow } from "../../routing/FeatureNavigation"
import { moderationItems } from '../../features/moderation/navigation'
import { EventList } from "../../features/moderation/Events"



export function GuildOverview({ features, moderation }: { features: Feature[]; moderation: {summary: Record<string, unknown>; events: ModerationEvent[]; lockdown: unknown} }) {
  const { t } = useTranslation(['moderation', 'common']); const { guildId = '' } = useParams(); const enabled = features.filter(item => item.enabled)
  return <main className={s.page}><SectionHead title={t('nav.overview')} description={t('overview.description')}/><PermissionNotice features={features}/><div className={s.overviewGrid}><section className={s.protectionPanel}><div className={s.panelHead}><ShieldCheck/><div><h2>{t('moderation.protection')}</h2><p>Moderation、AutoMod、Anti-Spam、Anti-Raid</p></div></div><dl><div><dt>Moderation</dt><dd><Status active={features.find(item => item.id === 'moderation')?.enabled || false}>{features.find(item => item.id === 'moderation')?.enabled ? t('common.enabled') : t('common.disabled')}</Status></dd></div>{moderationItems.slice(0,3).map(([id,key]) => <div key={id}><dt>{t(key)}</dt><dd><Status active={features.find(item => item.id === id)?.enabled || false}>{features.find(item => item.id === id)?.enabled ? t('common.enabled') : t('common.disabled')}</Status></dd></div>)}</dl><Link className={s.textLink} to={`/servers/${guildId}/moderation`}>{t('overview.check')}<ChevronRight/></Link></section><section className={s.activityPanel}><div className={s.panelHead}><Activity/><div><h2>{t('moderation.recent')}</h2><p>{t('overview.activity')}</p></div></div><EventList events={moderation.events} compact/></section></div><section className={s.featureIndex}><div className={s.panelHead}><Gauge/><div><h2>{t('overview.enabled')}</h2><p>{t('overview.enabledDescription')}</p></div></div><div className={s.featureRows}>{enabled.map(item => <FeatureNavRow key={item.id} item={item} guildId={guildId} status={t('common.enabled')}/>)}</div></section></main>
}
