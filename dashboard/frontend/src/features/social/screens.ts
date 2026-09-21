import type { ScreenLoader } from '../contracts'

export const loadProvider: ScreenLoader = () => import('./Provider').then(module => ({ default: module.SocialProviderPage }))

