import { client } from '../../shared/api/client'
import type { components, paths } from '../../shared/api/generated'
import { agentJson } from './json'
import { api } from '../../shared/api'
import type { Source } from '../../shared/api/types'
const jsonOptions = { headers: { 'Content-Type': 'application/json' }, transformRequest: [agentJson] }
export async function listAgentSources(): Promise<Source[]> {
  const sources: Source[] = [], visited = new Set<string>()
  let cursor: string | undefined
  do {
    const page = await api.sources('', '', '', cursor)
    sources.push(...page.items)
    cursor = page.next_cursor ?? undefined
    if (cursor && visited.has(cursor)) throw new Error('Source pagination did not advance')
    if (cursor) visited.add(cursor)
  } while (cursor)
  return sources
}
export type Agent = components['schemas']['AgentDTO']
export type AgentDetail = components['schemas']['AgentDetail']
export type AgentPage = components['schemas']['AgentPage']
export type Revision = components['schemas']['RevisionDTO']
export type RevisionConfig = components['schemas']['RevisionConfig']
export type Channel = components['schemas']['ChannelConfig']
export type ChannelSource = components['schemas']['ChannelSource']
export type Region = components['schemas']['Region']
export type AgentCreate = components['schemas']['AgentCreate']
export type Validation = components['schemas']['ValidationDTO']
export type CapabilityCatalog = components['schemas']['CapabilityCatalog']
export type CapabilityItem = components['schemas']['CapabilityItem']
export type Run = components['schemas']['RunDTO']
export type Operation = components['schemas']['OperationDTO']
export type Workspace = components['schemas']['WorkspaceDTO']
export type MonitorEvent = components['schemas']['AgentEventDTO']
export type MonitorEventPage = components['schemas']['AgentEventPage']
export type EventDetail = components['schemas']['EventDetail']
export type Playback = components['schemas']['PlaybackDTO']
export type Missed = components['schemas']['MissedDTO']
export type ExportJob = components['schemas']['ExportDTO']
export type Comparison = components['schemas']['ComparisonDTO']
export type Scenario = components['schemas']['DemoScenario']['scenario']
export type EventFilters = Omit<NonNullable<paths['/api/v1/agents/{agent_id}/events']['get']['parameters']['query']>, 'limit' | 'cursor'>
const keyOptions = (key: string) => ({ ...jsonOptions, headers: { ...jsonOptions.headers, 'Idempotency-Key': key } })
const base = (id: string) => `/agents/${encodeURIComponent(id)}`
export interface ListFilters { status?: string; scene?: string; archived?: boolean; sort?:string }
export const agentApi = {
  list: (q = '', source_id = '', cursor?: string, filters: ListFilters = {}) => client.get<AgentPage>('/agents', { params: { q, source_id: source_id || undefined, cursor, limit: 24, ...filters } }).then(r => r.data),
  detail: (id: string) => client.get<AgentDetail>(`/agents/${encodeURIComponent(id)}`).then(r => r.data),
  create: (body: AgentCreate, key: string) => client.post<AgentDetail>('/agents', body, { ...jsonOptions, headers: { ...jsonOptions.headers, 'Idempotency-Key': key } }).then(r => r.data),
  rename: (id: string, body: { name: string; description: string; row_version: number }) => client.patch<AgentDetail>(`/agents/${encodeURIComponent(id)}`, body, jsonOptions).then(r => r.data),
  clone: (id: string, base_revision_id: string, row_version: number, key: string) => client.post<Revision>(`/agents/${encodeURIComponent(id)}/revisions`, { base_revision_id, row_version }, { ...jsonOptions, headers: { ...jsonOptions.headers, 'Idempotency-Key': key } }).then(r => r.data),
  save: (revision: Revision, config: RevisionConfig) => client.patch<Revision>(`/revisions/${encodeURIComponent(revision.id)}`, { config, row_version: revision.row_version }, jsonOptions).then(r => r.data),
  catalog: () => client.get<CapabilityCatalog>('/agent-services/capabilities').then(r => r.data),
  validate: (revision: Revision) => client.post<Validation>(`/revisions/${encodeURIComponent(revision.id)}/validations`, { row_version: revision.row_version }, jsonOptions).then(r => r.data),
  validation: (id: string) => client.get<Validation>(`/validations/${encodeURIComponent(id)}`).then(r => r.data),
  confirm: (revision: Revision, validation: Validation, key: string) => client.post<Revision>(`/revisions/${encodeURIComponent(revision.id)}/confirmations`, { row_version: revision.row_version, validation_id: validation.id, config_hash: validation.config_hash, limitations_acknowledged: true }, keyOptions(key)).then(r => r.data),
  workspace: (id: string) => client.get<Workspace>(`${base(id)}/workspace`).then(r => r.data),
  submit: (id: string, kind: 'start'|'apply', body: components['schemas']['StartInput'], key: string) => client.post<Operation>(`${base(id)}/${kind === 'start' ? 'run-groups' : 'revision-applications'}`, body, keyOptions(key)).then(r => r.data),
  stop: (id: string, runId: string, key: string) => client.post<Operation>(`${base(id)}/runs/${encodeURIComponent(runId)}/stop`, {}, keyOptions(key)).then(r => r.data),
  stopChannel: (id:string, channelId:string, key:string) => client.post<Operation>(`${base(id)}/channels/${encodeURIComponent(channelId)}/stop`,{},keyOptions(key)).then(r=>r.data),
  operation: (id: string, operationId: string) => client.get<Operation>(`${base(id)}/operations/${encodeURIComponent(operationId)}`).then(r => r.data),
  archive: (agent: Agent, restore: boolean) => client.post<AgentDetail>(`${base(agent.id)}/${restore ? 'restore' : 'archive'}`, {row_version:agent.row_version}, jsonOptions).then(r => r.data),
  remove: (agent: Agent) => client.delete(`${base(agent.id)}`,{params:{row_version:agent.row_version}}).then(()=>undefined),
  events: (id: string, filters: EventFilters = {}, cursor?: string) => client.get<MonitorEventPage>(`${base(id)}/events`, {params:{...filters,cursor,limit:30}}).then(r => r.data),
  event: (id: string, eventId: string) => client.get<EventDetail>(`${base(id)}/events/${encodeURIComponent(eventId)}`).then(r => r.data),
  feedback: (id: string, event: EventDetail, label: 'correct'|'false_positive', reason: string, key: string) => client.post<EventDetail>(`${base(id)}/events/${encodeURIComponent(event.id)}/feedback`, {label,reason,row_version:event.row_version}, keyOptions(key)).then(r => r.data),
  missed: (id: string) => client.get<components['schemas']['MissedPage']>(`${base(id)}/missed-annotations`).then(r => r.data),
  addMissed: (id: string, body: components['schemas']['MissedInput'], key: string) => client.post<Missed>(`${base(id)}/missed-annotations`, body, keyOptions(key)).then(r => r.data),
  playback: (id: string, runId: string) => client.post<Playback>(`${base(id)}/runs/${encodeURIComponent(runId)}/playback`, {}, jsonOptions).then(r => r.data),
  evidence: (id: string, eventId: string, evidenceId: string) => client.post<Playback>(`${base(id)}/events/${encodeURIComponent(eventId)}/evidence/${encodeURIComponent(evidenceId)}/access-sessions`, {}, jsonOptions).then(r => r.data),
  releasePlayback: (id: string, sessionId: string) => client.delete(`${base(id)}/playback-sessions/${encodeURIComponent(sessionId)}`),
  retest: (agent: Agent, runId: string, key: string) => client.post<Revision>(`${base(agent.id)}/retests`, {baseline_run_id:runId,row_version:agent.row_version}, keyOptions(key)).then(r => r.data),
  comparison: (id: string, baseline: string, candidate: string) => client.get<Comparison>(`${base(id)}/comparisons`, {params:{baseline_run_id:baseline,candidate_run_id:candidate}}).then(r => r.data),
  export: (id: string, body: components['schemas']['ExportInput'], key: string) => client.post<ExportJob>(`${base(id)}/exports`, body, keyOptions(key)).then(r => r.data),
  exportDestinations: () => client.get<components['schemas']['ExportDestinations']>('/agent-services/export-destinations').then(r=>r.data),
  exportStatus: (id: string, jobId: string) => client.get<ExportJob>(`${base(id)}/exports/${encodeURIComponent(jobId)}`).then(r => r.data),
  exportAction: (id: string, jobId: string, action: 'cancel'|'retry', key: string) => client.post<ExportJob>(`${base(id)}/exports/${encodeURIComponent(jobId)}/${action}`, {}, keyOptions(key)).then(r => r.data),
  seed: () => client.post<AgentDetail>('/agent-demo/seed', {}, jsonOptions).then(r => r.data),
  scenario: (scenario: Scenario, runId?: string) => client.post('/agent-demo/scenario', {scenario,run_id:runId ?? null}, jsonOptions).then(r => r.data),
}
