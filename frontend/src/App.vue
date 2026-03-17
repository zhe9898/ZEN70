<template>
  <div class="min-h-screen bg-base-300">
    <nav class="navbar bg-base-100 shadow-md">
      <div class="flex-1">
        <router-link to="/" class="btn btn-ghost text-xl">ZEN70</router-link>
        <router-link v-if="auth.isAdmin" to="/" class="btn btn-ghost btn-sm">控制台</router-link>
        <router-link to="/family" class="btn btn-ghost btn-sm">家庭</router-link>
        <router-link to="/board" class="btn btn-ghost btn-sm text-primary font-bold">🗼 家族信标</router-link>
      </div>
      <div class="flex-none gap-2">
        <div class="dropdown dropdown-end">
          <label tabindex="0" class="btn btn-sm btn-ghost m-1">
            主题 / 壁纸
          </label>
          <ul tabindex="0" class="dropdown-content z-[100] menu p-2 shadow-2xl bg-base-100/90 backdrop-blur-xl rounded-box w-56">
            <li class="menu-title"><span>视觉引擎</span></li>
            <li><a @click="themeStore.toggleWallpaper()">动态流体背景 ({{ themeStore.liveWallpaperEnabled ? '开' : '关' }})</a></li>
            <li><a @click="triggerWallpaperUpload">🖼️ 设置自定义壁纸</a></li>
            <li v-if="themeStore.customWallpaperUrl"><a @click="themeStore.clearCustomWallpaper" class="text-error">✕ 恢复默认壁纸</a></li>
            <div class="divider my-0"></div>
            <li class="menu-title"><span>色彩主题</span></li>
            <li v-for="t in themeStore.availableThemes" :key="t">
              <a @click="themeStore.setTheme(t)" :class="{ 'active': themeStore.currentTheme === t }">{{ t }}</a>
            </li>
          </ul>
        </div>
        
        <!-- 隐藏的壁纸上传输入框 -->
        <input type="file" ref="wallpaperInput" class="hidden" accept="image/*" @change="handleWallpaperUpload" />
        <div class="dropdown dropdown-end" v-if="auth.token && !auth.isElder && !auth.isChild">
          <label tabindex="0" class="btn btn-sm btn-ghost m-1 flex items-center gap-1">
            <span v-if="auth.aiRoutePreference === 'cloud'">☁️ 云端增强</span>
            <span v-else-if="auth.aiRoutePreference === 'local'">🛡️ 本地优先</span>
            <span v-else>🤖 自动路由</span>
          </label>
          <ul tabindex="0" class="dropdown-content z-[100] menu p-2 shadow bg-base-100 rounded-box w-52">
            <li class="menu-title"><span>AI 大脑计算链路</span></li>
            <li><a @click="auth.updateAiPreference('local')" :class="{'active': auth.aiRoutePreference === 'local'}">🛡️ 私有本地版 (安全)</a></li>
            <li><a @click="auth.updateAiPreference('cloud')" :class="{'active': auth.aiRoutePreference === 'cloud'}">☁️ 云端增强版 (高速)</a></li>
            <li><a @click="auth.updateAiPreference('auto')" :class="{'active': auth.aiRoutePreference === 'auto'}">🤖 自动智能路由</a></li>
          </ul>
        </div>
        <button class="btn btn-sm btn-ghost" @click="refresh">刷新</button>
      </div>
    </nav>
    <LiveWallpaper />
    <main class="relative z-10 p-4">
      <RouterView />
    </main>

    <!-- 情绪隔离与优雅降级控制层 (法典 2.5 & 3.3.1) -->
    <div 
      v-if="isMaintenanceMode" 
      class="fixed inset-0 z-50 flex items-center justify-center bg-base-100/30 backdrop-blur-md"
    >
      <div class="text-center bg-base-100 p-8 rounded-xl shadow-2xl max-w-sm">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-16 h-16 mx-auto mb-4 text-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <h2 class="text-2xl font-bold mb-2">设备维护中</h2>
        <p class="text-base-content/70 mb-4">
          硬件暂时离线或系统过载，请稍后再试。
        </p>
        <div v-if="auth.isAdmin" class="text-left bg-base-300 p-3 rounded text-xs overflow-auto">
          <p class="font-bold text-error">控制台调试信息:</p>
          <pre>{{ maintenanceError || 'No trace available' }}</pre>
        </div>
        <button class="btn btn-primary mt-4" @click="resetMaintenance">尝试恢复</button>
      </div>
    </div>

    <!-- 离线存储警告 Toast (法典 6.1.3 免责) -->
    <div v-if="persistWarn" class="toast toast-end z-50">
      <div class="alert alert-warning">
        <span>离线灾备存储受限。应用数据可能被清理。</span>
        <button class="btn btn-ghost btn-sm" @click="persistWarn = false">✕</button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useSwitchStore } from "@/stores/switch";
import { createSSE } from "@/utils/sse";
import { API } from "@/utils/api";
import { requestPersistentStorage } from "@/utils/persist";
import { initWebPush } from "@/utils/push";
import type { HardwareEvent, SwitchEvent } from "@/types/sse";
import LiveWallpaper from "@/components/LiveWallpaper.vue";

const auth = useAuthStore();
const themeStore = useThemeStore();
const capsStore = useCapabilitiesStore();
const switchStore = useSwitchStore();
let closeSSE: (() => void) | null = null;

const isMaintenanceMode = ref(false);
const maintenanceError = ref<any>(null);
const persistWarn = ref(false);

// M10.2 壁纸上传状态
const wallpaperInput = ref<HTMLInputElement | null>(null);

function triggerWallpaperUpload() {
  if (wallpaperInput.value) {
    wallpaperInput.value.click();
  }
}

function handleWallpaperUpload(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (event) => {
    if (event.target?.result && typeof event.target.result === 'string') {
      themeStore.setCustomWallpaper(event.target.result);
    }
  };
  reader.readAsDataURL(file);
  
  // 清空防止同名文件不触发 change
  if (wallpaperInput.value) {
    wallpaperInput.value.value = "";
  }
}

function refresh() {
  capsStore.fetchCapabilities();
}

function resetMaintenance() {
  isMaintenanceMode.value = false;
  maintenanceError.value = null;
  refresh();
}

function handleMaintenanceEvent(e: Event) {
  const customEvent = e as CustomEvent;
  isMaintenanceMode.value = true;
  maintenanceError.value = customEvent.detail;
}

function handleOnline() {
  capsStore.syncOnReconnect();
}

onMounted(async () => {
  const granted = await requestPersistentStorage();
  if (!granted) persistWarn.value = true;
  
  // 法典 M5.3: 初始化 Web Push VAPID 订阅 (静默或弹窗请求)
  initWebPush().catch((e: any) => console.error("Web Push Error", e));

  capsStore.fetchCapabilities();
  switchStore.loadCached();
  window.addEventListener("online", handleOnline);
  window.addEventListener("zen70-maintenance-mode", handleMaintenanceEvent);
  closeSSE = createSSE(
    API.events(),
    (ev) => {
      if (ev.type === "hardware:events") capsStore.updateHardware(ev.data as HardwareEvent);
      if (ev.type === "switch:events") switchStore.updateFromEvent(ev.data as SwitchEvent);
      if (ev.type === "board:events") window.dispatchEvent(new CustomEvent("zen70-sse-board", { detail: ev }));
    },
    ["hardware:events", "switch:events", "board:events"],
    { onFallbackOffline: () => capsStore.syncOnReconnect() }
  );
});

onUnmounted(() => {
  window.removeEventListener("online", handleOnline);
  window.removeEventListener("zen70-maintenance-mode", handleMaintenanceEvent);
  closeSSE?.();
});
</script>
