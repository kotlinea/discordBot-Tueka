import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Loading, NotFound } from '../../../components/Feedback'

const Inbox = lazy(() => import('./Inbox').then(module => ({ default: module.TicketInbox })))
const Detail = lazy(() => import('./Detail').then(module => ({ default: module.TicketDetail })))
const Panels = lazy(() => import('./Panels').then(module => ({ default: module.TicketPanels })))
const PanelEditor = lazy(() => import('./PanelEditor'))

export function TicketInboxRoutes() {
  return <Suspense fallback={<Loading/>}><Routes>
    <Route index element={<Inbox/>}/><Route path=":ticketId" element={<Detail/>}/>
    <Route path="*" element={<NotFound/>}/>
  </Routes></Suspense>
}
export function TicketPanelRoutes() {
  return <Suspense fallback={<Loading/>}><Routes>
    <Route index element={<Panels/>}/><Route path="new" element={<PanelEditor/>}/><Route path=":panelId" element={<PanelEditor/>}/>
    <Route path="*" element={<NotFound/>}/>
  </Routes></Suspense>
}
export function TicketSettingsAlias() {
  const { guildId = '' } = useParams()
  return <Navigate to={`/servers/${guildId}/tickets/settings`} replace/>
}
