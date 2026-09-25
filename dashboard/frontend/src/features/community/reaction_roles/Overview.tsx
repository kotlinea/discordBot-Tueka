import { useSaveMutation } from '../../../components/forms/useSaveMutation'




import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Settings, Trash2, Wrench } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request } from "../../../api"

import type { ReactionRoleMessage } from "../../../types"
import s from "../../../styles/App.module.css"
import { Loading, Failure, Empty, Status, SectionHead } from '../../../components/Feedback'
import { SettingsDialog } from './SettingsDialog'


export function ReactionRoleOverview({ settingsDialog = false }: { settingsDialog?: boolean }){
  const {guildId=''}=useParams();const {t}=useTranslation(['tickets', 'reactionRoles', 'common']);const queryClient=useQueryClient();const navigate=useNavigate();const closeSettings=()=>navigate(`/servers/${guildId}/reaction-roles`)
  const query=useQuery({queryKey:['reactionRoles',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/reaction-roles", `/guilds/${guildId}/reaction-roles`)})
  const resources=useQuery({queryKey:['resources',guildId],queryFn:()=>request("GET /api/v1/guilds/{guild_id}/resources", `/guilds/${guildId}/resources`)})
  const fix=useSaveMutation({mutationFn:(id:number)=>request("POST /api/v1/guilds/{guild_id}/reaction-roles/messages/{config_id}/fix", `/guilds/${guildId}/reaction-roles/messages/${id}/fix`, {method:'POST'}),onSuccess:()=>queryClient.invalidateQueries({queryKey:['reactionRoles',guildId]})})
  const remove=useSaveMutation({mutationFn:(item:ReactionRoleMessage)=>request("DELETE /api/v1/guilds/{guild_id}/reaction-roles/messages/{config_id}", `/guilds/${guildId}/reaction-roles/messages/${item.id}`, {method:'DELETE',headers:{'if-match':String(item.revision||0)}}),onSuccess:()=>queryClient.invalidateQueries({queryKey:['reactionRoles',guildId]})})
  if(query.isLoading||resources.isLoading)return <Loading/>;if((query.error&&!query.data)||(resources.error&&!resources.data))return <main className={s.page}><Failure error={query.error||resources.error} retry={()=>{void query.refetch();void resources.refetch()}}/></main>;const data=query.data!;const channelName=(id:string|null)=>resources.data?.channels.find(channel=>channel.id===id)?.name||(id?t('editing.missingResource')+': '+id:t('tickets.notSelected'))
  return <main className={s.page}>{(query.error||resources.error)&&<Failure error={query.error||resources.error} retry={()=>{void query.refetch();void resources.refetch()}}/>}{(fix.error||remove.error)&&<Failure error={fix.error||remove.error}/>}<SectionHead title={t('reactionRoles.title')} description={t('reactionRoles.subtitle')}/>
    <section className={s.rrStatus}><div><strong>{t('reactionRoles.enabled')}</strong><Status active={data.settings.enabled}>{data.settings.enabled?t('common.enabled'):t('common.disabled')}</Status></div><div><strong>{t('reactionRoles.published')}</strong><span>{data.summary.active}</span></div><div><strong>{t('reactionRoles.needsAttention')}</strong><span>{data.summary.pending+data.summary.failed}</span></div><div><strong>{t('reactionRoles.scheduled')}</strong><span>{data.summary.scheduled}</span></div></section>
    {data.items.length?<section className={s.rrList} aria-label={t('reactionRoles.messages')}>{data.items.map(item=><article key={item.id}><div><strong>{item.name}</strong><span>{item.embed.title}</span></div><div><Status active={data.settings.enabled&&item.enabled&&item.status==='active'}>{item.locked?t('reactionRoles.locked'):!item.enabled?t('editing.off'):item.status==='active'?t('reactionRoles.published'):item.status||t('editing.unknown')}</Status><small>{t(`reactionRoles.types.${item.behavior_type}`)} · {item.mappings.length}{t('reactionRoles.mappingUnit')}</small></div><span>{channelName(item.channel_id)}</span><div className={s.rowActions}><button disabled={fix.isPending||remove.isPending} onClick={()=>fix.mutate(item.id!)}><Wrench/>{t('reactionRoles.fix')}</button><Link to={`/servers/${guildId}/reaction-roles/${item.id}`}><Settings/>{t('common.edit')}</Link><button disabled={fix.isPending||remove.isPending} onClick={()=>{if(confirm(t('editing.deleteConfirm',{count:1})+' '+item.name))remove.mutate(item)}}><Trash2/>{t('common.remove')}</button></div>{item.last_error&&<small className={s.socialError}>{item.last_error}</small>}</article>)}</section>:<Empty title={t('reactionRoles.empty')} body={t('reactionRoles.emptyBody')} action={<Link className={s.primaryButton} to={`/servers/${guildId}/reaction-roles/new`}><Plus/>{t('reactionRoles.create')}</Link>}/>}
    {settingsDialog&&<SettingsDialog guildId={guildId} initial={data.settings} onClose={closeSettings} onSaved={async()=>{await query.refetch();closeSettings()}}/>}
  </main>
}

export function ReactionRoleSettingsPage() { return <ReactionRoleOverview settingsDialog/> }
