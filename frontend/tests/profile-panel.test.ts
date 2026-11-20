import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ProfilePanel from '../src/modules/sources/ProfilePanel.vue'
import { profileApi, type SemanticProfile } from '../src/modules/sources/profileApi'

const future = Date.now() / 1000 + 600
const profile: SemanticProfile = {
  source_id: 'cam', view_version: 'v1', version: 5,
  intrinsic: { resolution: '960x540', mount_position: '山地道路' },
  runtime: {}, evaluated_at: 1_000.0, updated_at: '2026-11-17T00:00:00Z',
  attributes: [{
    key: 'lighting', value: { label: 'strong_glare' }, source_kind: 'probe',
    source_frame_ts: 12.5, roi: [], observed_at: 900.0, confidence: 0.9, tau_seconds: 60,
    hard_expiry_at: future, stored_state: 'valid', state: 'valid', strength: 0.786721,
    usable: true, reason: null, version: 2,
  }],
}
afterEach(() => vi.restoreAllMocks())

it('shows intrinsic resolution read-only with attribute validity and strength', async () => {
  const read = vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '960 × 540' } })
  try {
    await flushPromises()
    expect(read).toHaveBeenCalledWith('cam')
    expect(wrapper.text()).toContain('版本 5')
    expect(wrapper.text()).toContain('960 × 540')
    expect(wrapper.text()).toContain('强光眩光')
    expect(wrapper.text()).not.toContain('strong_glare')
    expect(wrapper.text()).toContain('低频探针')
    expect(wrapper.text()).toContain('有效')
    expect(wrapper.text()).toContain('0.79')
    expect(wrapper.text()).toContain('剩余')
    expect(wrapper.findAll('input')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('mount_position')
  } finally { wrapper.unmount() }
})

it('falls back to the stored intrinsic resolution when the source has none', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('960x540')
  } finally { wrapper.unmount() }
})

it('states plainly that an empty profile invents nothing', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue({ ...profile, attributes: [], version: 0 })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('还没有动态属性')
    expect(wrapper.text()).toContain('不会臆造任何场景条件')
  } finally { wrapper.unmount() }
})

it('analyzes frames with the configured LLM and shows what was written', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const analyze = vi.spyOn(profileApi, 'analyze').mockResolvedValue({
    source_id: 'cam', analyzed: ['lighting', 'occlusion'], profile,
    analyzed_at: '2026-11-20T00:00:00Z',
  })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="大模型分析画面"]').trigger('click')
    await flushPromises()
    expect(analyze).toHaveBeenCalledWith('cam')
    expect(wrapper.text()).toContain('已写入动态属性：光照、遮挡')
  } finally { wrapper.unmount() }
})

it('surfaces an LLM analysis failure without touching the profile', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const analyze = vi.spyOn(profileApi, 'analyze').mockRejectedValue(new Error('DeepSeek 官方接口暂不支持图像输入'))
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    await wrapper.get('[aria-label="大模型分析画面"]').trigger('click')
    await flushPromises()
    expect(analyze).toHaveBeenCalledWith('cam')
    expect(wrapper.text()).toContain('DeepSeek 官方接口暂不支持图像输入')
  } finally { wrapper.unmount() }
})

it('shows expired attributes as expired once the hard expiry passes', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue({
    ...profile,
    attributes: [{ ...profile.attributes[0]!, hard_expiry_at: Date.now() / 1000 - 10 }],
  })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('已过期（未知）')
    expect(wrapper.text()).toContain('已过期')
  } finally { wrapper.unmount() }
})

it('deletes an attribute and refreshes the profile', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const remove = vi.spyOn(profileApi, 'deleteAttribute').mockResolvedValue({ ...profile, attributes: [] })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam', resolution: '' } })
  try {
    await flushPromises()
    const button = wrapper.findAll('button').find(item => item.text().includes('删除'))
    await button!.trigger('click')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('cam', 'lighting')
  } finally { wrapper.unmount() }
})
