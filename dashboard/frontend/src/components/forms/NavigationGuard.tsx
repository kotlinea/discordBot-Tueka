import { createContext, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useBlocker } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

type EditState = { dirty: boolean; pending: boolean; allowed: boolean }
export const NavigationGuardContext = createContext<Map<symbol, () => EditState> | null>(null)

/** One router blocker combines the active editors, including nested dialogs. */
export function NavigationGuard({ children }: { children: ReactNode }) {
  const edits = useRef(new Map<symbol, () => EditState>()).current
  const { t } = useTranslation('common')
  const active = () => [...edits.values()].map(read => read()).filter(state => !state.allowed && (state.dirty || state.pending))
  const blocker = useBlocker(({ currentLocation, nextLocation }) => active().length > 0 &&
    currentLocation.pathname + currentLocation.search !== nextLocation.pathname + nextLocation.search)
  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (!active().some(state => state.pending) && confirm(t('editing.discardConfirm'))) blocker.proceed()
    else blocker.reset()
  }, [blocker, t])
  return <NavigationGuardContext.Provider value={edits}>{children}</NavigationGuardContext.Provider>
}
