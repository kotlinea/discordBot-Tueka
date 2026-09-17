import { useTranslation } from 'react-i18next'
import type { ModerationEvent } from "../../types"
import s from "../../styles/App.module.css"
import { Empty } from "../../components/Feedback"



export function EventList({ events, compact = false }: { events: ModerationEvent[]; compact?: boolean }) { const { t, i18n } = useTranslation(['common']); if (!events.length) return <Empty title={t('common.noData')} body={t('overview.emptyEvents')}/>; return <div className={compact ? s.compactEvents : s.events}>{events.map(event => <article key={event.id}><div className={s.eventMarker}/><div><div className={s.eventMeta}><span>{event.family}</span><time>{new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(event.created_at * 1000)}</time></div><strong>{event.reason}</strong><p>Event #{event.id}{event.case_id ? ` · Case #${event.case_id}` : ''}{event.target_user_id ? ` · User ${event.target_user_id}` : ''}</p></div></article>)}</div> }
