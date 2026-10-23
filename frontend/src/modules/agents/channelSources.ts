import type { Channel, ChannelSource, RevisionConfig, Run } from './api'
export const MAX_CHANNEL_SOURCES=16
export function channelSources(channel:Channel):ChannelSource[]{
  return channel.sources?.length?channel.sources:channel.source_id?[channel as ChannelSource]:[]
}
export const sourceCount=(config:RevisionConfig)=>(config.channels??[]).reduce((n,c)=>n+channelSources(c).length,0)
export function setChannelSources(channel:Channel,ids:string[]){
  const old=new Map(channelSources(channel).map(b=>[b.source_id,b]))
  channel.sources=[...new Set(ids)].map(source_id=>old.has(source_id)?{...old.get(source_id)!}:{source_id,regions:[],start_media_ms:null,end_media_ms:null})
  channel.source_id=null;channel.regions=[];channel.start_media_ms=null;channel.end_media_ms=null
}
export const runSourceKey=(value:{channel_id:string;source_id:string})=>JSON.stringify([value.channel_id,value.source_id])
export interface WallGroup {id:string;name:string;tiles:{key:string;binding:ChannelSource;run?:Run}[]}
export function wallGroups(config:RevisionConfig,runs:Run[]):WallGroup[]{
  const groups:WallGroup[]=(config.channels??[]).map(c=>({id:c.channel_id!,name:c.name,tiles:channelSources(c).map(binding=>({key:runSourceKey({channel_id:c.channel_id!,source_id:binding.source_id}),binding}))}))
  for(const run of runs){
    let group=groups.find(g=>g.id===run.channel_id)
    if(!group){group={id:run.channel_id,name:run.channel_name,tiles:[]};groups.push(group)}
    const key=runSourceKey(run),tile=group.tiles.find(t=>t.key===key)
    if(tile)tile.run=run
    else group.tiles.push({key,run,binding:{source_id:run.source_id,regions:[]}})
  }
  return groups
}
