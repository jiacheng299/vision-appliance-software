import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RevisionEditor from '../src/modules/agents/RevisionEditor.vue'
import { modelApi } from '../src/modules/model-management/api'
import { agentApi, type Revision } from '../src/modules/agents/api'
import { copyConfig, newChannel } from '../src/modules/agents/draft'
import { channelSources } from '../src/modules/agents/channelSources'
import { agentJson } from '../src/modules/agents/json'
import { templatesApi } from '../src/modules/agents/templatesApi'
import ParameterFields from '../src/modules/agents/ParameterFields.vue'
import { task,template,pool,catalog } from './fixtures/agentTemplates'

vi.mock('naive-ui', async () => {
  const { defineComponent } = await import('vue')
  const Box = defineComponent({ template: '<div><slot/><slot name="footer"/></div>' })
  return {
    NDrawer: defineComponent({name:'TestDrawer',props:['maskClosable','closeOnEsc'],emits:['update:show'],template:'<div><slot/></div>'}), NDrawerContent: Box,
    NButton: defineComponent({ props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot/></button>' }),
    NInput: defineComponent({ props: ['value', 'inputProps'], emits: ['update:value'], template: '<input v-bind="inputProps" :value="value" @input="$emit(\'update:value\', $event.target.value)"/>' }),
    NSelect: defineComponent({ props: ['value'], emits: ['update:value'], template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><option value="source-new">新视频源</option></select>' }),
    NInputNumber: Box, NCheckbox: Box,
  }
})
function revision(): Revision {
  return { id: 'rev-1', agent_id: 'agent-1', revision_no: 1, base_revision_id: null, state: 'draft', row_version: 1, created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', config: { schema_version: '1.0', channels: [newChannel()] } }
}
function editor(value = revision()) {
  return mount(RevisionEditor, { props: { revision: value, sources: [] }, global: { stubs: { RegionEditor: true } } })
}
function button(wrapper: ReturnType<typeof editor>, label: string) { return wrapper.findAll('button').find(b => b.text() === label)! }
afterEach(() => vi.restoreAllMocks())
beforeEach(() => { vi.spyOn(modelApi,'templates').mockResolvedValue({items:[],fingerprint:'test',data_origin:'real'}); vi.spyOn(agentApi,'catalog').mockResolvedValue({items:[],fingerprint:'test',data_origin:'real'}) })

describe('agent revision editing', () => {
  it('edits task parameter values while preserving its original template version and model',async()=>{
    const original=task().latest_revision
    vi.spyOn(templatesApi,'parameters').mockResolvedValue({version:'1',items:pool,editable_by_user:false})
    const newer=template(2);newer.revisions.push(template().latest_revision)
    vi.spyOn(templatesApi,'detail').mockResolvedValue(newer)
    vi.mocked(agentApi.catalog).mockResolvedValue(catalog)
    const save=vi.spyOn(agentApi,'save').mockResolvedValue(original)
    const wrapper=editor(original);await flushPromises()
    expect(wrapper.text()).toContain('v1')
    expect(wrapper.text()).not.toContain('添加通道')
    expect(wrapper.find('[aria-label="通道任务模式"]').exists()).toBe(false)
    wrapper.getComponent(ParameterFields).vm.$emit('update:settings',[{key:'confidence_threshold',value:.9,required:true}]);await flushPromises()
    await button(wrapper,'保存草稿').trigger('click');await flushPromises()
    const config=save.mock.calls[0]![1]
    expect(config.agent_template_ref).toEqual(original.config.agent_template_ref)
    expect(config.channels![0]!.capability_ref).toEqual(original.config.channels![0]!.capability_ref)
    expect(config.channels![0]!.parameters![0]!.value).toBe(.9)
    expect(original.config.channels![0]!.parameters![0]!.value).toBe(.8)
    wrapper.unmount()
  })
  it('closes through the mask but preserves dirty input when discard is canceled',async()=>{
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    const wrapper=editor(),drawer=wrapper.getComponent({name:'TestDrawer'})
    expect(drawer.props('maskClosable')).toBe(true)
    await wrapper.get('input').setValue('尚未保存的配置')
    drawer.vm.$emit('update:show',false);await flushPromises()
    expect(confirm).toHaveBeenCalledOnce();expect(wrapper.emitted('close')).toBeUndefined()
    confirm.mockReturnValue(true);drawer.vm.$emit('update:show',false);await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1);wrapper.unmount()
  })
  it('preserves Chinese, emoji and line breaks using transport-safe JSON', () => {
    const body = { name: '北门监测 🔔', description: '第一行\n第二行', quote: '"与\\' }
    const encoded = agentJson(body)
    expect(encoded).toMatch(/^[\x00-\x7f]*$/)
    expect(JSON.parse(encoded)).toEqual(body)
  })
  it('keeps input on a concurrent save conflict and never changes the loaded snapshot', async () => {
    const original = revision(), before = copyConfig(original.config)
    const save = vi.spyOn(agentApi, 'save').mockRejectedValue({ response: { status: 409, data: { error: { code: 'revision_conflict' } } } })
    const wrapper = editor(original)
    await wrapper.get('input').setValue('编辑后的通道')
    await button(wrapper, '保存草稿').trigger('click'); await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    expect(original.config).toEqual(before)
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('编辑后的通道')
    expect(wrapper.text()).toContain('当前输入已保留')
    expect(wrapper.emitted('saved')).toBeUndefined()
    wrapper.unmount()
  })
  it('asks before abandoning edits and respects cancel', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = editor()
    await wrapper.get('input').setValue('尚未保存')
    await button(wrapper, '取消').trigger('click')
    expect(confirm).toHaveBeenCalledOnce()
    expect(wrapper.emitted('close')).toBeUndefined()
    confirm.mockReturnValue(true)
    await button(wrapper, '取消').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
  it('clears source-specific regions and media range when changing source', async () => {
    const original = revision(), channel = original.config.channels![0]!
    channel.source_id = 'source-old'; channel.start_media_ms = 0; channel.end_media_ms = 2000
    channel.regions = [{ id: 'roi', name: '', points: [[0, 0], [1, 0], [0, 1]] }]
    const save = vi.spyOn(agentApi, 'save').mockResolvedValue(original)
    const wrapper = editor(original)
    await wrapper.get('select').setValue('source-new')
    await button(wrapper, '保存草稿').trigger('click'); await flushPromises()
    const submitted = save.mock.calls[0]![1].channels![0]!
    expect(channelSources(submitted)[0]!.source_id).toBe('source-new')
    expect(submitted.regions).toEqual([])
    expect(submitted.start_media_ms).toBeNull()
    expect(submitted.end_media_ms).toBeNull()
    expect(channel.source_id).toBe('source-old')
    wrapper.unmount()
  })
})
