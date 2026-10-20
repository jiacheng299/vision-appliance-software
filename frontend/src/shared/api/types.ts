export interface Source { id: string; name: string; kind: 'file' | 'camera'; status: string; created_at: string; updated_at: string; row_version: number; observed_at: string | null; address: string | null; width: number | null; height: number | null; fps: number | null; duration_ms: number | null; size_bytes: number | null; sha256: string | null; preview_url: string | null; thumbnail_url: string | null; error_code: string | null; error_message: string | null }
export interface Upload { id: string; state: string; received_bytes: number; size_bytes: number; source_id: string | null; error_code: string | null; error_message: string | null }
export interface CameraInput { name: string; kind: 'camera'; address: string; username?: string; password?: string }
export interface SourceTest { id: string; state: string; source_id: string; error_code?: string; message?: string }
export interface MediaSession { session_id: string; protocol: 'file' | 'hls' | 'webrtc'; playback_url: string; expires_at: string }
export interface Event { id: string; event_type: string; source_id: string; source_name: string; run_id: string; revision_id: string; occurred_at: string | null; start_media_ms: number | null; reason: string; evidence_status: string; review_status: string }
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface Dashboard { counts: { sources_total: number; sources_online: number; active_runs: number; today_events: number }; sources: Source[]; recent_events: Event[]; task_summary: { running: number; completed: number; waiting: number } }
export interface Service { key: string; name: string; status: 'ready' | 'unavailable' | 'degraded'; message: string; observed_at: string }
export interface RuntimeSample { observed_at: string; cpu_percent: number; memory_percent: number; gpu_percent: number | null }
export interface Runtime extends RuntimeSample { disk: { used_bytes: number; total_bytes: number; free_bytes: number }; sources: { total: number; online: number }; runs: { running: number; completed: number; failed: number }; services: Service[]; models: unknown[]; workers: unknown[]; history: RuntimeSample[] }
export interface Log { id: string; occurred_at: string; level: string; module: string; message: string }
export type SettingsSection = 'general' | 'storage' | 'resources' | 'security' | 'diagnostics'
export interface Settings { section: SettingsSection; values: Record<string, unknown>; row_version: number }
export interface RealtimeEnvelope { schema_version: string; event_id: string; sequence: number; type: string; occurred_at: string; aggregate_id: string; payload: unknown }
