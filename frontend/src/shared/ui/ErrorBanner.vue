<script setup lang="ts">
import { NButton } from 'naive-ui'
withDefaults(defineProps<{error:string; retryable?:boolean}>(), {retryable:true})
defineEmits<{retry:[]}>()
</script>
<template><div v-if="error" class="error-banner" role="alert"><span>{{error}}</span><NButton v-if="retryable" size="small" secondary type="error" @click="$emit('retry')">重试</NButton></div></template>
