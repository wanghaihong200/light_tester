// APP自动化(计划 12):SoloPi 原生用例 JSON 域
import { http, withSseToken } from './client'
import type { AppCaseJson, AppPerfSeries, AppRun, AppRunStatus, AppScript, CheckDef, DeviceInfo } from '../types'

const TERMINAL_RUN_STATUS: AppRunStatus[] = ['passed', 'failed', 'cancelled']

export interface DeviceCase {
  file_name: string
  // harness = PC CLI 推送写入 harness-import;export = 手机 App「导出用例」写入 /sdcard/solopi/export
  source: 'harness' | 'export'
}

export interface AppRunCreateBody {
  script_id: number
  device_serials: string[]
  perf_items?: string[]
  pre_checks?: CheckDef[]
  post_checks?: CheckDef[]
  startup_time?: boolean
  allow_high_risk?: boolean
}

export type AppRunEvent =
  | { type: 'status'; status: string }
  | { type: 'snapshot'; status: string; run_state: string | null; error: string | null }
  | { type: 'done'; status: string; state?: string }
  | { type: 'error'; message: string }

export const listAppScripts = (projectId: number) =>
  http.get<AppScript[]>(`/projects/${projectId}/app-scripts`)

export const getAppScript = (id: number) => http.get<AppScript>(`/app-scripts/${id}`)

export const createAppScript = (
  projectId: number,
  body: { name?: string; case: AppCaseJson; allow_high_risk?: boolean },
) => http.post<AppScript>(`/projects/${projectId}/app-scripts`, body)

export const updateAppScript = (
  id: number,
  body: { name?: string; description?: string; case?: AppCaseJson; allow_high_risk?: boolean },
) => http.put<AppScript>(`/app-scripts/${id}`, body)

export const deleteAppScript = (id: number) => http.del(`/app-scripts/${id}`)

// 导出为 Appium pytest 产物并推送到项目的 app 自动化仓(终审 I3,对齐 exportUiScript);
// 400 时后端 detail 为字符串或 {errors:[…]}(不可导出步骤清单),由调用方经 e.body?.detail 渲染
export const exportAppScript = (id: number, body: { branch: string; commit_message?: string }) =>
  http.post<{ ok: boolean; branch: string; commit_short: string; pushed_files: string[]; files: string[] }>(
    `/app-scripts/${id}/export`, body)

export const listDeviceCases = (projectId: number, serial: string) =>
  http.get<DeviceCase[]>(
    `/projects/${projectId}/app-scripts/device-cases?serial=${encodeURIComponent(serial)}`)

export const importDeviceCase = (
  projectId: number,
  body: { serial: string; file_name: string; source?: 'harness' | 'export'; name?: string; allow_high_risk?: boolean },
) => http.post<AppScript>(`/projects/${projectId}/app-scripts/import-device`, body)

export const importUploadCase = (
  projectId: number,
  file: File,
  opts: { name?: string; allow_high_risk?: boolean } = {},
) => {
  const fd = new FormData()
  fd.append('file', file)
  if (opts.name) fd.append('name', opts.name)
  fd.append('allow_high_risk', String(!!opts.allow_high_risk))
  return http.upload<AppScript>(`/projects/${projectId}/app-scripts/import-upload`, fd)
}

export const listAppDevices = () => http.get<DeviceInfo[]>('/app-devices')

export const listPerfItems = (serial: string) =>
  http.get<{ items: string[] }>(`/app-devices/${encodeURIComponent(serial)}/perf-items`)

export const createAppRuns = (projectId: number, body: AppRunCreateBody) =>
  http.post<AppRun[]>(`/projects/${projectId}/app-runs`, body)

export const listAppRuns = (projectId: number, params: { script_id?: number; batch_id?: string } = {}) => {
  const q = new URLSearchParams()
  if (params.script_id != null) q.set('script_id', String(params.script_id))
  if (params.batch_id) q.set('batch_id', params.batch_id)
  const qs = q.toString()
  return http.get<AppRun[]>(`/projects/${projectId}/app-runs${qs ? `?${qs}` : ''}`)
}

export const getAppRun = (id: number) => http.get<AppRun>(`/app-runs/${id}`)

export const forceFinishAppRun = (id: number) => http.post<AppRun>(`/app-runs/${id}/force-finish`, {})

export const getAppRunPerfSeries = (id: number) =>
  http.get<{ series: AppPerfSeries[] }>(`/app-runs/${id}/perf-series`)

export const getAppComparison = (projectId: number, batchId: string) =>
  http.get<{ batch_id: string; script_id: number; script_name: string; runs: AppRun[] }>(
    `/projects/${projectId}/app-runs/comparison?batch_id=${encodeURIComponent(batchId)}`)

export function subscribeAppRunEvents(runId: number, onEvent: (e: AppRunEvent) => void): () => void {
  const es = new EventSource(withSseToken(`/api/app-runs/${runId}/events`))
  es.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data) as AppRunEvent)
    } catch {
      /* 坏帧忽略 */
    }
  }
  // 断线兜底(终审 T13①):后端终态断流/网络抖动会触发 onerror,EventSource 默认还会自动重连;
  // 这里关流防重连,并回读最新状态——已终态给 snapshot(关流+回读语义),否则报连接断开。
  // handler 置空防「正常 done 后消费方才 close」与迟到 onerror 双触发。
  es.onerror = () => {
    es.onerror = null
    es.close()
    void getAppRun(runId)
      .then((run) => {
        if (TERMINAL_RUN_STATUS.includes(run.status)) {
          onEvent({ type: 'snapshot', status: run.status, run_state: run.run_state, error: run.error })
        } else {
          onEvent({ type: 'error', message: 'SSE 连接断开' })
        }
      })
      .catch(() => onEvent({ type: 'error', message: 'SSE 连接断开' }))
  }
  return () => es.close()
}
