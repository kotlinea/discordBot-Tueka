import { useSettingsDraft } from '../components/forms/useSettingsDraft'
import { useSaveMutation } from '../components/forms/useSaveMutation'
import { useUnsavedChanges } from '../components/forms/useUnsavedChanges'
import { EditNotice } from '../components/forms/EditNotice'
import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Switch from '@radix-ui/react-switch'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Moon, Save, Settings, Sparkles, Sun, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, request, encodeBody } from "../api"
import type { Appearance, ColorScheme, Locale, Preferences, Session } from "../types"
import s from "../styles/App.module.css"
import { Failure } from "../components/Feedback"



export function applyPreferences(value: Preferences) {
  const scheme = value.color_scheme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : value.color_scheme
  document.documentElement.dataset.appearance = value.appearance
  document.documentElement.dataset.colorScheme = scheme
  document.documentElement.lang = value.locale
  localStorage.setItem('tueka.preferences', JSON.stringify(value))
}

export function PreferencesDialog({ session }: { session: Session }) {
  const { t, i18n } = useTranslation(['common']); const query = useQueryClient(); const [open, setOpen] = useState(false)
  const editor=useSettingsDraft(session.preferences,session.preferences,session.user.id);const {draft,setDraft}=editor

  const mutation = useSaveMutation({ mutationFn: (value: Preferences) => request("PUT /api/v1/preferences", '/preferences', { method: 'PUT', body: encodeBody("PUT /api/v1/preferences", value) }), onSuccess: async value => { editor.accept(value); applyPreferences(value); await i18n.changeLanguage(value.locale); query.setQueryData<Session>(['session'], old => old ? { ...old, preferences: value } : old); await query.invalidateQueries({queryKey:['session']}); setOpen(false) } })
  useUnsavedChanges(open&&editor.dirty,mutation.isPending)
  const discard=()=>{editor.discard();mutation.reset();setOpen(false)}
  return <Dialog.Root open={open} onOpenChange={next=>{if(next)setOpen(true);else if(!mutation.isPending&&(!editor.dirty||confirm(t('editing.discardConfirm'))))discard()}}><Dialog.Trigger asChild><button className={s.iconButton} aria-label={t('prefs.title')}><Settings/></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.dialog}><div className={s.dialogHead}><div><Dialog.Title>{t('prefs.title')}</Dialog.Title><Dialog.Description>端末をまたいで同じ表示設定を使用します。</Dialog.Description></div><Dialog.Close className={s.iconButton}><X/><span className={s.srOnly}>{t('common.close')}</span></Dialog.Close></div>
    <EditNotice dirty={editor.dirty} changedRemotely={editor.changedRemotely}/><fieldset className={s.moduleFields} disabled={mutation.isPending}><div className={s.field}><label>{t('prefs.locale')}</label><select value={draft.locale} onChange={e => setDraft({ ...draft, locale: e.target.value as Locale })}><option value="ja">日本語</option><option value="en">English</option></select></div>
    <div className={s.field}><label>{t('prefs.appearance')}</label><div className={s.segmented}>{(['precision','community','atmosphere'] as Appearance[]).map(item => { const selected = draft.appearance === item; return <button key={item} type="button" aria-pressed={selected} onClick={() => setDraft({ ...draft, appearance: item })}>{selected && <Check aria-hidden="true"/>}<span>{t(`prefs.${item}`)}</span></button> })}</div><small>現在: {t(`prefs.${draft.appearance}`)}</small></div>
    <div className={s.field}><label>{t('prefs.scheme')}</label><div className={s.segmented}>{(['system','light','dark'] as ColorScheme[]).map(item => { const selected = draft.color_scheme === item; return <button key={item} type="button" aria-pressed={selected} onClick={() => setDraft({ ...draft, color_scheme: item })}>{selected ? <Check aria-hidden="true"/> : item === 'system' ? <Sparkles/> : item === 'light' ? <Sun/> : <Moon/>}<span>{t(`prefs.${item}`)}</span></button> })}</div><small>現在: {t(`prefs.${draft.color_scheme}`)}</small></div>
    <label className={s.switchRow}><span><strong>サイドレールを折り畳む</strong><small>機能は検索パレットから引き続き開けます。</small></span><Switch.Root checked={draft.navigation_collapsed} onCheckedChange={value => setDraft({ ...draft, navigation_collapsed: value })} className={s.switch}><Switch.Thumb/></Switch.Root></label>
    {mutation.error && <Failure error={mutation.error}/>}<div className={s.dialogActions}><button type="button" className={s.secondaryButton} disabled={mutation.isPending} onClick={discard}>{t('common.discard')}</button><button className={s.primaryButton} disabled={mutation.isPending||!editor.dirty} onClick={() => mutation.mutate(draft)}><Save/>{t('common.save')}</button></div>
  </fieldset></Dialog.Content></Dialog.Portal></Dialog.Root>
}
