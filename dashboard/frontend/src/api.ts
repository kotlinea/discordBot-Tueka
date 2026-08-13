import type { Session } from './types'

let csrfToken = ''
export class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message) } }
export function setCsrf(value: string) { csrfToken = value }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('content-type')) headers.set('content-type', 'application/json')
  if (init.method && init.method !== 'GET') headers.set('x-csrf-token', csrfToken)
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'same-origin' })
  if (response.status === 401) { window.location.assign('/login'); throw new ApiError(401, 'authentication_required', 'Login required') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'object' ? body.detail : body
    throw new ApiError(response.status, body.code || detail.code || 'request_failed', typeof body.detail === 'string' ? body.detail : detail.message || detail.detail || 'Request failed')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
export async function loadSession(): Promise<Session> { const value = await api<Session>('/session'); setCsrf(value.csrf_token); return value }
