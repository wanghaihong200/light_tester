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
    // 默认按 CPU 数(16)开 worker,SFC 编译争抢反而拖慢全量、挤出 router 用例超时(单跑恒绿);
    // 限 8 实测 322 条 26s 全绿(不限时 45s 且偶发超时)
    maxWorkers: 8,
  },
})
