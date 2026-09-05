<template>
  <el-dialog :model-value="visible" title="项目成员" width="640px" @update:model-value="$emit('update:visible', $event)">
    <el-table v-loading="loading" :data="members" size="small" data-test="members-table">
      <el-table-column prop="display_name" label="显示名" min-width="120" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column label="角色" width="130">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            size="small"
            :data-user-id="row.user_id"
            data-test="role-select"
            @change="onRoleChange(row, $event)"
          >
            <el-option v-for="r in ROLES" :key="r" :label="ROLE_LABEL[r]" :value="r" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button link type="danger" size="small" data-test="remove-member" @click="onRemove(row)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部添加行:viewer 可读列表,但添加/改角色/移除由后端 owner 闸拦截,403 detail 直接透出 -->
    <div class="add-row">
      <!-- 用户名改为模糊搜索选择(Task 3 UserSearchSelect,v-model=username),避免手输用户名 404 -->
      <UserSearchSelect v-model="addName" size="small" class="add-name" style="width: 100%" />
      <el-select v-model="addRole" class="add-role" size="small" data-test="add-role">
        <el-option v-for="r in ROLES" :key="r" :label="ROLE_LABEL[r]" :value="r" />
      </el-select>
      <el-button type="primary" size="small" :loading="adding" data-test="add-submit" @click="onAdd">添加</el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'
import { membersApi, type MemberInfo, type MemberRole } from '../api/members'
import UserSearchSelect from './UserSearchSelect.vue'

const props = defineProps<{ visible: boolean; projectId: number }>()
const emit = defineEmits<{ 'update:visible': [boolean]; changed: [] }>()

const ROLES: MemberRole[] = ['owner', 'editor', 'viewer']
const ROLE_LABEL: Record<MemberRole, string> = { owner: 'owner', editor: 'editor', viewer: 'viewer' }

const members = ref<MemberInfo[]>([])
const loading = ref(false)
const addName = ref('')
const addRole = ref<MemberRole>('viewer')
const adding = ref(false)

watch(
  () => props.visible,
  async (v) => {
    if (v) await load()
  },
  { immediate: true },
)

async function load() {
  loading.value = true
  try {
    members.value = await membersApi.list(props.projectId)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function onRoleChange(row: MemberInfo, role: MemberRole) {
  const prev = row.role
  try {
    await membersApi.changeRole(props.projectId, row.user_id, role)
    row.role = role
    emit('changed')
  } catch (e) {
    // 末位 owner 自降等 409:恢复原角色,后端 detail 原样透出
    row.role = prev
    ElMessage.error((e as Error).message)
  }
}

async function onRemove(row: MemberInfo) {
  try {
    await membersApi.remove(props.projectId, row.user_id)
    members.value = members.value.filter((m) => m.user_id !== row.user_id)
    emit('changed')
  } catch (e) {
    ElMessage.error((e as Error).message) // 末位 owner 移除 409「项目至少需要一名 owner」
  }
}

async function onAdd() {
  const username = addName.value.trim()
  if (!username) {
    ElMessage.warning('请输入用户名')
    return
  }
  adding.value = true
  try {
    const added = await membersApi.add(props.projectId, username, addRole.value)
    members.value = [...members.value, added]
    addName.value = ''
    addRole.value = 'viewer'
    emit('changed')
  } catch (e) {
    ElMessage.error((e as Error).message) // 409「已是项目成员」/ 404「user not found」/ 403
  } finally {
    adding.value = false
  }
}
</script>

<style scoped>
.add-row {
  align-items: center;
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.add-name {
  flex: 1;
}
.add-role {
  width: 120px;
}
</style>
