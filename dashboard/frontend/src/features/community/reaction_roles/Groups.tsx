import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request } from '../../../api'
import { Failure, Loading, SectionHead } from '../../../components/Feedback'
import { LinkGroups } from './LinkGroups'
import s from '../../../styles/App.module.css'

export function ReactionRoleGroups() {
  const { guildId = '' } = useParams()
  const { t } = useTranslation(['reactionRoles', 'common'])
  const query = useQuery({ queryKey: ['reactionRoles', guildId], queryFn: () => request('GET /api/v1/guilds/{guild_id}/reaction-roles', `/guilds/${guildId}/reaction-roles`) })
  if (query.isLoading) return <Loading/>
  return <main className={s.page}>
    <SectionHead title={t('reactionRoles.linkGroups')} description={t('reactionRoles.linkBody')}/>
    {query.error ? <Failure error={query.error} retry={() => void query.refetch()}/> : <LinkGroups guildId={guildId} items={query.data!.items}/>}
  </main>
}
