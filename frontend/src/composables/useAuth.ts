import { computed, ref } from 'vue'
import { authApi, type UserInfo } from '../api/auth'
import { getToken, setToken } from '../api/client'

// 模块级单例 state:登录态全局唯一,顶栏/路由守卫/页面共享同一份 token/user
const token = ref<string | null>(getToken())
const user = ref<UserInfo | null>(null)
const isAdmin = computed(() => user.value?.is_admin === true)

export function useAuth() {
  async function login(username: string, password: string) {
    const r = await authApi.login(username, password)
    setToken(r.token)
    token.value = r.token
    user.value = r.user
  }

  function logout() {
    setToken(null)
    token.value = null
    user.value = null
    location.hash = '#/login'
  }

  // 已有 token 才拉当前用户;失败交由调用方决定是否静默(401 已由 client 统一踢登录)
  async function fetchMe() {
    if (!getToken()) return
    user.value = await authApi.me()
  }

  return { token, user, isAdmin, login, logout, fetchMe }
}

// 仅测试用:模块级状态在用例间共享,需要显式复位(同 useTabs.resetTabs)
export function resetAuth(): void {
  setToken(null)
  token.value = null
  user.value = null
}
