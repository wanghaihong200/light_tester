<template>
  <div class="users-view">
    <div class="page-head">
      <h2 class="page-title">用户管理</h2>
      <el-button type="primary" data-test="new-user" @click="openCreate">+ 新建用户</el-button>
    </div>
    <div class="panel-card">
      <el-table v-loading="loading" :data="users" data-test="users-table">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="display_name" label="显示名" min-width="140" />
        <el-table-column label="管理员" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">{{ row.is_admin ? '管理员' : '普通' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'warning'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="{ row }">
            <el-button link type="primary" data-test="reset-pwd" @click="onResetPwd(row)">重置密码</el-button>
            <el-button
              link
              :type="row.is_active ? 'danger' : 'success'"
              data-test="toggle-active"
              @click="onToggleActive(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button link type="primary" data-test="assign-perm" @click="openPerms(row)">项目权限</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="createVisible" title="新建用户" width="440px">
      <el-form label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" maxlength="64" placeholder="登录名" data-test="create-username" />
        </el-form-item>
        <el-form-item label="显示名" required>
          <el-input v-model="form.display_name" maxlength="64" placeholder="昵称" data-test="create-display-name" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="至少 6 位"
            data-test="create-password"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" data-test="create-save" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 项目授权弹窗:行内「项目权限」打开;changed 暂无派生状态,绑定为空操作保留契约 -->
    <UserProjectsDialog
      v-if="permUser"
      :user-id="permUser.id"
      :username="permUser.username"
      :visible="permVisible"
      @update:visible="permVisible = $event"
      @changed="() => {}"
    />
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { UserInfo } from '../api/auth'
import { usersApi, type UserUpdateInput } from '../api/users'
import { useAuth } from '../composables/useAuth'
import UserProjectsDialog from '../components/UserProjectsDialog.vue'

const router = useRouter()
const { user, isAdmin, fetchMe } = useAuth()
const users = ref<UserInfo[]>([])
const loading = ref(false)
const createVisible = ref(false)
const saving = ref(false)
const form = ref({ username: '', display_name: '', password: '' })
const permUser = ref<UserInfo | null>(null)
const permVisible = ref(false)

function openPerms(row: UserInfo) {
  permUser.value = row
  permVisible.value = true
}

async function load() {
  loading.value = true
  try {
    users.value = await usersApi.list()
  } catch (e) {
    ElMessage.error((e as Error).message) // 403 detail「需要管理员权限」等由后端定文案
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // admin 守卫第二层(路由 meta 是第一层):刷新直达 #/users 时 fetchMe 未跑完、isAdmin 还是假,
  // 路由层无法判定 → 此处补拉 me 再判;非 admin 提示并回首页。401 已由 client 统一踢登录,这里静默
  if (!user.value) {
    try {
      await fetchMe()
    } catch {
      return
    }
  }
  if (!isAdmin.value) {
    ElMessage.warning('需要管理员权限')
    void router.replace('/')
    return
  }
  await load()
})

function openCreate() {
  form.value = { username: '', display_name: '', password: '' }
  createVisible.value = true
}

async function save() {
  if (!form.value.username.trim() || !form.value.display_name.trim() || form.value.password.length < 6) {
    ElMessage.warning('请填写用户名、显示名,密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await usersApi.create({
      username: form.value.username.trim(),
      display_name: form.value.display_name.trim(),
      password: form.value.password,
    })
    createVisible.value = false
    ElMessage.success('用户已创建')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message) // 409「用户名已存在」等后端 detail
  } finally {
    saving.value = false
  }
}

async function onResetPwd(row: UserInfo) {
  let password: string
  try {
    const r = await ElMessageBox.prompt(`为「${row.display_name}」设置新密码(至少 6 位)`, '重置密码', {
      inputType: 'password',
      inputPattern: /^.{6,}$/,
      inputErrorMessage: '密码至少 6 位',
    })
    password = r.value
  } catch {
    return
  }
  await applyUpdate(row.id, { password })
}

async function onToggleActive(row: UserInfo) {
  await applyUpdate(row.id, { is_active: !row.is_active })
}

// 禁用即下线(不提供删除);自操作由后端 409「不能操作自己的账号」拒绝,detail 直接透出
async function applyUpdate(id: number, body: UserUpdateInput) {
  try {
    await usersApi.update(id, body)
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
</script>

<style scoped>
.users-view {
  padding-top: 16px;
}
.page-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  color: var(--el-text-color-primary);
  font-size: 18px;
  margin: 0;
}
.panel-card {
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-large);
  box-shadow: var(--pro-card-shadow);
  padding: 12px 16px;
}
</style>
