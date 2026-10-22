import { describe, it, expect } from 'vitest'
import { csrfToken, humanError } from '../src/shared/api/client'
import { validateCredentials } from '../src/shared/auth/validation'
import { validateSettings } from '../src/modules/settings/validation'
import { safeMediaUrl } from '../src/shared/media/url'
import { uploadFile } from '../src/modules/sources/upload'
import { permittedRoutes } from '../src/app/navigation'

describe('session and error boundaries', () => {
  it('reads the exact CSRF cookie even with similarly named cookies', () => {
    expect(csrfToken('other_vision_csrf=bad; vision_csrf=hello%2Bworld')).toBe('hello+world')
    expect(csrfToken('vision_session=secret')).toBe('')
  })
  it('never exposes internal server errors', () => {
    expect(humanError({ response: { status: 500, data: { error: { code: 'INTERNAL_ERROR', message: 'Traceback secret', request_id: 'request-1' } } } })).not.toContain('Traceback')
    expect(humanError({ response: { status: 409, data: {} } })).toContain('刷新')
  })
  it('requires a strong first administrator password but accepts existing login passwords', () => {
    expect(validateCredentials('admin', 'short', true)).toContain('12')
    expect(validateCredentials('admin', 'short', false)).toBe('')
    expect(validateCredentials(' ', 'long-password', true)).not.toBe('')
  })
})
describe('settings and route boundaries', () => {
  it('rejects invalid integer settings before sending a write', () => {
    expect(validateSettings('resources', { max_concurrent_jobs: 0, connection_timeout_seconds: 30, reconnect_attempts: 3 })).not.toBe('')
    expect(validateSettings('resources', { max_concurrent_jobs: 2, connection_timeout_seconds: 30, reconnect_attempts: 3 })).toBe('')
    expect(validateSettings('general', { system_name: '', timezone: 'Asia/Shanghai' })).not.toBe('')
  })
  it('enables agents while leaving task creation and models deferred', () => {
    expect(permittedRoutes('/create')).toBe(false)
    expect(permittedRoutes('/agents')).toBe(true)
    expect(permittedRoutes('/agents/123/config')).toBe(true)
    expect(permittedRoutes('/agents/123/unknown')).toBe(false)
    expect(permittedRoutes('/models')).toBe(false)
    expect(permittedRoutes('/sources/123')).toBe(true)
    expect(permittedRoutes('/settings/security')).toBe(true)
  })
  it('rejects external or unprotected playback addresses', () => {
    expect(safeMediaUrl('rtsp://camera/live')).toBeNull()
    expect(safeMediaUrl('https://example.com/file.mp4')).toBeNull()
    expect(safeMediaUrl('/api/v1/sources/abc/media')).toBe('/api/v1/sources/abc/media')
    expect(safeMediaUrl('/api/v1/../../private')).toBeNull()
  })
})
describe('file upload protocol', () => {
  it('uploads sequential raw chunks and only finishes after server readiness', async () => {
    const calls: string[] = []
    let polls = 0
    const result = await uploadFile(new File(['abcdef'], 'sample.mp4'), {
      create: async () => ({id:'u1',state:'uploading',received_bytes:0,size_bytes:6,source_id:null,error_code:null,error_message:null}),
      chunk: async (_id, n, data) => { calls.push(`${n}:${data.size}`) },
      complete: async () => { calls.push('complete') },
      get: async () => ({id:'u1',state:++polls === 1 ? 'probing' : 'ready',received_bytes:6,size_bytes:6,source_id:polls === 1 ? null : 's1',error_code:null,error_message:null}),
      cancel: async () => {},
    }, () => {}, {chunkSize:4, wait:async () => {}})
    expect(calls).toEqual(['0:4','1:2','complete'])
    expect(result.source_id).toBe('s1')
    expect(polls).toBe(2)
  })
})
