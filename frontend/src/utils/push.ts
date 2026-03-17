/**
 * Web Push 订阅模块 (M5.3)
 */
// Base64Url 解析工具（VAPID 需要用到）
export function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export async function initWebPush() {
  // 1. 检查浏览器是否支持 Service Worker 和 PushManager
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.warn("当前浏览器不支持 Web Push");
    return false;
  }

  try {
    // 2. 只有在此之前已经授权过，或者主动调起 requestPermission，才继续
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.warn("用户拒绝了通知权限");
      return false;
    }

    // 3. 等待 PWA Service Worker 就绪
    const registration = await navigator.serviceWorker.ready;

    // 获取当前已有的订阅
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      // 4. 去后端拿 VAPID 公钥
      const res = await fetch("/api/v1/auth/push/vapid-public-key");
      if (!res.ok) throw new Error("无法获取 VAPID 公钥");
      const { vapid_public_key } = await res.json();
      
      const convertedVapidKey = urlBase64ToUint8Array(vapid_public_key);
      
      // 5. 调用浏览器原生注册
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedVapidKey
      });
    }

    // 6. 将 subscription 序列化通过 API 传给后端
    const subJSON = subscription.toJSON();
    if (subJSON.endpoint && subJSON.keys) {
      const token = localStorage.getItem("zen70-token");
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      await fetch("/api/v1/auth/push/subscribe", {
        method: "POST",
        headers,
        body: JSON.stringify({
          endpoint: subJSON.endpoint,
          keys: subJSON.keys,
          user_agent: navigator.userAgent
        })
      });
    }

    console.log("Web Push 订阅成功并上报");
    return true;

  } catch (err: unknown) {
    console.error("Web Push 订阅全链路失败", err);
    return false;
  }
}
