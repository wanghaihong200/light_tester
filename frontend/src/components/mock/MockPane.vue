<template>
  <!-- 计划13 T8 占位壳:仅为让 mock/http 路由的懒加载 import 可解析(vite 静态分析要求组件文件存在);
       完整的实例列表/规则/命中面板由 T9 的 MockPane 全量替换本文件 -->
  <section class="mock-pane">
    <h2>HTTP Mock</h2>
    <p>接口Mock 面板建设中(计划 13 T9 交付)</p>
  </section>
</template>

<script setup lang="ts">
// T8 路由占位:projectId 由 T9 的 MockPane 经 useRoute().params.id 自取(模式同 WebAutoPane)
</script>

<style scoped>
.mock-pane {
  padding: 16px;
}
.mock-pane h2 {
  font-size: 16px;
  margin: 0 0 8px;
}
</style>
