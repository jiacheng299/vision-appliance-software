<script setup lang="ts">
import SharedRegionEditor from '../../shared/media/RegionEditor.vue'
import type { Region } from './api'
import type { Source } from '../../shared/api/types'
defineProps<{ regions: Region[]; source?: Source; disabled?: boolean; demo?: boolean }>()
const emit = defineEmits<{ change: [regions: Region[]]; pending: [pending: boolean] }>()
</script>
<template><SharedRegionEditor v-bind="$props" @change="emit('change',$event)" @pending="emit('pending',$event)"/></template>
