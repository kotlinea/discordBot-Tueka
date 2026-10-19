import { defineFeature } from '../defaults'

const loadSettings = () => import('./suggestions/Settings')

export const feature = defineFeature({
  screenKind: 'workspace',
  id: 'suggestions', category: 'engagement',
  path: 'suggestions', namespaces: ['suggestions', 'common'],
  titleKey: 'suggestions.title',
  load: loadSettings, settingsPath: 'modules/suggestions', settingsLoad: loadSettings,
  pages:[{id:'roadmap',path:'roadmap',titleKey:'suggestions.roadmap',kind:'navigation',access:'manager',load:()=>import('./suggestions/Roadmap')}],
})
