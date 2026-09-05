<template>
  <div class="docs-pane">
    <el-upload
      drag
      action=""
      accept=".md"
      :show-file-list="false"
      :http-request="doUpload"
      class="uploader"
    >
      <div class="upload-hint">拖拽 .md 文件到此处,或点击上传(需求文档 / API 定义)</div>
    </el-upload>

    <el-table :data="documents" v-loading="loading" border>
      <el-table-column prop="filename" label="文件名" min-width="240" />
      <el-table-column label="上传时间" width="180">
        <template #default="{ row }">{{ new Date(row.uploaded_at).toLocaleString('zh-CN', { hour12: false }) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="download(row)">下载</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { onMounted, ref } from 'vue'
import { downloadFile } from '../api/client'
import { deleteDocument, listDocuments, uploadDocument } from '../api/documents'
import type { DocumentItem } from '../types'

const props = defineProps<{ projectId: number }>()

const documents = ref<DocumentItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    documents.value = await listDocuments(props.projectId)
  } catch (e) {
    ElMessage.error(`加载文档列表失败:${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function doUpload(options: UploadRequestOptions) {
  if (!options.file.name.toLowerCase().endsWith('.md')) {
    ElMessage.warning('仅支持 .md 文件')
    return
  }
  try {
    await uploadDocument(props.projectId, options.file)
    ElMessage.success(`已上传:${options.file.name}`)
    await load()
  } catch (e) {
    ElMessage.error(`上传失败:${(e as Error).message}`)
  }
}

// 后端 401 门禁后 window.open 直链带不了 Authorization:经 http 客户端 fetch→blob 触发下载
async function download(row: DocumentItem) {
  try {
    await downloadFile(`/documents/${row.id}/download`, row.filename)
  } catch (e) {
    ElMessage.error(`下载失败:${(e as Error).message}`)
  }
}

async function remove(row: DocumentItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.filename}」?`, '删除文档', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDocument(row.id)
    await load()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}
</script>

<style scoped>
.docs-pane {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.uploader {
  width: 100%;
}
.upload-hint {
  padding: 20px 0;
  color: #909399;
}
</style>
