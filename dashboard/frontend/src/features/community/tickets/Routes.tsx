
import { Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Loading, NotFound } from "../../../components/Feedback"

const TicketPanelEditor = lazy(() => import("./PanelEditor"))
const TicketHub = lazy(() => import("./Hub").then(module => ({ default: module.TicketHub })))
const TicketInbox = lazy(() => import("./Inbox").then(module => ({ default: module.TicketInbox })))
const TicketDetail = lazy(() => import("./Detail").then(module => ({ default: module.TicketDetail })))
const TicketPanels = lazy(() => import("./Panels").then(module => ({ default: module.TicketPanels })))
const TicketPanelMessages = lazy(() => import("./Configuration").then(module => ({ default: module.TicketPanelMessages })))
const TicketForms = lazy(() => import("./Configuration").then(module => ({ default: module.TicketForms })))
const TicketTeams = lazy(() => import("./Configuration").then(module => ({ default: module.TicketTeams })))
const TicketSettingsPage = lazy(() => import("./Settings").then(module => ({ default: module.TicketSettingsPage })))
const TicketArchive = lazy(() => import("./Archive").then(module => ({ default: module.TicketArchive })))
const TicketTags = lazy(() => import("./Configuration").then(module => ({ default: module.TicketTags })))
const TicketStats = lazy(() => import("./Stats").then(module => ({ default: module.TicketStats })))


export function TicketRoutes() { return <Suspense fallback={<Loading/>}><Routes><Route index element={<TicketHub/>}/><Route path="inbox" element={<TicketInbox/>}/><Route path="inbox/:ticketId" element={<TicketDetail/>}/><Route path="panels" element={<TicketPanels/>}/><Route path="panels/new" element={<TicketPanelEditor/>}/><Route path="panels/:panelId" element={<TicketPanelEditor/>}/><Route path="panel-messages" element={<TicketPanelMessages/>}/><Route path="forms" element={<TicketForms/>}/><Route path="teams" element={<TicketTeams/>}/><Route path="settings" element={<TicketSettingsPage/>}/><Route path="transcripts" element={<TicketArchive/>}/><Route path="tags" element={<TicketTags/>}/><Route path="stats" element={<TicketStats/>}/><Route path="*" element={<NotFound/>}/></Routes></Suspense> }
