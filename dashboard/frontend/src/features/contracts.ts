import type { ComponentType } from 'react'
import type { Feature } from '../types'
import type { LucideIcon } from 'lucide-react'
import type { FieldOptions } from '../components/forms/SettingField'

export type Namespace = 'common' | 'moderation' | 'tickets' | 'reactionRoles' | 'social' | 'suggestions'
export interface FeatureScreenProps { features: Feature[]; definition?: FeatureDefinition }
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
  readonly nested?: boolean
  readonly settingsPath?: string
  readonly settingsLoad?: ScreenLoader
  readonly overview?: boolean
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
  readonly hub?: { readonly path: string; readonly load: ScreenLoader; readonly namespaces: readonly Namespace[]; readonly paletteKey: string }
}
