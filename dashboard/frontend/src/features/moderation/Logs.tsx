import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ListFilter } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { ModerationEvent } from "../../types"
import s from "../../styles/App.module.css"
import { SectionHead, Loading, Failure } from "../../components/Feedback"
import { EventList } from "./Events"



export function Logs() { const { t } = useTranslation(['moderation', 'common']); const { guildId = '' } = useParams(); const [family,setFamily] = useState(''); const query = useQuery({ queryKey: ['events',guildId,family], queryFn: () => request("GET /api/v1/guilds/{guild_id}/moderation/events", `/guilds/${guildId}/moderation/events?limit=100${family ? `&family=${family}` : ''}`) }); return <main className={s.page}><SectionHead title={t('moderation.logs')} description="検知、制裁、管理操作の履歴を確認します。"/><div className={s.toolbar}><label className={s.filterField}><ListFilter/><span className={s.srOnly}>Family</span><select value={family} onChange={e => setFamily(e.target.value)}><option value="">すべて</option><option value="automod">AutoMod</option><option value="anti_spam">Anti-Spam</option><option value="anti_raid">Anti-Raid</option></select></label></div>{query.isLoading ? <Loading/> : query.error ? <Failure error={query.error}/> : <EventList events={query.data?.items || []}/>}</main> }
