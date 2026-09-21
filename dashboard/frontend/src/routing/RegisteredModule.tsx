import { lazy } from 'react'
import { useParams } from 'react-router-dom'
import type { FeatureScreenProps } from '../features/contracts'
import { featureRegistry } from '../features/registry'
import { NotFound } from '../components/Feedback'

const screens = new Map(featureRegistry.features.map(feature => [feature.id, lazy(() => featureRegistry.load(feature.id))]))

export function RegisteredModule(props: FeatureScreenProps) {
  const { guildId = '', moduleId = '' } = useParams()
  const definition = featureRegistry.features.find(feature => feature.id === moduleId && feature.path === `modules/${moduleId}`)
  const Screen = definition && screens.get(moduleId)
  return Screen ? <Screen key={`${guildId}/${moduleId}`} {...props}/> : <NotFound/>
}
