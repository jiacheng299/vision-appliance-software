import { newId } from '../../shared/ids'
import type { components } from '../../shared/api/generated'
import { regionError, type Point } from '../../shared/media/regionGeometry'
export type Config=components['schemas']['RevisionConfig']
export type Channel=components['schemas']['ChannelConfig']
export type Binding=components['schemas']['ChannelSource']
export function newGroup():Channel{return{channel_id:newId(),name:'监测任务',task_mode:'template',sources:[],requirement_text:'',target:'',rule:'',duration_seconds:null,capability_ref:null}}
export function bindings(c:Channel):Binding[]{return c.sources?.length?c.sources:c.source_id?[{source_id:c.source_id,regions:c.regions??[],start_media_ms:c.start_media_ms,end_media_ms:c.end_media_ms}]:[]}
export function selectSources(c:Channel,ids:string[]){const old=new Map(bindings(c).map(b=>[b.source_id,b]));c.sources=[...new Set(ids)].map(source_id=>old.get(source_id)??{source_id,regions:[],start_media_ms:null,end_media_ms:null});c.source_id=null;c.regions=[];c.start_media_ms=null;c.end_media_ms=null}
export function taskInputs(config:Config){return(config.channels??[]).flatMap((channel,index)=>bindings(channel).map((binding,sourceIndex)=>({key:`${index}:${sourceIndex}`,channel,binding})))}
export function isSingleInput(config:Config){return(config.channels?.length??0)===1&&taskInputs(config).length<=1}
export function cleanTaskName(name:string){return name.replace(/(?:\s*[（(]副本[）)])+\s*$/u,'').trim()}
export function copyForNewTask(config:Config,key?:string|null):Config{
  const choices=taskInputs(config),selected=key?choices.find(c=>c.key===key):choices.length===1?choices[0]:undefined
  if((choices.length>1&&!selected)||(key&&!selected))throw Error('请选择本次要检测的一路视频。')
  if(!selected&&(config.channels?.length??0)>1)throw Error('请在智能体管理中选择需要复制的通道。')
  const copy=JSON.parse(JSON.stringify(config)) as Config
  const channel=JSON.parse(JSON.stringify(selected?.channel??config.channels?.[0]??newGroup())) as Channel
  channel.channel_id=newId();channel.execution_plan=null
  selectSources(channel,selected?[selected.binding.source_id]:[])
  copy.channels=[channel]
  return copy
}
export function draftIssue(name:string,config:Config,pending:boolean):string{
  if(!name.trim())return '请填写任务名称。'
  if(pending)return '区域尚在绘制，请先闭合并保存区域，或撤销全部点。'
  if(!isSingleInput(config))return '每个任务仅检测一路视频，请选择一个监控源或上传的视频。'
  for(const c of config.channels??[]){if(!c.name.trim())return '请填写通道名称。';if(bindings(c).length>16)return '每个通道最多选择16路视频。';for(const b of bindings(c)){if((b.start_media_ms==null)!==(b.end_media_ms==null)||(b.start_media_ms!=null&&b.end_media_ms!=null&&(b.start_media_ms<0||b.end_media_ms<=b.start_media_ms)))return '请填写有效的录像起止区间。';for(const r of b.regions??[]){const e=regionError(r.points as Point[]);if(e)return e}}}
  return ''
}
export function retryKey(scope:string,payload:unknown):string{const storageKey=`vision.create.${scope}`,signature=JSON.stringify(payload);try{const old=JSON.parse(sessionStorage.getItem(storageKey)??'null') as {signature:string;key:string}|null;if(old?.signature===signature)return old.key}catch{/* malformed storage */}const key=newId();sessionStorage.setItem(storageKey,JSON.stringify({signature,key}));return key}

export function planningSignature(c:Channel):string{const {execution_plan:_,...input}=c;return JSON.stringify(input)}
export function taskMode(c:Channel):'template'|'natural_language'{return c.task_mode??'natural_language'}
