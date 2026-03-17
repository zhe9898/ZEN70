import { defineStore } from "pinia";
import { ref } from "vue";
import { http } from "@/utils/http";
import { saveCapabilities, loadCapabilities } from "@/services/offlineStorage";
import type { Capabilities } from "@/types/capability";
import type { HardwareEvent } from "@/types/sse";

const pathToSvc = (p: string): string | null => (p.match(/\/([^/]+)$/)?.[1] ?? null);

export const useCapabilitiesStore = defineStore("capabilities", () => {
  const caps = ref<Capabilities>({});
  const loading = ref(false);
  const error = ref<string | null>(null);
  /** 当前数据来自离线缓存 */
  const isOffline = ref(false);

  async function fetchCapabilities(): Promise<void> {
    loading.value = true;
    error.value = null;
    isOffline.value = false;
    if (!navigator.onLine) {
      const cached = await loadCapabilities();
      if (cached && Object.keys(cached).length > 0) {
        caps.value = cached;
        isOffline.value = true;
      } else {
        error.value = null;
      }
      loading.value = false;
      return;
    }
    try {
      const { data } = await http.get<Capabilities>("/v1/capabilities");
      caps.value = data ?? {};
      await saveCapabilities(caps.value);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "加载失败";
      const cached = await loadCapabilities();
      if (cached && Object.keys(cached).length > 0) {
        caps.value = cached;
        isOffline.value = true;
      }
    } finally {
      loading.value = false;
    }
  }

  /** 网络恢复后调用，拉取最新数据并刷新 UI */
  async function syncOnReconnect(): Promise<void> {
    if (!navigator.onLine) return;
    await fetchCapabilities();
  }

  /** 根据 SSE 硬件事件更新对应能力状态 */
  function updateHardware(ev: HardwareEvent): void {
    const path = ev.path;
    const state = ev.state as "online" | "offline" | "unknown" | undefined;
    if (!path || !state) return;
    const svc = pathToSvc(path);
    for (const [name, cap] of Object.entries(caps.value)) {
      const match =
        (svc && name.toLowerCase().includes(svc)) || (cap.endpoint && cap.endpoint.includes(path));
      if (match) caps.value[name] = { ...cap, status: state, reason: ev.reason };
    }
  }

  return { caps, loading, error, isOffline, fetchCapabilities, syncOnReconnect, updateHardware };
});
