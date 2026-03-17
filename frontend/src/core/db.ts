import Dexie, { type Table } from 'dexie';

export interface CachedAsset {
  id: string;
  url: string;
  base64Data: string;
  timestamp: number;
}

export class Zen70OfflineDB extends Dexie {
  cachedAssets!: Table<CachedAsset, string>;

  constructor() {
    super('Zen70OfflineDB');
    this.version(1).stores({
      cachedAssets: 'id, url, timestamp' // Primary key and indexed props
    });
  }
}

export const db = new Zen70OfflineDB();

export const cacheImage = async (id: string, url: string) => {
    try {
        // 先检查是否已有缓存
        const existing = await db.cachedAssets.get(id);
        if (existing) return;

        // Fetch 并转为 Base64
        const response = await fetch(url);
        if (!response.ok) return;
        
        const blob = await response.blob();
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        
        reader.onloadend = async () => {
            const base64data = reader.result as string;
            await db.cachedAssets.put({
                id,
                url,
                base64Data: base64data,
                timestamp: Date.now()
            });
        };
    } catch (e) {
        console.warn('Failed to cache image for offline use:', e);
    }
};

export const getCachedImage = async (id: string): Promise<string | null> => {
    try {
        const record = await db.cachedAssets.get(id);
        return record ? record.base64Data : null;
    } catch (e) {
        return null;
    }
};
