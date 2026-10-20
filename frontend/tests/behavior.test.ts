import { describe, it, expect } from 'vitest'
import { humanError } from '../src/shared/api/client'
import { validateSettings } from '../src/modules/settings/validation'
import { safeMediaUrl } from '../src/shared/media/url'
import { uploadFile } from '../src/modules/sources/upload'
import { permittedRoutes } from '../src/app/navigation'

describe('error boundaries', () => {
  it('never exposes internal server errors', () => {
    expect(humanError({ response: { status: 500, data: { error: { code: 'INTERNAL_ERROR', message: 'Traceback secret', request_id: 'request-1' } } } })).not.toContain('Traceback')
    expect(humanError({ response: { status: 409, data: {} } })).toContain('刷新')
  })
})
describe('settings and route boundaries', () => {
  it('rejects invalid integer settings before sending a write', () => {
    expect(validateSettings('resources', { max_concurrent_jobs: 0, connection_timeout_seconds: 30, reconnect_attempts: 3 })).not.toBe('')
    expect(validateSettings('resources', { max_concurrent_jobs: 2, connection_timeout_seconds: 30, reconnect_attempts: 3 })).toBe('')
    expect(validateSettings('general', { system_name: '', timezone: 'Asia/Shanghai' })).not.toBe('')
  })
  it('has no deferred module destination', () => {
    expect(permittedRoutes('/create')).toBe(false)
    expect(permittedRoutes('/agents')).toBe(false)
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
