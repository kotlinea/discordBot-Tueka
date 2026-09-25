import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { request } from '../../api'
import type { Feature, Guild } from '../../types'
import { Failure, SectionHead } from '../../components/Feedback'
import { PermissionDiagnostics } from '../../components/PermissionDiagnostics'
import s from '../../styles/App.module.css'

export function ServerInformation({ guild, features }: { guild: Guild; features: Feature[] }) {
  const { t } = useTranslation('common')
  const resources = useQuery({ queryKey: ['resources', guild.id], queryFn: () => request('GET /api/v1/guilds/{guild_id}/resources', `/guilds/${guild.id}/resources`) })
  const missing = [...new Set(features.flatMap(feature => feature.missing_permissions))]
  return <main className={s.page}>
    <SectionHead title={t('nav.settings')} description={t('serverInfo.description')}/>
    <section className={s.protectionPanel}><dl>
      <div><dt>{t('serverInfo.name')}</dt><dd>{guild.name}</dd></div>
      <div><dt>{t('serverInfo.id')}</dt><dd><code>{guild.id}</code></dd></div>
    </dl></section>
    {resources.isLoading ? <p role="status">{t('common.loading')}</p> : resources.error ? <Failure error={resources.error} retry={() => void resources.refetch()}/> : <section className={s.protectionPanel}><dl>
      <div><dt>{t('serverInfo.channels')}</dt><dd>{resources.data!.channels.length}</dd></div>
      <div><dt>{t('serverInfo.roles')}</dt><dd>{resources.data!.roles.length}</dd></div>
    </dl></section>}
    <PermissionDiagnostics title={t('serverInfo.permissions')} messages={missing}/>
    <p className={s.sectionCopy}>{t('serverInfo.featureSettings')}</p>
  </main>
}
