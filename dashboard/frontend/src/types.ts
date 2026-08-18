export type Locale = 'ja' | 'en'
export type Appearance = 'precision' | 'community' | 'atmosphere'
export type ColorScheme = 'system' | 'light' | 'dark'
export interface Preferences { locale: Locale; appearance: Appearance; color_scheme: ColorScheme; navigation_collapsed: boolean; revision: number }
export interface Session { user: { id: string; name: string; avatar_url: string }; csrf_token: string; preferences: Preferences }
export interface Guild { id: string; name: string; icon: string | null }
export interface Resource { id: string; name: string; type?: number; position?: number }
export interface Feature { id: string; category: string; parent: string | null; title: string; description: string; fields: string[]; required_fields: string[]; required_bot_permissions: string[]; enabled: boolean; settings: Record<string, unknown>; revision: number; missing_permissions: string[] }
export interface ModerationEvent { id: number; family: string; event_type: string; source: string; target_user_id?: number; channel_id?: number; reason: string; mode: string; case_id?: number; created_at: number }
export interface Rule { id?: number; guild_id?: number; family: string; event_type: string; name: string; enabled: boolean; mode: 'monitor' | 'enforce'; priority: number; stop_on_match: boolean; trigger_type: string; trigger_config: Record<string, unknown>; conditions: Record<string, unknown>; exemptions: Record<string, unknown>; actions: Array<Record<string, unknown>>; revision?: number }
export interface SocialTemplate { content: string; title: string; description: string; color: string; url: string; thumbnail_url: string; image_url: string; footer: string }
export interface SocialTarget { id: number; provider: string; account_key: string; external_id?: string; handle?: string; display_name?: string; avatar_url?: string; status: 'pending'|'active'|'degraded'|'error'; last_error?: string; last_checked_at?: number; revision: number }
export interface SocialSubscription { id: number; provider: string; account_id: string; channel_id: string; role_id: string|null; events: string[]; event_channels: Record<string,string>; templates: Record<string,SocialTemplate>; enabled: boolean; status: string; last_error?: string; revision: number; target: SocialTarget|null }
export interface SocialProviderSummary { id: string; available: boolean; events: string[]; count: number; limit: number }
