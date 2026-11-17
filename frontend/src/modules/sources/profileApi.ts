import { client } from '../../shared/api/client'
import type { components } from '../../shared/api/generated'

export type SemanticProfile = components['schemas']['ProfileView']
export type ProfileAttribute = components['schemas']['AttributeView']
export type AttributeSource = 'frame' | 'language' | 'probe' | 'device'

export const INTRINSIC_KEYS = ['resolution', 'lens', 'mount_position', 'field_of_view',
  'stream', 'device_id'] as const

export interface AttributeDraft {
  value: string
  source_kind: AttributeSource
  confidence: number
  tau_seconds?: number | null
  expires_in_seconds?: number | null
}

const base = (sourceId: string) => `/sources/${encodeURIComponent(sourceId)}/semantic-profile`
const json = { headers: { 'Content-Type': 'application/json' } }

export const profileApi = {
  read: (sourceId: string, at?: number) => client.get<SemanticProfile>(base(sourceId),
    { params: at === undefined ? {} : { at } }).then(response => response.data),
  updateIntrinsic: (sourceId: string, values: Record<string, string>) =>
    client.put<SemanticProfile>(base(sourceId), { values }, json).then(response => response.data),
  upsertAttribute: (sourceId: string, key: string, draft: AttributeDraft) => {
    const now = Date.now() / 1000
    const body: Record<string, unknown> = {
      value: { label: draft.value }, source_kind: draft.source_kind,
      observed_at: now, confidence: draft.confidence,
    }
    if (draft.tau_seconds) body.tau_seconds = draft.tau_seconds
    if (draft.expires_in_seconds) body.hard_expiry_at = now + draft.expires_in_seconds
    return client.put<SemanticProfile>(`${base(sourceId)}/attributes/${encodeURIComponent(key)}`,
      body, json).then(response => response.data)
  },
  deleteAttribute: (sourceId: string, key: string) =>
    client.delete<SemanticProfile>(`${base(sourceId)}/attributes/${encodeURIComponent(key)}`)
      .then(response => response.data),
}
