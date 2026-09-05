// 多端 UI 自动化(计划 10):跨端脚本/运行/应用快照;脚本 CRUD 与 SSE 订阅复用 uiAutomation.ts
import type { UiAuthState, UiRun, UiScript } from '../types'
import { http } from './client'

export function listCrossScripts(projectId: number) {
  return http.get<UiScript[]>(`/projects/${projectId}/ui-scripts?scope=cross`)
}
export function listRunsByTarget(projectId: number, driverTarget?: string) {
  return http.get<UiRun[]>(`/projects/${projectId}/ui-runs${driverTarget ? `?driver_target=${driverTarget}` : ''}`)
}
export function listAuthStates(projectId: number, kind?: 'web_storage' | 'android_snapshot') {
  return http.get<UiAuthState[]>(`/projects/${projectId}/ui-auth-states${kind ? `?kind=${kind}` : ''}`)
}
export function collectAndroidSnapshot(projectId: number, body: { name: string; app_package: string }) {
  return http.post<UiAuthState>(`/projects/${projectId}/ui-auth-states/android-snapshot`, body)
}
