import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Loading, NotFound } from '../../components/Feedback'

const List = lazy(() => import('./RuleList').then(module => ({ default: module.RuleList })))
const Editor = lazy(() => import('./RuleEditor').then(module => ({ default: module.RuleEditor })))

export default function RuleRoutes({ family, defaultTrigger }: { family: string; defaultTrigger: string }) {
  return <Suspense fallback={<Loading/>}><Routes>
    <Route index element={<List family={family}/>}/>
    <Route path="rules/:ruleId" element={<Editor family={family} defaultTrigger={defaultTrigger}/>}/>
    <Route path="*" element={<NotFound/>}/>
  </Routes></Suspense>
}
