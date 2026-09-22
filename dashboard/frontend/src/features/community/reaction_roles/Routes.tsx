import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Loading, NotFound } from '../../../components/Feedback'
import type { FeatureScreenProps } from '../../contracts'

const Overview = lazy(() => import('./Overview').then(module => ({ default: module.ReactionRoleOverview })))
const Editor = lazy(() => import('./Editor').then(module => ({ default: module.ReactionRoleEditor })))

export default function ReactionRoles({ definition }: FeatureScreenProps) {
  const { guildId = '' } = useParams()
  if (!definition) return <NotFound/>
  return <Suspense fallback={<Loading/>}><Routes>
    <Route index element={<Overview/>}/>
    <Route path="new" element={<Editor/>}/>
    <Route path=":configId" element={<Editor/>}/>
    <Route path="*" element={<Navigate to={`/servers/${guildId}/${definition.path}`} replace/>}/>
  </Routes></Suspense>
}
