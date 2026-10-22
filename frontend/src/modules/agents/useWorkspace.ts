import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { agentApi, type Operation, type Workspace } from './api'
import { agentError } from './state'
const terminal = new Set(['succeeded','partial_failed','failed','canceled'])
export function useWorkspace(id: Ref<string>, onSettled: () => void) {
  const data = ref<Workspace|null>(null), operations = ref<Operation[]>([]), error = ref(''), operationError = ref(''), loading = ref(false)
  let generation=0, timer:ReturnType<typeof setTimeout>|undefined, stopped=false
  const storageKey=()=>`vision.agent.operations.${id.value}`
  function saveIds() { sessionStorage.setItem(storageKey(),JSON.stringify(operations.value.filter(o=>!terminal.has(o.state)).map(o=>o.id))) }
  async function refresh() {
    const current=++generation, agentId=id.value; loading.value=true
    try { const result=await agentApi.workspace(agentId); if(current===generation){data.value=result.runtime_available?result:{...result,runs:data.value?.runs??[],observed_at:data.value?.observed_at??result.observed_at};error.value=''} }
    catch(e){if(current===generation)error.value=agentError(e)}
    finally{if(current===generation)loading.value=false}
  }
  function track(operation:Operation) { operations.value=[operation,...operations.value.filter(o=>o.id!==operation.id)].slice(0,30);saveIds();void refresh() }
  async function poll() {
    const agentId=id.value
    const pending=operations.value.filter(o=>!terminal.has(o.state))
    let settled=false
    for(const old of pending){
      try{
        const result=await agentApi.operation(agentId,old.id)
        if(stopped||id.value!==agentId)return
        operations.value=operations.value.map(o=>o.id===result.id?result:o);operationError.value=''
        if(terminal.has(result.state))settled=true
      }catch(e){if(id.value===agentId)operationError.value=agentError(e)}
    }
    if(stopped||id.value!==agentId)return
    saveIds();await refresh()
    if(settled)onSettled()
    if(!stopped)timer=setTimeout(()=>void poll(),2000)
  }
  watch(id,async()=>{
    generation++;clearTimeout(timer);data.value=null;operations.value=[];error.value='';operationError.value=''
    const agentId=id.value
    let ids:string[]=[]
    try{ids=JSON.parse(sessionStorage.getItem(storageKey())??'[]') as string[]}catch{/* ignore invalid local UI state */}
    for(const operationId of ids.slice(0,16)){
      try{const operation=await agentApi.operation(agentId,operationId);if(id.value===agentId)operations.value.push(operation)}catch(e){operationError.value=agentError(e)}
    }
    if(id.value===agentId&&!stopped)void poll()
  },{immediate:true})
  onScopeDispose(()=>{stopped=true;generation++;clearTimeout(timer)})
  return {data,operations,error,operationError,loading,refresh,track}
}
