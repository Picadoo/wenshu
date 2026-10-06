import { recordLocalActivity } from 'src/data/activity';

// ----------------------------------------------------------------------

export type HighlightEntry = {
  id: string;
  tab: string;
  block: number;
  start: number;
  end: number;
  text: string;
  createdAt: string;
};

export type VocabEntry = {
  word: string;
  context: string;
  createdAt: string;
};

/** 阅读状态（本地标记；与 vault index 的 reading 字段并存，本地优先展示） */
export type ReadingMark = '' | '在读' | '已读' | '重读';

export function readingMarkColor(mark: string) {
  if (mark === '在读') return 'info' as const;
  if (mark === '已读') return 'success' as const;
  if (mark === '重读') return 'primary' as const;
  return 'default' as const;
}

/** 待引用：读的时候打算用；已引用：自己文稿里已经用过。 */
export type CiteMark = '' | '待引用' | '已引用';

export type PaperFlags = {
  reading: ReadingMark;
  /** 重点论文 */
  starred: boolean;
  cite: CiteMark;
};

export function normalizeFlags(raw?: Partial<PaperFlags> & { cited?: boolean }): PaperFlags {
  const cite: CiteMark =
    raw?.cite === '待引用' || raw?.cite === '已引用'
      ? raw.cite
      : raw?.cited
        ? '已引用'
        : '';
  return {
    reading: raw?.reading || '',
    starred: Boolean(raw?.starred),
    cite,
  };
}

export type PaperUserData = {
  note: string;
  highlights: HighlightEntry[];
  vocab: VocabEntry[];
  flags: PaperFlags;
  updatedAt: string;
};

export const EMPTY_FLAGS: PaperFlags = { reading: '', starred: false, cite: '' };

export const EMPTY_USER_DATA: PaperUserData = {
  note: '',
  highlights: [],
  vocab: [],
  flags: { ...EMPTY_FLAGS },
  updatedAt: '',
};

/**
 * 后端抽象：浏览器阶段只有 localStorage；桌面版（Tauri）注册文件后端，
 * 笔记/高亮/生词直接写回 vault，并记活动日志。
 */
export interface NotesBackend {
  kind: 'file' | 'local' | 'http';
  load: (slug: string) => Promise<PaperUserData | null>;
  save: (slug: string, data: PaperUserData) => Promise<void>;
}

let fileBackend: NotesBackend | null = null;

export function registerNotesBackend(backend: NotesBackend | null) {
  fileBackend = backend;
}

export function getNotesBackend() {
  return fileBackend;
}

function storageKey(slug: string) {
  return `wenshu.notes.${slug}`;
}

function emptyUserData(): PaperUserData {
  return {
    note: '',
    highlights: [],
    vocab: [],
    flags: { ...EMPTY_FLAGS },
    updatedAt: '',
  };
}

export function loadPaperData(slug: string): PaperUserData {
  if (!slug) return emptyUserData();
  try {
    const raw = window.localStorage.getItem(storageKey(slug));
    if (!raw) return emptyUserData();
    const parsed = JSON.parse(raw) as Partial<PaperUserData>;
    return {
      note: parsed.note ?? '',
      highlights: parsed.highlights ?? [],
      vocab: parsed.vocab ?? [],
      flags: normalizeFlags(parsed.flags),
      updatedAt: parsed.updatedAt ?? '',
    };
  } catch {
    return emptyUserData();
  }
}

const pendingSaves = new Map<string, number>();

function scheduleBackendSave(slug: string, data: PaperUserData) {
  if (!fileBackend) return;
  const existing = pendingSaves.get(slug);
  if (existing) window.clearTimeout(existing);
  pendingSaves.set(
    slug,
    window.setTimeout(() => {
      pendingSaves.delete(slug);
      void fileBackend?.save(slug, data).catch((error: unknown) => {
        window.dispatchEvent(new CustomEvent('wenshu-save-error', { detail: error instanceof Error ? error.message : '笔记文件保存失败' }));
      });
    }, 1500)
  );
}

export function savePaperData(slug: string, patch: Partial<PaperUserData>): PaperUserData {
  if (!slug) return emptyUserData();
  const next: PaperUserData = {
    ...loadPaperData(slug),
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(storageKey(slug), JSON.stringify(next));
  } catch {
    throw new Error('本机笔记保存失败：请检查浏览器存储空间或权限');
  }
  recordLocalActivity();
  scheduleBackendSave(slug, next);
  return next;
}

/** 显式保存时等待文件/云端写入，错误由界面显示。 */
export async function flushNotesBackend(slug: string) {
  const pending = pendingSaves.get(slug);
  if (pending) window.clearTimeout(pending);
  pendingSaves.delete(slug);
  if (fileBackend) await fileBackend.save(slug, loadPaperData(slug));
}

/** 桌面版启动后：把文件后端里的数据合并进来（文件优先，本地缺失时保留本地）。 */
export async function hydrateFromBackend(slug: string): Promise<PaperUserData> {
  if (!slug) return emptyUserData();
  if (!fileBackend) return loadPaperData(slug);
  try {
    const remote = await fileBackend.load(slug);
    const local = loadPaperData(slug);
    if (!remote) return local;
    if (local.updatedAt && (!remote.updatedAt || local.updatedAt >= remote.updatedAt)) {
      return local;
    }
    const merged: PaperUserData = {
      note: remote.note || local.note,
      highlights: remote.highlights.length ? remote.highlights : local.highlights,
      vocab: remote.vocab.length ? remote.vocab : local.vocab,
      flags: (() => {
        const incoming = remote.flags as Partial<PaperFlags> & { cited?: boolean };
        return incoming.reading || incoming.starred || incoming.cite || incoming.cited
          ? normalizeFlags(incoming)
          : local.flags;
      })(),
      updatedAt: remote.updatedAt || local.updatedAt,
    };
    window.localStorage.setItem(storageKey(slug), JSON.stringify(merged));
    return merged;
  } catch {
    return loadPaperData(slug);
  }
}

/** 云端拉取后直接落地本地缓存，不改 updatedAt、不触发回写。 */
export function hydrateLocalPaperData(slug: string, data: PaperUserData) {
  try {
    window.localStorage.setItem(storageKey(slug), JSON.stringify(data));
  } catch {
    // 忽略
  }
}

export function listLocalSlugs(): string[] {
  const prefix = 'wenshu.notes.';
  const slugs: string[] = [];
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key?.startsWith(prefix)) slugs.push(key.slice(prefix.length));
    }
  } catch {
    // 忽略
  }
  return slugs;
}

export function loadPaperFlags(slug: string): PaperFlags {
  return loadPaperData(slug).flags;
}

export function makeId() {
  return `hl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}
