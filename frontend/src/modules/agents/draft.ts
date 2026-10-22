import type { Channel, RevisionConfig } from './api'
import { regionError, type Point } from './regionGeometry'
export function emptyConfig(): RevisionConfig { return { schema_version: '1.0', channels: [] } }
export function newChannel(): Channel {
  return { channel_id: crypto.randomUUID(), name: '监测通道', source_id: null, requirement_text: '', target: '', rule: '', duration_seconds: null, start_media_ms: null, end_media_ms: null, regions: [], capability_ref: null }
}
export function copyConfig(config: RevisionConfig): RevisionConfig {
  return JSON.parse(JSON.stringify(config)) as RevisionConfig
}
export function draftError(config: RevisionConfig): string {
  for (const [index, channel] of (config.channels ?? []).entries()) {
    if (!channel.name.trim()) return `请填写第 ${index + 1} 路的名称。`
    for(const region of channel.regions??[]){const error=regionError(region.points as Point[]);if(error)return `第 ${index+1} 路：${error}`}
    if (channel.duration_seconds != null && (!Number.isInteger(channel.duration_seconds) || channel.duration_seconds <= 0 || channel.duration_seconds > 86400)) return '持续时长应为 1 到 86400 的整数秒。'
    const start = channel.start_media_ms, end = channel.end_media_ms
    if ((start == null) !== (end == null) || (start != null && end != null && (start < 0 || start >= end))) return '录像区间需要同时填写开始和结束，结束应晚于开始。'
  }
  return ''
}
