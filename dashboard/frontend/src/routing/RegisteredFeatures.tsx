import { lazy, Suspense } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'
import { Route, Routes, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { FeatureScreenProps, ScreenLoader } from '../features/contracts'
import { featureRegistry } from '../features/registry'
import { Loading, NotFound } from '../components/Feedback'
import { featurePattern } from './catalog'
import { WorkspaceNavigation } from './WorkspaceNavigation'
import { ConfigurationContext, ConfigurationState } from '../components/feature/ConfigurationState'

const sharedScreens = new Map<ScreenLoader, LazyExoticComponent<ComponentType<FeatureScreenProps>>>()
const screens = new Map(featureRegistry.routes.map(feature => {
  let Screen = sharedScreens.get(feature.load)
  if (!Screen) {
    Screen = lazy(() => featureRegistry.loadRoute(feature.path))
    sharedScreens.set(feature.load, Screen)
  }
  return [feature.path, Screen]
}))
const hubs = featureRegistry.categories.filter(category => category.hub).map(category => ({ category, Screen: lazy(() => featureRegistry.loadCategory(category.id)) }))

function FeatureScreen({ definition, features, staffOnly }: FeatureScreenProps & { staffOnly: boolean }) {
  const { guildId = '' } = useParams()
  useTranslation([...(definition?.namespaces ?? ['common'])])
  const Screen = definition && screens.get(definition.path)
  if (!Screen || !definition || (staffOnly && definition.access !== 'ticket_staff')) return <NotFound/>
  const owner = featureRegistry.get(definition.id)
  return <ConfigurationContext.Provider value={{ feature: features.find(item => item.id === definition.id), features, fields: owner?.fields }}>
    {!staffOnly && <ConfigurationState/>}
    {definition.screenKind === 'workspace' && <WorkspaceNavigation definition={owner} staffOnly={staffOnly}/>}
    <Screen key={`${guildId}/${definition.path}`} features={features} definition={definition}/>
  </ConfigurationContext.Provider>
}

export function RegisteredFeatures({ features, staffOnly = false }: FeatureScreenProps & { staffOnly?: boolean }) {
  const { guildId = '' } = useParams()
  return <Suspense fallback={<Loading/>}><Routes>
    {!staffOnly && hubs.map(({ category, Screen }) => <Route key={category.id} path={category.hub!.path} element={<Screen key={`${guildId}/${category.id}`} features={features}/>}/>)}
    {featureRegistry.routes.map(definition =>
      <Route key={definition.path} path={featurePattern(definition)} element={<FeatureScreen features={features} definition={definition} staffOnly={staffOnly}/>}/>)}
    <Route path="*" element={<NotFound/>}/>
  </Routes></Suspense>
}
