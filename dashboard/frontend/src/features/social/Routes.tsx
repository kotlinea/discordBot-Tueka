import { Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Loading } from "../../components/Feedback"

const SocialHub = lazy(() => import("./Hub").then(module => ({ default: module.SocialHub })))
const SocialProviderPage = lazy(() => import("./Provider").then(module => ({ default: module.SocialProviderPage })))

export function SocialRoutes() { return <Suspense fallback={<Loading/>}><Routes><Route index element={<SocialHub/>}/><Route path=":provider" element={<SocialProviderPage/>}/></Routes></Suspense> }
