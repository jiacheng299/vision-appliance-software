import { flushPromises, mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import DashboardPage from '../src/modules/dashboard/DashboardPage.vue'
import MediaPlayer from '../src/shared/media/MediaPlayer.vue'
import { api } from '../src/shared/api'
vi.mock('../src/shared/realtime/useRealtime', () => ({useRealtime: () => ({connected:true})}))

describe('dashboard video wall', () => {
  it.each(['failed', 'disconnected'])('offers reconnect for a %s camera and reloads its status', async (status) => {
    const camera={id:'offline',name:'Offline camera',kind:'camera',status,error_message:'视频连接失败'}
    const fetch=vi.spyOn(api,'dashboard').mockResolvedValue({sources:[camera],counts:{sources_total:1,sources_online:0},recent_events:[],task_summary:{}} as any)
    vi.spyOn(api,'runtime').mockResolvedValue({disk:{used_bytes:1,total_bytes:10}} as any)
    const reconnect=vi.spyOn(api,'testSource').mockResolvedValue({id:'test',source_id:'offline',state:'queued'})
    const wrapper=mount(DashboardPage,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'},MediaPlayer:true}}})
    try {
      await flushPromises()
      const button=wrapper.get('button[aria-label="重新连接：Offline camera"]')
      expect(button.attributes('disabled')).toBeUndefined()
      expect(wrapper.text()).toContain('视频连接失败')
      await button.trigger('click')
      await flushPromises()
      expect(reconnect).toHaveBeenCalledWith('offline')
      expect(fetch).toHaveBeenCalledTimes(2)
    } finally {wrapper.unmount();vi.restoreAllMocks()}
  })

  it('restarts only the selected recording without testing camera connectivity', async () => {
    vi.spyOn(api,'dashboard').mockResolvedValue({sources:[
      {id:'file',name:'Recording',kind:'file',status:'ready'},
      {id:'camera',name:'Camera',kind:'camera',status:'online'},
    ],counts:{sources_total:2,sources_online:1},recent_events:[],task_summary:{}} as any)
    vi.spyOn(api,'runtime').mockResolvedValue({disk:{used_bytes:1,total_bytes:10}} as any)
    const test=vi.spyOn(api,'testSource')
    const wrapper=mount(DashboardPage,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'},MediaPlayer:true}}})
    try {
      await flushPromises()
      const [recording,camera]=wrapper.findAllComponents(MediaPlayer).map(p=>p.vm)
      await wrapper.get('button[aria-label="重新播放：Recording"]').trigger('click')
      await flushPromises()
      const players=wrapper.findAllComponents(MediaPlayer)
      expect(players[0].vm).not.toBe(recording)
      expect(players[1].vm).toBe(camera)
      expect(test).not.toHaveBeenCalled()
    } finally {wrapper.unmount();vi.restoreAllMocks()}
  })

  it('shows reconnect errors and allows another attempt', async () => {
    vi.spyOn(api,'dashboard').mockResolvedValue({sources:[
      {id:'camera',name:'Camera',kind:'camera',status:'online'},
    ],counts:{sources_total:1,sources_online:1},recent_events:[],task_summary:{}} as any)
    vi.spyOn(api,'runtime').mockResolvedValue({disk:{used_bytes:1,total_bytes:10}} as any)
    const reconnect=vi.spyOn(api,'testSource').mockRejectedValue(new Error('offline'))
    const wrapper=mount(DashboardPage,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'},MediaPlayer:true}}})
    try {
      await flushPromises()
      const button=wrapper.get('button[aria-label="重新连接：Camera"]')
      await button.trigger('click');await flushPromises()
      expect(wrapper.get('[role="alert"]').text()).toContain('本机服务')
      expect(button.attributes('disabled')).toBeUndefined()
      await button.trigger('click');await flushPromises()
      expect(reconnect).toHaveBeenCalledTimes(2)
    } finally {wrapper.unmount();vi.restoreAllMocks()}
  })

  it('mounts automatic looping players for ready recordings and cameras', async () => {
    vi.spyOn(api,'dashboard').mockResolvedValue({sources:[
      {id:'file',name:'recording',kind:'file',status:'ready'},
      {id:'camera',name:'live',kind:'camera',status:'online'},
      {id:'pending',name:'import',kind:'file',status:'transcoding'},
    ],counts:{sources_total:3,sources_online:1},recent_events:[],task_summary:{}} as any)
    vi.spyOn(api,'runtime').mockResolvedValue({disk:{used_bytes:1,total_bytes:10}} as any)
    const wrapper=mount(DashboardPage,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'},MediaPlayer:true}}})
    try {
      await flushPromises()
      const players=wrapper.findAllComponents(MediaPlayer)
      expect(players).toHaveLength(2)
      expect(players.map(p=>p.props('source').id)).toEqual(['file','camera'])
      for(const player of players) {
        expect(player.props('autoStart')).toBe(true)
        expect(player.props('loop')).toBe(true)
      }
    } finally {wrapper.unmount();vi.restoreAllMocks()}
  })
})
