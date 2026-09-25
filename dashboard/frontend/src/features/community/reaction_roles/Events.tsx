import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request } from '../../../api'
import { Empty, Failure, Loading, SectionHead } from '../../../components/Feedback'
import s from '../../../styles/App.module.css'

export function ReactionRoleEvents() {
  const { guildId = '' } = useParams()
  const { t, i18n } = useTranslation(['reactionRoles', 'common'])
  const query = useQuery({ queryKey: ['reactionRoleEvents', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/reaction-roles/events', `/guilds/${guildId}/reaction-roles/events?limit=20`) })
  if (query.isLoading) return <Loading/>
  return <main className={s.page}>
    <SectionHead title={t('reactionRoles.audit')} description={t('reactionRoles.auditBody')}/>
    {query.error ? <Failure error={query.error} retry={() => void query.refetch()}/> : query.data!.items.length ? <div className={s.events}>{query.data!.items.map(event => <article key={event.id}>
      <div className={s.eventMarker}/><div>
        <div className={s.eventMeta}><span>{event.result}</span><time>{new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(event.created_at * 1000)}</time></div>
        <strong>{event.event_type}</strong><p>{event.reason || `Event #${event.id}`}</p>
      </div>
    </article>)}</div> : <Empty title={t('common.noData')} body={t('reactionRoles.noEvents')}/>}
  </main>
}
