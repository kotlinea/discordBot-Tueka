import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronRight, FileText, Gauge, MessageSquareWarning } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { TicketItem, TicketSettings } from "../../types"
import s from "../../styles/App.module.css"
import { Loading, Failure, SectionHead } from "../../components/Feedback"
import { ticketSections } from "./catalog"



export function TicketHub() {
  const {guildId=''}=useParams(); const {t}=useTranslation(['tickets', 'common']); const query=useQuery({queryKey:['tickets',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/tickets", `/guilds/${guildId}/tickets`),refetchInterval:5000})
  if(query.isLoading)return <Loading/>; if(query.error)return <main className={s.page}><Failure error={query.error}/></main>; const data=query.data!
  return <main className={s.page}><SectionHead title={t('tickets.title')} description={t('tickets.subtitle')} actions={<Link className={s.primaryButton} to="inbox"><MessageSquareWarning/>{t('tickets.inbox')}</Link>}/>{!data.transcript_storage.available&&<div className={s.failure}><AlertTriangle/><div><strong>{t('tickets.keyMissing')}</strong><p>TICKET_ENCRYPTION_KEY</p></div></div>}<section className={s.protectionPanel}><div className={s.panelHead}><Gauge/><div><h2>{t('tickets.current')}</h2></div></div><dl><div><dt>{t('tickets.open')}</dt><dd className={s.numeric}>{data.summary.open}</dd></div><div><dt>{t('tickets.unclaimed')}</dt><dd className={s.numeric}>{data.summary.unclaimed}</dd></div><div><dt>{t('tickets.closed30')}</dt><dd className={s.numeric}>{data.summary.closed_30d}</dd></div></dl></section><div className={s.moderationIndex}>{ticketSections.filter(([path])=>data.can_manage||['inbox','transcripts'].includes(path)).map(([path,label])=><Link key={path} to={path}><FileText/><div><strong>{t(`tickets.${path==='panel-messages'?'panelMessages':path}`,label)}</strong><span>{t(`tickets.${path==='panel-messages'?'panelMessagesBody':`${path}Body`}`,'')}</span></div><ChevronRight/></Link>)}</div></main>
}
