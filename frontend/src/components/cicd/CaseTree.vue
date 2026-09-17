<!-- frontend/src/components/cicd/CaseTree.vue -->
<!-- 用例树(IDEA 运行器风格):类分组 → 方法分组(数据驱动重名合并) → 子用例;
     含失败/未执行行的类默认展开,叶子点击 emit('locate') 供日志定位。 -->
<template>
  <div class="case-tree">
    <div v-for="g in groups" :key="g.key" class="cls">
      <div class="row" @click="toggle(g.key)">
        <span class="chev">{{ expanded.has(g.key) ? '▾' : '▸' }}</span>
        <span class="ic" :class="g.status">{{ ICON[g.status] ?? '·' }}</span>
        <span class="name" :title="g.fullName">{{ g.label }}</span>
        <span class="msg"></span>
        <span class="time">{{ fmtTime(g.time) }}</span>
      </div>
      <template v-if="expanded.has(g.key)">
        <template v-for="m in g.methods" :key="m.key">
          <div class="row indent1" @click="toggle(m.key)">
            <span class="chev">{{ expanded.has(m.key) ? '▾' : '▸' }}</span>
            <span class="ic" :class="m.status">{{ ICON[m.status] ?? '·' }}</span>
            <span class="name" :title="m.label">{{ m.label }}</span>
            <span class="msg"></span>
            <span class="time">{{ fmtTime(m.time) }}</span>
          </div>
          <template v-if="expanded.has(m.key)">
            <div v-for="leaf in m.leaves" :key="leaf.key" class="row indent2 leaf"
                 :title="leaf.row.message ?? ''" @click.stop="emit('locate', leaf.row)">
              <span class="chev spacer"></span>
              <span class="ic" :class="leaf.row.status">{{ ICON[leaf.row.status] ?? '·' }}</span>
              <span class="name">{{ leaf.row.name }}</span>
              <span class="msg">{{ leaf.row.message }}</span>
              <span class="time">{{ fmtTime(leaf.row.time_s) }}</span>
            </div>
          </template>
        </template>
      </template>
    </div>
    <div v-if="!groups.length" class="empty">暂无用例数据</div>
  </div>
</template>

<script lang="ts">
import type { CiCaseRow } from '../../api/cicd'

// 报告行 = JUnit 产物行 + 快照未执行行(skipped_note 标注);script setup 不能 export,类型放本块
export type CaseRow = CiCaseRow & { skipped_note?: boolean }
</script>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

const props = defineProps<{ rows: CaseRow[] }>()
const emit = defineEmits<{ (e: 'locate', row: CaseRow): void }>()

const ICON: Record<string, string> = { passed: '✓', failed: '✕', skipped: '⊘', not_run: '⊘' }
// 状态聚合取最差:failed > not_run > skipped > passed
const RANK: Record<string, number> = { passed: 0, skipped: 1, not_run: 2, failed: 3 }

interface Leaf { key: string; row: CaseRow }
interface MethodNode { key: string; label: string; status: string; time: number; leaves: Leaf[] }
interface ClassNode { key: string; label: string; fullName: string; status: string; time: number; methods: MethodNode[] }

function worst(a: string, b: string): string {
  return (RANK[b] ?? 0) > (RANK[a] ?? 0) ? b : a
}

/** 方法组标签:去掉数据驱动后缀 `[参数]` 与 `(序号)` */
function methodBase(name: string): string {
  const base = name.replace(/\[[^\]]*\]/g, '').replace(/\(\d+\)\s*$/, '').trim()
  return base || name
}

const groups = computed<ClassNode[]>(() => {
  const out: ClassNode[] = []
  const byClass = new Map<string, ClassNode>()
  for (const row of props.rows) {
    const cls = row.class_name || '(未分类)'
    let c = byClass.get(cls)
    if (!c) {
      c = { key: `c:${cls}`, label: cls.split('.').pop() ?? cls, fullName: cls,
            status: 'passed', time: 0, methods: [] }
      byClass.set(cls, c)
      out.push(c)
    }
    c.status = worst(c.status, row.status)
    c.time += row.time_s
    const base = methodBase(row.name)
    let m = c.methods.find((x) => x.label === base)
    if (!m) {
      m = { key: `${c.key}|m:${base}`, label: base, status: 'passed', time: 0, leaves: [] }
      c.methods.push(m)
    }
    m.status = worst(m.status, row.status)
    m.time += row.time_s
    m.leaves.push({ key: `${m.key}|${row.name}|${m.leaves.length}`, row })
  }
  return out
})

const expanded = reactive(new Set<string>())

// 数据整体替换(拉取/终态刷新)时重置展开态:含失败或未执行的类默认展开,
// 其内含失败/未执行的方法组也展开;全通过的类/方法默认收起
watch(() => props.rows, (rows) => {
  expanded.clear()
  for (const g of groups.value) {
    if (g.status === 'passed') continue
    expanded.add(g.key)
    for (const m of g.methods) {
      if (m.status !== 'passed') expanded.add(m.key)
    }
  }
  void rows
}, { immediate: true })

function toggle(key: string): void {
  if (expanded.has(key)) expanded.delete(key)
  else expanded.add(key)
}

function fmtTime(t: number): string {
  if (!t) return '-'
  return t < 1 ? `${Math.round(t * 1000)} 毫秒` : `${t.toFixed(2)} 秒`
}
</script>

<style scoped>
.case-tree { font-size: 13px; }
.row {
  align-items: center; border-radius: 4px; cursor: default; display: flex;
  gap: 6px; line-height: 24px; padding: 0 8px;
}
.row.indent1 { padding-left: 24px; }
.row.indent2 { padding-left: 40px; }
.row.leaf { cursor: pointer; }
.row.leaf:hover { background: var(--el-fill-color-light); }
.chev { color: var(--pro-muted); cursor: pointer; flex: 0 0 12px; text-align: center; }
.chev.spacer { visibility: hidden; }
.ic { flex: 0 0 16px; text-align: center; }
.ic.passed { color: var(--el-color-success); }
.ic.failed { color: var(--el-color-danger); font-weight: 700; }
.ic.skipped, .ic.not_run { color: var(--el-color-info); }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg {
  color: var(--el-text-color-secondary); flex: 1 1 auto; font-size: 12px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.time { color: var(--pro-muted); flex: 0 0 auto; font-size: 12px; }
.empty { color: var(--pro-muted); padding: 12px; text-align: center; }
</style>
