<template>
  <div class="max-w-4xl mx-auto py-8 px-4">
    <h2 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-amber-400 to-orange-500 mb-2">
      系统设置
    </h2>
    <p class="text-sm text-base-content/60 mb-6">管理功能开关、AI Provider 端点、模型选择、系统状态</p>

    <!-- Tab 导航 -->
    <div class="tabs tabs-boxed bg-base-200 mb-6 flex-wrap">
      <a class="tab" :class="{ 'tab-active': activeTab === 'flags' }" @click="activeTab = 'flags'">🎛️ 功能开关</a>
      <a v-if="!authStore.isChild" class="tab" :class="{ 'tab-active': activeTab === 'switches' }" @click="activeTab = 'switches'; loadSwitches()">🔘 资源熔断器</a>
      <a v-if="!authStore.isChild" class="tab" :class="{ 'tab-active': activeTab === 'network' }" @click="activeTab = 'network'; loadNetConfig()">🌐 网络配置</a>
      <a v-if="!authStore.isChild" class="tab" :class="{ 'tab-active': activeTab === 'endpoints' }" @click="activeTab = 'endpoints'; loadEndpoints()">🔌 AI 端点</a>
      <a class="tab" :class="{ 'tab-active': activeTab === 'ai' }" @click="activeTab = 'ai'; scanModels()">🧠 AI 模型</a>
      <a class="tab" :class="{ 'tab-active': activeTab === 'system' }" @click="activeTab = 'system'">⚙️ 系统</a>
    </div>

    <!-- === Tab 1: 功能开关 === -->
    <div v-if="activeTab === 'flags'" class="space-y-4">
      <div v-if="flagsLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-primary loading-lg"></span>
      </div>
      <div v-else>
        <div v-for="category in flagCategories" :key="category" class="mb-6">
          <h3 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">
            {{ categoryLabels[category] || category }}
          </h3>
          <div class="space-y-3">
            <div v-for="flag in flagsByCategory(category)" :key="flag.key"
              class="card bg-base-100 shadow border border-base-200 p-4">
              <div class="flex items-center justify-between">
                <div class="flex-1">
                  <h4 class="font-medium text-sm">{{ flag.key }}</h4>
                  <p class="text-xs text-base-content/50 mt-1">{{ flag.description }}</p>
                </div>
                <input type="checkbox" class="toggle toggle-primary" :checked="flag.enabled"
                  @change="toggleFlag(flag.key)" :disabled="toggling === flag.key || authStore.isChild" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- === Tab: 资源熔断器 (Hardware Switches) === -->
    <div v-if="activeTab === 'switches'" class="space-y-4">
      <div class="mb-4 p-3 bg-base-200 rounded-lg text-sm text-base-content/60">
        🛡️ 物理层容器资源大闸。关闭后系统将直接在底层执行 `docker pause` 强制冻结容器释放 CPU 算力，开启则执行 `unpause`。
      </div>
      <div v-if="switchesLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-error loading-lg"></span>
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="(sw, name) in hardwareSwitches" :key="name" class="card bg-base-100 shadow border border-base-200 p-5">
          <div class="flex items-center justify-between">
            <div class="flex-1">
              <h4 class="font-bold text-lg flex items-center gap-2">
                {{ sw.label || name }} 
                <span class="badge badge-sm" :class="sw.state === 'ON' ? 'badge-success' : sw.state === 'OFF' ? 'badge-error' : 'badge-warning'">{{ sw.state }}</span>
              </h4>
              <p class="text-xs text-base-content/50 mt-1 font-mono">ID: {{ name }}</p>
              <p class="text-xs text-base-content/40 mt-1" v-if="sw.updated_at">
                最后操作: {{ new Date(sw.updated_at * 1000).toLocaleString() }} ({{ sw.updated_by }})
              </p>
              <p class="text-xs text-base-content/40 mt-0.5" v-if="sw.reason">原因: {{ sw.reason }}</p>
            </div>
            <div class="flex flex-col items-center">
              <input type="checkbox" class="toggle toggle-error toggle-lg" :checked="sw.state === 'ON'"
                @change="toggleHwSwitch(name, sw.state === 'ON' ? 'OFF' : 'ON')" :disabled="togglingSwitch === name" />
              <span v-if="togglingSwitch === name" class="loading loading-spinner loading-xs mt-2"></span>
            </div>
          </div>
        </div>
        <div v-if="Object.keys(hardwareSwitches).length === 0" class="col-span-full text-center py-12 text-base-content/40">
          <p class="text-lg">暂无可用硬件开关</p>
          <p class="text-sm mt-1">请检查 Topology Sentinel 探针是否正常运行，或 system.yaml 是否配置了 switch_container_map</p>
        </div>
      </div>
    </div>

    <!-- === Tab 2: 网络配置 === -->
    <div v-if="activeTab === 'network'">
      <div v-if="netLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-primary loading-lg"></span>
      </div>
      <div v-else class="space-y-6">
        <!-- 端口配置 -->
        <div>
          <h3 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">🔌 服务端口</h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div v-for="item in netPortItems" :key="item.key" class="card bg-base-100 shadow border border-base-200 p-4">
              <label class="text-xs font-medium text-base-content/60">{{ item.label }}</label>
              <div class="flex gap-2 mt-1">
                <input type="text" class="input input-sm input-bordered flex-1 font-mono" v-model="netVals[item.key]" :placeholder="item.placeholder" @keyup.enter="saveNetVal(item.key)" />
                <button class="btn btn-sm btn-primary" @click="saveNetVal(item.key)" :disabled="savingNet === item.key">
                  <span v-if="savingNet === item.key" class="loading loading-spinner loading-xs"></span>
                  保存
                </button>
              </div>
            </div>
          </div>
        </div>
        <!-- 域名配置 -->
        <div>
          <h3 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">🌍 域名挂载</h3>
          <div class="space-y-3">
            <div v-for="item in netDomainItems" :key="item.key" class="card bg-base-100 shadow border border-base-200 p-4">
              <label class="text-xs font-medium text-base-content/60">{{ item.label }}</label>
              <p class="text-xs text-base-content/40 mt-0.5">{{ item.hint }}</p>
              <div class="flex gap-2 mt-1">
                <input type="text" class="input input-sm input-bordered flex-1 font-mono" v-model="netVals[item.key]" :placeholder="item.placeholder" @keyup.enter="saveNetVal(item.key)" />
                <button class="btn btn-sm btn-primary" @click="saveNetVal(item.key)" :disabled="savingNet === item.key">
                  <span v-if="savingNet === item.key" class="loading loading-spinner loading-xs"></span>
                  保存
                </button>
              </div>
            </div>
          </div>
        </div>
        <!-- 存储路径 -->
        <div>
          <h3 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3">💾 存储路径</h3>
          <div class="space-y-3">
            <div v-for="item in netPathItems" :key="item.key" class="card bg-base-100 shadow border border-base-200 p-4">
              <label class="text-xs font-medium text-base-content/60">{{ item.label }}</label>
              <div class="flex gap-2 mt-1">
                <input type="text" class="input input-sm input-bordered flex-1 font-mono" v-model="netVals[item.key]" :placeholder="item.placeholder" @keyup.enter="saveNetVal(item.key)" />
                <button class="btn btn-sm btn-primary" @click="saveNetVal(item.key)" :disabled="savingNet === item.key">
                  <span v-if="savingNet === item.key" class="loading loading-spinner loading-xs"></span>
                  保存
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="netMsg" class="mt-4 alert" :class="netOk ? 'alert-success' : 'alert-error'">
        <span>{{ netMsg }}</span>
      </div>
    </div>

    <!-- === Tab 3: AI 端点配置 === -->
    <div v-if="activeTab === 'endpoints'">
      <div class="mb-4 p-3 bg-base-200 rounded-lg text-sm text-base-content/60">
        💡 填写地址后点击保存，系统会自动扫描该后端的已下载模型并注册。
      </div>
      <div v-if="endpointsLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-primary loading-lg"></span>
      </div>
      <div v-else class="space-y-3">
        <div v-for="(ep, key) in endpoints" :key="key"
          class="card bg-base-100 shadow border border-base-200 p-4">
          <div class="flex items-start gap-4">
            <div class="flex-1">
              <h4 class="font-bold text-sm">{{ ep.label }}</h4>
              <p class="text-xs text-base-content/50 mt-0.5">{{ ep.description }}</p>
              <div class="mt-2 flex gap-2 items-center">
                <input
                  type="text"
                  class="input input-sm input-bordered flex-1 font-mono text-xs"
                  :placeholder="ep.default_url || '输入地址，如 http://192.168.1.100:' + (ep.default_port || '端口')"
                  v-model="epUrls[key]"
                  @keyup.enter="saveEndpoint(key)"
                />
                <button class="btn btn-sm btn-primary" @click="saveEndpoint(key)"
                  :disabled="savingEndpoint === key">
                  <span v-if="savingEndpoint === key" class="loading loading-spinner loading-xs"></span>
                  保存
                </button>
              </div>
              <div class="mt-1 flex gap-2 items-center text-xs">
                <span v-if="ep.default_port" class="text-base-content/40">默认端口: {{ ep.default_port }}</span>
                <span class="badge badge-xs" :class="epHealthClass(key)">
                  {{ epHealthLabel(key) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="endpointMsg" class="mt-4 alert" :class="endpointSuccess ? 'alert-success' : 'alert-error'">
        <span>{{ endpointMsg }}</span>
      </div>
    </div>

    <!-- === Tab 3: AI 模型 === -->
    <div v-if="activeTab === 'ai'">
      <div class="flex items-center justify-between mb-4">
        <span class="text-sm text-base-content/60">📡 每次打开此页面自动扫描所有已配置 Provider</span>
        <button class="btn btn-sm btn-primary gap-1" @click="scanModels" :disabled="scanning">
          <span v-if="scanning" class="loading loading-spinner loading-xs"></span>
          🔍 扫描模型
        </button>
      </div>
      <div v-if="modelsLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-primary loading-lg"></span>
      </div>
      <div v-else>
        <div v-for="(models, providerName) in modelsByProvider" :key="providerName" class="mb-6">
          <h3 class="text-sm font-semibold text-base-content/50 uppercase tracking-wider mb-3 flex items-center gap-2">
            {{ providerLabels[providerName] || providerName }}
            <span class="badge badge-sm badge-ghost">{{ models.length }}</span>
          </h3>
          <div class="grid grid-cols-1 gap-3">
            <div v-for="model in models" :key="model.id"
              class="card bg-base-100 shadow border transition-all cursor-pointer hover:shadow-lg"
              :class="isModelSelected(model) ? 'border-primary ring-2 ring-primary/20' : 'border-base-200'"
              @click="selectModel(model)">
              <div class="card-body p-4">
                <h4 class="font-bold text-sm flex items-center gap-2 flex-wrap">
                  {{ model.name || model.id }}
                  <span v-if="model.auto_discovered" class="badge badge-xs badge-accent">自动发现</span>
                  <span v-if="isModelSelected(model)" class="badge badge-xs badge-primary">当前</span>
                </h4>
                <p v-if="model.description" class="text-xs text-base-content/50 mt-1">{{ model.description }}</p>
                <div class="flex gap-2 mt-2 flex-wrap">
                  <span v-for="cap in model.capabilities" :key="cap" class="badge badge-xs badge-outline"
                    :class="capColor(cap)">{{ capLabel(cap) }}</span>
                  <span v-if="model.size_gb" class="badge badge-xs badge-ghost">{{ model.size_gb }} GB</span>
                  <span v-if="model.size" class="badge badge-xs badge-ghost">{{ model.size }}</span>
                  <span v-if="model.dim" class="badge badge-xs badge-ghost">{{ model.dim }}维</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="!Object.keys(modelsByProvider).length" class="text-center py-12 text-base-content/40">
          <p class="text-lg">暂无可用模型</p>
          <p class="text-sm mt-1">请先在"端点配置"Tab 填写地址，然后点击"扫描模型"</p>
        </div>
      </div>
      <div v-if="switchMsg" class="mt-4 alert" :class="switchOk ? 'alert-success' : 'alert-error'">
        <span>{{ switchMsg }}</span>
      </div>
    </div>

    <!-- === Tab 4: 系统信息 === -->
    <div v-if="activeTab === 'system'">
      <div v-if="sysLoading" class="flex justify-center py-12">
        <span class="loading loading-spinner text-primary loading-lg"></span>
      </div>
      <div v-else-if="sysInfo" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="stat bg-base-100 shadow rounded-xl border border-base-200">
          <div class="stat-title">系统版本</div>
          <div class="stat-value text-lg">v{{ sysInfo.version }}</div>
          <div class="stat-desc">Python {{ sysInfo.python }}</div>
        </div>
        <div class="stat bg-base-100 shadow rounded-xl border border-base-200">
          <div class="stat-title">操作系统</div>
          <div class="stat-value text-lg">{{ sysInfo.os }}</div>
          <div class="stat-desc">{{ sysInfo.architecture }}</div>
        </div>
        <div class="stat bg-base-100 shadow rounded-xl border border-base-200">
          <div class="stat-title">GPU 状态</div>
          <div class="stat-value text-lg" :class="sysInfo.gpu?.includes('available') ? 'text-success' : 'text-warning'">
            {{ sysInfo.gpu?.includes('available') ? '✅ 可用' : '⚠️ 未检测到' }}
          </div>
        </div>
        <div class="stat bg-base-100 shadow rounded-xl border border-base-200" v-if="sysInfo.disk">
          <div class="stat-title">存储空间</div>
          <div class="stat-value text-lg">
            {{ sysInfo.disk.free_gb ? sysInfo.disk.free_gb + ' GB' : sysInfo.disk.status }}
          </div>
          <div class="stat-desc" v-if="sysInfo.disk.usage_pct">已用 {{ sysInfo.disk.usage_pct }}%</div>
        </div>
        <div class="stat bg-base-100 shadow rounded-xl border border-base-200 col-span-full" v-if="sysInfo.ai_providers">
          <div class="stat-title">AI Provider 状态</div>
          <div class="flex gap-2 mt-2 flex-wrap">
            <div v-for="(h, n) in sysInfo.ai_providers" :key="n"
              class="badge gap-1"
              :class="h.status === 'online' ? 'badge-success' : h.status === 'available' ? 'badge-info' : 'badge-ghost'">
              {{ n }}: {{ h.status }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- === Tab 5: 数据库与灾备 === -->
    <div v-if="activeTab === 'database'">
      <div class="text-slate-400 p-8 text-center bg-slate-900 rounded-2xl">
        数据库高级配置项开发中...
      </div>
    </div>

    <!-- === Tab 6: 数据信任圈与保险柜 === -->
    <div v-if="activeTab === 'privacy'">
      <PrivacyVault />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import PrivacyVault from '@/views/PrivacyVault.vue';

const authStore = useAuthStore();
const API = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

const activeTab = ref('flags');
const flagsLoading = ref(true);
const sysLoading = ref(false);
const modelsLoading = ref(false);
const scanning = ref(false);
const endpointsLoading = ref(false);
interface FeatureFlag {
  id: string;
  category: string;
  name: string;
  description: string;
  value: boolean;
  key: string;
  enabled: boolean;
}

interface SwitchState {
  state: string;
  reason?: string;
  updated_at: number;
  updated_by: string;
  label?: string;
}

interface AIProviderEndpoint {
  url: string;
  default_url?: string;
  default_port?: number;
  label?: string;
  description?: string;
  [key: string]: unknown;
}

interface AIModel {
  id: string;
  name: string;
  provider: string;
  description?: string;
  capabilities?: string[];
  auto_discovered?: boolean;
  size_gb?: number;
  size?: number | string;
  dim?: number;
}

interface DiskInfo {
  status: string;
  free_gb?: number;
  usage_pct?: number;
}

interface SystemInfo {
  version: string;
  python: string;
  os: string;
  architecture: string;
  gpu?: string;
  disk?: DiskInfo;
  ai_providers?: Record<string, { status: string }>;
}

const flags = ref<FeatureFlag[]>([]);
const sysInfo = ref<SystemInfo | null>(null);
const toggling = ref<string | null>(null);
const modelsByProvider = ref<Record<string, AIModel[]>>({});
const selectedModels = ref<Record<string, string>>({});
const switchMsg = ref('');
const switchOk = ref(false);

// 资源熔断器
const switchesLoading = ref(false);
const hardwareSwitches = ref<Record<string, SwitchState>>({});
const togglingSwitch = ref<string | null>(null);

// 端点配置
const endpoints = ref<Record<string, AIProviderEndpoint>>({});
const epUrls = ref<Record<string, string>>({});
const providerHealth = ref<Record<string, { status: string }>>({});
const savingEndpoint = ref<string | null>(null);
const endpointMsg = ref('');

// 网络配置
const netLoading = ref(false);
const netVals = ref<Record<string, string>>({});
const savingNet = ref<string | null>(null);
const netMsg = ref('');
const netOk = ref(false);

const netPortItems = [
  { key: 'backend_port', label: '后端 API 端口', placeholder: '8000' },
  { key: 'frontend_port', label: '前端服务端口', placeholder: '5173' },
  { key: 'caddy_http_port', label: 'Caddy HTTP 端口', placeholder: '80' },
  { key: 'caddy_https_port', label: 'Caddy HTTPS 端口', placeholder: '443' },
];
const netDomainItems = [
  { key: 'caddy_domain', label: 'Caddy 反代域名', placeholder: 'home.example.com', hint: '填写后 Caddy 自动签发 HTTPS 证书' },
  { key: 'cf_tunnel_domain', label: 'Cloudflare Tunnel 公网域名', placeholder: 'zen70.example.com', hint: '通过 CF Tunnel 暴露到公网的域名' },
  { key: 'headscale_domain', label: 'Headscale 内网域名', placeholder: 'hc.internal', hint: 'WireGuard P2P VPN 内网域名' },
];
const netPathItems = [
  { key: 'media_path', label: '媒体文件根路径', placeholder: '/mnt/media' },
  { key: 'jellyfin_data_path', label: 'Jellyfin 媒体库路径', placeholder: '/mnt/media/jellyfin' },
];
const endpointSuccess = ref(false);

const categoryLabels: Record<string, string> = {
  ai: '🧠 AI 智能引擎', media: '🎬 媒体中心', iot: '🏠 物联家居', general: '⚙️ 通用',
};
const providerLabels: Record<string, string> = {
  ollama: '🦙 Ollama', lm_studio: '🖥️ LM Studio', localai: '🏠 LocalAI',
  text_gen_webui: '📝 text-gen-webui', vllm: '⚡ vLLM', jan: '🤖 Jan',
  gpt4all: '🌍 GPT4All', custom_openai: '🔌 自定义 OpenAI', local_clip: '🖼️ 本地 CLIP',
};

const flagCategories = computed(() => Array.from(new Set(flags.value.map((f: FeatureFlag) => f.category))));
function flagsByCategory(cat: string) { return flags.value.filter((f: FeatureFlag) => f.category === cat); }

function capLabel(c: string) {
  const map: Record<string, string> = { chat: '💬 对话', embed: '📐 向量', vision: '👁️ 视觉', audio: '🎤 语音', code: '💻 代码' };
  return map[c] || c;
}
function capColor(c: string) {
  const map: Record<string, string> = { chat: 'badge-primary', embed: 'badge-secondary', vision: 'badge-accent', code: 'badge-warning' };
  return map[c] || '';
}
function isModelSelected(m: AIModel) {
  return Object.values(selectedModels.value).some((v) => typeof v === 'string' && v.includes(m.id));
}
function epHealthClass(key: string) {
  const s = providerHealth.value[key]?.status;
  return s === 'online' ? 'badge-success' : s === 'available' ? 'badge-info' : s === 'not_configured' ? 'badge-ghost' : 'badge-error';
}
function epHealthLabel(key: string) {
  const s = providerHealth.value[key]?.status;
  return s === 'online' ? '在线' : s === 'available' ? '可用' : s === 'not_configured' ? '未配置' : '离线';
}

async function authFetch(url: string, opts: RequestInit = {}) {
  const t = authStore.token;
  if (!t) throw new Error('401');
  return fetch(`${API}${url}`, { ...opts, headers: { ...opts.headers, Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' } });
}

async function loadFlags() {
  flagsLoading.value = true;
  try { const r = await authFetch('/v1/settings/flags'); if (r.ok) flags.value = (await r.json()).data || []; }
  catch (e) { console.error(e); } finally { flagsLoading.value = false; }
}
async function toggleFlag(key: string) {
  toggling.value = key;
  try { const r = await authFetch(`/v1/settings/flags/${key}`, { method: 'PUT' }); if (r.ok) await loadFlags(); }
  catch (e) { console.error(e); } finally { toggling.value = null; }
}

async function loadSwitches() {
  switchesLoading.value = true;
  try {
    const r = await authFetch('/v1/switches');
    if (r.ok) {
      hardwareSwitches.value = await r.json();
    }
  } catch (e) { console.error('加载硬件开关失败:', e); } 
  finally { switchesLoading.value = false; }
}

async function toggleHwSwitch(name: string, newState: string) {
  togglingSwitch.value = name;
  try {
    const r = await authFetch(`/v1/switches/${name}`, {
      method: 'POST',
      body: JSON.stringify({ state: newState })
    });
    if (r.ok) {
      const updated = await r.json();
      hardwareSwitches.value[name] = updated;
    }
  } catch (e) { console.error('切换硬件开关失败:', e); } 
  finally { togglingSwitch.value = null; }
}

async function loadEndpoints() {
  endpointsLoading.value = true;
  try {
    const r = await authFetch('/v1/settings/ai-providers/endpoints');
    if (r.ok) {
      const d = await r.json();
      endpoints.value = d.endpoints || {};
      for (const [k, v] of Object.entries(endpoints.value)) {
        epUrls.value[k] = v.url || '';
      }
    }
    const h = await authFetch('/v1/settings/ai-providers/health');
    if (h.ok) providerHealth.value = (await h.json()).providers || {};
  } catch (e) { console.error(e); }
  finally { endpointsLoading.value = false; }
}

async function saveEndpoint(key: string) {
  savingEndpoint.value = key;
  endpointMsg.value = '';
  try {
    const r = await authFetch(`/v1/settings/ai-providers/${key}/url`, {
      method: 'PUT', body: JSON.stringify({ url: epUrls.value[key] || '' }),
    });
    const d = await r.json();
    if (r.ok) {
      endpointSuccess.value = true;
      endpointMsg.value = d.message + ' — 正在自动扫描模型...';
      // 保存后自动扫描全部模型
      const scanRes = await authFetch('/v1/settings/ai-models/scan', { method: 'POST' });
      if (scanRes.ok) {
        const sd = await scanRes.json();
        const g: Record<string, AIModel[]> = {};
        for (const m of (sd.models as AIModel[]) || []) { const p = m.provider || '?'; if (!g[p]) g[p] = []; g[p].push(m); }
        modelsByProvider.value = g;
        endpointMsg.value = d.message + ` ✅ 自动扫描完成，发现 ${sd.discovered || 0} 个模型`;
      }
    } else {
      endpointSuccess.value = false;
      endpointMsg.value = d.detail || '保存失败';
    }
    // 刷新健康状态
    const h = await authFetch('/v1/settings/ai-providers/health');
    if (h.ok) providerHealth.value = (await h.json()).providers || {};
  } catch (e) { endpointSuccess.value = false; endpointMsg.value = '网络异常'; }
  finally { savingEndpoint.value = null; }
}

async function loadModels() {
  modelsLoading.value = true;
  try {
    const r = await authFetch('/v1/settings/ai-models');
    if (r.ok) modelsByProvider.value = (await r.json()).by_provider || {};
    const s = await authFetch('/v1/settings/system');
    if (s.ok) selectedModels.value = (await s.json()).ai_models || {};
  } catch (e) { console.error(e); }
  finally { modelsLoading.value = false; }
}

async function scanModels() {
  scanning.value = true; switchMsg.value = '';
  try {
    const r = await authFetch('/v1/settings/ai-models/scan', { method: 'POST' });
    if (r.ok) {
      const d = await r.json();
      switchOk.value = true; switchMsg.value = d.message;
      const g: Record<string, AIModel[]> = {};
      for (const m of (d.models as AIModel[]) || []) { const p = m.provider || '?'; if (!g[p]) g[p] = []; g[p].push(m); }
      modelsByProvider.value = g;
    }
  } catch (e) { switchOk.value = false; switchMsg.value = '扫描失败'; }
  finally { scanning.value = false; }
}

async function selectModel(model: AIModel) {
  const caps = model.capabilities || ['chat'];
  const cap = caps.includes('embed') ? 'embed' : caps.includes('vision') ? 'vision' : 'chat';
  switchMsg.value = '';
  try {
    const r = await authFetch('/v1/settings/ai-model', {
      method: 'PUT', body: JSON.stringify({ capability: cap, model_id: model.id, provider: model.provider }),
    });
    const d = await r.json();
    if (r.ok) { switchOk.value = true; switchMsg.value = d.message; selectedModels.value[cap] = `${model.provider}:${model.id}`; }
    else { switchOk.value = false; switchMsg.value = d.detail || '选择失败'; }
  } catch (e) { switchOk.value = false; switchMsg.value = '网络异常'; }
}

async function loadNetConfig() {
  netLoading.value = true;
  try {
    const r = await authFetch('/v1/settings/config');
    if (r.ok) {
      const d = await r.json();
      const all: Record<string, { value: string }> = d.data || {};
      for (const item of [...netPortItems, ...netDomainItems, ...netPathItems]) {
        netVals.value[item.key] = all[item.key]?.value || '';
      }
    }
  } catch (e) { console.error(e); }
  finally { netLoading.value = false; }
}

async function saveNetVal(key: string) {
  savingNet.value = key; netMsg.value = '';
  try {
    const r = await authFetch(`/v1/settings/config/${key}`, {
      method: 'PUT', body: JSON.stringify({ value: netVals.value[key] || '' }),
    });
    const d = await r.json();
    if (r.ok) { netOk.value = true; netMsg.value = d.message; }
    else { netOk.value = false; netMsg.value = d.detail || '保存失败'; }
  } catch (e) { netOk.value = false; netMsg.value = '网络异常'; }
  finally { savingNet.value = null; }
}

async function loadSystemInfo() {
  sysLoading.value = true;
  try { const r = await authFetch('/v1/settings/system'); if (r.ok) sysInfo.value = await r.json(); }
  catch (e) { console.error(e); } finally { sysLoading.value = false; }
}

onMounted(async () => { await loadFlags(); loadModels(); loadSystemInfo(); });
</script>
