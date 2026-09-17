import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import s from "../../styles/App.module.css"
import { SectionHead, Loading, Failure, Empty } from "../../components/Feedback"



export function Infractions() { const { t } = useTranslation(['moderation', 'common']); const { guildId = '' } = useParams(); const [userId,setUserId] = useState(''); const [selected,setSelected] = useState(''); const query = useQuery({ queryKey: ['infractions',guildId,selected], queryFn: () => request("GET /api/v1/guilds/{guild_id}/moderation/infractions/{user_id}", `/guilds/${guildId}/moderation/infractions/${selected}`), enabled: Boolean(selected) }); return <main className={s.page}><SectionHead title={t('moderation.infractions')} description="有効ポイント、Warning、ケース履歴をユーザー単位で確認します。"/><form className={s.userSearch} onSubmit={e => { e.preventDefault(); if (/^\d+$/.test(userId)) setSelected(userId) }}><label className={s.field}><span>DiscordユーザーID</span><input value={userId} onChange={e => setUserId(e.target.value)} inputMode="numeric"/><small>ユーザーIDを入力して履歴を取得します。</small></label><button className={s.primaryButton}><Search/>履歴を検索</button></form>{query.isLoading && <Loading/>}{query.error && <Failure error={query.error}/>} {query.data && <div className={s.infractionLayout}><section><p>有効ポイント</p><strong className={s.pointValue}>{query.data.active_points}</strong></section><section><h2>Moderation history</h2>{query.data.cases.length ? <div className={s.caseList}>{query.data.cases.map((item,index) => <article key={String(item.id || index)}><strong>Case #{String(item.id)}</strong><span>{String(item.action)} · {String(item.reason || '理由なし')}</span></article>)}</div> : <Empty title="履歴はありません" body="Warningまたは処置が記録されると表示されます。"/>}</section></div>}</main> }
