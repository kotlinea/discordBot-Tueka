import { useContext, useEffect, useRef } from 'react'
import { NavigationGuardContext } from './NavigationGuard'
import { useTranslation } from 'react-i18next'

export function useUnsavedChanges(dirty: boolean, pending = false) {
  const { t } = useTranslation('common')
  const router = useContext(NavigationGuardContext)
  const allowed = useRef(false)
  useEffect(() => { allowed.current = false }, [dirty, pending])
  const state = useRef({ dirty, pending })
  state.current = { dirty, pending }
  useEffect(() => {
    if (!router) return
    const key = Symbol('editor')
    router.set(key, () => ({ ...state.current, allowed: allowed.current }))
    return () => { router.delete(key) }
  }, [router])
  useEffect(() => {
    if (!dirty && !pending) return
    const before = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const click = (event: MouseEvent) => {
      const anchor = (event.target as HTMLElement).closest<HTMLAnchorElement>('a[href]')
      if (!anchor || anchor.download || anchor.origin !== location.origin || anchor.href === location.href || anchor.target === '_blank' || event.ctrlKey || event.metaKey) return
      if (pending || !confirm(t('editing.discardConfirm'))) { event.preventDefault(); event.stopPropagation() }
    }
    addEventListener('beforeunload', before)
    if (!router) document.addEventListener('click', click, true)
    return () => { removeEventListener('beforeunload', before); document.removeEventListener('click', click, true) }
  }, [dirty, pending, router, t])
  return () => { allowed.current = true }
}
