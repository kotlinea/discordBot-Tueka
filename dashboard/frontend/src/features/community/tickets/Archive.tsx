import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../../api"
import type { TicketItem } from "../../../types"
import { TicketSimpleList } from "./List"



export function TicketArchive(){const {guildId=''}=useParams();const {t}=useTranslation(['tickets', 'common']);const query=useQuery({queryKey:['ticketArchive',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/tickets/items", `/guilds/${guildId}/tickets/items?status=closed`)});return <TicketSimpleList title={t('tickets.transcripts')} body={t('tickets.transcriptsBody')} loading={query.isLoading} error={query.error} items={(query.data?.items||[]).map(item=>({id:item.id,title:`Ticket #${item.ticket_number}`,body:item.closed_at?new Date(item.closed_at*1000).toLocaleString():'-',active:true,to:`/servers/${guildId}/tickets/inbox/${item.id}`}))}/>}
