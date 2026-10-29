import { describe,it,expect,vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent,onUnmounted } from 'vue'
import { channelSources,setChannelSources,wallGroups } from '../src/modules/agents/channelSources'
import { newChannel } from '../src/modules/agents/draft'
import { actualRuns } from '../src/modules/agents/state'
import type { Revision,Run } from '../src/modules/agents/api'
import type { Source } from '../src/shared/api/types'
import VideoWall from '../src/modules/agents/VideoWall.vue'
vi.mock('naive-ui',async()=>{const {defineComponent}=await import('vue');return {
  NButton:defineComponent({props:['disabled'],template:'<button :disabled="disabled"><slot/></button>'}),
  NSelect:defineComponent({props:['value','options'],template:'<select/>'})
}})
it('keeps regions attached to their source when selection changes, with one shared rule',()=>{
  const c=newChannel();c.source_id='A';c.rule='dwell';c.regions=[{id:'r',name:'door',points:[[0,0],[1,0],[0,1]]}]
  setChannelSources(c,['A','B']);expect(channelSources(c)[0]!.regions).toHaveLength(1);expect(channelSources(c)[1]!.regions).toEqual([])
  setChannelSources(c,['B','A']);expect(channelSources(c)[1]!.regions).toHaveLength(1);expect(c.rule).toBe('dwell');expect(c.source_id).toBeNull()
})
it('does not collapse different sources in the same channel into one run',()=>{
  const row=(id:string,source_id:string,state:Run['state'])=>({id,source_id,state,channel_id:'group',created_at:id}) as Run
  const runs=actualRuns([row('1','A','running'),row('2','B','failed'),row('0','A','stopped')])
  expect(runs).toHaveLength(2)
  const c=newChannel();c.channel_id='group';setChannelSources(c,['A'])
  expect(wallGroups({schema_version:'1.0',channels:[c]},runs)[0]!.tiles).toHaveLength(2)
})
it('opens only visible wall tiles and releases all players when changing page',async()=>{
  const c=newChannel();setChannelSources(c,['A','B','C','D','E'])
  const released=vi.fn(),Player=defineComponent({props:{autoStart:Boolean},setup(){onUnmounted(released)},template:'<div class="test-player"/>'})
  const wrapper=mount(VideoWall,{props:{agentId:'a',revision:{id:'r',config:{schema_version:'1.0',channels:[c]}} as Revision,runs:[],sources:['A','B','C','D','E'].map(id=>({id,name:id,kind:'file'} as Source)),runtimeAvailable:false},global:{stubs:{MediaPlayer:Player,RunPlayer:Player,AgentStatus:true}}})
  const button=(text:string)=>wrapper.findAll('button').find(b=>b.text()===text)!
  expect(wrapper.findAll('.wall-tile')).toHaveLength(4);expect(wrapper.findAll('.test-player')).toHaveLength(0)
  await button('打开本页画面').trigger('click');expect(wrapper.findAll('.test-player')).toHaveLength(4)
  expect(wrapper.findAllComponents(Player).every(player=>player.props('autoStart')===true)).toBe(true)
  await wrapper.setProps({revision:JSON.parse(JSON.stringify(wrapper.props('revision')))})
  expect(wrapper.findAll('.test-player')).toHaveLength(4)
  expect(released).not.toHaveBeenCalled()
  await button('下一页').trigger('click');expect(wrapper.findAll('.wall-tile')).toHaveLength(1);expect(released).toHaveBeenCalledTimes(4)
  expect(wrapper.findAll('.test-player')).toHaveLength(0);wrapper.unmount()
})
it('passes persisted absence state to the wall player without adding it to player identity',async()=>{
  const c=newChannel();c.channel_id='group';c.name='主通道';setChannelSources(c,['A'])
  const run={id:'run-1',agent_id:'a',revision_id:'r',revision_no:1,channel_id:'group',channel_name:'主通道',source_id:'A',source_kind:'camera',state:'running',recording_available:false,config_snapshot:{schema_version:'1.0',channels:[]},message:'',alert_state:'absence',data_origin:'real'} as Run
  const Player=defineComponent({props:['identity','alertActive','alertLabel'],template:'<div class="run-player-stub" :data-identity="identity" :data-alert-active="alertActive" :data-alert-label="alertLabel"/>'})
  const wrapper=mount(VideoWall,{props:{agentId:'a',revision:{id:'r',config:{schema_version:'1.0',channels:[c]}} as Revision,runs:[run],sources:[{id:'A',name:'A',kind:'camera'} as Source],runtimeAvailable:true},global:{stubs:{MediaPlayer:true,RunPlayer:Player,AgentStatus:true}}})
  await wrapper.get('[aria-label="打开画面：A"]').trigger('click')
  const player=wrapper.get('.run-player-stub')
  expect(player.attributes('data-alert-active')).toBe('true')
  expect(player.attributes('data-alert-label')).toBe('人员缺岗')
  expect(player.attributes('data-identity')).toBe('run-1:running:true')
  wrapper.unmount()
})
it('shows a persistent alert on a closed absence tile and clears it when the run is normal',async()=>{
  const c=newChannel();c.channel_id='group';c.name='主通道';setChannelSources(c,['A'])
  const run={id:'run-1',agent_id:'a',revision_id:'r',revision_no:1,channel_id:'group',channel_name:'主通道',source_id:'A',source_kind:'camera',state:'running',recording_available:false,config_snapshot:{schema_version:'1.0',channels:[]},message:'',alert_state:'absence',data_origin:'real'} as Run
  const wrapper=mount(VideoWall,{props:{agentId:'a',revision:{id:'r',config:{schema_version:'1.0',channels:[c]}} as Revision,runs:[run],sources:[{id:'A',name:'A',kind:'camera'} as Source],runtimeAvailable:true},global:{stubs:{MediaPlayer:true,RunPlayer:true,AgentStatus:true}}})

  expect(wrapper.find('.run-player').exists()).toBe(false)
  expect(wrapper.get('.wall-tile').classes()).toContain('alert-active')
  expect(wrapper.get('.wall-poster [role="alert"]').text()).toBe('人员缺岗')

  await wrapper.setProps({runs:[{...run,alert_state:'normal'}]})
  expect(wrapper.get('.wall-tile').classes()).not.toContain('alert-active')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  wrapper.unmount()
})
