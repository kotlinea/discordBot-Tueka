import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { Resource, SocialSubscription, SocialTemplate } from "../../types"
import s from "../../styles/App.module.css"
import { Loading, Failure, SectionHead, Status, Empty } from "../../components/Feedback"
import { socialNames } from "./catalog"
import { SocialEditor } from "./Editor"



export function SocialProviderPage() {
  const { guildId = '', provider = '' } = useParams(); const { t } = useTranslation(['social', 'common']); const queryClient = useQueryClient(); const [editing,setEditing] = useState<SocialSubscription|null|undefined>(undefined)
  const query = useQuery({ queryKey: ['socialSubscriptions',guildId,provider], queryFn: () => request("GET /api/v1/guilds/{guild_id}/social/{provider}/subscriptions", `/guilds/${guildId}/social/${provider}/subscriptions`), refetchInterval: 5000 })
  const resources = useQuery({ queryKey: ['resources',guildId], queryFn: () => request("GET /api/v1/guilds/{guild_id}/resources", `/guilds/${guildId}/resources`) })
  const remove = useMutation({ mutationFn: (item:SocialSubscription) => request("DELETE /api/v1/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}", `/guilds/${guildId}/social/${provider}/subscriptions/${item.id}`, { method:'DELETE', headers:{'if-match':String(item.revision)} }), onSuccess: () => queryClient.invalidateQueries({queryKey:['socialSubscriptions',guildId,provider]}) })
  const retry = useMutation({ mutationFn: (item:SocialSubscription) => request("POST /api/v1/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}/retry", `/guilds/${guildId}/social/${provider}/subscriptions/${item.id}/retry`, {method:'POST'}), onSuccess: () => queryClient.invalidateQueries({queryKey:['socialSubscriptions',guildId,provider]}) })
  if (query.isLoading || resources.isLoading) return <Loading/>; if (query.error || resources.error) return <Failure error={query.error || resources.error}/>
  const data = query.data!; const unofficial = ['tiktok','instagram'].includes(provider)
  return <main className={s.page}><SectionHead title={`${socialNames[provider] || provider} ${t('social.title')}`} description={t('social.subtitle')} actions={<button className={s.primaryButton} disabled={!data.available || data.items.length>=data.limit} onClick={() => setEditing(null)}><Plus/>{t('social.add')}</button>}/>{unofficial && <div className={s.permissionNotice}><AlertTriangle/><div><strong>{t('social.unofficial')}</strong><p>{t('social.unofficialBody')}</p></div></div>}{!data.available && <div className={s.failure}><AlertTriangle/><div><strong>{t('social.setupRequired')}</strong><p>{t('social.workerOfflineBody')}</p></div></div>}{data.items.length ? <div className={s.socialList}>{data.items.map(item => { const target=item.target; const status=item.enabled?(target?.status || item.status):'disabled'; return <article key={item.id}><div className={s.socialIdentity}>{target?.avatar_url ? <img src={target.avatar_url} alt=""/> : <span>{(target?.display_name || item.account_id).slice(0,1).toUpperCase()}</span>}<div><strong>{target?.display_name || item.account_id}</strong><small>@{target?.handle || item.account_id}</small></div></div><div><Status active={status==='active'}>{status==='disabled'?t('common.disabled'):t(`social.${status==='active'?'active':status==='pending'?'pending':status==='degraded'?'degraded':'error'}`)}</Status>{(target?.last_error || item.last_error) && <small className={s.socialError}>{target?.last_error || item.last_error}</small>}</div><div className={s.socialDestinations}><span>{t('social.defaultChannel')}</span><code>#{item.channel_id}</code><small>{item.events.map(event => t(`social.${event}`)).join(' · ')}</small></div><div className={s.rowActions}><button onClick={() => setEditing(item)}>{t('common.edit')}</button>{item.enabled&&status!=='active' && <button onClick={() => retry.mutate(item)}>{t('social.retry')}</button>}<button onClick={() => { if (window.confirm(`${target?.display_name || item.account_id}`)) remove.mutate(item) }}><Trash2/>{t('common.remove')}</button></div></article>})}</div> : <Empty title={t('social.empty')} body={t('social.emptyBody')} action={data.available && <button className={s.primaryButton} onClick={() => setEditing(null)}><Plus/>{t('social.add')}</button>}/>} {editing !== undefined && <SocialEditor guildId={guildId} provider={provider} data={data} resources={resources.data!} initial={editing} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); await queryClient.invalidateQueries({queryKey:['socialSubscriptions',guildId,provider]}); await queryClient.invalidateQueries({queryKey:['social',guildId]}) }}/>}</main>
}

export type SocialListResponse = { items: SocialSubscription[]; available: boolean; events: string[]; limit: number; variables: string[]; defaults: Record<string,SocialTemplate> }
