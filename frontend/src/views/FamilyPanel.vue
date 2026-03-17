<template>
  <div class="container mx-auto py-4">
    <h1 class="text-2xl font-bold mb-4">家庭面板</h1>
    <p class="text-base-content/70">简化视图（后续实现）</p>
        <!-- 全屋智能（新加模块） -->
        <button 
          @click="router.push('/iot')"
          class="bg-indigo-900/40 p-10 rounded-[3rem] shadow-xl hover:-translate-y-2 border border-indigo-700/50 transition-all group flex flex-col items-center"
        >
          <div class="w-32 h-32 bg-indigo-800/50 rounded-full flex items-center justify-center mb-6 group-hover:bg-indigo-600/50 transition-colors">
            <span class="text-6xl">💡</span>
          </div>
          <h2 class="text-3xl font-bold text-white mb-2">全屋智能</h2>
          <p class="text-indigo-300 font-medium">随时控制灯光与传感器</p>
        </button>
      </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
const router = useRouter();
</script>
