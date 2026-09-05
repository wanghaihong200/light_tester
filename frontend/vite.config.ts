import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true, // 双栈监听(IPv4+IPv6):Node 17+ 默认只绑 ::1,IPv4 解析 localhost 的浏览器会连不上
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
  },
})
