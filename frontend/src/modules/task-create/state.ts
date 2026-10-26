import type { components } from '../../shared/api/generated'
import { regionError, type Point } from '../../shared/media/regionGeometry'
export type Config=components['schemas']['RevisionConfig']
export type Channel=components['schemas']['ChannelConfig']
export type Binding=components['schemas']['ChannelSource']
export function newGroup():Channel{return{channel_id:crypto.randomUUID(),name:'通道',sources:[],requirement_text:'',target:'',rule:'',duration_seconds:null,capability_ref:null}}
export function bindings(c:Channel):Binding[]{return c.sources?.length?c.sources:c.source_id?[{source_id:c.source_id,regions:c.regions??[],start_media_ms:c.start_media_ms,end_media_ms:c.end_media_ms}]:[]}
export function selectSources(c:Channel,ids:string[]){const old=new Map(bindings(c).map(b=>[b.source_id,b]));c.sources=[...new Set(ids)].map(source_id=>old.get(source_id)??{source_id,regions:[],start_media_ms:null,end_media_ms:null});c.source_id=null;c.regions=[];c.start_media_ms=null;c.end_media_ms=null}
export function copyForNewTask(config:Config):Config{const copy=JSON.parse(JSON.stringify(config)) as Config;for(const c of copy.channels??[]){c.channel_id=crypto.randomUUID();selectSources(c,bindings(c).map(b=>b.source_id))}return copy}
export function draftIssue(name:string,config:Config,pending:boolean):string{
  if(!name.trim())return '请填写任务名称。'
  if(pending)return '区域尚在绘制，请先闭合并保存区域，或撤销全部点。'
  if((config.channels??[]).reduce((n,c)=>n+bindings(c).length,0)>64)return '每个任务最多绑定64路视频。'
  for(const c of config.channels??[]){if(!c.name.trim())return '请填写通道名称。';if(bindings(c).length>16)return '每个通道最多选择16路视频。';for(const b of bindings(c)){if((b.start_media_ms==null)!==(b.end_media_ms==null)||(b.start_media_ms!=null&&b.end_media_ms!=null&&(b.start_media_ms<0||b.end_media_ms<=b.start_media_ms)))return '请填写有效的录像起止区间。';for(const r of b.regions??[]){const e=regionError(r.points as Point[]);if(e)return e}}}
  return ''
}
export function retryKey(scope:string,payload:unknown):string{const storageKey=`vision.create.${scope}`,signature=JSON.stringify(payload);try{const old=JSON.parse(sessionStorage.getItem(storageKey)??'null') as {signature:string;key:string}|null;if(old?.signature===signature)return old.key}catch{/* malformed storage */}const key=crypto.randomUUID();sessionStorage.setItem(storageKey,JSON.stringify({signature,key}));return key}
