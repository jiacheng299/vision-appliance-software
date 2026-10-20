<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NPopover, NTooltip, zhCN, dateZhCN } from 'naive-ui'
import { navigation } from './navigation'
import Icon from '../shared/ui/Icon.vue'
const router=useRouter(),mobile=ref(false),search=ref('')
const theme={common:{primaryColor:'#2367ed',primaryColorHover:'#397bf1',primaryColorPressed:'#1857ce',borderRadius:'5px',fontSize:'13px',fontFamily:'"Microsoft YaHei", "PingFang SC", system-ui, sans-serif',textColorBase:'#17233b',borderColor:'#e6edf5'}}
function searchSources(){void router.push({path:'/sources',query:search.value?{q:search.value}:{}});mobile.value=false}
function keyboard(event:KeyboardEvent){if((event.ctrlKey||event.metaKey)&&event.key==='k'){event.preventDefault();document.querySelector<HTMLInputElement>('.global-search input')?.focus()}}
onMounted(()=>{window.addEventListener('keydown',keyboard)})
onUnmounted(()=>{window.removeEventListener('keydown',keyboard)})
</script>
<template><NConfigProvider :theme-overrides="theme" :locale="zhCN" :date-locale="dateZhCN"><NMessageProvider><div class="app-shell"><div class="scrim" :class="{visible:mobile}" @click="mobile=false"/><aside class="sidebar" :class="{open:mobile}" aria-label="主导航"><RouterLink to="/dashboard" class="brand"><span class="brand-mark"/>视觉监测验证</RouterLink><nav class="nav-list"><template v-for="item in navigation" :key="item.label"><NTooltip v-if="item.disabled" trigger="hover"><template #trigger><span><button class="nav-entry" disabled><Icon :name="item.icon"/>{{item.label}}<span class="later">稍后</span></button></span></template>此模块将在后续版本接入</NTooltip><RouterLink v-else :to="item.path!" class="nav-entry" @click="mobile=false"><Icon :name="item.icon"/>{{item.label}}</RouterLink></template></nav><div class="sidebar-foot"><span><span class="dot"/>本地部署工作空间</span><div>基础版本 · 视觉验证平台</div></div></aside><header class="topbar"><button class="icon-button mobile-toggle" aria-label="展开导航" @click="mobile=!mobile"><Icon name="menu"/></button><form class="global-search" @submit.prevent="searchSources"><Icon name="search" :size="17"/><input v-model="search" aria-label="搜索视频源" placeholder="搜索视频源名称或地址…"/><kbd>Ctrl K</kbd></form><div class="top-actions"><NPopover trigger="click" placement="bottom-end"><template #trigger><button class="icon-button" aria-label="通知"><Icon name="bell"/></button></template><div style="width:245px;padding:8px"><strong>工作空间通知</strong><p style="font-size:12px;color:#78859a;margin-top:8px">当前没有新的通知。事件记录请在快速监控看板查看。</p></div></NPopover></div></header><main class="workspace"><RouterView/></main></div></NMessageProvider></NConfigProvider></template>
