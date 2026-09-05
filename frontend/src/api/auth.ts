import { http } from './client'

export interface UserInfo {
  id: number
  username: string
  display_name: string
  is_admin: boolean
  is_active: boolean
}

export const authApi = {
  login: (username: string, password: string) =>
    http.post<{ token: string; user: UserInfo }>('/auth/login', { username, password }),
  me: () => http.get<UserInfo>('/auth/me'),
}
