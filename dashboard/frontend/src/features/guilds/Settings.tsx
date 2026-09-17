import { useParams } from 'react-router-dom'
import type { Feature } from "../../types"
import s from "../../styles/App.module.css"
import { SectionHead } from "../../components/Feedback"
import { FeatureNavRow } from "./FeatureNavigation"



export function ServerSettings({ features }: { features: Feature[] }) {
  const { guildId = '' } = useParams()
  const modules = features.filter(item => !item.parent && item.id !== 'moderation' && item.category !== 'social')
  return <main className={s.page}><SectionHead title="サーバー設定" description="入退室、ロール、レベリング、チケット、通知などを設定します。"/><div className={s.featureRows}>{modules.map(item => <FeatureNavRow key={item.id} item={item} guildId={guildId} status={item.enabled ? '有効' : '無効'}/>)}</div></main>
}
