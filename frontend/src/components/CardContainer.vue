<template>
  <div v-if="loading && isEmpty" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
    <SkeletonCard v-for="i in 6" :key="i" />
  </div>
  <div v-else-if="error && isEmpty" class="alert alert-warning m-4">
    <span>{{ error }}</span>
    <button class="btn btn-sm" @click="refresh">重试</button>
  </div>
  <div v-else class="p-4">
    <div v-if="capsStore.isOffline && !isEmpty" class="alert alert-info mb-4">
      <span>离线模式，数据可能不是最新</span>
    </div>
    <div v-else-if="isEmpty" class="alert alert-warning m-4">
      <span>暂无能力数据，请确保后端服务已启动并联网后刷新</span>
      <button class="btn btn-sm" @click="refresh">刷新</button>
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    <div
      v-for="(cap, name) in caps"
      :key="name"
      class="card bg-base-200 shadow-xl relative overflow-hidden transition-all duration-300 transform"
    >
      <!-- 离线或维护屏蔽遮罩层 (法典 6.2.1 情绪隔离与物理锁定) -->
      <div 
        v-if="cap.status === 'offline' || capsStore.isOffline" 
        class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-base-100/40 backdrop-blur-[4px] pointer-events-none"
      >
        <span class="text-lg font-bold select-none text-base-content/80 drop-shadow-md tracking-wider">
          设备维护中
        </span>
      </div>

      <div class="card-body" :class="{ 'opacity-50 pointer-events-none': cap.status === 'offline' || capsStore.isOffline }">
        <h2 class="card-title flex items-center gap-2">
          {{ name }}
          <span
            :class="STATUS_CLASS[cap.status] || 'badge-warning'"
            class="badge badge-sm"
          >
            {{ cap.status }}
          </span>
        </h2>
        <p class="text-sm text-base-content/80">端点: {{ cap.endpoint || "-" }}</p>
        <p v-if="cap.models?.length" class="text-sm">模型: {{ cap.models.join(", ") }}</p>
        <p v-if="cap.reason" class="text-sm text-warning">{{ cap.reason }}</p>
        <div class="card-actions justify-end mt-2">
          <SwitchItem :service-name="String(name)" :cap="cap" @toggle="onToggle" />
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useCapabilitiesStore } from "@/stores/capabilities";
import SwitchItem from "./SwitchItem.vue";
import SkeletonCard from "./SkeletonCard.vue";

const capsStore = useCapabilitiesStore();
const caps = computed(() => capsStore.caps);
const loading = computed(() => capsStore.loading);
const error = computed(() => capsStore.error);
const isEmpty = computed(() => Object.keys(caps.value).length === 0);

function refresh() {
  capsStore.fetchCapabilities();
}

const STATUS_CLASS: Record<string, string> = {
  online: "badge-success",
  offline: "badge-error",
  unknown: "badge-warning",
};

function onToggle(name: string) {
  console.log("[ZEN70] toggle switch (placeholder)", name);
  // 后续实现 POST /api/v1/switches/:name
}
</script>
