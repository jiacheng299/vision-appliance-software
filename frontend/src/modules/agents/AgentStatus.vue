<script setup lang="ts">
import { computed } from 'vue'
import { label } from './state'
const props=defineProps<{value:string}>()
const tone=computed(()=>['running','ready','succeeded','correct','published'].includes(props.value)?'good':['failed','partial_failed','false_positive','missing','expired'].includes(props.value)?'bad':['queued','starting','stopping','reconnecting','pending','unknown'].includes(props.value)?'warn':'')
</script>
<template><span class="status" :class="tone"><span class="dot"/>{{label(value)}}</span></template>
