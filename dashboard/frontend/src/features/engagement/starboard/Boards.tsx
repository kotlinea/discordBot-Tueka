import {useEffect,useState} from 'react'
import {useParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import type {FeatureScreenProps} from '../../contracts'
import {request} from '../../../api'
import {Failure,Loading} from '../../../components/Feedback'
import {BoardEditor} from './BoardEditor'
import {Records} from './Records'
import s from '../../../styles/App.module.css'

export default function Boards({features}:FeatureScreenProps){
  const {guildId=''}=useParams();const {t}=useTranslation('starboard');const [selected,setSelected]=useState<number|null>(null),[editorBusy,setEditorBusy]=useState(false),[recordBusy,setRecordBusy]=useState(false)
  const busy=editorBusy||recordBusy
  useEffect(()=>{setSelected(null);setEditorBusy(false);setRecordBusy(false)},[guildId])
  const query=useQuery({queryKey:['starboards',guildId],queryFn:async()=>{
    const [boards,resources]=await Promise.all([request('GET /api/v1/guilds/{guild_id}/starboard/boards',`/guilds/${guildId}/starboard/boards`),request('GET /api/v1/guilds/{guild_id}/resources',`/guilds/${guildId}/resources`)]);return {...boards,channels:resources.channels.filter(c=>[0,5,10,11,12,15,16].includes(c.type??-1))}
  }})
  if(query.isLoading&&!query.data)return <Loading/>
  if(query.error&&!query.data)return <main className={s.page}><Failure error={query.error} retry={()=>void query.refetch()}/></main>
  const rows=query.data?.items??[],item=rows.find(board=>board.id===selected),enabled=Boolean(features.find(f=>f.id==='starboard')?.enabled)&&!query.error
  return <main className={s.page}><h1>{t('starboard.title')}</h1><p>{t('starboard.help')}</p><p>{t('starboard.limits')}</p>{!enabled&&<p>{t('starboard.disabled')}</p>}
    {query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}
    {!rows.length&&<p>{t('starboard.empty')}</p>}
    <div className={s.rowActions}><button disabled={busy||selected===null} onClick={()=>setSelected(null)}>{t('starboard.new')}</button>{rows.map(board=><button style={{whiteSpace:'normal',overflowWrap:'anywhere',maxWidth:'100%',minWidth:0}} key={board.id} disabled={busy||selected===board.id} onClick={()=>setSelected(board.id)}>{t('starboard.select')} #{board.id} · {board.config.name}</button>)}</div>
    <BoardEditor key={`editor:${guildId}:${selected??'new'}`} guildId={guildId} item={item} enabled={enabled&&!recordBusy&&(Boolean(item)||rows.length<10)} channels={query.data?.channels??[]} onBusy={setEditorBusy} onCreated={board=>setSelected(board.id)}/>
    {item&&<Records key={`records:${guildId}:${item.id}`} guildId={guildId} board={item} enabled={enabled} busy={editorBusy} onBusy={setRecordBusy}/>}
  </main>
}
