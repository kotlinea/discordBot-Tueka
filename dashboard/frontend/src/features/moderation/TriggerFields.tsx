import type { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { Resource } from '../../types'
import { ResourceSelect, selectedIds } from '../../components/ResourcePicker'
import type { RuleForm } from './ruleForm'
import s from '../../styles/App.module.css'

export function TriggerFields({ form, channels }: { form: UseFormReturn<RuleForm>; channels: Resource[] }) {
  const { t } = useTranslation('moderation')
  const trigger = form.watch('trigger_type'); const config = form.watch('trigger_config')
  const update = (key: string, value: unknown) => form.setValue('trigger_config', { ...config, [key]: value }, { shouldDirty: true })
  const text = (field: 'keywordsText'|'allowText'|'patternsText'|'domainsText', label: string, required = false) => <label className={s.field}><span>{t(`operations.${label}`)}</span><textarea aria-label={t(`operations.${label}`)} {...form.register(field, { required })}/><small>{t('operations.lines')}</small></label>
  const numeric = (key: string, min: number, max: number, fallback = min) => <label className={s.field} key={key}><span>{t(`operations.${key}`)}</span><input type="number" min={min} max={max} required value={config[key] === '' ? '' : Number(config[key] ?? fallback)} onChange={event=>update(key, event.target.value === '' ? '' : Number(event.target.value))}/></label>
  return <div className={s.formGrid}>
    {trigger === 'keyword' && <>{text('keywordsText','keywords',true)}{text('allowText','allow')}<label className={s.field}><span>{t('operations.match')}</span><select value={String(config.match || 'wildcard')} onChange={event=>update('match',event.target.value)}>{['wildcard','contains'].map(value=><option key={value} value={value}>{t(`operations.${value}`)}</option>)}</select></label></>}
    {trigger === 'regex' && text('patternsText','patterns',true)}
    {trigger === 'domain' && <>{text('domainsText','domains',true)}<label className={s.field}><span>{t('operations.domainMode')}</span><select value={String(config.mode || 'blacklist')} onChange={event=>update('mode',event.target.value)}>{['blacklist','block_all_except'].map(value=><option key={value} value={value}>{t(`operations.${value}`)}</option>)}</select></label></>}
    {'limit' in config && <><label className={s.field}><span>{t('operations.limit')}</span><input type="number" min={trigger==='duplicate'?2:1} max="100" {...form.register('limit',{valueAsNumber:true,min:trigger==='duplicate'?2:1,max:100,required:true})}/></label><label className={s.field}><span>{t('operations.window')}</span><input type="number" min="1" max="300" {...form.register('windowSeconds',{valueAsNumber:true,min:1,max:300,required:true})}/></label></>}
    {trigger==='caps'&&<>{numeric('percentage',10,100)}{numeric('minimum_letters',1,100)}</>}
    {trigger==='new_account_ratio'&&<>{numeric('percentage',1,100)}{numeric('account_age_days',1,3650)}</>}
    {trigger==='new_member_activity'&&numeric('join_age_minutes',1,10080)}
    {trigger==='emoji_sticker_rate'&&numeric('per_message_limit',1,100)}
    {trigger==='duplicate'&&numeric('similarity_percent',70,100,100)}
    {trigger==='media_only'&&<label className={s.compactSwitch}><input type="checkbox" checked={Boolean(config.allow_links)} onChange={event=>update('allow_links',event.target.checked)}/>{t('operations.allow_links')}</label>}
    {trigger==='honeypot'&&<ResourceSelect label={t('operations.honeypot')} multiple items={channels} value={config.channel_ids} onChange={value=>update('channel_ids',selectedIds(value))}/>}
    {['safe_browsing','phishing_link','discord_invite'].includes(trigger)&&<p>{t('operations.noConfig')}</p>}
  </div>
}
