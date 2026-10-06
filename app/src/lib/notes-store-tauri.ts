import TurndownService from 'turndown';

import { papers } from 'src/data/papers';
import { localIsoDate } from 'src/data/activity';

import { loadPaperData, listLocalSlugs, registerNotesBackend } from './notes-store';

import type { NotesBackend, PaperUserData } from './notes-store';

// ----------------------------------------------------------------------

export function isTauri() {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

type AppConfig = {
  vaultDir?: string;
  webVaultDir?: string;
};

let cachedConfig: AppConfig | null = null;

async function tauriInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(command, args);
}

async function loadConfig(): Promise<AppConfig> {
  if (cachedConfig) return cachedConfig;
  try {
    const raw = await tauriInvoke<string>('get_config');
    cachedConfig = JSON.parse(raw || '{}') as AppConfig;
  } catch {
    cachedConfig = {};
  }
  return cachedConfig;
}

export async function getVaultDir(): Promise<string> {
  const config = await loadConfig();
  return config.vaultDir ?? '';
}

export async function chooseVaultDir(): Promise<string> {
  const { open } = await import('@tauri-apps/plugin-dialog');
  const dir = await open({ directory: true, title: '选择 vault 文库目录（Obsidian 库根目录）' });
  if (typeof dir !== 'string' || !dir) return '';
  cachedConfig = { ...(await loadConfig()), vaultDir: dir };
  await tauriInvoke('set_config', { contents: JSON.stringify(cachedConfig, null, 2) });
  return dir;
}

/** 阅读镜像与笔记文库分别配置，避免把源 vault 误当同步目录。 */
export async function getWebVaultDir(): Promise<string> {
  return (await loadConfig()).webVaultDir ?? '';
}

export async function chooseWebVaultDir(): Promise<string> {
  const { open } = await import('@tauri-apps/plugin-dialog');
  const dir = await open({ directory: true, title: '选择阅读镜像目录（含 catalog.json）' });
  if (typeof dir !== 'string' || !dir) return '';
  cachedConfig = { ...(await loadConfig()), webVaultDir: dir };
  await tauriInvoke('set_config', { contents: JSON.stringify(cachedConfig, null, 2) });
  return dir;
}

function joinPath(...parts: string[]) {
  return parts
    .map((part) => part.replace(/[\\/]+$/, ''))
    .join('/')
    .replace(/\\/g, '/');
}

const turndown = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });

const lastActivityLog = new Map<string, number>();

async function appendActivity(vaultDir: string, slug: string) {
  const now = Date.now();
  const last = lastActivityLog.get(slug) ?? 0;
  if (now - last < 10 * 60 * 1000) return; // 同一篇 10 分钟内只记一次
  lastActivityLog.set(slug, now);
  const entry = { date: localIsoDate(), type: 'save', slug };
  await tauriInvoke('append_line', {
    path: joinPath(vaultDir, '90_系统', '_活动日志.jsonl'),
    line: JSON.stringify(entry),
  });
}

function annotationPath(vaultDir: string, slug: string) {
  return joinPath(vaultDir, '90_系统', '_web批注', `${slug}.json`);
}

const fileBackend: NotesBackend = {
  kind: 'file',

  async load(slug: string): Promise<PaperUserData | null> {
    const vaultDir = await getVaultDir();
    if (!vaultDir) return null;
    const path = annotationPath(vaultDir, slug);
    const exists = await tauriInvoke<boolean>('file_exists', { path });
    if (!exists) return null;
    const raw = await tauriInvoke<string>('read_text', { path });
    return JSON.parse(raw) as PaperUserData;
  },

  async save(slug: string, data: PaperUserData): Promise<void> {
    const vaultDir = await getVaultDir();
    if (!vaultDir) return;

    await tauriInvoke('write_text', {
      path: annotationPath(vaultDir, slug),
      contents: JSON.stringify(data, null, 2),
    });

    const paper = papers.find((item) => item.slug === slug);

    // 我的笔记镜像成 markdown，Obsidian 直接可读
    if (paper && data.note) {
      const markdown = turndown.turndown(data.note);
      await tauriInvoke('write_text', {
        path: joinPath(vaultDir, paper.vault.folder, 'content', `${paper.pid}.我的笔记.md`),
        contents: `---\nnoteType: mynote\npaper: "[[${paper.pid}]]"\nsource: 文枢桌面版\n---\n\n${markdown}\n`,
      });
    }

    // 生词清单镜像
    if (paper && data.vocab.length) {
      const lines = data.vocab.map((entry) => `- **${entry.word}** — ${entry.context || '（无上下文）'}`);
      await tauriInvoke('write_text', {
        path: joinPath(vaultDir, '90_系统', '_生词', `${slug}.md`),
        contents: `# ${paper.title} · 生词清单\n\n${lines.join('\n')}\n`,
      });
    }

    await appendActivity(vaultDir, slug);
  },
};

/** 应用启动时调用：在 Tauri 环境注册文件后端。 */
export async function initTauriNotesBackend() {
  if (!isTauri()) return false;
  registerNotesBackend(fileBackend);
  return true;
}

/** 把浏览器 localStorage 里的笔记数据一键迁移到 vault 文件。 */
export async function migrateLocalToVault(): Promise<number> {
  const vaultDir = await getVaultDir();
  if (!vaultDir) return 0;
  const slugs = listLocalSlugs();
  let migrated = 0;
  await Promise.all(
    slugs.map(async (slug) => {
      const data = loadPaperData(slug);
      if (!data.note && !data.highlights.length && !data.vocab.length) return;
      await fileBackend.save(slug, data);
      migrated += 1;
    })
  );
  return migrated;
}
