<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <div class="brand">
        <span class="brand-logo">轻</span>
        <h2 class="brand-name">轻测试 LightTester</h2>
        <p class="brand-sub">登录后继续使用</p>
      </div>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" data-test="username" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password data-test="password" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" class="submit-btn" data-test="submit">
          登 录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../composables/useAuth'

const username = ref('')
const password = ref('')
const loading = ref(false)
const { login } = useAuth()

async function submit() {
  if (!username.value || !password.value) return
  loading.value = true
  try {
    await login(username.value, password.value)
    location.hash = '#/'
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  align-items: center;
  background: var(--pro-bg-gradient);
  background-attachment: fixed;
  display: flex;
  justify-content: center;
  min-height: 100vh;
}
.login-card {
  border: 1px solid var(--pro-line);
  border-radius: var(--border-radius-large);
  box-shadow: var(--pro-panel-shadow);
  text-align: center;
  width: 360px;
}
.brand {
  margin-bottom: 20px;
}
.brand-logo {
  background: var(--el-color-primary);
  border-radius: var(--border-radius-base);
  color: #fff;
  display: inline-block;
  font-size: 18px;
  font-weight: 600;
  height: 40px;
  line-height: 40px;
  width: 40px;
}
.brand-name {
  color: var(--el-text-color-primary);
  font-size: 18px;
  margin: 12px 0 4px;
}
.brand-sub {
  color: var(--pro-muted);
  font-size: 12px;
  margin: 0;
}
.submit-btn {
  width: 100%;
}
</style>
