import { onMounted, onUnmounted, ref } from 'vue'
import { humanError } from '../api/client'
export function useResource<T>(fetcher:()=>Promise<T>, options:{coalesce?:boolean}={}) {
  const data=ref<T|null>(null), loading=ref(false), error=ref('')
  let active=true, generation=0, inFlight:Promise<void>|null=null
  function refresh():Promise<void> {
    if(!active)return Promise.resolve()
    if(options.coalesce&&inFlight)return inFlight
    const version=++generation
    loading.value=true;error.value=''
    const request=(async()=>{
      try {const result=await fetcher();if(active&&version===generation)data.value=result} catch(e) {if(active&&version===generation)error.value=humanError(e)} finally {if(active&&version===generation)loading.value=false}
    })()
    inFlight=request
    void request.then(()=>{if(inFlight===request)inFlight=null})
    return request
  }
  onMounted(refresh)
  onUnmounted(()=>{active=false})
  return {data,loading,error,refresh}
}
export function formatDate(value:string|null|undefined):string {return value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '尚无记录'}
export function formatBytes(value:number|null|undefined):string {
  if(value==null)return '未知'
  if(value===0)return '0 B'
  const i=Math.min(Math.floor(Math.log(value)/Math.log(1024)),4)
  return `${(value/1024**i).toFixed(i?1:0)} ${['B','KB','MB','GB','TB'][i]}`
}
export function percent(value:number|null|undefined):string {return value==null?'未知':`${value.toFixed(1)}%`}
export function duration(value:number|null):string {if(value==null)return '未知';const s=Math.floor(value/1000);return `${Math.floor(s/60)} 分 ${s%60} 秒`}
