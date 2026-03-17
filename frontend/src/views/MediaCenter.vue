<template>
  <div class="max-w-6xl mx-auto py-8 px-4">
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
      <div>
        <h2 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-500 to-fuchsia-500">
          家庭媒体中心
        </h2>
        <p class="text-sm text-base-content/70 mt-1">由 Jellyfin 流媒体引擎驱动｜GPU 硬解码｜BFF 角色视界折叠</p>
      </div>
      <div class="badge badge-lg" :class="statusBadge">
        {{ statusText }}
      </div>
    </div>

    <!-- 引擎离线状态 -->
    <div v-if="status === 'offline'" class="text-center py-24 bg-base-200 rounded-2xl shadow-inner border-2 border-base-300">
      <div class="text-6xl mb-4 opacity-50">📡</div>
      <h3 class="text-xl font-medium text-base-content/80">流媒体引擎离线</h3>
      <p class="text-sm text-base-content/50 mt-2">请检查存储介质是否接入，并在控制台启动 Jellyfin 容器。</p>
    </div>

    <!-- 加载中 -->
    <div v-else-if="loading" class="flex justify-center py-20">
      <span class="loading loading-spinner text-primary loading-lg"></span>
    </div>

    <!-- 媒体库卡片 -->
    <div v-else-if="libraries.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="lib in libraries"
        :key="lib.id"
        class="card bg-base-100 shadow-xl border border-base-200 hover:shadow-2xl hover:scale-[1.02] transition-all cursor-pointer"
        @click="openLibrary(lib)"
      >
        <div class="card-body">
          <div class="flex items-center gap-3">
            <span class="text-3xl">{{ getLibIcon(lib.type) }}</span>
            <div>
              <h3 class="card-title text-lg">{{ lib.name }}</h3>
              <p class="text-xs text-base-content/50">{{ lib.type }}</p>
            </div>
          </div>
          <div class="mt-4 text-xs text-base-content/40">
            {{ lib.locations.length }} 个存储路径
          </div>
        </div>
      </div>
    </div>

    <!-- 空媒体库 -->
    <div v-else class="text-center py-24 bg-base-200 rounded-2xl shadow-inner border-2 border-base-300">
      <div class="text-6xl mb-4 opacity-50">🎬</div>
      <h3 class="text-xl font-medium text-base-content/80">暂无可见的媒体库</h3>
      <p class="text-sm text-base-content/50 mt-2">管理员需在 Jellyfin 控制台创建媒体库后才能在此展示。</p>
    </div>

    <!-- 转码引擎状态 -->
    <div class="mt-8 p-4 bg-base-200 rounded-xl" v-if="transcodeStatus">
      <div class="flex items-center gap-3">
        <span class="text-xl">{{ transcodeStatus.engine === 'hardware' ? '⚡' : '🐢' }}</span>
        <div>
          <p class="text-sm font-medium">{{ transcodeStatus.hint }}</p>
          <p class="text-xs text-base-content/50" v-if="transcodeStatus.cpu_utilization !== undefined">
            CPU 负载: {{ (transcodeStatus.cpu_utilization * 100).toFixed(0) }}%
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';

const authStore = useAuthStore();
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

const status = ref<'loading' | 'online' | 'offline'>('loading');
const loading = ref(true);
const libraries = ref<any[]>([]);
const transcodeStatus = ref<any>(null);

const statusText = computed(() => {
  if (status.value === 'online') return '引擎在线';
  if (status.value === 'offline') return '引擎离线';
  return '检测中...';
});

const statusBadge = computed(() => {
  if (status.value === 'online') return 'badge-success';
  if (status.value === 'offline') return 'badge-error';
  return 'badge-warning';
});

function getLibIcon(type: string) {
  const icons: Record<string, string> = {
    movies: '🎬',
    tvshows: '📺',
    music: '🎵',
    books: '📚',
    photos: '📷',
  };
  return icons[type] || '📁';
}

async function authFetch(url: string, options: RequestInit = {}) {
  const token = authStore.token;
  if (!token) throw new Error('Unauthorized');
  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });
}

async function fetchStatus() {
  try {
    const res = await authFetch('/v1/media/status');
    const data = await res.json();
    status.value = data.status === 'online' ? 'online' : 'offline';
  } catch {
    status.value = 'offline';
  }
}

async function fetchLibraries() {
  loading.value = true;
  try {
    const res = await authFetch('/v1/media/libraries');
    if (res.ok) {
      const data = await res.json();
      libraries.value = data.data || [];
    }
  } catch (err) {
    console.error('Failed to load libraries', err);
  } finally {
    loading.value = false;
  }
}

async function fetchTranscodeHint() {
  try {
    const res = await authFetch('/v1/media/transcode/hint', { method: 'POST' });
    if (res.ok) {
      transcodeStatus.value = await res.json();
    }
  } catch {
    // 静默失败
  }
}

function openLibrary(lib: any) {
  // 直接打开 Jellyfin Web UI 对应的库页面
  window.open(`/jellyfin/web/index.html#!/library?parentId=${lib.id}`, '_blank');
}

onMounted(async () => {
  await fetchStatus();
  if (status.value === 'online') {
    await Promise.all([fetchLibraries(), fetchTranscodeHint()]);
  } else {
    loading.value = false;
  }
});
</script>
