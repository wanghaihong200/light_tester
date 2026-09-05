import type {
  UiAuthState, UiRun, UiScript, UiScriptDoc, UiStep, UiVariable,
} from '../types'
import { http, withSseToken } from './client'

// 脚本 CRUD
export function listUiScripts(projectId: number) {
  return http.get<UiScript[]>(`/projects/${projectId}/ui-scripts`)
}
export function createUiScript(projectId: number, body: { name: string; description?: string | null; script: UiScriptDoc }) {
  return http.post<UiScript>(`/projects/${projectId}/ui-scripts`, {
    name: body.name, description: body.description, script: body.script,
  })
}
export function updateUiScript(id: number, body: { name: string; description?: string | null; script: UiScriptDoc }) {
  return http.put<UiScript>(`/ui-scripts/${id}`, {
    name: body.name, description: body.description, script: body.script,
  })
}
export function deleteUiScript(id: number) {
  return http.del(`/ui-scripts/${id}`)
}

// 录制会话
export function startRecording(projectId: number, authStateId?: number) {
  return http.post<{ recording_id: number }>(`/projects/${projectId}/ui-recordings`,
    authStateId != null ? { auth_state_id: authStateId } : {})
}
export function insertAssert(recordingId: number, body: {
  target: Record<string, unknown>; assert_type: string; text?: string; mode?: string
}) {
  return http.post<{ steps: UiStep[] }>(`/ui-recordings/${recordingId}/assert`, body)
}
export function stopRecording(recordingId: number) {
  return http.post<{ meta: { start_url: string }; variables: UiVariable[]; steps: UiStep[] }>(
    `/ui-recordings/${recordingId}/stop`)
}
export function cancelRecording(recordingId: number) {
  return http.post<void>(`/ui-recordings/${recordingId}/cancel`)
}

// 执行
export function createUiRun(projectId: number, body: {
  script_id: number; mode?: 'headless' | 'headed'; variables?: Record<string, string>; auth_state_id?: number
}) {
  return http.post<UiRun>(`/projects/${projectId}/ui-runs`, body)
}
export function getUiRun(id: number) { return http.get<UiRun>(`/ui-runs/${id}`) }
export function listUiRuns(projectId: number, scriptId?: number) {
  return http.get<UiRun[]>(`/projects/${projectId}/ui-runs${scriptId ? `?script_id=${scriptId}` : ''}`)
}
export function forceFinishRun(id: number) {
  return http.post<UiRun>(`/ui-runs/${id}/force-finish`)
}

// 登录态
export function listUiAuthStates(projectId: number) {
  return http.get<UiAuthState[]>(`/projects/${projectId}/ui-auth-states`)
}
export function deleteUiAuthState(id: number) { return http.del(`/ui-auth-states/${id}`) }
export function collectAuthState(projectId: number, name: string) {
  return http.post<{ collect_id: number }>(`/projects/${projectId}/ui-auth-states/collect`, { name })
}
export function saveAuthState(collectId: number) {
  return http.post<UiAuthState>(`/ui-auth-collect/${collectId}/save`)
}
export function cancelAuthCollect(collectId: number) {
  return http.post<void>(`/ui-auth-collect/${collectId}/cancel`)
}

// 通用 SSE 订阅(录制流与执行流同构;EventSource 带不了 Authorization,经 query token 鉴权)
function subscribeSse(url: string, onEvent: (e: Record<string, unknown>) => void): () => void {
  const es = new EventSource(withSseToken(url))
  let closed = false
  es.onmessage = (ev) => {
    if (closed) return
    try { onEvent(JSON.parse(ev.data)) } catch { /* 非 JSON 忽略 */ }
  }
  es.onerror = () => {
    if (!closed) { closed = true; es.close(); onEvent({ type: 'error', message: '连接中断' }) }
  }
  return () => { if (!closed) { closed = true; es.close() } }
}

export const subscribeRecordingEvents = (rid: number, onEvent: (e: Record<string, unknown>) => void) =>
  subscribeSse(`/api/ui-recordings/${rid}/events`, onEvent)
export const subscribeRunEvents = (rid: number, onEvent: (e: Record<string, unknown>) => void) =>
  subscribeSse(`/api/ui-runs/${rid}/events`, onEvent)
