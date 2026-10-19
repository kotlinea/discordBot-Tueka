import {useState} from 'react'
import {useParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {useTranslation} from 'react-i18next'
import {request} from '../../../api'
import {Failure,Loading} from '../../../components/Feedback'
import {Chart,metrics} from './Chart'
import type {Metric} from './Chart'
import s from '../../../styles/App.module.css'

export default function Report(){
  const {guildId=''}=useParams();const {t}=useTranslation('insights')
  const [start,setStart]=useState(''),[end,setEnd]=useState(''),[range,setRange]=useState(''),[metric,setMetric]=useState<Metric>('messages')
  const query=useQuery({queryKey:['insights',guildId,'report',range],queryFn:()=>request('GET /api/v1/guilds/{guild_id}/insights',`/guilds/${guildId}/insights${range}`),refetchInterval:30000})
  const data=query.data,days=data?.days??[]
  return <main className={s.page}><h1>{t('insights.title')}</h1><p>{t('insights.help')}</p><p>{t('insights.utc')}</p>
    <form className={s.applicationSection} onSubmit={e=>{
      e.preventDefault()
      const first=start||days[0]?.day||'',last=end||days.at(-1)?.day||''
      setStart(first);setEnd(last)
      setRange(`?${new URLSearchParams({start:first,end:last})}`)
    }}>
      <label className={s.field}>{t('insights.start')}<input type="date" required value={start||days[0]?.day||''} onChange={e=>setStart(e.target.value)}/></label>
      <label className={s.field}>{t('insights.end')}<input type="date" required value={end||days.at(-1)?.day||''} onChange={e=>setEnd(e.target.value)}/></label>
      <button disabled={query.isFetching}>{t('insights.apply')}</button>
    </form>
    {query.isLoading&&!data&&<Loading/>}{query.error&&<Failure error={query.error} retry={()=>void query.refetch()}/>}
    {data&&<section className={s.applicationSection} aria-label={t('insights.home')}><h2>{t('insights.home')}</h2>
      <p role="status">{t(!data.enabled?'insights.off':data.collecting?'insights.collecting':'insights.waiting')}</p>
      {data.last_observed!==null&&<p style={{overflowWrap:'anywhere'}}>{t('insights.lastObserved')}: <time dateTime={new Date(data.last_observed*1000).toISOString()}>{new Date(data.last_observed*1000).toISOString()}</time></p>}<p>{t('insights.coverage')}</p>
      {!days.some(day=>day.observed)&&<p>{t('insights.noData')}</p>}
      <label className={s.field}>{t('insights.metric')}<select value={metric} onChange={e=>setMetric(e.target.value as Metric)}>{metrics.map(key=><option key={key} value={key}>{t(`insights.${key}`)}</option>)}</select></label>
      <Chart days={days} metric={metric}/>
      <div style={{maxWidth:'100%',overflowX:'auto'}} tabIndex={0} role="region" aria-label={t('insights.table')}><table style={{width:'100%',minWidth:'42rem',whiteSpace:'nowrap',borderCollapse:'collapse'}}><caption>{t('insights.table')} · {days[0]?.day} — {days.at(-1)?.day}</caption>
        <thead><tr><th scope="col">{t('insights.day')}</th>{metrics.map(key=><th scope="col" key={key}>{t(`insights.${key}`)}</th>)}</tr></thead>
        <tbody>{days.map(day=><tr key={day.day}><th scope="row">{day.day}</th>{metrics.map(key=><td key={key}>{day[key]===null?t('insights.unknown'):day[key]?.toLocaleString()}</td>)}</tr>)}</tbody>
      </table></div>
    </section>}
  </main>
}
