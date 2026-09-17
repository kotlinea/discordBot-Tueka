import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, encodeBody, request, setCsrf } from '../api'

afterEach(() => vi.unstubAllGlobals())

describe('generated API client', () => {
  it('preserves Discord IDs and sends the generated operation method and CSRF', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'queued' }), { status: 202 }))
    vi.stubGlobal('fetch', fetch)
    setCsrf('session-csrf')
    const operation = 'POST /api/v1/guilds/{guild_id}/reaction-roles/messages/{config_id}/move' as const
    const id = '1234567890123456789'
    await request(operation, '/guilds/1/reaction-roles/messages/2/move', {
      body: encodeBody(operation, { channel_id: id, message_id: id }),
    })
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/v1/guilds/1/reaction-roles/messages/2/move')
    expect(options.method).toBe('POST')
    expect(options.headers.get('x-csrf-token')).toBe('session-csrf')
    expect(JSON.parse(options.body)).toEqual({ channel_id: id, message_id: id })
  })

  it('retains field errors and revision conflicts without retrying mutations', async () => {
    const detail = { code: 'revision_conflict', message: 'Reload first', errors: [{ path: 'revision', message: 'Stale' }] }
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 409 }))
    vi.stubGlobal('fetch', fetch)
    const error = await request('PUT /api/v1/preferences', '/preferences', {
      body: encodeBody('PUT /api/v1/preferences', { revision: 1 }),
    }).catch(error => error)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, code: detail.code, fields: detail.errors })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('downloads a binary attachment using its generated response type', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('attachment', { headers: { 'content-type': 'application/octet-stream' } })))
    const blob = await request('GET /api/v1/tickets/attachments/{attachment_id}', '/tickets/attachments/2')
    expect(blob.size).toBe(10)
    expect(blob.type).toBe('application/octet-stream')
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = reject
      reader.readAsText(blob)
    })
    expect(text).toBe('attachment')
  })

  it('handles empty successful deletion responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('DELETE /api/v1/guilds/{guild_id}/tickets/tags/{tag_id}', '/guilds/1/tickets/tags/2')).resolves.toBeUndefined()
  })
})
