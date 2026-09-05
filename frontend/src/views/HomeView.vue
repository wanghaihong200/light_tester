<template>
  <div class="home-view">
    <div class="page-head">
      <h2 class="page-title">项目</h2>
      <el-button class="new-project" type="primary" @click="openCreate">+ 新建项目</el-button>
    </div>
    <div v-loading="loading" class="card-grid">
      <div v-for="p in projects" :key="p.id" class="project-card">
        <div class="card-title" @click="$router.push(`/projects/${p.id}`)">{{ p.name }}</div>
        <div class="card-desc" :title="p.description ?? ''">{{ p.description || '暂无描述' }}</div>
        <div class="card-meta">{{ formatTime(p.created_at) }}</div>
        <div class="card-actions">
          <el-button size="small" type="primary" @click="$router.push(`/projects/${p.id}`)">进入</el-button>
          <el-button size="small" @click="openEdit(p)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(p)">删除</el-button>
        </div>
      </div>
      <div v-if="!loading && projects.length === 0" class="empty-tip">还没有项目,点右上角「+ 新建项目」开始</div>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑项目' : '新建项目'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="100" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="Git 仓库">
          <el-input v-model="form.git_repo_url" maxlength="500" placeholder="http(s)://…/repo.git,接口生成任务与工程同步用" />
        </el-form-item>
        <el-form-item label="Git Token">
          <el-input
            v-model="form.git_token"
            maxlength="200"
            :placeholder="editing ? '留空表示不修改' : '可选,GitLab 访问 Token'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { createProject, deleteProject, listProjects, updateProject } from '../api/projects'
import type { Project } from '../types'

const projects = ref<Project[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref<Project | null>(null)
const form = ref({ name: '', description: '', git_repo_url: '', git_token: '' })

async function load() {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch (e) {
    ElMessage.error(`加载项目失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', git_repo_url: '', git_token: '' }
  dialogVisible.value = true
}
function openEdit(p: Project) {
  editing.value = p
  // git_token 后端不返回,无法回填 → 留空表示不修改(exclude_unset 语义)
  form.value = { name: p.name, description: p.description ?? '', git_repo_url: p.git_repo_url ?? '', git_token: '' }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      // token 仅在用户输入时提交:显式传 null 会把已存 token 清掉(exclude_unset 只区分字段是否出现)
      const payload: Parameters<typeof updateProject>[1] = {
        name: form.value.name.trim(),
        description: form.value.description || null,
        git_repo_url: form.value.git_repo_url.trim() || null,
      }
      if (form.value.git_token.trim()) payload.git_token = form.value.git_token.trim()
      await updateProject(editing.value.id, payload)
    } else {
      await createProject({
        name: form.value.name.trim(),
        description: form.value.description || null,
        git_repo_url: form.value.git_repo_url.trim() || null,
        git_token: form.value.git_token.trim() || null,
      })
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(`保存失败:${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function onDelete(p: Project) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${p.name}」?其下用例树、文档将全部删除。`, '删除项目', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteProject(p.id)
    await load()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.home-view {
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
.card-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}
.project-card {
  background: var(--pro-card-bg);
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-large);
  box-shadow: var(--pro-card-shadow);
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.project-card:hover {
  box-shadow: 0 10px 28px rgba(68, 87, 150, 0.12);
  transform: translateY(-2px);
}
.card-title {
  color: var(--el-text-color-primary);
  cursor: pointer;
  font-size: 15px;
  font-weight: 700;
}
.card-title:hover {
  color: var(--el-color-primary);
}
.card-desc {
  color: var(--el-text-color-regular);
  display: -webkit-box;
  min-height: 36px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.card-meta {
  color: var(--pro-muted);
  font-size: 12px;
}
.card-actions {
  display: flex;
  gap: 8px;
}
.empty-tip {
  color: var(--pro-muted);
  grid-column: 1 / -1;
  padding: 48px 0;
  text-align: center;
}
</style>
