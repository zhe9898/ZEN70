<template>
  <div class="smart-home min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white p-6 md:p-12 relative overflow-hidden">
    
    <!-- 装饰性光晕底色 -->
    <div class="absolute top-0 left-0 w-full h-96 bg-indigo-600/20 blur-[120px] rounded-full pointer-events-none"></div>

    <!-- 顶栏导航 -->
    <header class="relative z-10 flex items-center justify-between mb-12">
      <div class="flex items-center gap-4">
        <button 
          @click="goBack"
          class="w-14 h-14 rounded-full bg-slate-800/80 hover:bg-slate-700 flex items-center justify-center transition-all backdrop-blur-md border border-slate-700 shadow-xl group"
        >
          <span class="text-2xl group-hover:-translate-x-1 transition-transform">←</span>
        </button>
        <h1 class="text-4xl md:text-5xl font-extrabold bg-gradient-to-r from-indigo-300 to-purple-400 bg-clip-text text-transparent">
          全屋智能中控
        </h1>
      </div>

      <!-- 语音呼叫大脑 -->
      <button 
        @click="activateVoice"
        class="flex items-center gap-3 px-6 py-3 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 font-bold text-lg shadow-[0_0_20px_rgba(99,102,241,0.4)] transition-all hover:scale-105 active:scale-95"
      >
        <span class="animate-pulse">🎙️</span>
        <span>呼叫小 Z 管家</span>
      </button>
    </header>

    <!-- 主体设备网格 -->
    <main class="relative z-10 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 max-w-7xl mx-auto">
      
      <!-- 加载骨架屏 (Skeleton UI) -->
      <template v-if="isInitialLoading">
        <div v-for="i in 4" :key="'skel-'+i" class="device-card relative p-6 rounded-3xl backdrop-blur-xl border border-white/5 bg-white/5 shadow-2xl animate-pulse flex flex-col justify-between h-48">
          <div class="w-16 h-16 rounded-2xl bg-slate-700/50 mb-6"></div>
          <div>
            <div class="h-3 w-12 bg-slate-700/50 rounded mb-2"></div>
            <div class="h-6 w-24 bg-slate-600/50 rounded mb-2"></div>
            <div class="h-4 w-16 bg-slate-700/50 rounded"></div>
          </div>
        </div>
      </template>

      <template v-else>
        <div 
          v-for="device in devices" 
          :key="device.id"
          v-memo="[device.state, device.name]"
          class="device-card relative group p-6 rounded-3xl backdrop-blur-xl border border-white/10 shadow-2xl transition-all duration-300 hover:-translate-y-2 cursor-pointer flex flex-col justify-between"
          :class="getDeviceBgClass(device.state)"
          @click="toggleDevice(device)"
        >
        <!-- 右上角发光状态圆点 -->
        <div class="absolute top-4 right-4 flex h-3 w-3">
          <span v-if="device.state === 'ON' || device.state === 'OPEN'" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-3 w-3" :class="device.state === 'ON' || device.state === 'OPEN' ? 'bg-emerald-500' : 'bg-slate-600'"></span>
        </div>

        <div class="icon-wrapper w-16 h-16 rounded-2xl flex items-center justify-center mb-6 text-3xl transition-transform group-hover:scale-110 relative overflow-hidden" :class="getIconBgClass(device.state)">
          <template v-if="device.isLoading">
            <svg class="animate-spin h-8 w-8 text-current" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </template>
          <template v-else>
            {{ device.icon }}
          </template>
        </div>
        
        <div>
          <p class="text-slate-400 text-sm font-semibold mb-1 uppercase tracking-wider">{{ device.room }}</p>
          <h3 class="text-xl font-bold text-white mb-2 line-clamp-1">{{ device.name }}</h3>
          <p class="text-lg font-medium" :class="device.state === 'ON' || device.state === 'OPEN' ? 'text-indigo-300' : 'text-slate-500'">
            {{ getDisplayState(device) }}
          </p>
        </div>
      </template>
    </main>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';

const router = useRouter();
const devices = ref<any[]>([]);
const isInitialLoading = ref(true);
let evtSource: EventSource | null = null;

const apiBase = import.meta.env.VITE_API_BASE || '/api/v1';

onMounted(async () => {
    await fetchDevices();
    setupSSE();
});

onUnmounted(() => {
    if (evtSource) {
        evtSource.close();
    }
});

const fetchDevices = async () => {
    isInitialLoading.value = true;
    try {
        const res = await axios.get(`${apiBase}/iot/devices`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('zen70-token')}` }
        });
        devices.value = res.data.devices || [];
    } catch (err) {
        console.error("加载物联设备失败", err);
    } finally {
        isInitialLoading.value = false;
    }
};

// 监听 Redis 中转过来的 MQTT 实时状态刷屏
const setupSSE = () => {
    const token = localStorage.getItem('zen70-token');
    evtSource = new EventSource(`${apiBase}/events/stream?token=${token}`);
    
    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'iot_update') {
                const idx = devices.value.findIndex(d => d.id === data.device_id);
                if (idx !== -1) {
                    // 硬件物理确认后，撤销遮罩，正式翻转状态
                    devices.value[idx].state = data.state;
                    devices.value[idx].isLoading = false;
                }
            }
        } catch (e) {
            // ignore
        }
    };
};

// 触发指令 (坚决执行 V2.7 物理防抖确认标准)
const toggleDevice = async (device: any) => {
    if (device.isLoading || device.type === 'sensor') return;
    
    let targetState = 'OFF';
    
    if (device.type === 'light') {
        targetState = device.state === 'ON' ? 'OFF' : 'ON';
    } else if (device.type === 'curtain') {
        targetState = device.state === 'OPEN' ? 'CLOSED' : 'OPEN';
    }

    // 不做乐观更新，而是挂起 Loading 态
    device.isLoading = true;

    // 10秒超时回滚保护
    const timeoutId = setTimeout(() => {
        if (device.isLoading) {
            device.isLoading = false;
            console.warn(`[IoT] Timeout waiting for hardware ACK for ${device.id}`);
        }
    }, 10000);

    try {
        await axios.post(`${apiBase}/iot/control`, {
            device_id: device.id,
            action: targetState
        }, {
            headers: { Authorization: `Bearer ${localStorage.getItem('zen70-token')}` }
        });
        // API 返回 200 仅代表指令下发到 Queue，不解除 Loading
    } catch (e: any) {
        clearTimeout(timeoutId);
        device.isLoading = false;
        if (e.response && e.response.status === 503) {
            alert("⚠️ 指令遭熔断拦截：全设备桥接中继(HomeAssistant)已离线！");
        } else {
            console.error("下发指令失败", e);
        }
    }
};

const activateVoice = () => {
    alert("Voice Assistant function calling integration planned for next step...");
};

const goBack = () => {
    router.back();
};

// --- 视觉拟态辅助函数 ---

const getDeviceBgClass = (state: string) => {
    const isOn = state === 'ON' || state === 'OPEN';
    return isOn 
        ? 'bg-gradient-to-br from-indigo-900/40 to-indigo-800/20 border-indigo-500/30' 
        : 'bg-white/5 hover:bg-white/10 border-white/5';
};

const getIconBgClass = (state: string) => {
    const isOn = state === 'ON' || state === 'OPEN';
    return isOn ? 'bg-indigo-500/30 text-indigo-300' : 'bg-slate-700 text-slate-400';
};

const getDisplayState = (device: any) => {
    if (device.type === 'sensor') return device.state;
    if (device.type === 'light') return device.state === 'ON' ? '已开启' : '已关闭';
    if (device.type === 'curtain') return device.state === 'OPEN' ? '已打开' : '已闭合';
    return device.state;
};

// --- 结束 ---
</script>

<style scoped>
/* Glassmorphism custom highlights */
.device-card::before {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 2px;
    background: linear-gradient(to bottom right, rgba(255,255,255,0.2), rgba(255,255,255,0));
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask-composite: exclude;
    pointer-events: none;
}
</style>
