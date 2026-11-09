<script setup lang="ts">
import { computed } from 'vue'
import type { Runtime } from '../../shared/api/types'
import Icon from '../../shared/ui/Icon.vue'

const props = defineProps<{ status?: Runtime['trust_check_status'] }>()
const states = {
  active: { label: '已开启', tone: 'good', message: '在任务的「画面与报警」中展开可信检查，查看近期诊断。' },
  disabled: { label: '已关闭', tone: '', message: '可在工作台配置中启用，保存后重启服务。' },
  unavailable: { label: '暂不可用', tone: 'warn', message: '请核对真实 YOLO 运行时和服务日志。' },
  write_failed: { label: '写入异常', tone: 'bad', message: '请检查工作台日志目录的可写状态。' },
  waiting: { label: '待确认', tone: '', message: '等待服务返回可信检查状态。' },
}
const state = computed(() => states[props.status ?? 'waiting'] ?? states.waiting)
</script>

<template>
  <section class="panel trust-card" aria-label="可信检查">
    <div class="stat-icon green"><Icon name="shield"/></div>
    <div class="trust-card-copy">
      <h2>可信检查</h2>
      <p>诊断采样间断、检测波动和报警证据异常</p>
      <small>{{ state.message }}</small>
    </div>
    <span class="status" :class="state.tone">{{ state.label }}</span>
  </section>
</template>

<style scoped>
.trust-card { display: flex; align-items: center; gap: 14px; margin: 18px 0; }
.trust-card .stat-icon { flex: 0 0 40px; height: 40px; margin: 0; }
.trust-card-copy { flex: 1; min-width: 0; }
.trust-card-copy p { margin: 4px 0; }
.trust-card .status { white-space: nowrap; }
</style>
