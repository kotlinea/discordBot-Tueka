import * as Switch from '@radix-ui/react-switch'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { Feature, Resource } from "../../types"
import s from "../../styles/App.module.css"
import { ResourceSelect } from "../../components/ResourcePicker"
import { lines } from "../moderation/ruleForm"
import { ModuleSettings as SettingsForm } from '../../components/feature/ModuleSettings'



export function ModuleSettings({ features }: { features: Feature[] }) {
  const { moduleId = '' } = useParams()
  return <SettingsForm key={moduleId} feature={features.find(item => item.id === moduleId)} renderField={props => <ModuleField {...props}/>}/>
}
export function ModuleField({ name, value, channels, roles, onChange }: { name: string; value: unknown; channels: Resource[]; roles: Resource[]; onChange: (value: unknown) => void }) {
  const { t } = useTranslation(['common']); const label = fieldLabel(name); const multiple = name.endsWith('_ids'); const template = TEMPLATE_FIELDS[name]
  if (typeof value === 'boolean') return <label className={s.switchRow}><span><strong>{label}</strong></span><Switch.Root checked={value} onCheckedChange={onChange} className={s.switch}><Switch.Thumb/></Switch.Root></label>
  if (name.endsWith('category_id') || name.endsWith('category_ids')) return <ResourceSelect label={label} value={value} items={channels.filter(item => item.type === 4)} multiple={multiple} onChange={onChange}/>
  if (name.endsWith('channel_id') || name.endsWith('channel_ids') || name === 'temp_voice_trigger_id') return <ResourceSelect label={label} value={value} items={name === 'temp_voice_trigger_id' ? channels.filter(item => [2,13].includes(item.type ?? -1)) : channels.filter(item => item.type !== 4)} multiple={multiple} onChange={onChange}/>
  if (name.endsWith('role_id') || name.endsWith('role_ids')) return <ResourceSelect label={label} value={value} items={roles} multiple={multiple} onChange={onChange}/>
  if (template) return <label className={s.field}><span>{label}</span>{template.multiline ? <textarea maxLength={template.maxLength} value={String(value || '')} onChange={event => onChange(event.currentTarget.value)}/> : <input maxLength={template.maxLength} value={String(value || '')} onChange={event => onChange(event.currentTarget.value)}/>}<span className={s.templateHelp}><strong>{t('template.available')}</strong>{template.variables.map(variable => <span key={variable}><code>{`{${variable}}`}</code><span>{t(`template.variables.${variable}`)}</span></span>)}</span></label>
  if (Array.isArray(value) || name.includes('template') || name.includes('content') || name.includes('format')) return <label className={s.field}><span>{label}</span><textarea value={Array.isArray(value) ? value.join('\n') : String(value || '')} onChange={e => onChange(Array.isArray(value) ? lines(e.target.value) : e.target.value)}/></label>
  return <label className={s.field}><span>{label}</span><input type={typeof value === 'number' ? 'number' : 'text'} value={String(value ?? '')} onChange={e => onChange(typeof value === 'number' ? Number(e.target.value) : e.target.value)}/></label>
}

export const FIELD_LABELS: Record<string, string> = {
  default_role_id: '参加時に付与するロール', text_notification_channel_id: 'テキストレベル通知先', text_role_rewards: 'テキストレベル報酬',
  voice_enabled: 'ボイスレベル', voice_notification_channel_id: 'ボイスレベル通知先', voice_role_rewards: 'ボイスレベル報酬', voice_xp_per_minute: '1分あたりのボイスXP', voice_allow_solo: '1人のボイスチャンネルでもXPを付与', voice_allow_muted: 'ミュート中もXPを付与',
  default_log_channel_id: '既定のログチャンネル', log_channel_id: 'ログチャンネル', notify_channel_id: '管理者への通知先', management_channel_id: 'サーバーログチャンネル',
  immune_role_ids: '除外ロール', immune_user_ids: '除外ユーザーID', immune_channel_ids: '除外チャンネル', evidence_excluded_channel_ids: '本文を保存しないチャンネル', evidence_retention_days: 'ログ本文の保持日数', exclude_bots: 'Botを除外', exclude_webhooks: 'Webhookを除外',
  default_lockdown_minutes: '既定のLockdown時間（分）', point_thresholds: '警告ポイントの制裁しきい値',
  log_message: 'メッセージの投稿・編集・削除', log_voice: 'ボイスチャンネルの参加・退出・移動', log_channel: 'チャンネル・カテゴリ・スレッドの変更', log_member: 'メンバーの参加・退出・制裁', log_role: 'ロールの作成・更新・削除', log_server: 'サーバー設定の変更',
  reaction_role_channel_id: 'パネル投稿先', reaction_role_ids: '選択可能なロール', reaction_role_title: 'パネルタイトル', reaction_role_description: 'パネルの説明',
  stats_channel_id: '統計表示用ボイスチャンネル', stats_template: 'チャンネル名テンプレート',
  temp_voice_trigger_id: '作成トリガー', temp_voice_category_id: '作成先カテゴリ', temp_voice_name: 'チャンネル名',
  ticket_panel_channel_id: 'パネル投稿先', ticket_category_id: 'チケット作成先カテゴリ', ticket_staff_role_id: '対応スタッフロール', ticket_log_channel_id: 'チケットログチャンネル', ticket_panel_title: 'パネルタイトル', ticket_panel_description: 'パネルの説明',
  trust_retention_days: '信頼度データの保持日数', trust_flag_threshold: '要確認とするスコア',
}

export const TEMPLATE_FIELDS: Record<string, { variables: string[]; multiline: boolean; maxLength: number }> = {
  stats_template: { variables: ['members','humans','bots','roles'], multiline: false, maxLength: 90 },
  temp_voice_name: { variables: ['member'], multiline: false, maxLength: 100 },
}

export function fieldLabel(name: string) { return FIELD_LABELS[name] || '設定項目' }
