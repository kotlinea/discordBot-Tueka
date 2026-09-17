import { Route, Routes } from 'react-router-dom'
import type { Feature } from "../../types"
import { lazy, Suspense } from 'react'
import { Loading } from "../../components/Feedback"

const ModerationHub = lazy(() => import("./Hub").then(module => ({ default: module.ModerationHub })))
const RuleList = lazy(() => import("./RuleList").then(module => ({ default: module.RuleList })))
const RuleEditor = lazy(() => import("./RuleEditor").then(module => ({ default: module.RuleEditor })))
const Infractions = lazy(() => import("./Infractions").then(module => ({ default: module.Infractions })))
const Actions = lazy(() => import("./Actions").then(module => ({ default: module.Actions })))
const Logs = lazy(() => import("./Logs").then(module => ({ default: module.Logs })))

export function ModerationRoutes({ features }: { features: Feature[] }) { return <Suspense fallback={<Loading/>}><Routes><Route index element={<ModerationHub features={features}/>} /><Route path="automod" element={<RuleList family="automod"/>}/><Route path="anti_spam" element={<RuleList family="anti_spam"/>}/><Route path="anti_raid" element={<RuleList family="anti_raid"/>}/><Route path=":family/rules/new" element={<RuleEditor/>}/><Route path=":family/rules/:ruleId" element={<RuleEditor/>}/><Route path="infractions" element={<Infractions/>}/><Route path="moderation_actions" element={<Actions/>}/><Route path="moderation_logs" element={<Logs/>}/></Routes></Suspense> }
