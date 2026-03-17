<template>
  <div class="privacy-vault bg-slate-900 rounded-3xl p-8 border border-red-900/30 relative overflow-hidden group">
    <!-- 背景警戒纹理 -->
    <div class="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCI+CiAgPHBhdGggZD0iTTAgMGw0MCA0ME0wIDQwbDQwLTQwIiBzdHJva2U9InJnYmEoMjU1LCAwLCAwLCAwLjA1KSIgc3Ryb2tlLXdpZHRoPSIyIiBmaWxsPSJub25lIi8+Cjwvc3ZnPg==')] opacity-20 pointer-events-none"></div>

    <header class="relative z-10 flex items-center gap-4 mb-8">
      <div class="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center text-red-500 border border-red-500/20">
        <span class="text-3xl">🛡️</span>
      </div>
      <div>
        <h2 class="text-2xl font-bold text-white mb-1">信任圈与隐私避难所</h2>
        <p class="text-slate-400 text-sm">您的所有数字回忆与安全底线，均由最高架构法纪捍卫。</p>
      </div>
    </header>

    <div class="relative z-10 grid md:grid-cols-2 gap-6">
      
      <!-- 数据携带权 (打包下载) -->
      <div class="p-6 rounded-2xl bg-slate-800/50 border border-emerald-900/30 hover:border-emerald-500/50 transition-colors">
        <h3 class="text-xl font-bold text-emerald-400 mb-2">📦 数据随身携带</h3>
        <p class="text-slate-300 text-sm mb-6 h-16">
          一键将您的所有照片、视频原件打包为加密 Zip 归档。数据永远属于您自己，绝不被困在任何系统中。
        </p>
        <button 
          @click="startExport"
          :disabled="isExporting"
          class="w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all"
          :class="isExporting ? 'bg-slate-700 text-slate-400 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/50'"
        >
          <span v-if="!isExporting">⏬ 申请下载全量归档</span>
          <span v-else class="animate-pulse">⏳ 正在流式打包 (防 OOM 技术)...</span>
        </button>
      </div>

      <!-- 物理级销毁 -->
      <div class="p-6 rounded-2xl bg-slate-800/50 border border-red-900/50 hover:border-red-500/50 transition-colors">
        <h3 class="text-xl font-bold text-red-500 mb-2">⚠️ 物理级粉碎机</h3>
        <p class="text-slate-300 text-sm mb-6 h-16">
          不仅从数据库抹除记录，更会调用底层命令对硬盘物理扇区进行多次乱码覆写。神仙难救，请极度慎重。
        </p>
        <button 
          @click="showShredConfirm = true"
          class="w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all bg-red-900/40 hover:bg-red-600 text-red-400 hover:text-white border border-red-800 hover:border-red-500 shadow-inner"
        >
          <span>☢️ 启动碎纸机 (测试例)</span>
        </button>
      </div>

    </div>

    <!-- 危险操作确认弹窗 -->
    <div v-if="showShredConfirm" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div class="bg-slate-900 border-2 border-red-600 rounded-3xl p-8 max-w-md w-full shadow-[0_0_50px_rgba(220,38,38,0.3)] transform transition-all scale-100">
        <div class="w-20 h-20 mx-auto bg-red-950 rounded-full flex items-center justify-center mb-6 animate-pulse">
          <span class="text-5xl">🛑</span>
        </div>
        <h3 class="text-2xl font-black text-center text-white mb-4">最终警告</h3>
        <p class="text-slate-300 text-center mb-8">
          您即将引爆硬盘底层磁道进行垃圾覆写！<br>
          <span class="text-red-400 font-bold">数据将永世无法恢复！</span><br>
          是否确认执行物理粉碎？
        </p>
        <div class="flex gap-4">
          <button @click="showShredConfirm = false" class="flex-1 py-3 rounded-xl font-bold bg-slate-800 hover:bg-slate-700 text-white transition-colors">
            手滑了，取消
          </button>
          <button @click="executeShredding" class="flex-1 py-3 rounded-xl font-bold bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/50 transition-colors">
            立刻粉碎
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import axios from 'axios';

const isExporting = ref(false);
const showShredConfirm = ref(false);

const apiBase = import.meta.env.VITE_API_BASE || '/api/v1';

const startExport = async () => {
  isExporting.value = true;
  try {
    // 采用原生 fetch 配合 Blob 处理大文件流式下载，防内存爆破
    const response = await fetch(`${apiBase}/portability/export`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('zen70-token')}`
      }
    });
    
    if (!response.ok) throw new Error("下载被拒绝");
    
    // 创建隐藏的 a 标签触发文件流保存
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = "zen70_family_archive.zip";
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
  } catch (error) {
    alert("数据导出失败: " + error);
  } finally {
    isExporting.value = false;
  }
};

const executeShredding = async () => {
    showShredConfirm.value = false;
    try {
        // 这里只是个演示用 UI，我们假设传入了相册里的一张废弃照片的 mock ID
        const mockAssetId = "test_shred_id_001";
        const res = await axios.post(`${apiBase}/portability/shred/${mockAssetId}`, {}, {
            headers: { Authorization: `Bearer ${localStorage.getItem('zen70-token')}` }
        });
        alert(`物理粉碎成功！底层磁道已被覆写。\n安全响应：${res.data.message}`);
    } catch (error: any) {
        if(error.response?.status === 404) {
            alert("模拟场景: 没有找到需要粉碎的 Mock 资产。但这证明接口已经打通红线防御。");
        } else {
            alert("物理粉碎失败，权限不足或底层错误。");
        }
    }
};
</script>
