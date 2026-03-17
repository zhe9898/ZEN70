<template>
  <div class="kids-mode relative min-h-screen bg-sky-300 overflow-hidden">
    <!-- 背景点缀动画 -->
    <div class="absolute inset-0 z-0 pointer-events-none opacity-50">
      <div class="cloud absolute top-10 left-10 w-32 h-16 bg-white rounded-full mix-blend-overlay animate-pulse"></div>
      <div class="cloud absolute top-40 right-20 w-48 h-20 bg-white rounded-full mix-blend-overlay animate-pulse delay-700"></div>
    </div>

    <!-- 头部导航 -->
    <header class="relative z-10 flex justify-between p-6">
      <div class="bg-white/80 backdrop-blur-md px-6 py-3 rounded-full shadow-lg border-2 border-white">
        <h1 class="text-3xl font-black text-sky-600 tracking-widest">童玩空间</h1>
      </div>
      <button 
        @click="logout"
        class="bg-rose-400 hover:bg-rose-500 text-white px-6 py-3 rounded-full font-bold text-xl shadow-lg border-2 border-rose-300 transition-transform active:scale-95"
      >
        退出玩耍
      </button>
    </header>

    <!-- 限制时间倒计时 (防沉迷) -->
    <div class="relative z-10 flex justify-center mt-6">
       <div class="bg-amber-100 border-4 border-amber-400 p-4 rounded-3xl shadow-xl flex items-center gap-4">
           <span class="text-4xl animate-bounce">⏱️</span>
           <div>
               <p class="text-amber-800 font-bold text-lg">剩余看动画时间</p>
               <p class="text-amber-600 font-black text-3xl">{{ formattedTime }}</p>
           </div>
       </div>
    </div>

    <!-- 核心功能区 -->
    <main class="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-8 px-6 mt-12 max-w-5xl mx-auto">
      <!-- 动画片专区 -->
      <button class="bg-white p-10 rounded-[3rem] shadow-[0_20px_0_0_rgba(14,165,233,0.3)] hover:translate-y-2 hover:shadow-[0_10px_0_0_rgba(14,165,233,0.3)] border-4 border-sky-400 transition-all group flex flex-col items-center">
        <div class="w-40 h-40 bg-sky-100 rounded-full flex items-center justify-center mb-6 border-4 border-sky-300 group-hover:bg-sky-200 transition-colors">
            <span class="text-8xl">📺</span>
        </div>
        <h2 class="text-5xl font-black text-slate-800 mb-4">看动画片</h2>
        <p class="text-xl text-slate-500 font-bold">小猪佩奇、海底小纵队都在这</p>
      </button>

      <!-- 问答管家 (Prompt 拦截区) -->
      <button 
        @click="openAITeacher"
        class="bg-white p-10 rounded-[3rem] shadow-[0_20px_0_0_rgba(244,114,182,0.3)] hover:translate-y-2 hover:shadow-[0_10px_0_0_rgba(244,114,182,0.3)] border-4 border-pink-400 transition-all group flex flex-col items-center"
      >
        <div class="w-40 h-40 bg-pink-100 rounded-full flex items-center justify-center mb-6 border-4 border-pink-300 group-hover:bg-pink-200 transition-colors">
            <span class="text-8xl">🦉</span>
        </div>
        <h2 class="text-5xl font-black text-slate-800 mb-4">问问猫头鹰</h2>
        <p class="text-xl text-slate-500 font-bold">有问题？直接对着猫头鹰说话</p>
      </button>
    </main>

    <!-- 防沉迷锁机覆盖层 -->
    <div v-if="timeUp" class="fixed inset-0 z-50 bg-slate-900/95 backdrop-blur-3xl flex flex-col items-center justify-center">
        <span class="text-9xl mb-8">😴</span>
        <h1 class="text-6xl font-black text-white mb-6">猫头鹰去睡觉啦</h1>
        <p class="text-3xl text-slate-400 mb-12 font-bold max-w-2xl text-center leading-relaxed">
            今天看屏幕的时间已经用完咯。<br/>保护眼睛，明天我们再一起玩吧！
        </p>
        <button 
            @click="logout"
            class="px-12 py-6 bg-rose-500 hover:bg-rose-600 text-white text-3xl font-black rounded-full border-4 border-rose-400 shadow-xl active:scale-95"
        >
            乖乖退出
        </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const auth = useAuthStore();

// 防沉迷时间限制 (硬编码演示 30 分钟)
const timeLeft = ref(30 * 60); 
const timeUp = ref(false);
let timer: any = null;

const formattedTime = computed(() => {
    const m = Math.floor(timeLeft.value / 60);
    const s = timeLeft.value % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
});

onMounted(() => {
    timer = setInterval(() => {
        if (timeLeft.value > 0) {
            timeLeft.value--;
        } else {
            timeUp.value = true;
            clearInterval(timer);
        }
    }, 1000);
});

onUnmounted(() => {
    if (timer) clearInterval(timer);
});

const openAITeacher = () => {
    // 实际场景应唤起语音对话框，后台路由会将 Prompt 覆写为“早教老师”
    alert("Voice LLM interface starting with Kid-Mode constraints...");
};

const logout = () => {
    auth.setToken(null);
    router.push({ name: 'login' });
};
</script>

<style scoped>
.kids-mode * {
    font-family: 'Comic Sans MS', 'Chalkboard SE', 'Nunito', sans-serif;
}
</style>
