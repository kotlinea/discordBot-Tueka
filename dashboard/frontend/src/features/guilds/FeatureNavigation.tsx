import { PermissionDiagnostics } from '../../components/PermissionDiagnostics'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, BookOpen, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Feature } from "../../types"
import s from "../../styles/App.module.css"
import { featurePath } from '../../routing/catalog'
import { Status } from "../../components/Feedback"



export function FeatureNavRow({ item, guildId, status }: { item: Feature; guildId: string; status: string }) { const { t } = useTranslation('common'); return <div className={s.featureRowWithDocs}><Link to={featurePath(guildId,item)}><div><strong>{item.title}</strong><span>{item.description}</span></div><Status active={item.enabled}>{status}</Status><ChevronRight/></Link><a href={item.docs_path} target="_blank" rel="noopener noreferrer" aria-label={t('overview.docsFor', { title: item.title })}><BookOpen/><span>{t('overview.docs')}</span></a></div> }

export function PermissionNotice({features}:{features:Feature[]}) { const {t}=useTranslation(['moderation','common']); return <PermissionDiagnostics title={t('moderation.permissions')} messages={features.flatMap(item=>item.missing_permissions)}/> }
