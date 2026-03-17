<template>
  <div class="elderly-dashboard">
    <!-- 极简头部导航 -->
    <header class="navbar flex items-center justify-between p-4 mb-6">
      <div class="flex items-center gap-3">
        <h1 class="text-3xl font-bold bg-gradient-to-r from-teal-400 to-emerald-500 bg-clip-text text-transparent">
          ZEN70 陪伴
        </h1>
      </div>
      <button
        @click="logout"
        class="logout-btn px-6 py-3 rounded-full font-bold text-xl bg-gray-800 hover:bg-red-900 border border-gray-700 transition-colors"
      >
        退出账号
      </button>
    </header>

    <main class="grid grid-cols-1 md:grid-cols-2 gap-8 px-4 max-w-6xl mx-auto">
      
      <!-- 卡片 1: 看孙子 (照片/视频) -->
      <button 
        @click="goToGallery"
        class="action-card flex flex-col items-center justify-center p-12 rounded-3xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 hover:from-teal-900 hover:border-teal-500 transition-all group"
      >
        <div class="icon-wrapper w-32 h-32 mb-8 rounded-full bg-gray-700 flex items-center justify-center group-hover:bg-teal-800 transition-colors">
          <span class="text-6xl">👶</span>
        </div>
        <h2 class="text-5xl font-extrabold text-white mb-4 tracking-wider">看孙子</h2>
        <p class="text-2xl text-gray-400 font-medium">看最新的照片和视频记录</p>
      </button>

      <!-- 卡片 2: 找电影 (流媒体) -->
      <button 
        @click="goToMedia"
        class="action-card flex flex-col items-center justify-center p-12 rounded-3xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 hover:from-purple-900 hover:border-purple-500 transition-all group"
      >
        <div class="icon-wrapper w-32 h-32 mb-8 rounded-full bg-gray-700 flex items-center justify-center group-hover:bg-purple-800 transition-colors">
          <span class="text-6xl">🎬</span>
        </div>
        <h2 class="text-5xl font-extrabold text-white mb-4 tracking-wider">看电视</h2>
        <p class="text-2xl text-gray-400 font-medium">打开家庭专属影院</p>
      </button>

      <!-- 卡片 3: AI 语音管家 -->
      <button 
        @click="triggerVoice"
        class="action-card flex flex-col items-center justify-center p-12 rounded-3xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 hover:from-blue-900 hover:border-blue-500 transition-all group md:col-span-2"
      >
        <div class="icon-wrapper w-32 h-32 mb-8 rounded-full bg-gray-700 flex items-center justify-center group-hover:bg-blue-800 transition-colors">
          <span class="text-6xl">🎙️</span>
        </div>
        <h2 class="text-5xl font-extrabold text-white mb-4 tracking-wider">呼叫小 Z</h2>
        <p class="text-2xl text-gray-400 font-medium">有事直接对我说</p>
      </button>

    </main>

    <!-- 异常安抚层 (断网/设备下线) -->
    <div v-if="offlineMode" class="fixed inset-0 z-50 flex items-center justify-center overflow-hidden">
        <!-- 模糊背景 -->
        <div class="absolute inset-0 bg-black/60 backdrop-blur-xl grayscale"></div>
        <img 
            v-if="cachedBackdrop" 
            :src="cachedBackdrop" 
            class="absolute inset-0 w-full h-full object-cover opacity-20"
        />
        
        <!-- 温和弹窗 -->
        <div class="relative z-10 bg-gray-900 border-2 border-yellow-600/50 p-12 rounded-3xl max-w-2xl text-center shadow-2xl">
            <span class="text-8xl mb-6 block">☕</span>
            <h2 class="text-4xl font-bold text-white mb-6 leading-relaxed">
                家庭数据阵列正在维护中<br/>或者网络走神了
            </h2>
            <p class="text-2xl text-gray-400 mb-10">
                别担心，您的家人可能在升级系统。<br/>您可以稍后重试，或者给他们打个电话。
            </p>
            <button 
                @click="offlineMode = false"
                class="px-10 py-5 bg-yellow-600 hover:bg-yellow-500 text-white text-3xl font-bold rounded-full transition-transform active:scale-95"
            >
                我知道了
            </button>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { getCachedImage } from '@/core/db';

const router = useRouter();
const auth = useAuthStore();

// 离线/异常安抚模式
const offlineMode = ref(false);
const cachedBackdrop = ref<string | null>(null);

onMounted(() => {
    // 监听全局离线事件 (可由 axios 拦截器或 window.addEventListener('offline') 触发)
    window.addEventListener('offline', () => {
        triggerRestMode();
    });
});

const triggerRestMode = async () => {
    offlineMode.value = true;
    
    // 从 Dexie.js (IndexedDB) 获取离线图片缓存
    const cache = await getCachedImage("elderly_dashboard_bg");
    if (cache) {
        cachedBackdrop.value = cache;
    } else {
        cachedBackdrop.value = "https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?q=80&w=2070&auto=format&fit=crop";
    }
};

const goToGallery = () => {
    router.push({ name: 'gallery' });
};

const goToMedia = () => {
    router.push({ name: 'media' });
};

const triggerVoice = () => {
    alert("Voice assistant UI coming soon...");
};

const logout = () => {
    auth.setToken(null);
    router.push({ name: 'login' });
};
</script>

<style scoped>
.elderly-dashboard {
  min-height: 100vh;
  background-color: #000;
  color: #fff;
}
/* Focus rings for accessibility */
button:focus-visible {
    outline: 4px solid #14b8a6;
    outline-offset: 4px;
}
</style>
