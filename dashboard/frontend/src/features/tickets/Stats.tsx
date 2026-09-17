import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import s from "../../styles/App.module.css"
import { Loading, Failure, SectionHead } from "../../components/Feedback"



export function TicketStats(){const {guildId=''}=useParams();const {t}=useTranslation(['tickets', 'common']);const query=useQuery({queryKey:['ticketStats',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/tickets/stats", `/guilds/${guildId}/tickets/stats`)});if(query.isLoading)return <Loading/>;if(query.error)return <main className={s.page}><Failure error={query.error}/></main>;return <main className={s.page}><SectionHead title={t('tickets.stats')} description={t('tickets.statsBody')}/><section className={s.protectionPanel}><dl><div><dt>{t('tickets.open')}</dt><dd>{query.data!.summary.open}</dd></div><div><dt>{t('tickets.unclaimed')}</dt><dd>{query.data!.summary.unclaimed}</dd></div><div><dt>{t('tickets.closed30')}</dt><dd>{query.data!.summary.closed_30d}</dd></div></dl></section><div className={s.featureRows}>{query.data!.panels.map(item=><div className={s.ruleRow} key={item.id}><div><strong>{item.name}</strong></div><span>Total {item.total} · Open {item.open} · Closed {item.closed}</span><span>{item.average_resolution_seconds==null?'-':`${Math.round(item.average_resolution_seconds/60)} min`}</span></div>)}</div></main>}
