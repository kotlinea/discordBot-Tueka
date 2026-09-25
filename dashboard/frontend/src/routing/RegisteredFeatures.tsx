import { lazy, Suspense } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'
import { Link, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { FeatureScreenProps, ScreenLoader } from '../features/contracts'
import { featureRegistry } from '../features/registry'
import { Loading, NotFound } from '../components/Feedback'
import { featurePattern } from './catalog'
import s from '../styles/App.module.css'

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
  const { t } = useTranslation([...(definition?.namespaces ?? ['common'])])
  const Screen = definition && screens.get(definition.path)
  if (!Screen || !definition || (staffOnly && definition.access !== 'ticket_staff')) return <NotFound/>
  const owner = featureRegistry.get(definition.id)
  const pages = definition.screenKind === 'workspace' ? owner.pages.filter(page => !staffOnly || page.access === 'ticket_staff') : []
  const base = featureRegistry.path(guildId, owner.id)
  return <>
    {pages.length > 0 && <nav className={s.featureNavigation} aria-label={t('common.featureNavigation')}>
      <NavLink end className={s.secondaryButton} to={base}>{t('nav.overview')}</NavLink>
      {pages.map(page => page.kind === 'action'
        ? <Link key={page.id} className={s.primaryButton} to={`${base}/${page.path}`}>{t(page.titleKey)}</Link>
        : <NavLink key={page.id} className={s.secondaryButton} to={`${base}/${page.path}`}>{t(page.titleKey)}</NavLink>)}
    </nav>}
    <Screen key={`${guildId}/${definition.path}`} features={features} definition={definition}/>
  </>
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
