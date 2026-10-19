import { useState } from 'react'
import * as Dialog from '../components/WorkspaceDialog'
import { BookOpen, LogOut, X } from 'lucide-react'
import type { Session } from "../types"
import s from "../styles/App.module.css"



export function LogoutButton() {
  const [open, setOpen] = useState(false)
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><button className={s.logoutButton} aria-label="ログアウト"><LogOut/><span>ログアウト</span></button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className={s.overlay}/><Dialog.Content className={s.confirmDialog}>
      <div className={s.dialogHead}><div><Dialog.Title>ログアウトしますか？</Dialog.Title><Dialog.Description>Tuekaの管理画面からログアウトします。Discordのログイン状態は維持されます。</Dialog.Description></div><Dialog.Close className={s.iconButton}><X/><span className={s.srOnly}>閉じる</span></Dialog.Close></div>
      <div className={s.dialogActions}><Dialog.Close className={s.secondaryButton}>キャンセル</Dialog.Close><a className={s.dangerButton} href="/logout"><LogOut/>ログアウト</a></div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>
}

export function AccountIdentity({ session }: { session: Session }) { return <div className={s.accountIdentity}><img src={session.user.avatar_url} alt=""/><span>{session.user.name}</span></div> }

export function DocsLink({ path = '/docs/', label = 'ドキュメント' }: { path?: string; label?: string }) {
  return <a className={s.docsButton} href={path} aria-label={label} target="_blank" rel="noopener noreferrer"><BookOpen/><span>{label}</span></a>
}
