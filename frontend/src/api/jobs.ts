import type { GenerationJob, SSEEvent, StagingResponse } from '../types'
import { http, withSseToken } from './client'

// 创建生成任务(模块三选一:选中 id / 手输名字 / 留空)
export function createJob(projectId: number, payload: { documentId: number; targetModuleId?: number; targetModuleName?: string; jobType?: 'case_generation' | 'api_generation'; userPrompt?: string }) {
  const body: Record<string, unknown> = { document_id: payload.documentId }
  if (payload.targetModuleId != null) body.target_module_id = payload.targetModuleId
  if (payload.targetModuleName) body.target_module_name = payload.targetModuleName
  if (payload.jobType) body.job_type = payload.jobType
  if (payload.userPrompt) body.user_prompt = payload.userPrompt
  return http.post<GenerationJob>(`/projects/${projectId}/jobs`, body)
}

// 列出项目下所有任务
export function listJobs(projectId: number) {
  return http.get<GenerationJob[]>(`/projects/${projectId}/jobs`)
}

// 获取单个任务详情
export function getJob(id: number) {
  return http.get<GenerationJob>(`/jobs/${id}`)
}

// 获取暂存区内容
export function listStaging(jobId: number) {
  return http.get<StagingResponse>(`/jobs/${jobId}/staging`)
}

// 接受暂存用例
export function acceptStaging(jobId: number, ids: number[]) {
  return http.post<{ accepted: number; feature_point_ids: Record<string, number> }>(`/jobs/${jobId}/staging/accept`, { ids })
}

// 拒绝单条暂存用例
export function rejectStaged(id: number) {
  return http.del(`/staged/${id}`)
}

// 订阅任务 SSE 事件流(EventSource 带不了 Authorization,经 query token 鉴权)
export function subscribeJobEvents(jobId: number, onEvent: (e: SSEEvent) => void): () => void {
  const es = new EventSource(withSseToken(`/api/jobs/${jobId}/events`))
  let closed = false

  es.onmessage = (event) => {
    if (closed) return
    try {
      const data = JSON.parse(event.data)
      onEvent(data)
    } catch {
      // JSON 解析失败,忽略
    }
  }

  es.onerror = () => {
    if (!closed) {
      closed = true
      es.close()
      onEvent({ type: 'error', message: '连接中断' })
    }
  }

  return () => {
    if (!closed) {
      closed = true
      es.close()
    }
  }
}
