import { flushPromises, mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import DashboardPage from '../src/modules/dashboard/DashboardPage.vue'
import MediaPlayer from '../src/shared/media/MediaPlayer.vue'
import { api } from '../src/shared/api'
vi.mock('../src/shared/realtime/useRealtime', () => ({useRealtime: () => ({connected:true})}))

describe('dashboard video wall', () => {
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
