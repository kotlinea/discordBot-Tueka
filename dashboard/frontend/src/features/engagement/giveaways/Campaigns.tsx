import {useEffect,useState} from 'react'
import {useParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {FeatureScreenProps} from '../../contracts'
import {request} from '../../../api'
import {Failure,Loading} from '../../../components/Feedback'
import {Editor} from './Editor'
import {History} from './History'
import s from '../../../styles/App.module.css'

export default function Campaigns({features}:FeatureScreenProps){
  const {guildId=''}=useParams();const {t}=useTranslation('giveaways')
  const [selected,setSelected]=useState<number|null>(null),[editorBusy,setEditorBusy]=useState(false),[historyBusy,setHistoryBusy]=useState(false)
  useEffect(()=>{setSelected(null);setEditorBusy(false);setHistoryBusy(false)},[guildId])
  const query=useQuery({queryKey:['giveaways',guildId],queryFn:async()=>{
    const [campaigns,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/giveaways',`/guilds/${guildId}/giveaways?limit=100`),request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)]);return {...campaigns,...resources}
  },refetchInterval:query=>query.state.data?.items.some(row=>row.id===selected&&['open','closing'].includes(row.status))?5000:false})
  if(query.isLoading&&!query.data)return <Loading/>
  if(query.error&&!query.data)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  const rows=query.data?.items??[],item=rows.find(row=>row.id===selected)
  const enabled=Boolean(features.find(f=>f.id==='giveaways')?.enabled)&&!query.error,busy=editorBusy||historyBusy
  return <main className={s.page}><h1>{t('giveaways.title')}</h1><p>{t('giveaways.help')}</p><p>{t('giveaways.limits')}</p>{!enabled&&<p>{t('giveaways.disabled')}</p>}
    {query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}{!rows.length&&<p>{t('giveaways.empty')}</p>}
    <div className={s.rowActions}><button disabled={busy||selected===null} onClick={()=>setSelected(null)}>{t('giveaways.new')}</button>{rows.map(row=><button style={{whiteSpace:'normal',overflowWrap:'anywhere',maxWidth:'100%',minWidth:0}} key={row.id} disabled={busy||selected===row.id} onClick={()=>setSelected(row.id)}>{t('giveaways.select')} #{row.id} · {row.config.title} · {t(`giveaways.status.${row.status}`)}</button>)}</div>
    <Editor key={`editor:${guildId}:${selected??'new'}`} guildId={guildId} item={item} enabled={enabled&&!historyBusy&&(Boolean(item)||rows.length<100)} channels={query.data?.channels??[]} roles={query.data?.roles??[]} onBusy={setEditorBusy} onCreated={row=>setSelected(row.id)}/>
    {item&&<History key={`history:${guildId}:${item.id}`} guildId={guildId} item={item} enabled={enabled} busy={editorBusy} onBusy={setHistoryBusy}/>}
  </main>
}
