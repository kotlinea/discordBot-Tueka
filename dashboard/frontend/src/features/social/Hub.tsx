import { socialNames } from './catalog'
import { useQuery } from '@tanstack/react-query'
import { Activity, ChevronRight } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { SocialProviderSummary } from "../../types"
import s from "../../styles/App.module.css"
import { Loading, Failure, SectionHead, Status } from "../../components/Feedback"



export function SocialHub() {
  const { guildId = '' } = useParams(); const { t } = useTranslation(['social', 'common']); const query = useQuery({ queryKey: ['social',guildId], queryFn: () => request("GET /api/v1/guilds/{guild_id}/social", `/guilds/${guildId}/social`), refetchInterval: 10000 })
  if (query.isLoading) return <Loading/>; if (query.error) return <Failure error={query.error} retry={() => void query.refetch()}/>
  return <main className={s.page}><SectionHead title={t('social.title')} description={t('social.subtitle')}/><div className={query.data?.worker.online ? s.workerOnline : s.workerOffline}><Activity/><div><strong>{t(query.data?.worker.online ? 'social.workerOnline' : 'social.workerOffline')}</strong><p>{t(query.data?.worker.online ? 'social.workerOnlineBody' : 'social.workerOfflineBody')}</p></div></div><div className={s.socialGrid}>{query.data?.providers.map(provider => <Link key={provider.id} to={provider.id} className={s.socialCard}><div className={s.socialMark}>{socialNames[provider.id]?.slice(0,1)}</div><div><strong>{socialNames[provider.id]}</strong><span>{provider.count} / {provider.limit} {t('social.accounts')}</span></div><Status active={provider.available}>{t(provider.available ? 'social.available' : 'social.setupRequired')}</Status><ChevronRight/></Link>)}</div></main>
}
