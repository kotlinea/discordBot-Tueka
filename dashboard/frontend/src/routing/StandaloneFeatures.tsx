import { lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { featureRegistry } from '../features/registry'

const screens = featureRegistry.features.flatMap(feature => (feature.standalone ?? []).map(route => ({ ...route, Screen: lazy(route.load) })))

export function StandaloneFeatures() {
  const location = useLocation()
  return <Routes>
    {screens.map(({ path, Screen }) => <Route key={path} path={path} element={<Screen key={location.pathname} features={[]}/>}/>)}
    <Route path="*" element={<Navigate to="/servers" replace/>}/>
  </Routes>
}
