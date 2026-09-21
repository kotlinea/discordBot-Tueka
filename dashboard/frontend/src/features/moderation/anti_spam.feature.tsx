import { defineFeature } from '../defaults'

export const feature = defineFeature({
  id: 'anti_spam', category: 'moderation', parent: 'moderation',
  path: 'moderation/anti_spam', namespaces: ['moderation', 'common'],
  load: () => import('./RuleList').then(module => ({ default: () => <module.RuleList family="anti_spam"/> })),
})

