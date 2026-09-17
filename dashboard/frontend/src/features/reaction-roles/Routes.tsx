import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Loading } from '../../components/Feedback'

const Overview = lazy(() => import('./Overview').then(module => ({ default: module.ReactionRoleOverview })))
const Editor = lazy(() => import('./Editor').then(module => ({ default: module.ReactionRoleEditor })))

export default function ReactionRoles() {
  return <Suspense fallback={<Loading/>}><Routes>
    <Route index element={<Overview/>}/>
    <Route path="new" element={<Editor/>}/>
    <Route path=":configId" element={<Editor/>}/>
    <Route path="*" element={<Navigate to="." replace/>}/>
  </Routes></Suspense>
}
