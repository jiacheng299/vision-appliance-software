import { client, humanError } from '../../shared/api/client'
import type { components } from '../../shared/api/generated'
export type Model = components['schemas']['ModelDTO']
export type ModelInput = components['schemas']['ModelInput']
export type ModelPage = components['schemas']['ModelPage']
export type Deployments = components['schemas']['DeploymentPage']
export type Usage = Deployments['selections'][number]['usage']
export type ModelFile = components['schemas']['ModelFileDTO']
export type References = components['schemas']['ReferencePage']
export type ParseResult = components['schemas']['ParseResult']
export type FixedTemplate = components['schemas']['FixedTaskTemplate']
export type TaskPlan = components['schemas']['PlanResult']
export type PlanningChannel = components['schemas']['ChannelConfig']
export const modelApi = {
  templates: () => client.get<components['schemas']['FixedTemplatePage']>('/task-templates').then(r=>r.data),
  plan: (channel:PlanningChannel) => client.post<TaskPlan>('/requirements/plan',{channel}).then(r=>r.data),
  list: (q='',validation='',cursor?:string) => client.get<ModelPage>('/models',{params:{q,validation:validation||undefined,cursor,limit:24}}).then(r=>r.data),
  detail: (id:string,version?:string) => client.get<Model>(`/models/${encodeURIComponent(id)}`,{params:{version}}).then(r=>r.data),
  upload: (file:File, progress:(n:number)=>void) => client.post<ModelFile>('/model-files',file,{params:{filename:file.name},headers:{'Content-Type':'application/octet-stream'},timeout:0,onUploadProgress:event=>progress(Math.round(event.loaded/file.size*100))}).then(r=>r.data),
  create: (body:ModelInput,key:string,id?:string) => client.post<Model>(id?`/models/${encodeURIComponent(id)}/versions`:'/models',body,{headers:{'Idempotency-Key':key}}).then(r=>r.data),
  verify: (m:Model) => client.post<Model>(`/models/${encodeURIComponent(m.id)}/versions/${encodeURIComponent(m.version)}/verify`,{row_version:m.row_version}).then(r=>r.data),
  archive: (m:Model,acknowledge_history:boolean) => client.post<Model>(`/models/${encodeURIComponent(m.id)}/versions/${encodeURIComponent(m.version)}/archive`,{row_version:m.row_version,acknowledge_history}).then(r=>r.data),
  references: async (m:Model):Promise<References['items']> => {
    const result:References['items']=[],seen=new Set<string>();let cursor:string|undefined
    do{const page:References=await client.get<References>('/agent-services/references',{params:{model_id:m.id,model_version:m.version,cursor}}).then(r=>r.data);result.push(...page.items);cursor=page.next_cursor??undefined;if(cursor&&seen.has(cursor))throw Error('Reference pagination did not advance');if(cursor)seen.add(cursor)}while(cursor)
    return result
  },
  deployments: () => client.get<Deployments>('/llm/deployments').then(r=>r.data),
  select: (usage:Usage,deployment_id:string,row_version:number) => client.put(`/llm/selections/${usage}`,{deployment_id,row_version}),
  parse: (requirement_text:string) => client.post<ParseResult>('/requirements/parse',{requirement_text}).then(r=>r.data),
}
const publicCodes = new Set(['model_verifier_unavailable','model_conflict','model_archived','model_file_required','model_file_empty','model_file_too_large','model_version_exists','model_history_confirmation','model_in_use','llm_not_selected','llm_not_healthy','analysis_service_unavailable','reference_service_unavailable','catalog_changed','task_mode_invalid','execution_plan_stale','execution_plan_blocked','multimodal_service_unavailable','multimodal_execution_unavailable','multimodal_api_not_configured','multimodal_api_timeout','multimodal_api_invalid_response','multimodal_deployment_changed','multimodal_requirement_required','multimodal_template_limit'])
export function memberError(error:unknown):string{
  const detail=(error as {response?:{data?:{error?:{code?:string;message?:string}}}})?.response?.data?.error
  return detail?.code&&publicCodes.has(detail.code)&&detail.message?detail.message:humanError(error)
}
