import type { Session } from "./types"
import type { ErrorField, Operations } from './generated/api'

let csrfToken = ''
export class ApiError extends Error { constructor(public status: number, public code: string, message: string, public fields: ErrorField[] = []) { super(message) } }
export function setCsrf(value: string) { csrfToken = value }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('content-type')) headers.set('content-type', 'application/json')
  if (init.method && init.method !== 'GET') headers.set('x-csrf-token', csrfToken)
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'same-origin' })
  if (response.status === 401) { window.location.assign('/login'); throw new ApiError(401, 'authentication_required', 'Login required') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail && typeof body.detail === 'object' && !Array.isArray(body.detail) ? body.detail : body
    throw new ApiError(response.status, detail.code || 'request_failed', typeof body.detail === 'string' ? body.detail : detail.message || 'Request failed', detail.errors || [])
  }
  if (response.status === 204) return undefined as T
  if (response.headers.get('content-type')?.split(';')[0] === 'application/octet-stream') return response.blob() as Promise<T>
  return response.json()
}
export async function loadSession(): Promise<Session> { const value = await api<Session>('/session'); setCsrf(value.csrf_token); return value }

export function request<K extends keyof Operations>(operation: K, path: string, init: RequestInit = {}): Promise<Operations[K]['response']> {
  return api<Operations[K]['response']>(path, { ...init, method: operation.split(' ')[0] })
}

export function encodeBody<K extends keyof Operations>(_operation: K, value: Operations[K]['body']): string {
  return JSON.stringify(value)
}
