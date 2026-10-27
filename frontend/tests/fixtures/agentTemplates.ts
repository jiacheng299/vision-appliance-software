import type { ParameterDefinition,TemplateDetail } from '../../src/modules/agents/templatesApi'
import type { AgentDetail,CapabilityCatalog } from '../../src/modules/agents/api'
import type { Source } from '../../src/shared/api/types'
const time='2026-10-27T00:00:00Z'
export const reference={model_id:'fire-model',model_version:'1',template_id:'engine-fire',template_version:'1'}
export const pool:ParameterDefinition[]=[
  {key:'confidence_threshold',label:'置信度阈值',category:'检测条件',type:'number',description:'0到1',unit:'',minimum:0,maximum:1,step:.01,options:[]},
  {key:'min_count',label:'最小目标数量',category:'数量条件',type:'integer',description:'至少几个目标',unit:'个',minimum:0,maximum:100,step:1,options:[]},
  {key:'color',label:'目标颜色',category:'属性条件',type:'select',description:'模型须支持',unit:'',minimum:null,maximum:null,step:1,options:[{value:'red',label:'红色'},{value:'blue',label:'蓝色'}]},
  {key:'require_tracking',label:'启用目标跟踪',category:'跟踪条件',type:'boolean',description:'执行器须支持',unit:'',minimum:null,maximum:null,step:1,options:[]},
]
export const catalog:CapabilityCatalog={fingerprint:'fp',data_origin:'mock',items:[{name:'火灾模型 + 技术模板',reference,targets:['fire'],rules:['presence'],requires_region:[],requires_duration:[],limitations:['模拟'],parameter_keys:['confidence_threshold','min_count','color','require_tracking']}]}
export function template(version=1):TemplateDetail{
  const revision={id:`template-revision-${version}`,template_id:'template-1',revision_no:version,state:'published' as const,created_at:time,published_at:time,
    config:{model_ref:reference,default_target:'fire',default_rule:'presence',title:'火灾检测',summary:'火灾检测业务',parameters:[{key:'confidence_threshold',value:version===1?.8:.95,required:true}]}}
  return {id:'template-1',name:'火灾检测',description:'火灾检测业务',row_version:version,created_at:time,updated_at:time,archived_at:null,imported_from_agent_id:null,latest_revision:revision,published_revision:revision,revisions:[revision],task_count:0,source_count:0}
}
export const source:Source={id:'source-1',name:'入口录像',kind:'file',status:'ready',created_at:time,updated_at:time,row_version:1,observed_at:time,address:null,width:320,height:180,fps:10,duration_ms:10000,size_bytes:1000,sha256:'hash',preview_url:null,thumbnail_url:null,error_code:null,error_message:null}
export function task():AgentDetail{
  const revision={id:'task-revision',agent_id:'task-1',revision_no:1,base_revision_id:null,state:'draft' as const,row_version:1,created_at:time,updated_at:time,latest_validation_id:null,published_at:null,baseline_run_id:null,
    config:{schema_version:'1.0' as const,agent_template_ref:{template_id:'template-1',revision_id:'template-revision-1',revision_no:1,name:'火灾检测'},channels:[{channel_id:'channel',name:'火灾检测',task_mode:'template' as const,sources:[{source_id:source.id,regions:[],start_media_ms:null,end_media_ms:null}],requirement_text:'检测火源',target:'fire',rule:'presence',duration_seconds:null,capability_ref:reference,parameters:[{key:'confidence_threshold',value:.8,required:true}]}]}}
  return {id:'task-1',name:'仓库火灾检测任务',description:'',status:'draft',row_version:1,created_at:time,updated_at:time,latest_revision:revision,archived_at:null,desired_revision_id:null,today_event_count:null,latest_event_at:null,data_origin:'mock',active_run_count:0,active_revision_nos:[],failed_run_count:0,pending_review_count:null,revisions:[revision],execution_available:true,limitation:''}
}
