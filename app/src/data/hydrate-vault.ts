import { useSyncExternalStore } from 'react';

import { hydrateActivity } from './activity';
import { hydrateTerms } from './terms';
import { hydratePapers } from './papers';
import { VAULT_ORIGIN, VAULT_CONTRACT } from './vault';

import type { TermEntry } from './terms';
import type { ActivityData } from './activity';
import type { Paper, TopicDoc } from './papers';

// ----------------------------------------------------------------------
// 水化成功后递增：侧栏计数、论文库 useMemo 才能看到新目录（原地改数组不会触发 React）

let vaultEpoch = 0;
const vaultListeners = new Set<() => void>();

function emitVaultEpoch() {
  vaultEpoch += 1;
  vaultListeners.forEach((listener) => listener());
}

function subscribeVaultEpoch(listener: () => void) {
  vaultListeners.add(listener);
  return () => {
    vaultListeners.delete(listener);
  };
}

export function useVaultEpoch() {
  return useSyncExternalStore(
    subscribeVaultEpoch,
    () => vaultEpoch,
    () => 0
  );
}

// ----------------------------------------------------------------------

type CatalogJson = { papers?: Paper[]; topicDocs?: TopicDoc[] };
type TermsJson = { terms?: TermEntry[] };

let lastFingerprint = '';
let catalogInitialized = false;
let termsInitialized = false;

function catalogFingerprint(
  catalog: CatalogJson | null,
  termsData: TermsJson | null,
  activityData: ActivityData | null
) {
  const slugs = (catalog?.papers ?? []).map((item) => item.slug).join(',');
  return `${slugs}|${termsData?.terms?.length ?? 0}|${activityData?.generatedAt ?? ''}`;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    // no-cache（而非 no-store）：仍每次向服务器确认新鲜度，但内容没变时走 ETag 304，省下反复全量下载
    const response = await fetch(url, {
      cache: 'no-cache',
      credentials: VAULT_ORIGIN ? 'omit' : 'include',
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/**
 * 启动时从 vault 静态 JSON 水化目录/术语/活动数据。
 * 服务器上只更新 vault 目录（不重新构建）即可让新论文出现；
 * 初次拉取失败才加载构建兜底；已初始化时保留现有数据。
 */
export async function hydrateVaultData() {
  const root = VAULT_CONTRACT.publicRoot;
  const [catalog, termsData, activityData] = await Promise.all([
    fetchJson<CatalogJson>(VAULT_CONTRACT.catalog).then(async (data) => {
      if (Array.isArray(data?.papers) || catalogInitialized) return data;
      const { generatedPapers, generatedTopicDocs } = await import('./generated-catalog');
      return { papers: generatedPapers, topicDocs: generatedTopicDocs };
    }),
    fetchJson<TermsJson>(`${root}/terms.json`).then(async (data) => {
      if (Array.isArray(data?.terms) || termsInitialized) return data;
      const { generatedTerms } = await import('./generated-terms');
      return { terms: generatedTerms };
    }),
    fetchJson<ActivityData>(`${root}/activity.json`),
  ]);

  let changed = false;
  if (Array.isArray(catalog?.papers)) {
    hydratePapers(catalog.papers, catalog.topicDocs ?? []);
    catalogInitialized = true;
    changed = true;
  }
  if (Array.isArray(termsData?.terms)) {
    hydrateTerms(termsData.terms);
    termsInitialized = true;
    changed = true;
  }
  if (activityData?.days) {
    hydrateActivity(activityData);
    changed = true;
  }

  const fingerprint = catalogFingerprint(catalog, termsData, activityData);
  if (changed && fingerprint !== lastFingerprint) {
    lastFingerprint = fingerprint;
    emitVaultEpoch();
  }
}
