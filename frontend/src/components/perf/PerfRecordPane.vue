<script setup lang="ts">
// 计划14 Task9:APP 性能测试页——性能记录列表(来源筛选/多选/删除)+ 详情抽屉(曲线/汇总/CSV 下载)
// 计划14 Task10/11:接入手动导入向导 PerfImportDialog + 跨记录对比/趋势对话框(导入成功后刷新)
// projectId 经 ProjectView 的 :project-id 下发(同 WebAutoPane)
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePerfRecord, getPerfRecordSeries, listPerfRecords } from '../../api/perf'
import type { AppPerfSeries, PerfRecord, PerfSource } from '../../types'
// CLI perf-analyze 真实结构 {files:[…]} → 标准形(幂等;计划14 冒烟修复),曲线/统计表共用
import { normalizePerfSummary } from './perfOption'
import PerfCharts from './PerfCharts.vue'
import PerfCompareDialog from './PerfCompareDialog.vue'
import PerfImportDialog from './PerfImportDialog.vue'
import PerfSummaryTable from './PerfSummaryTable.vue'
import PerfTrendDialog from './PerfTrendDialog.vue'

const props = defineProps<{ projectId: number }>()

// ── 列表 ─────────────────────────────────────────────
// 来源筛选:''=全部(api 层对空串不序列化进 query)
const source = ref<'' | PerfSource>('')
const records = ref<PerfRecord[]>([])
const loading = ref(false)
// 请求序号守卫:快速切筛选时慢响应不覆盖新结果、不弹过期报错
let reloadSeq = 0

async function reload() {
  const seq = ++reloadSeq
  loading.value = true
  try {
    const data = await listPerfRecords(props.projectId, source.value ? { source: source.value } : {})
    if (seq !== reloadSeq) return
    records.value = data
  } catch (e) {
    if (seq !== reloadSeq) return
    ElMessage.error(`加载性能记录失败:${(e as Error).message}`)
  } finally {
    if (seq === reloadSeq) loading.value = false
  }
}
onMounted(reload)
watch(source, () => { reload() })

// 多选(对比入口):≥2 才可用;对比/趋势对话框由 Task 11 挂载到本页
const selected = ref<PerfRecord[]>([])
function onSelectionChange(rows: PerfRecord[]) {
  selected.value = rows
}

// ── 对比/趋势/导入对话框(Task 11 接入,均由 @close 关窗)──
const compareVisible = ref(false)
const trendVisible = ref(false)
const importVisible = ref(false)

function onImported(record: PerfRecord) {
  importVisible.value = false // 向导 emit close 也会置 false,此处兜底
  if (record.data_complete) ElMessage.success('导入成功') // 截断历史由向导 warning,不叠加成功提示
  reload()
}

// ── 详情抽屉 ─────────────────────────────────────────
const drawerVisible = ref(false)
const detailRecord = ref<PerfRecord | null>(null)
const detailSeries = ref<AppPerfSeries[]>([])
// perf_summary 喂 PerfCharts/PerfSummaryTable 前先归一(标准形透传,幂等)
const detailSummary = computed(() => normalizePerfSummary(detailRecord.value?.perf_summary))

async function openDetail(row: PerfRecord) {
  detailRecord.value = row
  detailSeries.value = [] // 先清空防上一条的曲线残留
  drawerVisible.value = true
  try {
    const res = await getPerfRecordSeries(row.id)
    if (detailRecord.value?.id !== row.id) return // 响应到达前已切换记录,丢弃过期响应
    detailSeries.value = res.series
  } catch {
    if (detailRecord.value?.id !== row.id) return
    detailSeries.value = [] // 拉取失败按无数据展示,不打断抽屉
    ElMessage.warning('性能序列加载失败')
  }
}

async function onDelete(row: PerfRecord) {
  try {
    await ElMessageBox.confirm(`删除性能记录「${row.name}」?曲线数据将一并清除。`, '删除记录', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deletePerfRecord(row.id)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error(`删除失败:${(e as Error).message}`)
  }
}

// ── CSV 下载:浏览器直接开 series 端点是 JSON,一期由前端把 series 拼文本 Blob 下载 ──
// 每个采集项一段(首行注释 `# item: <item>`,段间空行)
const SOURCE_TEXT: Record<PerfSource, string> = { run: '采集', import: '导入' }
const sourceTextOf = (s: PerfSource): string => SOURCE_TEXT[s] ?? s

// 极简转义:含逗号/引号/换行的单元格加引号,内部引号翻倍;
// 公式注入防御:以 = + - @ 开头的值前置 '(CSV 被 Excel 当公式执行的风险,计划14 终审)
function csvCell(v: string): string {
  const s = /^[=+\-@]/.test(v) ? `'${v}` : v
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function buildCsv(series: AppPerfSeries[]): string {
  return series
    .map((s) => [
      `# item: ${s.item}`,
      s.columns.map(csvCell).join(','),
      ...s.rows.map((r) => r.map(csvCell).join(',')),
    ].join('\n'))
    .join('\n\n')
}

// Windows Excel 靠 UTF-8 BOM 识别无 meta 的 CSV 编码,否则中文乱码
const UTF8_BOM = '\uFEFF'

// 文件名 sanitize:Windows 保留的 9 个非法字符替换为 _
function sanitizeFileName(name: string): string {
  return name.replace(/[/\\:*?"<>|]/g, '_')
}

function downloadCsv() {
  if (!detailRecord.value) return
  const blob = new Blob([`${UTF8_BOM}${buildCsv(detailSeries.value)}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${sanitizeFileName(detailRecord.value.name)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// 时间列:ISO 截断到分钟(PushDialog 同款,格式跨环境稳定);null → —
function fmtTime(iso: string | null): string {
  return iso ? iso.slice(0, 16).replace('T', ' ') : '—'
}
</script>

<template>
  <div class="perf-pane">
    <div class="toolbar">
      <span class="pane-title">性能记录</span>
      <el-select v-model="source" size="small" data-test="source-filter" class="source-select">
        <el-option label="全部" value="" />
        <el-option label="采集(run)" value="run" />
        <el-option label="导入(import)" value="import" />
      </el-select>
      <div class="toolbar-actions">
        <el-button size="small" data-test="trend-btn" @click="trendVisible = true">趋势分析</el-button>
        <el-button size="small" data-test="import-btn" @click="importVisible = true">导入</el-button>
        <el-button size="small" type="primary" data-test="compare-btn" :disabled="selected.length < 2" @click="compareVisible = true">对比</el-button>
      </div>
    </div>

    <!-- 详情只由操作列「详情」按钮触发(冒烟反馈:行点击易误开抽屉);row-key 必须:刷新换新引用时防 EP 内部状态坍缩 -->
    <el-table
      v-loading="loading" :data="records" row-key="id" border
      data-test="records-table"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
      <el-table-column label="来源" width="84" align="center">
        <template #default="{ row }">
          <el-tag :type="row.source === 'run' ? 'info' : 'success'" size="small" data-test="source-tag">
            {{ sourceTextOf(row.source) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="script_name" label="脚本" min-width="110">
        <template #default="{ row }">{{ row.script_name || '—' }}</template>
      </el-table-column>
      <el-table-column prop="device_serial" label="设备" width="130" />
      <el-table-column label="采集项" min-width="110">
        <template #default="{ row }">{{ row.perf_items.join(',') }}</template>
      </el-table-column>
      <el-table-column label="起止时间" min-width="230">
        <template #default="{ row }">{{ fmtTime(row.started_at) }} ~ {{ fmtTime(row.finished_at) }}</template>
      </el-table-column>
      <el-table-column label="数据完整性" width="104" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.data_complete" type="success" size="small">完整</el-tag>
          <el-tag v-else type="danger" size="small" data-test="incomplete-badge">数据不完整</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="132">
        <template #default="{ row }">
          <el-button link size="small" type="primary" data-test="detail-btn" @click.stop="openDetail(row)">详情</el-button>
          <el-button link size="small" type="danger" @click.stop="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && records.length === 0" description="暂无性能记录" />

    <!-- 详情抽屉:曲线 + 汇总表。startup_summary 挂在 AppRun 上、不在 PerfRecord,
         因此不渲染 StartupSummaryCard(它是 RunDetailDrawer 的组件) -->
    <el-drawer
      v-model="drawerVisible" :title="detailRecord?.name ?? '性能详情'"
      size="62%" data-test="detail-drawer"
    >
      <template v-if="detailRecord">
        <div class="detail-toolbar">
          <span class="detail-meta">
            设备 <b>{{ detailRecord.device_serial }}</b> · 来源 <b>{{ sourceTextOf(detailRecord.source) }}</b>
            <template v-if="detailRecord.script_name"> · 脚本 <b>{{ detailRecord.script_name }}</b></template>
            · 起止 {{ fmtTime(detailRecord.started_at) }} ~ {{ fmtTime(detailRecord.finished_at) }}
          </span>
          <el-button size="small" data-test="download-csv" :disabled="!detailSeries.length" @click="downloadCsv">下载 CSV</el-button>
        </div>
        <PerfCharts :series="detailSeries" :summary="detailSummary" />
        <h4 class="section-title">性能汇总</h4>
        <PerfSummaryTable :summary="detailSummary" />
      </template>
    </el-drawer>

    <!-- 跨记录对比(Task 11):勾选 ≥2 条记录后进入,传入选中 ids -->
    <PerfCompareDialog
      v-if="compareVisible" :project-id="projectId"
      :record-ids="selected.map((r) => r.id)" @close="compareVisible = false"
    />

    <!-- 性能趋势(Task 11):仅 run 来源按脚本@设备分组,内部自拉筛选数据 -->
    <PerfTrendDialog v-if="trendVisible" :project-id="projectId" @close="trendVisible = false" />

    <!-- 手动导入向导(计划14 Task10):成功后由 onImported 刷新列表 -->
    <PerfImportDialog
      v-if="importVisible" :project-id="projectId"
      @close="importVisible = false" @imported="onImported"
    />
  </div>
</template>

<style scoped>
.perf-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}
.toolbar {
  align-items: center;
  display: flex;
  gap: 8px;
}
.pane-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.source-select {
  width: 150px;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.detail-toolbar {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 8px;
}
.detail-meta {
  color: var(--el-text-color-regular);
  font-size: 12px;
}
.section-title {
  margin: 12px 0 6px;
}
</style>
