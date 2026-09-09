// 性能测试域(计划 14 / ADR-0010):性能记录 CRUD/统一 series/对比/趋势 + 设备历史导入
// 端点直译 backend/app/routers/perf.py,写法对齐 appAutomation.ts(http.get/post/del)
import { http } from './client'
import type { AppPerfSeries, DevicePerfHistoryItem, PerfRecord, TrendGroup } from '../types'

export const listPerfRecords = (projectId: number, params: { source?: string; script_id?: number; device_serial?: string } = {}) => {
  const q = new URLSearchParams()
  if (params.source) q.set('source', params.source)
  if (params.script_id != null) q.set('script_id', String(params.script_id))
  if (params.device_serial) q.set('device_serial', params.device_serial) // URLSearchParams 序列化时统一转义
  const qs = q.toString()
  return http.get<PerfRecord[]>(`/projects/${projectId}/perf-records${qs ? `?${qs}` : ''}`)
}

export const getPerfRecord = (id: number) => http.get<PerfRecord>(`/perf-records/${id}`)

export const deletePerfRecord = (id: number) => http.del(`/perf-records/${id}`)

export const getPerfRecordSeries = (id: number) =>
  http.get<{ record: PerfRecord; series: AppPerfSeries[] }>(`/perf-records/${id}/series`)

export const comparePerfRecords = (projectId: number, recordIds: number[]) =>
  http.post<{ records: PerfRecord[]; series: Record<string, AppPerfSeries[]> }>(
    `/projects/${projectId}/perf-records/compare`, { record_ids: recordIds })

export const getPerfTrend = (projectId: number, params: { script_id?: number; device_serial?: string } = {}) => {
  const q = new URLSearchParams()
  if (params.script_id != null) q.set('script_id', String(params.script_id))
  if (params.device_serial) q.set('device_serial', params.device_serial) // URLSearchParams 序列化时统一转义
  const qs = q.toString()
  return http.get<{ groups: TrendGroup[] }>(`/projects/${projectId}/perf-trend${qs ? `?${qs}` : ''}`)
}

export const listDevicePerfHistory = (serial: string, limit = 50) =>
  http.get<{ items: DevicePerfHistoryItem[] }>(
    `/app-devices/${encodeURIComponent(serial)}/perf-history?limit=${limit}`)

export const importPerfHistory = (
  projectId: number,
  body: { serial: string; history_id: string; name?: string },
) => http.post<PerfRecord>(`/projects/${projectId}/perf-records/import`, {
  serial: body.serial,
  history_id: body.history_id,
  ...(body.name ? { name: body.name } : {}),
})
