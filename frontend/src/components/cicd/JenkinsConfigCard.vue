<template>
  <el-card class="jenkins-card">
    <template #header><span>Jenkins 连接(CI/CD 执行通道)</span></template>
    <el-form label-width="170px" style="max-width: 640px">
      <el-form-item label="Jenkins 地址" required>
        <el-input v-model="form.base_url" placeholder="http://localhost:8081" />
      </el-form-item>
      <el-form-item label="用户名" required>
        <el-input v-model="form.api_user" placeholder="API token 所属用户" />
      </el-form-item>
      <el-form-item label="API Token" required>
        <el-input v-model="form.api_token" show-password placeholder="Jenkins → 用户 → Security → API Token" />
      </el-form-item>
      <el-form-item label="GitLab 对 Jenkins 暴露地址">
        <el-input v-model="form.gitlab_exposed_base" placeholder="http://host.docker.internal:8090" />
        <div class="hint">仓 remote 存的是宿主机地址(localhost:8090);Jenkins 容器克隆时由平台按此改写</div>
      </el-form-item>
      <el-form-item label="GitLab 凭据 ID">
        <el-input v-model="form.credential_id" placeholder="gitlab-creds(Jenkins 内手动配置的凭据 ID)" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="save">保存</el-button>
        <el-button @click="doTest">测试连接</el-button>
        <span v-if="testMsg" :class="['test-msg', testOk ? 'ok' : 'bad']">{{ testMsg }}</span>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getJenkinsConnection, putJenkinsConnection, testJenkinsConnection } from '../../api/cicd'
import type { JenkinsCfg } from '../../api/cicd'

const form = ref<JenkinsCfg>({ base_url: '', api_user: '', api_token: '',
  gitlab_exposed_base: 'http://host.docker.internal:8090', credential_id: 'gitlab-creds' })
const testMsg = ref('')
const testOk = ref(false)

async function save(): Promise<void> {
  await putJenkinsConnection(form.value)
  ElMessage.success('Jenkins 连接已保存')
}

async function doTest(): Promise<void> {
  try {
    await testJenkinsConnection()
    testOk.value = true
    testMsg.value = '连接成功'
  } catch (e) {
    testOk.value = false
    testMsg.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(async () => {
  const cfg = await getJenkinsConnection()
  if (cfg.configured) form.value = { base_url: cfg.base_url, api_user: cfg.api_user,
    api_token: cfg.api_token, gitlab_exposed_base: cfg.gitlab_exposed_base, credential_id: cfg.credential_id }
})
</script>

<style scoped>
.jenkins-card { margin-top: 20px; }
.hint { color: var(--pro-muted); font-size: 12px; }
.test-msg.ok { color: var(--el-color-success); margin-left: 10px; }
.test-msg.bad { color: var(--el-color-danger); margin-left: 10px; }
</style>
