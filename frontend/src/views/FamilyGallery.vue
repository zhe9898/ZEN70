<template>
  <div class="max-w-6xl mx-auto py-8 px-4 relative min-h-screen">
    <div class="flex flex-col mb-8 text-center sm:text-left">
      <h2 class="text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary drop-shadow-sm">
        数字极客相册 
        <span class="text-sm font-normal text-base-content/50 inline-block align-middle ml-2 tracking-normal">
          (RLS 租户隔离)
        </span>
      </h2>
      <p class="text-sm text-base-content/60 mt-2 font-light">您的专属数据金库。AI 通过跨模态理解能力，让您能随时追溯这些光阴。</p>
      
      <!-- 隐藏上传器 -->
      <input type="file" ref="fileInput" class="hidden" accept="image/*,video/*" @change="uploadAsset" />
    </div>
    
    <!-- AI 语义联邦搜索入口 (M9.3) -->
    <!-- AI 语义联邦搜索入口 (M9.3) -->
    <div class="mb-6 relative z-10 w-full max-w-2xl mx-auto">
      <div class="join w-full shadow-xl shadow-primary/5 rounded-full overflow-hidden">
        <input 
          v-model="searchQuery" 
          @keyup.enter="performSemanticSearch"
          type="text" 
          placeholder="✨ 试试对 AI 说：一条红色的狗在草地上跑..." 
          class="input input-bordered border-none focus:outline-none focus:ring-0 join-item w-full bg-base-100/80 backdrop-blur-md text-base-content placeholder:opacity-40" 
        />
        <button class="btn btn-primary join-item px-8 border-none" @click="performSemanticSearch" :disabled="searching">
          <span v-if="searching" class="loading loading-spinner loading-xs"></span>
          <span v-else>追溯</span>
        </button>
        <button v-if="isSearchMode" class="btn btn-ghost join-item border-none bg-base-100/80 backdrop-blur-md" @click="clearSearch">
          重置
        </button>
      </div>
    </div>
    
    <!-- 智能相册分类 Tabs (M10.3) -->
    <div class="flex justify-center mb-8">
      <div class="tabs tabs-boxed bg-base-200/50 backdrop-blur-sm p-1">
        <a class="tab transition-all duration-300" :class="{'tab-active text-primary font-medium shadow-sm bg-base-100': activeTab==='all'}" @click="setTab('all')">所有回忆</a>
        <a class="tab transition-all duration-300" :class="{'tab-active text-primary font-medium shadow-sm bg-base-100': activeTab==='video'}" @click="setTab('video')">🎬 视频时光</a>
        <a class="tab transition-all duration-300" :class="{'tab-active text-primary font-medium shadow-sm bg-base-100': activeTab==='emotion'}" @click="setTab('emotion')">✨ 高光时刻</a>
      </div>
    </div>
    
    <div v-if="loading" class="flex justify-center py-20 min-h-[50vh]">
      <span class="loading loading-ring text-primary w-16"></span>
    </div>
    
    <div v-else-if="filteredAssets.length === 0" class="text-center py-24 bg-base-100/40 backdrop-blur-xl rounded-3xl border border-base-200/50">
      <div class="text-6xl mb-6 opacity-40">👻</div>
      <h3 class="text-xl font-medium text-base-content/70">当前分类域内，没有任何文件</h3>
      <p class="text-sm text-base-content/40 mt-2">点击右下角的加号，上传一张全家福吧。</p>
    </div>
    
    <!-- M10.1 极简悬浮瀑布流布局 (Masonry Flex/Columns) -->
    <div v-else class="columns-2 sm:columns-3 md:columns-4 gap-4 space-y-4 pb-24">
      <div 
        v-for="asset in filteredAssets" 
        :key="asset.id" 
        class="break-inside-avoid relative group rounded-2xl overflow-hidden shadow-sm hover:shadow-2xl transition-all duration-500 bg-base-100/80 backdrop-blur aspect-auto flex flex-col items-center justify-center border border-white/5 cursor-pointer transform hover:-translate-y-1"
      >
        <!-- 悬浮顶部操作栏：删除 / 下载 / 设为壁纸 (M10.3) -->
        <div class="absolute top-0 left-0 right-0 p-3 bg-gradient-to-b from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-between z-20">
          <div class="flex gap-2">
            <a filter="download" :download="asset.original_filename" title="下载原片" :href="API_BASE + asset.file_path" @click.stop=""
               class="btn btn-xs btn-circle btn-ghost text-white hover:bg-white/20">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
            </a>
            <button @click.stop="setWallpaper(asset.file_path)" class="btn btn-xs btn-circle btn-ghost text-white hover:bg-white/20" title="设为全局壁纸">🖼️</button>
          </div>
          <button 
            @click.stop="deleteAsset(asset.id)"
            class="btn btn-xs btn-circle btn-error text-white shadow"
            title="永久物理删除"
          >✕</button>
        </div>

        <!-- 卡片主体占位 (如果有真实图片 url 可以替换为 img src) -->
        <div class="w-full h-48 bg-base-300/30 flex items-center justify-center text-6xl opacity-60 relative">
          {{ asset.asset_type === 'video' ? '🎬' : '🖼️' }}
          <div v-if="asset.is_emotion_highlight" class="absolute bottom-2 right-2 text-xl" title="高光情绪瞬间">✨</div>
        </div>

        <!-- 悬浮底部信息玻璃带 (M10.1) -->
        <div class="absolute bottom-0 left-0 right-0 p-3 bg-base-100/90 backdrop-blur-md opacity-0 group-hover:opacity-100 transition-opacity duration-300 translate-y-2 group-hover:translate-y-0 text-center">
          <p class="text-xs font-semibold text-base-content truncate px-1" :title="asset.original_filename">{{ asset.original_filename }}</p>
          <div class="flex justify-between w-full mt-1.5 opacity-50 px-1">
            <span class="text-[10px]">{{ formatSize(asset.file_size_bytes) }}</span>
            <span class="text-[10px]">{{ formatTime(asset.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- M10.3 FAB (Floating Action Button) -->
    <button @click="triggerUpload" class="btn btn-primary btn-circle btn-lg fixed bottom-8 right-8 shadow-2xl z-50 hover:scale-110 transition-transform">
      <span v-if="uploading" class="loading loading-spinner"></span>
      <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { http } from '@/utils/http';
import { useThemeStore } from '@/stores/theme';

const themeStore = useThemeStore();

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

const assets = ref<any[]>([]);
const loading = ref(true);
const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

// M10.3 分类相册 Tabs
const activeTab = ref<'all' | 'video' | 'emotion'>('all');

const filteredAssets = computed(() => {
  if (activeTab.value === 'all') return assets.value;
  if (activeTab.value === 'video') return assets.value.filter(a => a.asset_type === 'video');
  if (activeTab.value === 'emotion') return assets.value; // Emotion assets already filtered correctly by the API
  return assets.value;
});

// M9.3 智能查询状态
const searchQuery = ref("");
const searching = ref(false);
const isSearchMode = ref(false);

function setTab(tab: 'all' | 'video' | 'emotion') {
  activeTab.value = tab;
  fetchAssets();
}

function setWallpaper(filePath: string) {
  themeStore.setCustomWallpaper(API_BASE + filePath);
  alert("已设为全局高斯模糊壁纸！");
}

function triggerUpload() {
  if (fileInput.value) {
    fileInput.value.click();
  }
}

function formatTime(iso: string) {
  const date = new Date(iso);
  return `${date.getMonth() + 1}-${date.getDate()}`;
}

function formatSize(bytes: number) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

async function fetchAssets() {
  loading.value = true;
  isSearchMode.value = false;
  try {
    let url = '/v1/assets';
    if (activeTab.value === 'emotion') {
      url = '/v1/search/emotion';
    }
    const res = await http.get(url);
    assets.value = res.data.data || res.data.results || [];
  } catch (err) {
    console.error("Failed to load assets", err);
  } finally {
    loading.value = false;
  }
}

async function performSemanticSearch() {
  if (!searchQuery.value.trim()) {
    return fetchAssets();
  }
  
  searching.value = true;
  isSearchMode.value = true;
  
  try {
    const res = await http.get('/v1/search/semantic', { 
      params: { q: searchQuery.value, limit: 20 }
    });
    // 抹平 API 响应差异
    assets.value = res.data.results || [];
  } catch (err: any) {
    console.error("Search error", err);
    alert("请求失败: " + (err.response?.data?.error || "服务暂不可用"));
  } finally {
    searching.value = false;
  }
}

function clearSearch() {
  searchQuery.value = "";
  fetchAssets();
}

async function uploadAsset(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  
  uploading.value = true;
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    await http.post('/v1/assets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    await fetchAssets();
  } catch(err: any) {
    alert("上传失败: " + (err.response?.data?.detail || "网络异常"));
  } finally {
    uploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

async function deleteAsset(id: string) {
  if (!confirm("确认彻底删除极客相册中的此段回忆吗？物理删除不可恢复！")) {
    return;
  }
  
  try {
    await http.delete(`/v1/assets/${id}`);
    assets.value = assets.value.filter(a => a.id !== id);
  } catch (err: any) {
    alert("删除失败: " + (err.response?.data?.detail?.message || err.response?.data?.detail || "越权操作或文件不存在"));
  }
}

onMounted(() => {
  fetchAssets();
});
</script>
