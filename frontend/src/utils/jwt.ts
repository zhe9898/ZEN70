/** 解析 JWT payload（仅读取，不校验；校验由后端负责） */
export function decodePayload(token: string): { role?: string; sub?: string; username?: string } | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload as { role?: string; sub?: string; username?: string };
  } catch {
    return null;
  }
}
