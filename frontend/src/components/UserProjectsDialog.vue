<template>
  <el-dialog
    :model-value="visible"
    :title="`项目权限 - ${username}`"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-input
      v-model="filter"
      clearable
      placeholder="按项目名过滤"
      style="margin-bottom: 8px"
      data-test="project-filter"
    />
    <el-table v-loading="loading" :data="filtered" size="small" data-test="perm-table">
      <el-table-column prop="project_name" label="项目名" min-width="160" />
      <el-table-column label="角色" width="130">
        <template #default="{ row }">
          <el-select
            :model-value="draftOf(row)"
            size="small"
            :data-project-id="row.project_id"
            data-test="role-select"
            @update:model-value="onRoleInput(row, $event)"
          >
            <el-option v-for="r in ROLES" :key="r" :label="r" :value="r" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <!-- 未授权行:添加;已授权行:移除。末位 owner 自降/移除 409 detail 直接透出并回滚 -->
          <el-button v-if="row.role" link type="danger" size="small" data-test="remove-btn" @click="onRemove(row)">
            移除
          </el-button>
          <el-button
            v-else
            link
            type="primary"
            size="small"
            :loading="saving"
            data-test="assign-btn"
            @click="onAdd(row)"
          >
            添加
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { listProjects } from '../api/projects'
import { membersApi, type MemberRole } from '../api/members'
import { usersApi, type UserProjectRole } from '../api/users'

const props = defineProps<{ userId: number; username: string; visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [boolean]; changed: [] }>()

const ROLES: MemberRole[] = ['owner', 'editor', 'viewer']

// role=null 表示该用户未授权此项目(仍占一行,便于从全量项目直接添加)
interface Row {
  project_id: number
  project_name: string
  role: MemberRole | null
}

const rows = ref<Row[]>([])
const filter = ref('')
const loading = ref(false)
const saving = ref(false)
// 未授权行的角色草稿(授权行改角色走 changeRole,不落草稿),按 project_id 存
const drafts = ref<Record<number, MemberRole>>({})

watch(
  () => props.visible,
  async (v) => {
    if (v) await reload()
  },
  { immediate: true },
)

// 并行拉「该用户授权列表 + 全量项目」,求并成单表:授权行带角色,未授权行 role=null
async function reload() {
  loading.value = true
  try {
    const [granted, projects] = await Promise.all([usersApi.projects(props.userId), listProjects()])
    const roleByPid = new Map<number, UserProjectRole['role']>(granted.map((g) => [g.project_id, g.role]))
    rows.value = projects.map((p) => ({ project_id: p.id, project_name: p.name, role: roleByPid.get(p.id) ?? null }))
    drafts.value = {}
    filter.value = '' // 跨用户重开弹窗时清掉上一次的过滤条件
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => rows.value.filter((r) => r.project_name.includes(filter.value.trim())))

function draftOf(r: Row): MemberRole {
  return r.role ?? drafts.value[r.project_id] ?? 'viewer' // 未授权行默认 viewer
}

function onRoleInput(r: Row, role: MemberRole) {
  if (r.role) onRoleChange(r, role)
  else drafts.value[r.project_id] = role // 未授权行只是选草稿,不调接口
}

async function onAdd(r: Row, role: MemberRole = drafts.value[r.project_id] ?? 'viewer') {
  saving.value = true
  try {
    await membersApi.add(r.project_id, props.username, role)
    ElMessage.success('已授权')
    await reload()
    emit('changed')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败') // 409「已是项目成员」等后端 detail
  } finally {
    saving.value = false
  }
}

async function onRoleChange(r: Row, role: MemberRole) {
  const prev = r.role
  try {
    await membersApi.changeRole(r.project_id, props.userId, role)
    await reload()
    emit('changed')
  } catch (e) {
    // 末位 owner 自降等 409:恢复原角色,后端 detail 原样透出
    r.role = prev
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}

async function onRemove(r: Row) {
  try {
    await membersApi.remove(r.project_id, props.userId)
    await reload()
    emit('changed')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}
</script>
