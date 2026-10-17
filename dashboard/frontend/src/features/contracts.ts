import type { ComponentType } from 'react'
import type { Feature } from '../types'
import type { LucideIcon } from 'lucide-react'
import type { FieldOptions } from '../components/forms/SettingField'

export type Namespace = 'common' | 'moderation' | 'tickets' | 'reactionRoles' | 'social' | 'suggestions' | 'applications' | 'appeals'
export interface FeatureScreenProps { features: Feature[]; definition?: FeatureDefinition }
export type ScreenModule = { default: ComponentType<FeatureScreenProps> }
export type ScreenLoader = () => Promise<ScreenModule>
export type DisplayAccess = 'manager' | 'ticket_staff'

/** A screen entry, never a mutation callback. Saving remains owned by the feature. */
export interface FeaturePage {
  readonly id: string
  readonly path: string
  readonly titleKey: string
  readonly kind: 'navigation' | 'action'
  readonly access: DisplayAccess
  readonly load: ScreenLoader
  readonly nested?: boolean
  readonly group?: { readonly id: string; readonly titleKey: string }
  readonly breadcrumbs?: FeatureDefinition['breadcrumbs']
}

/** Presentation order is declaration order; independent of backend category/parent. */
export interface PresentationCategory {
  readonly id: string
  readonly titleKey: string
  readonly icon?: LucideIcon
}

export interface FeatureDefinition {
  readonly id: string
  readonly category: string
  readonly presentationCategory: string
  readonly screenKind: 'settings' | 'workspace'
  readonly homeTitleKey?: string
  readonly pages: readonly FeaturePage[]
  readonly parent?: string
  /** Existing path relative to /servers/:guildId; not an authorization rule. */
  readonly path: string
  readonly load: ScreenLoader
  readonly namespaces: readonly Namespace[]
  readonly access: DisplayAccess
  readonly nested?: boolean
  readonly settingsPath?: string
  readonly settingsLoad?: ScreenLoader
  readonly titleKey?: string
  readonly label?: (translate: (key: string) => string) => string
  readonly icon?: LucideIcon
  readonly inHub?: boolean
  readonly inPalette?: boolean
  readonly fields?: Readonly<Record<string, Omit<FieldOptions, 'label'> & { labelKey: string }>>
  readonly breadcrumbs?: (suffix: string[], translate: (key: string) => string) => { label: string; suffix?: string }[]
  readonly standalone?: readonly { path: string; load: ScreenLoader }[]
}

export interface CategoryDefinition {
  readonly id: string
  readonly titleKey: string
  readonly features: readonly FeatureDefinition[]
  readonly icon?: LucideIcon
  readonly hub?: { readonly path: string; readonly load: ScreenLoader; readonly namespaces: readonly Namespace[] }
}
