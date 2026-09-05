import type { UserInfo } from './auth'
import { http } from './client'

// 与后端 schemas_auth.UserOut 对齐(不返回 created_at,建号时间后端未暴露)
export type UserCreateInput = {
  username: string
  display_name: string
  password: string
  is_admin?: boolean
}

// 后端 exclude_unset 语义:只提交要改的字段(display_name/password/is_active 任意组合)
export type UserUpdateInput = {
  display_name?: string
  password?: string
  is_active?: boolean
}

/** 对齐后端 UserSearchItem(schemas_auth.py):搜索选人用,仅 3 字段。 */
export interface UserSearchItem {
  id: number
  username: string
  display_name: string
}

// 角色口径与 members.MemberRole 一致(此处独立声明,避免 users→members 运行时依赖)
export type Role = 'owner' | 'editor' | 'viewer'

/** 对齐后端 UserProjectRole(schemas_auth.py)。 */
export interface UserProjectRole {
  project_id: number
  project_name: string
  role: Role
}

export const usersApi = {
  list: () => http.get<UserInfo[]>('/users'),
  create: (body: UserCreateInput) => http.post<UserInfo>('/users', body),
  update: (id: number, body: UserUpdateInput) => http.put<UserInfo>(`/users/${id}`, body),
  search: (q: string) => http.get<UserSearchItem[]>(`/users/search?q=${encodeURIComponent(q)}&limit=20`),
  /** 管理员查某用户的项目授权(按项目名排序) */
  projects: (userId: number) => http.get<UserProjectRole[]>(`/users/${userId}/projects`),
}
