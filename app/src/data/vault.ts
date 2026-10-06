/**
 * paper-ingest 技能产物约定。
 *
 * 文库源在仓库旁的 vault/。构建前运行：
 *   python scripts/sync-vault.py
 * 会把每篇集群拷到 public/vault/papers/<slug>/，并生成 catalog。
 *
 * 技能实际落盘：
 *   Papers/<领域>/<pid>.md                         索引中枢
 *   Papers/<领域>/<英文文件夹>/content/<pid>.正文.md
 *   Papers/<领域>/<英文文件夹>/content/<pid>.正文.en.md
 *   Papers/<领域>/<英文文件夹>/content/<pid>.notes.md
 *   Papers/<领域>/<英文文件夹>/content/<pid>.cards.md
 *   Papers/<领域>/<英文文件夹>/content/<pid>.pdf
 *   Papers/<领域>/<英文文件夹>/content/<pid>.txt
 *   Papers/<领域>/<英文文件夹>/images/*
 *
 * 前端同步后的稳定 URL：
 *   /vault/catalog.json
 *   /vault/papers/<slug>/index.md
 *   /vault/papers/<slug>/content/<pid>.*
 *   /vault/papers/<slug>/images/*
 */

/**
 * 桌面版通过自定义协议读取示例库或用户选择的阅读镜像。
 * Web 版静态资源遵循 Vite base，可部署在站点子目录。
 */
import { appAssetUrl } from 'src/lib/app-env';

export const VAULT_ORIGIN =
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window ? 'http://vault.localhost' : '';
const VAULT_ROOT = VAULT_ORIGIN ? `${VAULT_ORIGIN}/vault` : appAssetUrl('vault');

/** catalog 和构建兜底共用源文库路径，读取时补上部署 base 或桌面协议。 */
export function withVaultOrigin<T>(data: T): T {
  if (VAULT_ROOT === '/vault') return data;
  return JSON.parse(
    JSON.stringify(data).split('"/vault/').join(`"${VAULT_ROOT}/`)
  ) as T;
}

export const VAULT_CONTRACT = {
  remote: false,
  publicRoot: VAULT_ROOT,
  catalog: `${VAULT_ROOT}/catalog.json`,
  files: {
    index: '<pid>.md',
    indexAlias: '<pid>.index.md',
    article: 'content/<pid>.正文.md',
    articleEn: 'content/<pid>.正文.en.md',
    articleAlias: 'content/<pid>.md',
    notes: 'content/<pid>.notes.md',
    cards: 'content/<pid>.cards.md',
    pdf: 'content/<pid>.pdf',
    txt: 'content/<pid>.txt',
  },
} as const;

export function vaultPublicDir(slug: string) {
  return `${VAULT_CONTRACT.publicRoot}/papers/${slug}`;
}

export function vaultPaths(slug: string) {
  const root = vaultPublicDir(slug);
  return {
    folder: root,
    index: `${root}/index.md`,
    article: `${root}/content`,
    articleEn: `${root}/content`,
    notes: `${root}/content`,
    cards: `${root}/content`,
    pdf: `${root}/content`,
    txt: `${root}/content`,
    images: `${root}/images`,
  };
}
