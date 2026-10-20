import { client } from '../../shared/api/client'
import type { components } from '../../shared/api/generated'
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
export type Region = components['schemas']['Region']
export type AgentCreate = components['schemas']['AgentCreate']
export const agentApi = {
  list: (q = '', source_id = '', cursor?: string) => client.get<AgentPage>('/agents', { params: { q, source_id: source_id || undefined, cursor, limit: 24 } }).then(r => r.data),
  detail: (id: string) => client.get<AgentDetail>(`/agents/${encodeURIComponent(id)}`).then(r => r.data),
  create: (body: AgentCreate, key: string) => client.post<AgentDetail>('/agents', body, { ...jsonOptions, headers: { ...jsonOptions.headers, 'Idempotency-Key': key } }).then(r => r.data),
  rename: (id: string, body: { name: string; description: string; row_version: number }) => client.patch<AgentDetail>(`/agents/${encodeURIComponent(id)}`, body, jsonOptions).then(r => r.data),
  clone: (id: string, base_revision_id: string, row_version: number, key: string) => client.post<Revision>(`/agents/${encodeURIComponent(id)}/revisions`, { base_revision_id, row_version }, { ...jsonOptions, headers: { ...jsonOptions.headers, 'Idempotency-Key': key } }).then(r => r.data),
  save: (revision: Revision, config: RevisionConfig) => client.patch<Revision>(`/revisions/${encodeURIComponent(revision.id)}`, { config, row_version: revision.row_version }, jsonOptions).then(r => r.data),
}
