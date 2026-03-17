/** API 基地址，SSE 等需完整 URL 时使用 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export const API = {
  events: () => `${API_BASE}/v1/events`,
  switch: (name: string) => `${API_BASE}/v1/switches/${name}`,
} as const;
