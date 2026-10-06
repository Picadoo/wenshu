import { papers } from './papers';
import { fetchVaultCatalog } from './vault-client';

import type { Paper } from './papers';
import type { VaultSource } from './vault-client';

export async function listPapers(source?: VaultSource): Promise<Paper[]> {
  if (source?.kind === 'http' && source.baseUrl) {
    const catalog = await fetchVaultCatalog(source);
    return catalog.papers;
  }
  return papers;
}

export async function getPaperBySlug(slug: string, source?: VaultSource): Promise<Paper | undefined> {
  const list = await listPapers(source);
  return list.find((item) => item.slug === slug);
}
