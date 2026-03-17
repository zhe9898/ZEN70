import Dexie, { type Table } from "dexie";
import type { Capabilities } from "@/types/capability";
import type { SwitchState } from "@/types/switch";

class Zen70Db extends Dexie {
  capabilities!: Table<{ key: string; data: Capabilities; updated: number }>;
  switches!: Table<{ name: string; data: SwitchState; updated: number }>;

  constructor() {
    super("Zen70Db");
    this.version(1).stores({ capabilities: "key", switches: "name" });
  }
}

const db = new Zen70Db();
const CAP_KEY = "latest";
const SW_PREFIX = "switch:";

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch (_err) {
    return fallback;
  }
}

export async function cacheCapabilities(caps: Capabilities): Promise<void> {
  await safe(() => db.capabilities.put({ key: CAP_KEY, data: caps, updated: Date.now() }), undefined);
}

export async function getCachedCapabilities(): Promise<Capabilities | null> {
  const row = await safe(() => db.capabilities.get(CAP_KEY), null);
  return row?.data ?? null;
}

export async function cacheSwitch(name: string, data: SwitchState): Promise<void> {
  await safe(() => db.switches.put({ name: SW_PREFIX + name, data, updated: Date.now() }), undefined);
}

export async function getCachedSwitches(): Promise<Record<string, SwitchState>> {
  const rows = await safe(() => db.switches.where("name").startsWith(SW_PREFIX).toArray(), []);
  const out: Record<string, SwitchState> = {};
  for (const r of rows) {
    out[r.name.slice(SW_PREFIX.length)] = r.data;
  }
  return out;
}
