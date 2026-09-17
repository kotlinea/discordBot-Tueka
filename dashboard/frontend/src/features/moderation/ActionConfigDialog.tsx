import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Resource } from "../../types"
import s from "../../styles/App.module.css"
import { defaultAction } from "./ruleForm"
import { ResourceSelect } from "../../components/ResourcePicker"



export function ActionConfigDialog({ action, channels, onClose, onSave }: { action: Record<string, unknown>; channels: Resource[]; onClose: () => void; onSave: (value: Record<string, unknown>) => void }) {
  const { t } = useTranslation(['moderation', 'common']); const type = String(action.type); const [draft,setDraft] = useState({...defaultAction(type),...action}); const update = (key: string, value: unknown) => setDraft(current => ({...current,[key]:value})); const messageAction = ['notify','dm','log'].includes(type)
  return <Dialog.Root open onOpenChange={open => { if (!open) onClose() }}><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.dialog}><div className={s.dialogHead}><div><Dialog.Title>{t(`actions.${type}`)}の設定</Dialog.Title><Dialog.Description>このルールで実行する処置の値を設定します。</Dialog.Description></div><Dialog.Close className={s.iconButton}><X/><span className={s.srOnly}>{t('common.close')}</span></Dialog.Close></div><div className={s.actionConfig}>
    {type === 'points' && <><label className={s.field}><span>加算ポイント</span><input autoFocus type="number" min="1" max="1000" value={Number(draft.points || 1)} onChange={event => update('points', Number(event.currentTarget.value))}/><small>1回の検知で加算するポイント</small></label><label className={s.field}><span>有効日数</span><input type="number" min="0" max="3650" value={Number(draft.expires_days ?? 30)} onChange={event => update('expires_days', Number(event.currentTarget.value))}/><small>0にすると失効しません。</small></label></>}
    {['timeout','tempban'].includes(type) && <label className={s.field}><span>期間（分）</span><input autoFocus type="number" min="1" max={type === 'timeout' ? 40320 : 525600} value={Number(draft.duration_minutes || 10)} onChange={event => update('duration_minutes', Number(event.currentTarget.value))}/><small>{type === 'timeout' ? '最大28日' : '最大365日'}</small></label>}
    {type === 'notify' && <ResourceSelect label="通知先チャンネル" value={draft.channel_id} items={channels.filter(item => item.type === 0)} onChange={value => update('channel_id', value)}/>} {messageAction && <label className={s.field}><span>{type === 'log' ? 'ログメッセージ' : '通知メッセージ'}</span><textarea autoFocus={type !== 'notify'} maxLength={type === 'log' ? 1000 : 500} value={String(draft.message || '')} onChange={event => update('message', event.currentTarget.value)}/><span className={s.templateHelp}><strong>利用可能な変数</strong>{['user','username','reason','server','channel','rule'].map(variable => <span key={variable}><code>{`{${variable}}`}</code><span>{t(`actionVariables.${variable}`)}</span></span>)}</span></label>}
  </div><div className={s.dialogActions}><Dialog.Close className={s.secondaryButton}>キャンセル</Dialog.Close><button type="button" className={s.primaryButton} onClick={() => { onSave(draft); onClose() }}><Check/>設定を反映</button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
}
