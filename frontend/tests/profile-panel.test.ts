import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NInput } from 'naive-ui'
import ProfilePanel from '../src/modules/sources/ProfilePanel.vue'
import { profileApi, type SemanticProfile } from '../src/modules/sources/profileApi'

const profile: SemanticProfile = {
  source_id: 'cam', view_version: 'v1', version: 5,
  intrinsic: { resolution: '960x540', mount_position: '山地道路' },
  runtime: {}, evaluated_at: 1_000.0, updated_at: '2026-11-17T00:00:00Z',
  attributes: [{
    key: 'lighting', value: { label: 'strong_glare' }, source_kind: 'frame',
    source_frame_ts: 12.5, roi: [], observed_at: 900.0, confidence: 0.9, tau_seconds: 60,
    hard_expiry_at: 1_600.0, stored_state: 'valid', state: 'valid', strength: 0.786721,
    usable: true, reason: null, version: 2,
  }],
}
afterEach(() => vi.restoreAllMocks())

it('shows the layered profile with attribute validity and strength', async () => {
  const read = vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    expect(read).toHaveBeenCalledWith('cam')
    expect(wrapper.text()).toContain('版本 5')
    expect(wrapper.text()).toContain('strong_glare')
    expect(wrapper.text()).toContain('有效')
    expect(wrapper.text()).toContain('0.79')
    expect(wrapper.text()).toContain('剩余 600 秒')
    const resolution = wrapper.findAllComponents(NInput)[0]
    expect((resolution.props() as { value: string }).value).toBe('960x540')
  } finally { wrapper.unmount() }
})

it('states plainly that an empty profile invents nothing', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue({ ...profile, attributes: [], version: 0 })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('还没有动态属性')
    expect(wrapper.text()).toContain('不会臆造任何场景条件')
  } finally { wrapper.unmount() }
})

it('writes an attribute with its source, confidence and validity', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const upsert = vi.spyOn(profileApi, 'upsertAttribute').mockResolvedValue(profile)
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    const key = wrapper.findAll('input').find(input => input.attributes('placeholder') === 'lighting')
    const label = wrapper.findAll('input').find(input => input.attributes('placeholder') === 'strong_glare')
    await key!.setValue('weather')
    await label!.setValue('snow')
    const submit = wrapper.findAll('button').find(button => button.text().includes('写入属性'))
    expect(submit).toBeTruthy()
    await submit!.trigger('click')
    await flushPromises()
    expect(upsert).toHaveBeenCalledWith('cam', 'weather', expect.objectContaining({
      value: 'snow', source_kind: 'frame', confidence: 0.8,
    }))
  } finally { wrapper.unmount() }
})

it('deletes an attribute and refreshes the profile', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const remove = vi.spyOn(profileApi, 'deleteAttribute').mockResolvedValue({ ...profile, attributes: [] })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    const button = wrapper.findAll('button').find(item => item.text().includes('删除'))
    await button!.trigger('click')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('cam', 'lighting')
  } finally { wrapper.unmount() }
})

it('refuses an unsafe attribute name before calling the server', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue({ ...profile, attributes: [] })
  const upsert = vi.spyOn(profileApi, 'upsertAttribute')
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    const key = wrapper.findAll('input').find(input => input.attributes('placeholder') === 'lighting')
    const label = wrapper.findAll('input').find(input => input.attributes('placeholder') === 'strong_glare')
    await key!.setValue('bad key')
    await label!.setValue('snow')
    const submit = wrapper.findAll('button').find(button => button.text().includes('写入属性'))
    expect(submit!.attributes('disabled')).toBeDefined()
    expect(upsert).not.toHaveBeenCalled()
  } finally { wrapper.unmount() }
})

it('can initialise the profile from the device record and reports what it did', async () => {
  vi.spyOn(profileApi, 'read').mockResolvedValue(profile)
  const bootstrap = vi.spyOn(profileApi, 'bootstrap').mockResolvedValue({
    source_id: 'cam', created: ['固有层 resolution=960x540'], skipped: ['固有层已完整'],
    notices: ['摄像头源不做首帧取图，动态层需由运行中的观察或人工写入。'],
    profile, bootstrapped_at: '2026-11-17T00:00:00Z',
  })
  const wrapper = mount(ProfilePanel, { props: { sourceId: 'cam' } })
  try {
    await flushPromises()
    const button = wrapper.findAll('button').find(item => item.text().includes('按设备记录初始化'))
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()
    expect(bootstrap).toHaveBeenCalledWith('cam')
    const result = wrapper.get('[aria-label="初始化结果"]')
    expect(result.text()).toContain('固有层 resolution=960x540')
    expect(result.text()).toContain('摄像头源不做首帧取图')
  } finally { wrapper.unmount() }
})