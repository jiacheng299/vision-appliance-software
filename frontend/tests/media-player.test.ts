import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MediaPlayer from '../src/shared/media/MediaPlayer.vue'
import { api } from '../src/shared/api'
import type { MediaSession, Source } from '../src/shared/api/types'

const hls = vi.hoisted(() => ({ instances: [] as any[], supported: true, importGate: null as Promise<void> | null }))
vi.mock('hls.js', async () => {
  if (hls.importGate) await hls.importGate
  return { default: class {
  static isSupported() { return hls.supported }
  static Events = { ERROR: 'error', MANIFEST_PARSED: 'manifest' }
  loadSource = vi.fn()
  attachMedia = vi.fn()
  destroy = vi.fn()
  listeners: Record<string, (...args: any[]) => void> = {}
  on(event: string, callback: (...args: any[]) => void) { this.listeners[event] = callback }
  constructor() { hls.instances.push(this) }
} }
})

const source = (id = 'camera-1') => ({ id, kind: 'camera' } as Source)
const session = (protocol: MediaSession['protocol'] = 'hls', url = '/api/v1/media/live/index.m3u8'): MediaSession => ({
  session_id: 'preview', protocol, playback_url: url, expires_at: '2099-01-01T00:00:00Z',
})
const wrappers: ReturnType<typeof mount>[] = []
function open() {
  const wrapper = mount(MediaPlayer, { props: { source: source() } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  hls.instances.length = 0
  hls.supported = true
  vi.spyOn(HTMLMediaElement.prototype, 'canPlayType').mockReturnValue('')
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(api, 'mediaSession').mockResolvedValue(session())
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
})

describe('media preview', () => {
  it('does not attach a delayed HLS module to a source that has been replaced', async () => {
    let finishImport!: () => void
    hls.importGate = new Promise(resolve => { finishImport = resolve })
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('video').exists()).toBe(true)
    await wrapper.setProps({ source: source('camera-2') })
    finishImport()
    await flushPromises()
    expect(wrapper.find('video').exists()).toBe(false)
    expect(hls.instances).toHaveLength(0)
    expect(wrapper.get('button').classes()).not.toContain('n-button--loading')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(hls.instances).toHaveLength(1)
    hls.importGate = null
  })

  it('uses hls.js when native HLS is unavailable and starts muted inline playback', async () => {
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(hls.instances).toHaveLength(1)
    const video = wrapper.get('video').element
    expect(hls.instances[0].loadSource).toHaveBeenCalledWith('/api/v1/media/live/index.m3u8')
    expect(hls.instances[0].attachMedia).toHaveBeenCalledWith(video)
    expect(video.muted).toBe(true)
    expect(video.playsInline).toBe(true)
    hls.instances[0].listeners.manifest()
    expect(video.play).toHaveBeenCalled()
  })

  it('uses native HLS when supported', async () => {
    vi.mocked(HTMLMediaElement.prototype.canPlayType).mockReturnValue('maybe')
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const video = wrapper.get('video').element
    expect(video.getAttribute('src')).toBe('/api/v1/media/live/index.m3u8')
    expect(video.muted).toBe(true)
    expect(video.autoplay).toBe(true)
    expect(hls.instances).toHaveLength(0)
  })

  it('preserves normal file controls without muting or autoplay', async () => {
    vi.mocked(api.mediaSession).mockResolvedValue(session('file', '/api/v1/media/clip.mp4'))
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const video = wrapper.get('video').element
    expect(video.getAttribute('src')).toBe('/api/v1/media/clip.mp4')
    expect(video.controls).toBe(true)
    expect(video.muted).toBe(false)
    expect(video.autoplay).toBe(false)
    expect(hls.instances).toHaveLength(0)
  })

  it('releases a native video source before unmount removes the element ref', async () => {
    vi.mocked(api.mediaSession).mockResolvedValue(session('file', '/api/v1/media/clip.mp4'))
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const video = wrapper.get('video').element
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    expect(video.hasAttribute('src')).toBe(false)
    expect(video.pause).toHaveBeenCalled()
    expect(video.load).toHaveBeenCalled()
  })

  it('destroys playback and releases the video when the source changes or unmounts', async () => {
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const video = wrapper.get('video').element
    const first = hls.instances[0]
    await wrapper.setProps({ source: source('camera-2') })
    expect(first.destroy).toHaveBeenCalledOnce()
    expect(video.pause).toHaveBeenCalled()
    expect(video.hasAttribute('src')).toBe(false)
    expect(wrapper.find('video').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    wrapper.unmount()
    expect(hls.instances[1].destroy).toHaveBeenCalledOnce()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
  })

  it('ignores a late session after source change and clears the old loading state', async () => {
    let finish!: (value: MediaSession) => void
    vi.mocked(api.mediaSession).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ source: source('camera-2') })
    expect(wrapper.get('button').classes()).not.toContain('n-button--loading')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    finish(session('file', '/api/v1/media/old.mp4'))
    await flushPromises()
    expect(hls.instances).toHaveLength(1)
    expect(wrapper.get('video').attributes('src')).not.toBe('/api/v1/media/old.mp4')
  })

  it('shows fatal HLS failures and supports a fresh retry without stale errors', async () => {
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const first = hls.instances[0]
    first.listeners.error('error', { fatal: false, type: 'networkError' })
    await flushPromises()
    expect(wrapper.find('video').exists()).toBe(true)
    first.listeners.error('error', { fatal: true, type: 'networkError' })
    await flushPromises()
    expect(wrapper.text()).toContain('网络')
    expect(wrapper.get('button').text()).toContain('重试')
    expect(first.destroy).toHaveBeenCalledOnce()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    first.listeners.error('error', { fatal: true, type: 'networkError' })
    await flushPromises()
    expect(wrapper.find('video').exists()).toBe(true)
    expect(hls.instances).toHaveLength(2)
  })

  it('rejects external playback URLs before loading media', async () => {
    vi.mocked(api.mediaSession).mockResolvedValue(session('hls', 'https://outside.test/live.m3u8'))
    const wrapper = open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('本地媒体访问规则')
    expect(wrapper.find('video').exists()).toBe(false)
    expect(hls.instances).toHaveLength(0)
  })
})

describe('automatic wall playback', () => {
  it('opens a camera automatically when requested', async () => {
    const wrapper = mount(MediaPlayer, { props: { source: source(), autoStart: true } })
    wrappers.push(wrapper)
    await flushPromises()
    expect(api.mediaSession).toHaveBeenCalledWith('camera-1')
    expect(wrapper.find('video').exists()).toBe(true)
    expect(hls.instances).toHaveLength(1)
  })
  it('plays wall recordings muted and looped', async () => {
    vi.mocked(api.mediaSession).mockResolvedValue(session('file', '/api/v1/media/clip.mp4'))
    const wrapper = mount(MediaPlayer, { props: { source: { ...source(), kind: 'file' }, autoStart: true, loop: true } })
    wrappers.push(wrapper)
    await flushPromises()
    const video = wrapper.get('video').element
    expect(video.autoplay).toBe(true)
    expect(video.muted).toBe(true)
    expect(video.loop).toBe(true)
    expect(video.play).toHaveBeenCalled()
  })
})
