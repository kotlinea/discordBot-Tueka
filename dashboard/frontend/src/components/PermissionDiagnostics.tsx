import { AlertTriangle } from 'lucide-react'
import s from '../styles/App.module.css'

export function PermissionDiagnostics({ title, messages, blocking = false }: {
  title: string; messages: string[]; blocking?: boolean
}) {
  if (!messages.length) return null
  return <div className={blocking ? s.failure : s.permissionNotice} role={blocking ? 'alert' : 'status'}>
    {!blocking && <AlertTriangle/>}<div><strong>{title}</strong><p>{[...new Set(messages)].join(' · ')}</p></div>
  </div>
}
