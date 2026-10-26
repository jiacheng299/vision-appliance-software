import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
const m=vi.hoisted(()=>({list:vi.fn(),references:vi.fn(),deployments:vi.fn(),upload:vi.fn(),create:vi.fn(),verify:vi.fn()}))
vi.mock('vue-router',()=>({useRoute:()=>({params:{},query:{}}),useRouter:()=>({})}))
vi.mock('../src/modules/model-management/api',()=>({modelApi:m,memberError:()=> '校验服务暂不可用'}))
vi.mock('naive-ui',async()=>{
 const {defineComponent}=await import('vue')
 const slot=defineComponent({template:'<div><slot/><slot name="footer"/></div>'})
 return {NButton:defineComponent({props:['disabled','loading','type'],template:'<button :disabled="disabled||loading"><slot/></button>'}),NInput:defineComponent({props:['value','inputProps','type'],emits:['update:value'],template:'<input v-bind="inputProps" :value="value" @input="$emit(\'update:value\',$event.target.value)"/>'}),NCheckbox:slot,NSelect:slot,NTabs:slot,NTabPane:slot,NDrawer:defineComponent({props:['show'],template:'<div v-if="show"><slot/></div>'}),NDrawerContent:slot}
})
import ModelsPage from '../src/modules/model-management/ModelsPage.vue'
const old={id:'m',name:'原模型',version:'1',runtime_type:'unknown',file_id:'old-file',template_id:'t',template:{name:'模板',version:'1',targets:['person'],rules:['dwell'],requires_region:['dwell'],requires_duration:['dwell'],defaults:{},limitations:[]},checksum:'hash',size_bytes:10,validation:'pending',validation_message:'等待校验',status:'available',row_version:1,data_origin:'real',created_at:'2026-10-26T00:00:00Z',updated_at:'2026-10-26T00:00:00Z'}
let wrapper:ReturnType<typeof mount>|undefined
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();m.list.mockResolvedValue({items:[old],next_cursor:null});m.references.mockResolvedValue([]);m.deployments.mockResolvedValue({items:[],selections:[]});m.upload.mockResolvedValue({id:'replacement-file'});m.create.mockImplementation(async body=>({...old,...body}));m.verify.mockImplementation(async body=>body)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
async function replace(){wrapper=mount(ModelsPage,{global:{stubs:{RouterLink:true}}});await flushPromises();const click=async(text:string)=>{await wrapper!.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises()};await click('详情');await click('创建新版本');await wrapper.get('input[aria-label="新模型版本"]').setValue('2');await wrapper.get('input[aria-label="新模板版本"]').setValue('2');const input=wrapper.get('input[type="file"]');Object.defineProperty(input.element,'files',{value:[new File(['replacement'],'new.weights')],configurable:true});await input.trigger('change');await wrapper.get('#model-form').trigger('submit');await flushPromises()}
it('uploads replacement weights instead of silently reusing the original file',async()=>{await replace();expect(m.upload).toHaveBeenCalledOnce();expect(m.create).toHaveBeenCalledWith(expect.objectContaining({version:'2',file_id:'replacement-file'}),expect.any(String),'m')})
it('keeps an imported model durable and explains a verifier failure',async()=>{m.verify.mockRejectedValue(new Error('unavailable'));await replace();expect(m.create).toHaveBeenCalledOnce();expect(wrapper!.text()).toContain('管理项已保存，校验未完成')})
