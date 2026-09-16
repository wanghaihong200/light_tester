import fs from 'node:fs'
import path from 'node:path'
import vue from '@vitejs/plugin-vue'
import { defineConfig, type Plugin } from 'vitest/config'

// 计划16(任务16,fix1)兜底:T15 懒加载路由与 PlansPane 引用的 CI/CD SFC 分属任务 17-20 落盘
// (PlanDialog/TriggerDialog/RunsPane/RunDetailPage),而 vitest 转换期要求 import 可解析
// (spec 里的 vi.mock 只在运行时接管,救不了 import-analysis)。
// 仅当「处于测试进程 且 目标 SFC 尚不存在」时把白名单路径重定向到虚拟空组件;
// 真实文件落盘后本兜底自动失效(build/dev 均不受影响),全部落盘后可整体删除本函数。
const PENDING_CICD_SFCS = ['src/components/cicd/PlanDialog.vue', 'src/components/cicd/TriggerDialog.vue', 'src/components/cicd/RunsPane.vue', 'src/components/cicd/RunDetailPage.vue']

function pendingCicdSfcStub(): Plugin {
  return {
    name: 'pending-cicd-sfc-stub',
    enforce: 'pre',
    resolveId(id, importer) {
      if (!process.env.VITEST || !importer || !id.endsWith('.vue')) return null
      const abs = path.resolve(path.dirname(importer), id).replace(/\\/g, '/')
      if (!PENDING_CICD_SFCS.some((p) => abs.endsWith(p)) || fs.existsSync(abs)) return null
      return `\0pending-cicd-sfc:${abs}.js`
    },
    load(id) {
      if (!id.startsWith('\0pending-cicd-sfc:')) return null
      return 'export default { name: "PendingCicdSfcStub" }'
    },
  }
}

export default defineConfig({
  plugins: [vue(), pendingCicdSfcStub()],
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
