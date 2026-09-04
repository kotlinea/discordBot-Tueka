import { useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Search, SmilePlus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Resource } from './types'
import { STANDARD_EMOJI_CATEGORIES } from './emojiCatalog'
import s from './styles/App.module.css'

interface EmojiPickerProps {
  value: string
  guildEmojis: Resource[]
  onChange: (value: string) => void
}

const customValue = (emoji: Resource) => `<${emoji.animated ? 'a' : ''}:${emoji.name}:${emoji.id}>`

export default function EmojiPicker({ value, guildEmojis, onChange }: EmojiPickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState<'standard'|'server'>('standard')
  const [category, setCategory] = useState(STANDARD_EMOJI_CATEGORIES[0].id)
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const standardEmojis = useMemo(() => {
    const available = normalizedQuery
      ? STANDARD_EMOJI_CATEGORIES.flatMap(item => item.emojis)
      : STANDARD_EMOJI_CATEGORIES.find(item => item.id === category)?.emojis || []
    return available.filter(item => !normalizedQuery || `${item.name} ${item.keywords} ${item.emoji}`.toLocaleLowerCase().includes(normalizedQuery))
  }, [category, normalizedQuery])
  const serverEmojis = guildEmojis.filter(item => !normalizedQuery || item.name.toLocaleLowerCase().includes(normalizedQuery))
  const selectedCustom = guildEmojis.find(item => customValue(item) === value)
  const choose = (next: string) => { onChange(next); setOpen(false); setQuery('') }

  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger className={s.emojiPickerTrigger} type="button">
      {selectedCustom
        ? <img src={`https://cdn.discordapp.com/emojis/${selectedCustom.id}.${selectedCustom.animated ? 'gif' : 'webp'}?size=48&quality=lossless`} alt="" aria-hidden="true"/>
        : <span aria-hidden="true">{value || '＋'}</span>}
      <span>{value ? t('emojiPicker.change') : t('emojiPicker.choose')}</span>
    </Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className={s.overlay}/>
      <Dialog.Content className={`${s.dialog} ${s.emojiPickerDialog}`}>
        <div className={s.dialogHead}><div><Dialog.Title>{t('emojiPicker.title')}</Dialog.Title><Dialog.Description>{t('emojiPicker.description')}</Dialog.Description></div><Dialog.Close className={s.iconButton}><X/></Dialog.Close></div>
        <div className={s.policyToggle} role="group" aria-label={t('emojiPicker.source')}>
          <button type="button" aria-pressed={source === 'standard'} onClick={() => setSource('standard')}>{t('emojiPicker.standard')}</button>
          <button type="button" aria-pressed={source === 'server'} onClick={() => setSource('server')}>{t('emojiPicker.server')}</button>
        </div>
        <label className={s.emojiSearch}><Search aria-hidden="true"/><span className={s.srOnly}>{t('emojiPicker.search')}</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder={t('emojiPicker.search')}/></label>
        {source === 'standard' && !normalizedQuery && <div className={s.emojiCategories} role="tablist" aria-label={t('emojiPicker.categories')}>{STANDARD_EMOJI_CATEGORIES.map(item => <button key={item.id} type="button" role="tab" aria-selected={category === item.id} aria-label={t(`emojiPicker.category.${item.id}`)} onClick={() => setCategory(item.id)}>{item.emojis[0].emoji}</button>)}</div>}
        <div className={s.emojiGrid} role="listbox" aria-label={source === 'standard' ? t('emojiPicker.standard') : t('emojiPicker.server')}>
          {source === 'standard' && standardEmojis.map(item => <button key={item.emoji} type="button" role="option" aria-selected={value === item.emoji} aria-label={item.name} title={item.name} onClick={() => choose(item.emoji)}>{item.emoji}</button>)}
          {source === 'server' && serverEmojis.map(item => <button key={item.id} type="button" role="option" aria-selected={value === customValue(item)} aria-label={item.name} title={item.name} onClick={() => choose(customValue(item))}><img src={`https://cdn.discordapp.com/emojis/${item.id}.${item.animated ? 'gif' : 'webp'}?size=48&quality=lossless`} alt="" aria-hidden="true"/></button>)}
          {((source === 'standard' && !standardEmojis.length) || (source === 'server' && !serverEmojis.length)) && <div className={s.emojiEmpty}><SmilePlus aria-hidden="true"/><span>{t('emojiPicker.empty')}</span></div>}
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
