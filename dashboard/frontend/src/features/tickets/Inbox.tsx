import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ListFilter } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { TicketItem } from "../../types"
import s from "../../styles/App.module.css"
import { SectionHead, Loading, Failure, Status, Empty } from "../../components/Feedback"



export function TicketInbox(){const {guildId=''}=useParams();const {t,i18n}=useTranslation(['tickets', 'common']);const [status,setStatus]=useState('open');const query=useQuery({queryKey:['ticketItems',guildId,status],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/tickets/items', `/guilds/${guildId}/tickets/items${status?`?status=${status}`:''}`),refetchInterval:3000});return <main className={s.page}><SectionHead title={t('tickets.inbox')} description={t('tickets.inboxBody')}/><div className={s.toolbar}><label className={s.filterField}><ListFilter/><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">{t('tickets.all')}</option><option value="open">{t('tickets.open')}</option><option value="closed">{t('tickets.closed')}</option></select></label></div>{query.isLoading?<Loading/>:query.error?<Failure error={query.error}/>:query.data!.items.length?<div className={s.featureRows}>{query.data!.items.map(item=><Link key={item.id} to={String(item.id)}><div><strong>Ticket #{item.ticket_number}</strong><span>{item.mode} · {new Intl.DateTimeFormat(i18n.language,{dateStyle:'medium',timeStyle:'short'}).format(item.created_at*1000)}</span></div><Status active={item.status==='open'}>{item.status}</Status><ChevronRight/></Link>)}</div>:<Empty title={t('tickets.empty')} body={t('tickets.emptyBody')}/>}</main>}
