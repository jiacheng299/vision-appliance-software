import { client,humanError } from '../../shared/api/client'
import { agentJson } from './json'
import type { components } from '../../shared/api/generated'
export type AgentTemplate=components['schemas']['TemplateDTO']
export type TemplateDetail=components['schemas']['TemplateDetail']
export type TemplateRevision=components['schemas']['TemplateRevisionDTO']
export type TemplateConfig=components['schemas']['TemplateConfig'] & {default_source?:components['schemas']['ChannelSource']|null}
export type ParameterSetting=components['schemas']['ParameterSetting']
export type ParameterDefinition=components['schemas']['ParameterDefinition']
export type TemplateTask=components['schemas']['TemplateTaskDTO']
export type TemplateSource=components['schemas']['TemplateSource']
export type TemplateTaskInput=components['schemas']['TemplateTaskCreate']
export type TemplateInput=components['schemas']['TemplateCreate']
const options=(key?:string)=>({headers:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},transformRequest:[agentJson]})
export interface TemplateMatcherStatus {configured:boolean;provider:'deepseek';model:string;threshold:number}
export interface TemplateMatchResult {status:'matched'|'no_match';template_id:string|null;template_revision_id:string|null;confidence:number;reason:string;uncovered_requirements:string[];provider:'deepseek';model:string}
export const templatesApi={
  matcherStatus:()=>client.get<TemplateMatcherStatus>('/agent-template-matcher').then(r=>r.data),
  match:(body:{requirement_text:string})=>client.post<TemplateMatchResult>('/agent-templates/match',body,options()).then(r=>r.data),
  list:(q='',cursor?:string,published_only=false,archived=false)=>client.get<components['schemas']['TemplatePage']>('/agent-templates',{params:{q,cursor,published_only,archived,limit:24}}).then(r=>r.data),
  detail:(id:string)=>client.get<TemplateDetail>(`/agent-templates/${encodeURIComponent(id)}`).then(r=>r.data),
  create:(body:TemplateInput,key:string)=>client.post<TemplateDetail>('/agent-templates',body,options(key)).then(r=>r.data),
  save:(row:AgentTemplate,body:TemplateInput)=>client.patch<TemplateDetail>(`/agent-templates/${row.id}`,{...body,row_version:row.row_version},options()).then(r=>r.data),
  publish:(row:AgentTemplate,key:string)=>client.post<TemplateDetail>(`/agent-templates/${row.id}/publish`,{row_version:row.row_version,revision_id:row.latest_revision.id},options(key)).then(r=>r.data),
  archive:(row:AgentTemplate,archived:boolean)=>client.post<TemplateDetail>(`/agent-templates/${row.id}/archive`,{row_version:row.row_version,archived},options()).then(r=>r.data),
  parameters:()=>client.get<components['schemas']['ParameterCatalog']>('/agent-parameter-options').then(r=>r.data),
  tasks:(id:string,cursor?:string)=>client.get<components['schemas']['TemplateTaskPage']>(`/agent-templates/${id}/tasks`,{params:{cursor,limit:50}}).then(r=>r.data),
  sources:(id:string,cursor?:string)=>client.get<components['schemas']['TemplateSourcePage']>(`/agent-templates/${id}/sources`,{params:{cursor,limit:100}}).then(r=>r.data),
  instantiate:(id:string,body:TemplateTaskInput,key:string)=>client.post<components['schemas']['AgentDetail']>(`/agent-templates/${id}/tasks`,body,options(key)).then(r=>r.data),
}
export const modelKey=(ref:TemplateConfig['model_ref'])=>ref?JSON.stringify(ref):null
export const plainModelName=(name:string)=>name.split(' + ')[0]!
export function templateError(error:unknown){const value=error as {response?:{data?:{error?:{message?:string}}}};return value?.response?.data?.error?.message??humanError(error)}
export async function allPublishedTemplates(){
  const result:AgentTemplate[]=[],visited=new Set<string>();let cursor:string|undefined
  do{const page=await templatesApi.list('',cursor,true);result.push(...page.items);cursor=page.next_cursor??undefined;if(cursor&&visited.has(cursor))throw new Error('Template pagination did not advance');if(cursor)visited.add(cursor)}while(cursor)
  return result
}
