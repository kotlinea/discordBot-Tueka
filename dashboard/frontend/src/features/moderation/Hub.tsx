import { useQuery } from '@tanstack/react-query'
import { Activity, ChevronRight, LockKeyhole, Settings } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { Feature } from "../../types"
import s from "../../styles/App.module.css"
import { Loading, SectionHead, Status } from "../../components/Feedback"
import { PermissionNotice } from "../../routing/FeatureNavigation"
import { moderationItems } from './navigation'
import { EventList } from "./Events"



export function ModerationHub({ features }: { features: Feature[] }) { const { t } = useTranslation(['moderation', 'common']); const { guildId = '' } = useParams(); const overview = useQuery({ queryKey: ['overview', guildId], queryFn: () => request("GET /api/v1/guilds/{guild_id}/overview", `/guilds/${guildId}/overview`) }); if (overview.isLoading) return <Loading/>; return <main className={s.page}><SectionHead title={t('moderation.title')} description={t('moderation.subtitle')} actions={<Link className={s.secondaryButton} to={`/servers/${guildId}/modules/moderation`}><Settings/>全体設定</Link>}/><PermissionNotice features={features}/>{overview.data?.moderation.lockdown && <div className={s.lockdownBanner}><LockKeyhole/><div><strong>Lockdownが有効です</strong><p>解除予定と復元状態をActionsで確認してください。</p></div><Link to="moderation_actions">確認</Link></div>}<div className={s.moderationIndex}>{moderationItems.map(([id,key,Icon]) => { const feature = features.find(item => item.id === id); return <Link key={id} to={id}><Icon/><div><strong>{t(key)}</strong><span>{feature?.description}</span></div><Status active={feature?.enabled || false}>{feature?.enabled ? t('common.enabled') : t('common.disabled')}</Status><ChevronRight/></Link> })}</div><section className={s.activityPanel}><div className={s.panelHead}><Activity/><div><h2>{t('moderation.recent')}</h2><p>直近10件</p></div></div><EventList events={overview.data?.moderation.events || []}/></section></main> }
