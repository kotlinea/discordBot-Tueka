import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { loadSession } from "./api"
import { applyPreferences } from "./app/Preferences"
import { Loading, Failure } from "./components/Feedback"
import { lazy, Suspense } from 'react'

const ServerPicker = lazy(() => import("./features/guilds/ServerPicker").then(module => ({ default: module.ServerPicker })))
const Shell = lazy(() => import("./app/Shell").then(module => ({ default: module.Shell })))
const TranscriptStandalone = lazy(() => import("./features/tickets/Transcript").then(module => ({ default: module.TranscriptStandalone })))

export default function App() { const session = useSession(); const { i18n } = useTranslation(['common']); useEffect(() => { if (session.data) { applyPreferences(session.data.preferences); void i18n.changeLanguage(session.data.preferences.locale) } }, [session.data, i18n]); if (session.isLoading) return <Loading/>; if (session.error || !session.data) return <Failure error={session.error}/>; return <Suspense fallback={<Loading/>}><Routes><Route path="/servers" element={<ServerPicker session={session.data}/>}/><Route path="/servers/:guildId/*" element={<Shell session={session.data}/>}/><Route path="/tickets/transcripts/:transcriptId" element={<TranscriptStandalone/>}/><Route path="*" element={<Navigate to="/servers" replace/>}/></Routes></Suspense> }

export function useSession() { return useQuery({ queryKey: ['session'], queryFn: loadSession }) }
