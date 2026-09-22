import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Plus } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../../api"
import type { TicketPanel } from "../../../types"
import s from "../../../styles/App.module.css"
import { Loading, SectionHead, Failure, Status, Empty } from "../../../components/Feedback"



export function TicketPanels(){const {guildId=''}=useParams();const {t}=useTranslation(['tickets', 'common']);const query=useQuery({queryKey:['ticketPanels',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/tickets/panels", `/guilds/${guildId}/tickets/panels`)});if(query.isLoading)return <Loading/>;return <main className={s.page}><SectionHead title={t('tickets.panels')} description={t('tickets.panelsBody')} actions={<Link className={s.primaryButton} to="new"><Plus/>{t('tickets.createPanel')}</Link>}/>{query.error?<Failure error={query.error}/>:query.data?.items.length?<div className={s.featureRows}>{query.data.items.map(item=><Link key={item.id} to={String(item.id)}><div><strong>{item.name}</strong><span>{item.mode==='channel'?'Channel':'Private Thread'} · {item.ticket_name_template}</span></div><Status active={item.enabled}>{item.enabled?t('common.enabled'):t('common.disabled')}</Status><ChevronRight/></Link>)}</div>:<Empty title={t('tickets.panels')} body={t('tickets.panelsBody')} action={<Link className={s.primaryButton} to="new"><Plus/>{t('tickets.createPanel')}</Link>}/>}</main>}
