<template>
  <div class="min-h-screen flex items-center justify-center bg-base-300">
    <div class="card w-full max-w-sm bg-base-100 shadow-xl">
      <div class="card-body">
        
        <div v-if="loading" class="flex justify-center py-8">
          <span class="loading loading-spinner loading-lg text-primary"></span>
        </div>

        <template v-else-if="viewState === 'bootstrap'">
          <h2 class="card-title justify-center text-primary mb-2">ZEN70 初始化</h2>
          <p class="text-sm text-base-content/70 text-center mb-6">
            系统检测到首次运行，请创建首个控制台管理员账号。
          </p>
          
          <form @submit.prevent="handleBootstrap">
            <div class="form-control mb-4">
              <label class="label"><span class="label-text">管理员账号</span></label>
              <input v-model="bootForm.username" type="text" placeholder="admin" class="input input-bordered w-full" required />
            </div>
            <div class="form-control mb-4">
              <label class="label"><span class="label-text">显示名称</span></label>
              <input v-model="bootForm.displayName" type="text" placeholder="主理人" class="input input-bordered w-full" />
            </div>
            <div class="form-control mb-6">
              <label class="label"><span class="label-text">安全密码 (至少8位)</span></label>
              <input v-model="bootForm.password" type="password" placeholder="••••••••" class="input input-bordered w-full" required minlength="8" />
            </div>
            <div v-if="errorMsg" class="alert alert-error text-sm py-2 mb-4">{{ errorMsg }}</div>
            <button type="submit" class="btn btn-primary w-full" :disabled="submitting">
              <span v-if="submitting" class="loading loading-spinner loading-sm"></span>
              接管系统
            </button>
          </form>
        </template>

        <template v-else-if="viewState === 'login'">
          <h2 class="card-title justify-center mb-6">ZEN70 登录</h2>
          
          <form @submit.prevent="handleLogin">
            <div class="form-control mb-4">
              <label class="label"><span class="label-text">账号</span></label>
              <input v-model="loginForm.username" type="text" placeholder="admin / family" class="input input-bordered w-full" required />
            </div>
            <div class="form-control mb-6">
              <label class="label"><span class="label-text">密码</span></label>
              <input v-model="loginForm.password" type="password" placeholder="••••••••" class="input input-bordered w-full" required />
            </div>
            <div v-if="errorMsg" class="alert alert-error text-sm py-2 mb-4">{{ errorMsg }}</div>
            <button type="submit" class="btn btn-primary w-full" :disabled="submitting">
              <span v-if="submitting" class="loading loading-spinner loading-sm"></span>
              安全登录
            </button>
            
            <div class="divider text-xs text-base-content/50">或者</div>
            
            <button type="button" class="btn btn-outline w-full" @click="handleWebAuthn">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5 mr-2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M7.864 4.243A7.5 7.5 0 0119.5 10.5c0 2.92-.556 5.709-1.568 8.268M5.742 6.364A7.465 7.465 0 004.5 10.5a7.464 7.464 0 01-1.15 3.993m1.989 3.559A11.209 11.209 0 008.25 10.5a3.75 3.75 0 117.5 0c0 .527-.021 1.049-.064 1.565M12 10.5a14.94 14.94 0 01-3.6 9.75M19.5 10.5h.008v.008H19.5V10.5z" />
              </svg>
              通行密钥验证
            </button>
          </form>
        </template>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

const loading = ref(true);
const submitting = ref(false);
const viewState = ref<"bootstrap" | "login">("login");
const errorMsg = ref("");

const bootForm = ref({ username: "", password: "", displayName: "" });
const loginForm = ref({ username: "", password: "" });

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

onMounted(async () => {
  try {
    const res = await fetch(`${API_BASE}/v1/auth/sys/status`);
    const data = await res.json();
    if (data.is_empty) {
      viewState.value = "bootstrap";
    } else {
      viewState.value = "login";
    }
  } catch (err) {
    errorMsg.value = "无法连接至网关探针";
  } finally {
    loading.value = false;
  }
});

async function handleBootstrap() {
  submitting.value = true;
  errorMsg.value = "";
  try {
    const res = await fetch(`${API_BASE}/v1/auth/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: bootForm.value.username,
        password: bootForm.value.password,
        display_name: bootForm.value.displayName || "Admin",
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.message || "初始化失败");
    
    auth.setToken(data.access_token);
    router.push("/");
  } catch (err: any) {
    errorMsg.value = err.message;
  } finally {
    submitting.value = false;
  }
}

async function handleLogin() {
  submitting.value = true;
  errorMsg.value = "";
  try {
    const res = await fetch(`${API_BASE}/v1/auth/password/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(loginForm.value)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.message || "登录失败");
    
    auth.setToken(data.access_token);
    
    // Redirect based on role
    if (auth.isAdmin) {
      router.push("/");
    } else {
      router.push("/family");
    }
  } catch (err: any) {
    errorMsg.value = err.message;
  } finally {
    submitting.value = false;
  }
}

function handleWebAuthn() {
  // TODO: Implement WebAuthn integration
  errorMsg.value = "通行密钥验证尚未完全实现";
}
</script>
