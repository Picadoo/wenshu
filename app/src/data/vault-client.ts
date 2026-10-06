import { papers } from './papers';
import { VAULT_CONTRACT, VAULT_ORIGIN } from './vault';

import type { Paper } from './papers';

export type VaultSourceKind = 'static' | 'http';

export type VaultSource = {
  kind: VaultSourceKind;
  baseUrl?: string;
};

export type VaultCatalog = {
  generatedAt: string;
  count: number;
  papers: Paper[];
};

const DEFAULT_SOURCE: VaultSource = {
  kind: 'static',
  baseUrl: VAULT_CONTRACT.publicRoot,
};

function joinUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

// 会话级缓存：切页签/并排/来回导航不重复拉同一篇 md（文库更新以刷新页面为界）
const textCache = new Map<string, Promise<string>>();
const TEXT_CACHE_LIMIT = 32;

export function fetchVaultText(path: string): Promise<string> {
  const cached = textCache.get(path);
  if (cached) {
    textCache.delete(path);
    textCache.set(path, cached);
    return cached;
  }
  const promise = fetch(path, { credentials: VAULT_ORIGIN ? 'omit' : 'include' }).then((response) => {
    if (!response.ok) {
      throw new Error(`文库读取失败 ${response.status}: ${path}`);
    }
    return response.text();
  });
  textCache.set(path, promise);
  if (textCache.size > TEXT_CACHE_LIMIT) textCache.delete(textCache.keys().next().value!);
  promise.catch(() => {
    if (textCache.get(path) === promise) textCache.delete(path);
  });
  return promise;
}

export async function fetchVaultCatalog(source: VaultSource = DEFAULT_SOURCE): Promise<VaultCatalog> {
  if (source.kind === 'http' && source.baseUrl) {
    const response = await fetch(joinUrl(source.baseUrl, 'catalog.json'));
    if (!response.ok) {
      throw new Error(`远程目录读取失败 ${response.status}`);
    }
    return response.json();
  }
  return {
    generatedAt: '',
    count: papers.length,
    papers,
  };
}

export function vaultIndexUrl(source: VaultSource = DEFAULT_SOURCE) {
  return source.baseUrl ? joinUrl(source.baseUrl, 'catalog.json') : VAULT_CONTRACT.catalog;
}
