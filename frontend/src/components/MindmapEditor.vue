<template>
  <div ref="containerRef" class="mindmap-container"></div>
</template>

<script setup lang="ts">
import MindMap from 'simple-mind-map'
import 'simple-mind-map/dist/simpleMindMap.esm.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { MindmapNode, NodeType } from '../adapters/tree'

const props = defineProps<{ data: MindmapNode | null }>()
const emit = defineEmits<{ (e: 'nodeActive', payload: { nodeType: NodeType; refId?: number }): void }>()

const containerRef = ref<HTMLElement>()
let mindMap: MindMap | null = null
let resizeObserver: ResizeObserver | null = null

const EMPTY: MindmapNode = { data: { text: '(空项目,请先添加模块)', uid: 'root-empty', nodeType: 'root' }, children: [] }

function hasSize(el: HTMLElement | undefined): boolean {
  return !!el && el.offsetWidth > 0 && el.offsetHeight > 0
}

// 幂等初始化:容器有真实尺寸才构造(simple-mind-map 对 0 尺寸容器直接抛错,
// 且错误发生在 mounted(post-flush)会中断 Vue 调度器,整页交互失效)
function initMindMap() {
  if (mindMap || !containerRef.value) return
  mindMap = new MindMap({
    el: containerRef.value,
    data: props.data ?? EMPTY,
    layout: 'logicalStructure',
    theme: 'default',
    // 编辑一律走右侧表单,禁用画布双击编辑与键盘进入编辑
    disableDBClickTapNode: true,
    enableAutoEnterTextEditWhenKeydown: false,
  })
  // 订阅 node_click 而非 node_active:抽屉关闭后节点仍是激活态,再点同一节点
  // 不会重新触发 node_active,会导致编辑抽屉无法再次打开(冒烟问题 1)
  mindMap.on('node_click', (node: { getData: (key: string) => unknown }) => {
    const nodeType = node.getData('nodeType') as NodeType | undefined
    if (!nodeType) return
    if (nodeType === 'root') emit('nodeActive', { nodeType: 'root' })
    else emit('nodeActive', { nodeType, refId: node.getData('refId') as number | undefined })
  })
}

onMounted(() => {
  if (hasSize(containerRef.value)) {
    initMindMap()
    return
  }
  // 隐藏 tab(display:none)下挂载:等容器显示出来再初始化。
  // 不可用 nextTick/重试猜时序——pane 显示与重挂是两条异步更新链(暂存入库后
  // 切 tab 的真实缺陷);ResizeObserver 由浏览器保证"显示必然触发"
  resizeObserver = new ResizeObserver(() => {
    if (hasSize(containerRef.value)) {
      resizeObserver?.disconnect()
      resizeObserver = null
      initMindMap()
    }
  })
  resizeObserver.observe(containerRef.value!)
})

watch(
  () => props.data,
  (d) => {
    if (mindMap && d) mindMap.setData(d)
  },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  mindMap?.destroy()
  mindMap = null
})
</script>

<style scoped>
.mindmap-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
/* simple-mind-map 官方要求:清零容器内元素默认边距 */
.mindmap-container :deep(*) {
  margin: 0;
  padding: 0;
}
</style>
