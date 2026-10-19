import {useTranslation} from 'react-i18next'
import type {InsightsDay} from '../../../types'

export const metrics=['messages','joins','leaves','voice_seconds','observed_seconds'] as const
export type Metric=typeof metrics[number]

export function Chart({days,metric}:{days:InsightsDay[];metric:Metric}){
  const {t}=useTranslation('insights')
  const maximum=Math.max(1,...days.map(day=>day[metric]??0))
  const step=600/Math.max(1,days.length)
  return <figure style={{margin:0,minWidth:0}}><figcaption>{t('insights.chart')} · {t(`insights.${metric}`)}</figcaption>
    <svg role="img" aria-label={`${t('insights.chart')} · ${t(`insights.${metric}`)}`} viewBox="0 0 640 240" style={{width:'100%',height:'auto',display:'block'}}>
      <title>{t('insights.chart')}</title><line x1={30} x2={630} y1={200} y2={200} stroke="currentColor"/>
      {days.map((day,index)=>{const value=day[metric],x=30+index*step,height=value===null?0:170*value/maximum
        return <g key={day.day}><title>{day.day}: {value===null?t('insights.unknown'):value.toLocaleString()}</title>
          {value===null?<line x1={x+step/2} x2={x+step/2} y1={190} y2={200} stroke="currentColor" strokeDasharray="2 2"/>:<rect x={x+step*.15} y={200-Math.max(1,height)} width={Math.max(1,step*.7)} height={Math.max(1,height)} fill="currentColor"/>}
        </g>})}
    </svg>
    <div style={{display:'flex',justifyContent:'space-between',gap:'1rem',flexWrap:'wrap',fontSize:'var(--text-sm)'}}><span>{days[0]?.day}</span><span>{days.at(-1)?.day}</span></div>
  </figure>
}
