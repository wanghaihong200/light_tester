<template>
  <aside class="side-menu" :class="{ collapsed }">
    <div class="brand" @click="emit('navigate', '/')">
      <img alt="轻测试" class="brand-logo" src="/favicon.gif" />
      <span v-if="!collapsed" class="brand-name">LightTester</span>
    </div>
    <div class="menu-item" :class="{ active: activeKey === 'home' }" @click="emit('navigate', '/')">
      <span class="menu-icon">⌂</span>
      <span v-if="!collapsed" class="menu-name">首页</span>
    </div>
    <!-- 项目态:上下文功能菜单树。分组轴=「AI 是否参与」(ADR-0007);文案见 CONTEXT.md 导航词条,勿改 -->
    <template v-if="projectId !== null">
      <template v-for="item in PROJECT_MENU" :key="item.key">
        <div
          v-if="isLeaf(item)"
          class="menu-item"
          :class="{ active: activeKey === itemKey(item) }"
          :title="collapsed ? item.label : undefined"
          @click="go(item)"
        >
          <span class="menu-icon">{{ item.icon }}</span>
          <span v-if="!collapsed" class="menu-name">{{ item.label }}</span>
        </div>
        <template v-else>
          <div
            class="menu-item menu-group-head"
            :title="collapsed ? item.label : undefined"
            @click="collapsed ? go(item.children[0]) : toggle(item.key)"
          >
            <span class="menu-icon">{{ item.icon }}</span>
            <span v-if="!collapsed" class="menu-name">{{ item.label }}</span>
            <span v-if="!collapsed" class="menu-caret" :class="{ open: expanded.has(item.key) }">▾</span>
          </div>
          <template v-if="!collapsed && expanded.has(item.key)">
            <div
              v-for="c in item.children"
              :key="c.key"
              class="menu-item sub-item"
              :class="{ active: activeKey === itemKey(c) }"
              @click="go(c)"
            >
              <span class="menu-name">{{ c.label }}</span>
            </div>
          </template>
        </template>
      </template>
    </template>
    <div class="menu-spacer" />
  </aside>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface MenuLeaf {
  key: string // 与路由名 project-<key> 对应(cases/knowledge/ai-jobs/ai-repo/ai-cross/ui-web/ui-app)
  label: string
  path: string
  icon?: string
}
interface MenuGroup {
  key: string
  label: string
  icon: string
  children: MenuLeaf[]
}

// 分组轴=「AI 是否参与」:AI 组收纳生成任务/自动化工程/多端 UI 自动化;UI 组收纳 Web/APP 自动化(选择器驱动/SoloPi 驱动)
const PROJECT_MENU: (MenuLeaf | MenuGroup)[] = [
  { key: 'cases', label: '功能用例管理', path: 'cases', icon: '▦' },
  { key: 'knowledge', label: '知识库', path: 'knowledge', icon: '📚' },
  {
    key: 'ai',
    label: 'AI测试',
    icon: '🤖',
    children: [
      { key: 'ai-jobs', label: '生成任务', path: 'ai/jobs' },
      { key: 'ai-repo', label: '自动化工程', path: 'ai/repo' },
      { key: 'ai-cross', label: '多端 UI 自动化', path: 'ai/cross' },
    ],
  },
  {
    key: 'ui',
    label: 'UI自动化',
    icon: '🖱',
    children: [
      { key: 'ui-web', label: 'Web自动化', path: 'ui/web' },
      { key: 'ui-app', label: 'APP自动化', path: 'ui/app' },
    ],
  },
]

const props = defineProps<{ activeKey: string; collapsed: boolean; projectId: number | null }>()
const emit = defineEmits<{ (e: 'navigate', path: string): void }>()

const isLeaf = (item: MenuLeaf | MenuGroup): item is MenuLeaf => !('children' in item)

function itemKey(item: MenuLeaf): string {
  return `project-${props.projectId}:${item.key}`
}

// 组默认全展开;可手动折叠;激活项落进某组时自动展开该组
const expanded = ref(new Set<string>(PROJECT_MENU.filter((i): i is MenuGroup => !isLeaf(i)).map((g) => g.key)))

function toggle(key: string): void {
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

watch(
  () => props.activeKey,
  (k) => {
    const m = k.match(/^project-\d+:(.+)$/)
    if (!m) return
    const group = PROJECT_MENU.find((i): i is MenuGroup => !isLeaf(i) && m[1].startsWith(`${i.key}-`))
    if (group && !expanded.value.has(group.key)) {
      expanded.value = new Set([...expanded.value, group.key])
    }
  },
  { immediate: true },
)

function go(item: MenuLeaf): void {
  emit('navigate', `/projects/${props.projectId}/${item.path}`)
}
</script>

<style scoped>
.side-menu {
  background: var(--pro-sidebar-bg);
  border-right: 1px solid var(--pro-sidebar-border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  padding: 12px 10px;
  transition: width 0.2s ease;
  width: 200px;
  flex-shrink: 0;
}
.side-menu.collapsed {
  width: 65px;
}
.brand {
  align-items: center;
  cursor: pointer;
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding: 4px 8px;
}
.brand-logo {
  border-radius: var(--border-radius-base);
  flex-shrink: 0;
  height: 30px;
  object-fit: cover;
  width: 30px;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
}
.menu-item {
  align-items: center;
  border-radius: var(--border-radius-base);
  color: var(--el-text-color-regular);
  cursor: pointer;
  display: flex;
  gap: 8px;
  margin-bottom: 2px;
  padding: 8px 10px;
  white-space: nowrap;
}
.menu-item:hover {
  background: var(--el-color-primary-light-9);
}
.menu-item.active {
  background: var(--el-color-primary);
  color: #fff;
}
.menu-group-head .menu-name {
  flex: 1;
}
.menu-caret {
  color: var(--pro-muted);
  font-size: 11px;
  transition: transform 0.15s ease;
}
.menu-caret.open {
  transform: rotate(180deg);
}
.sub-item {
  padding-left: 34px;
}
.sub-item .menu-name {
  font-size: 13px;
}
.menu-icon {
  flex-shrink: 0;
  font-size: 13px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  width: 16px;
}
.menu-spacer {
  flex: 1;
}
</style>
