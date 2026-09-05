<template>
  <div class="tab-bar">
    <div
      v-for="t in tabs"
      :key="t.key"
      class="tab-pill"
      :class="{ active: t.key === activeKey }"
      @click="emit('select', t.key)"
    >
      <span class="tab-name">{{ t.name }}</span>
      <span v-if="t.id !== undefined" class="tab-close" @click.stop="emit('close', t.key)">×</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTabs } from '../../composables/useTabs'

defineProps<{ activeKey: string }>()
const emit = defineEmits<{ (e: 'select', key: string): void; (e: 'close', key: string): void }>()
const { tabs } = useTabs()
</script>

<style scoped>
.tab-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 0;
}
.tab-pill {
  align-items: center;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--pro-line);
  border-radius: 999px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  display: flex;
  font-size: 12px;
  gap: 6px;
  padding: 4px 12px;
  user-select: none;
}
.tab-pill.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}
.tab-close {
  border-radius: 50%;
  font-size: 14px;
  line-height: 1;
  padding: 1px 3px;
}
.tab-close:hover {
  background: rgba(255, 255, 255, 0.35);
}
.tab-pill:not(.active) .tab-close:hover {
  background: var(--el-border-color);
}
</style>
