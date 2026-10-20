import { client } from './client'
import type { CameraInput, Dashboard, Event, Log, MediaSession, Page, Runtime, Settings, SettingsSection, Source, SourceTest, Upload } from './types'
export const api = {
  dashboard: () => client.get<Dashboard>('/dashboard').then(r=>r.data),
  runtime: () => client.get<Runtime>('/runtime/overview').then(r=>r.data),
  logs: (q='',level='') => client.get<Page<Log>>('/logs',{params:{q,level,limit:100}}).then(r=>r.data),
  events: () => client.get<Page<Event>>('/events').then(r=>r.data),
  sources: (q='',kind='',status='') => client.get<Page<Source>>('/sources',{params:{q,kind,status,limit:100}}).then(r=>r.data),
  source: (id:string) => client.get<Source>(`/sources/${encodeURIComponent(id)}`).then(r=>r.data),
  createCamera: (input:CameraInput) => client.post<Source>('/sources',input).then(r=>r.data),
  updateSource: (id:string,input:Partial<CameraInput>&{row_version:number}) => client.patch<Source>(`/sources/${encodeURIComponent(id)}`,input).then(r=>r.data),
  archiveSource: (id:string) => client.post(`/sources/${encodeURIComponent(id)}/archive`),
  testSource: (id:string) => client.post<SourceTest>(`/sources/${encodeURIComponent(id)}/tests`).then(r=>r.data),
  sourceTest: (id:string) => client.get<SourceTest>(`/source-tests/${encodeURIComponent(id)}`).then(r=>r.data),
  mediaSession: (id:string) => client.post<MediaSession>(`/sources/${encodeURIComponent(id)}/preview-sessions`).then(r=>r.data),
  getSettings: (section:SettingsSection) => client.get<Settings>(`/settings/${section}`).then(r=>r.data),
  saveSettings: (section:SettingsSection,values:Record<string,unknown>,row_version:number) => client.patch<Settings>(`/settings/${section}`,{values,row_version}).then(r=>r.data),
}
export const uploadTransport = {
  create: (filename:string,size_bytes:number) => client.post<Upload>('/uploads',{filename,size_bytes}).then(r=>r.data),
  chunk: (id:string,n:number,data:Blob) => client.put<Upload>(`/uploads/${id}/chunks/${n}`,data,{headers:{'Content-Type':'application/octet-stream'},timeout:120000}).then(r=>r.data),
  complete: (id:string) => client.post<Upload>(`/uploads/${id}/complete`,{}).then(r=>r.data),
  get: (id:string) => client.get<Upload>(`/uploads/${id}`).then(r=>r.data),
  cancel: (id:string) => client.delete(`/uploads/${id}`),
}
