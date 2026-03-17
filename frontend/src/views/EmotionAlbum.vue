<template>
  <div class="emotion-album min-h-screen bg-black text-white p-6 md:p-12">
    <!-- 头部极简导航 -->
    <header class="flex items-center justify-between mb-10">
      <div class="flex items-center gap-4">
        <button 
          @click="goBack"
          class="w-14 h-14 rounded-full bg-gray-800 hover:bg-gray-700 flex items-center justify-center transition-colors"
        >
          <span class="text-3xl">🔙</span>
        </button>
        <h1 class="text-4xl md:text-5xl font-extrabold bg-gradient-to-r from-pink-400 to-orange-400 bg-clip-text text-transparent">
          家庭情感相册
        </h1>
      </div>
    </header>

    <!-- 骨架屏加载 -->
    <div v-if="loading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div v-for="i in 6" :key="i" class="bg-gray-800 animate-pulse rounded-3xl aspect-[4/3] w-full"></div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="assets.length === 0" class="flex flex-col items-center justify-center mt-32 text-center">
      <span class="text-8xl mb-6">📷</span>
      <h2 class="text-3xl font-bold text-gray-300 mb-4">还没捕捉到家人的笑脸</h2>
      <p class="text-xl text-gray-500">AI 正在后台留意家里的温馨瞬间，晚点再来看看吧</p>
    </div>

    <!-- 瀑布流高光展示 -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      <div 
        v-for="asset in assets" 
        :key="asset.id"
        class="group relative aspect-[4/3] rounded-3xl overflow-hidden bg-gray-900 border border-gray-800 hover:border-pink-500 transition-colors shadow-xl"
      >
        <!-- 使用本地开发代理加载真实静态资源 -->
        <img 
          :src="`/media${asset.file_path}`" 
          @error="handleImageError"
          class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
          alt="Family Highlight"
        />
        
        <!-- 底部渐变半透明信息层 -->
        <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent p-6 pt-12">
          <p class="text-gray-300 text-sm mb-2 font-medium">
            {{ formatDate(asset.created_at) }}
          </p>
          <div class="flex flex-wrap gap-2">
            <span 
              v-for="(tag, idx) in asset.ai_tags.filter((t: string) => ['微笑', '奔跑', '聚餐', '婴儿'].includes(t))"
              :key="idx"
              class="px-3 py-1 bg-pink-500/20 text-pink-300 rounded-full text-xs font-bold border border-pink-500/30 backdrop-blur-sm"
            >
              {{ tag }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';

const router = useRouter();
const loading = ref(true);
const assets = ref<any[]>([]);

onMounted(async () => {
    try {
        // 请求刚才开放的情感相册专用端点
        const apiBase = import.meta.env.VITE_API_BASE || '/api/v1';
        const res = await axios.get(`${apiBase}/search/emotion`, {
            headers: {
                Authorization: `Bearer ${localStorage.getItem('zen70-token')}`
            }
        });
        assets.value = res.data.results || [];
    } catch (err) {
        console.error("加载情感相册失败", err);
    } finally {
        loading.value = false;
    }
});

const goBack = () => {
    router.back();
};

const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
};

// 后备图片，防止开发时没有真实挂载卷导致裂图
const handleImageError = (e: Event) => {
    const target = e.target as HTMLImageElement;
    target.src = 'https://images.unsplash.com/photo-1542037104857-ffbb0b915525?q=80&w=1600&auto=format&fit=crop';
};
</script>
