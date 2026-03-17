<template>
  <div class="min-h-screen flex items-center justify-center bg-base-300 pointer-events-auto relative z-20">
    <div class="card w-full max-w-sm bg-base-100 shadow-xl">
      <div class="card-body items-center text-center">
        
        <div v-if="loading" class="py-8">
          <span class="loading loading-spinner loading-lg text-primary"></span>
        </div>
        
        <template v-else-if="errorMsg">
          <h2 class="card-title text-error mb-2">邀请已失效</h2>
          <p class="text-sm text-base-content/70 mb-4">{{ errorMsg }}</p>
          <button class="btn" @click="goHome">返回首页</button>
        </template>
        
        <template v-else-if="successMsg">
          <div class="text-success mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-16 h-16 mx-auto">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 class="card-title text-success mb-2">绑定成功</h2>
          <p class="text-sm text-base-content/70 mb-6">{{ successMsg }}</p>
          <button class="btn btn-primary" @click="enterSystem">进入系统</button>
        </template>
        
        <template v-else>
          <div class="bg-primary/10 p-4 rounded-full mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-10 h-10 text-primary">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
            </svg>
          </div>
          <h2 class="card-title text-primary mb-2">ZEN70 授权邀请</h2>
          <p class="text-sm text-base-content/70 mb-6">
            指挥官已向您下发系统访问凭证。<br/>
            请验证您的生物特征（Face ID / 指纹）以将此设备物理绑定至家庭私有云。
          </p>
          
          <button class="btn btn-primary w-full mb-3" :disabled="processing" @click="bindDevice">
            <span v-if="processing" class="loading loading-spinner loading-sm"></span>
            验证身份并绑定本机
          </button>
          
          <button class="btn w-full btn-outline btn-sm text-base-content/60" :disabled="processing" @click="fallbackLogin">
            硬件不支持？直接免密登入
          </button>
        </template>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { startRegistration } from '@simplewebauthn/browser';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const token = ref<string>('');
const loading = ref(true);
const processing = ref(false);
const errorMsg = ref('');
const successMsg = ref('');

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

onMounted(() => {
  const qToken = route.query.token as string;
  if (!qToken) {
    errorMsg.value = "缺少有效的邀请凭证";
  } else {
    token.value = qToken;
  }
  loading.value = false;
});

async function bindDevice() {
  processing.value = true;
  errorMsg.value = "";
  try {
    // 1. 发起注册，获取 Options
    const beginRes = await fetch(`${API_BASE}/v1/auth/invites/${token.value}/webauthn/register/begin`, {
      method: 'POST'
    });
    const beginData = await beginRes.json();
    if (!beginRes.ok) throw new Error(beginData.detail || '会话启动失败');
    
    // 2. 唤起手机原生 WebAuthn 面板 (Face ID / Touch ID)
    const credential = await startRegistration(beginData.options);
    
    // 3. 将注册结果发回服务器，完成物理绑定与 Token 销毁
    const completeRes = await fetch(`${API_BASE}/v1/auth/invites/${token.value}/webauthn/register/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential })
    });
    
    const completeData = await completeRes.json();
    if (!completeRes.ok) throw new Error(completeData.detail || '物理绑定失败');
    
    // 4. 保存登录态
    authStore.setToken(completeData.access_token);
    successMsg.value = "您的设备已通过最高级别安全认证！";
    
  } catch (err: any) {
    console.error(err);
    errorMsg.value = err.message || "由于安全原因，认证流程已中止。";
  } finally {
    processing.value = false;
  }
}

async function fallbackLogin() {
  processing.value = true;
  errorMsg.value = "";
  try {
    const res = await fetch(`${API_BASE}/v1/auth/invites/${token.value}/fallback/login`, {
      method: 'POST'
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '免密登入失败');
    
    // 保存登录态，降级无需硬件签名
    authStore.setToken(data.access_token);
    successMsg.value = "已通过降级模式免密登入系统。";
  } catch (err: any) {
    console.error(err);
    errorMsg.value = err.message || "降级登入失败。";
  } finally {
    processing.value = false;
  }
}

function goHome() {
  router.push('/login');
}

function enterSystem() {
  if (authStore.isAdmin) {
    router.push('/');
  } else {
    router.push('/family');
  }
}
</script>
