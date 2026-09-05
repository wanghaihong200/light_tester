import { http } from './client'

export type MemberRole = 'owner' | 'editor' | 'viewer'

// 与后端 schemas_auth.MemberOut 对齐(join User 平铺 username/display_name)
export interface MemberInfo {
  id: number
  user_id: number
  username: string
  display_name: string
  role: MemberRole
}

export const membersApi = {
  list: (pid: number) => http.get<MemberInfo[]>(`/projects/${pid}/members`),
  add: (pid: number, username: string, role: MemberRole) =>
    http.post<MemberInfo>(`/projects/${pid}/members`, { username, role }),
  changeRole: (pid: number, userId: number, role: MemberRole) =>
    http.put<MemberInfo>(`/projects/${pid}/members/${userId}`, { role }),
  remove: (pid: number, userId: number) => http.del(`/projects/${pid}/members/${userId}`),
}
