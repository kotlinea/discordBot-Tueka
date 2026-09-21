import type { ComponentType } from 'react'
import type { Feature } from '../types'

export type Namespace = 'common' | 'moderation' | 'tickets' | 'reactionRoles' | 'social' | 'suggestions'
export interface FeatureScreenProps { features: Feature[] }
export type ScreenModule = { default: ComponentType<FeatureScreenProps> }
export type ScreenLoader = () => Promise<ScreenModule>

export interface FeatureDefinition {
  readonly id: string
  readonly category: string
  readonly parent?: string
  /** Existing path relative to /servers/:guildId; not an authorization rule. */
  readonly path: string
  readonly load: ScreenLoader
  readonly namespaces: readonly Namespace[]
  readonly access: 'manager' | 'ticket_staff'
}

export interface CategoryDefinition {
  readonly id: string
  readonly titleKey: string
  readonly features: readonly FeatureDefinition[]
}
