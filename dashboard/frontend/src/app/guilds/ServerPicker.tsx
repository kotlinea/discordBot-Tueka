import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../../api"
import type { Guild, Session } from "../../types"
import s from "../../styles/App.module.css"
import { Loading, Failure } from "../../components/Feedback"
import { DocsLink, AccountIdentity, LogoutButton } from "../Account"
import { guildIcon } from '../../routing/catalog'



export function ServerPicker({ session }: { session: Session }) { const { t } = useTranslation(['tickets', 'common']); const query = useQuery({ queryKey: ['guilds'], queryFn: () => request("GET /api/v1/guilds", '/guilds') }); if (query.isLoading) return <Loading/>; if (query.error) return <Failure error={query.error} retry={() => void query.refetch()}/>; return <main className={s.serverPage}><header><a className={s.wordmark} href="/">Tueka</a><div className={s.topActions}><DocsLink/><AccountIdentity session={session}/><LogoutButton/></div></header><section className={s.serverIntro}><p>Discordサーバー管理</p><h1>管理するサーバーを選択</h1><span>設定を変更するDiscordサーバーを選んでください。</span></section><section className={s.serverList} aria-label="Servers">{query.data?.items.map(guild => <Link key={guild.id} to={`/servers/${guild.id}${guild.access==='ticket_staff'?'/tickets':''}`}>{guildIcon(guild) ? <img src={guildIcon(guild)!} alt=""/> : <span>{guild.name.slice(0,1)}</span>}<div><strong>{guild.name}</strong><small>{guild.access==='ticket_staff'?t('tickets.inbox'):t('nav.overview')}</small></div><ChevronRight/></Link>)}</section></main> }
