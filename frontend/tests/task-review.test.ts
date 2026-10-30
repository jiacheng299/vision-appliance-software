import { it,expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskReview from '../src/modules/task-create/TaskReview.vue'
import { template,source,pool } from './fixtures/agentTemplates'
it('shows every input region and media range separately from shared conditions',()=>{
  const w=mount(TaskReview,{props:{templateName:'火灾检测',version:template().published_revision!,name:'园区任务',sources:[source,{...source,id:'camera',name:'二号摄像头',kind:'camera'}],
    bindings:[{source_id:source.id,start_media_ms:1000,end_media_ms:5000,regions:[{id:'one',name:'入口',points:[[0,0],[1,0],[1,1]]}]},{source_id:'camera',regions:[]}],
    settings:[{key:'confidence_threshold',value:.8,required:true}],definitions:pool,validation:null,operation:null,expired:false,ack:false,canAcknowledge:false,published:false},global:{stubs:{NCheckbox:true}}})
  const text=w.text()
  for(const value of ['入口录像','二号摄像头','入口','1 – 5 秒','监控直播','置信度阈值','0.8','尚未验证'])expect(text).toContain(value)
  w.unmount()
})
