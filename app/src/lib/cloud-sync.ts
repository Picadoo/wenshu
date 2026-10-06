import axios from './axios';
import { hydrateVaultData } from '../data/hydrate-vault';
import { loadVocabBook, vocabBookLatest, replaceVocabBook, subscribeVocabBook } from './vocab-book';
import { snapshotReaderState, mergeRemoteReaderState, subscribeReaderSession } from './reader-session';
import {
  loadPaperData,
  listLocalSlugs,
  registerNotesBackend,
  hydrateLocalPaperData,
} from './notes-store';

import type { VocabBookEntry } from './vocab-book';
import type { NotesBackend, PaperUserData } from './notes-store';

// ----------------------------------------------------------------------
// 云同步：登录后把每篇批注走 HTTP 后端，生词本 / 阅读进度走 KV 接口。
// localStorage 仍是本地缓存层，冲突按 updatedAt / at 较新者胜。

const httpBackend: NotesBackend = {
  kind: 'http',

  async load(slug: string): Promise<PaperUserData | null> {
    const res = await axios.get(`/api/notes/${encodeURIComponent(slug)}`);
    return (res.data?.data as PaperUserData | null) ?? null;
  },

  async save(slug: string, data: PaperUserData): Promise<void> {
    await axios.put(`/api/notes/${encodeURIComponent(slug)}`, data);
  },
};

let hydrating = false;

/** 全量对齐每篇批注：远端新则落地本地，本地新（或远端缺失）则推上去。 */
async function syncAllNotes() {
  const res = await axios.get('/api/notes');
  const remote = (res.data?.notes ?? {}) as Record<string, { data: PaperUserData; updatedAt: string }>;

  const pushes: Promise<void>[] = [];
  const slugs = new Set([...listLocalSlugs(), ...Object.keys(remote)]);
  slugs.forEach((slug) => {
    const server = remote[slug];
    const local = loadPaperData(slug);
    const localAt = local.updatedAt || '';
    const serverAt = server?.data?.updatedAt || '';
    if (server && serverAt > localAt) {
      hydrateLocalPaperData(slug, server.data);
    } else if (localAt && localAt > serverAt) {
      pushes.push(httpBackend.save(slug, local));
    }
  });
  await Promise.all(pushes);
}

async function syncVocabBook() {
  const res = await axios.get('/api/kv/vocab-book');
  const remote = res.data?.data as { book?: VocabBookEntry[] } | null;
  const remoteBook = remote?.book ?? [];
  const localLatest = vocabBookLatest();
  const remoteLatest = vocabBookLatest(remoteBook);
  if (remoteLatest > localLatest) {
    replaceVocabBook(remoteBook);
  } else if (localLatest && localLatest > remoteLatest) {
    await axios.put('/api/kv/vocab-book', { book: loadVocabBook() });
  }
}

async function syncReader() {
  const res = await axios.get('/api/kv/reader');
  const remote = res.data?.data as ReturnType<typeof snapshotReaderState> | null;
  if (remote) mergeRemoteReaderState(remote);
  await axios.put('/api/kv/reader', snapshotReaderState());
}

function debounced(fn: () => void, wait: number) {
  let timer = 0;
  return () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(fn, wait);
  };
}

let started = false;
const subscriptions: (() => void)[] = [];

export function stopCloudSync() {
  started = false;
  subscriptions.splice(0).forEach((unsubscribe) => unsubscribe());
  registerNotesBackend(null);
}

/** 登录成功后调用一次：注册 HTTP 批注后端 + 拉齐云端数据 + 订阅本地变更回推。 */
export async function initCloudSync() {
  if (started) return;
  started = true;

  hydrating = true;
  // 生产环境 vault JSON 有鉴权，登录前的启动水化会 401 落到烤入兜底；登录后重拉一次
  try {
    await Promise.all([hydrateVaultData(), syncAllNotes(), syncVocabBook(), syncReader()]);
    registerNotesBackend(httpBackend);
  } catch (error) {
    started = false;
    throw error;
  } finally {
    hydrating = false;
  }

  const pushVocab = debounced(() => {
    if (started) void axios.put('/api/kv/vocab-book', { book: loadVocabBook() }).catch(() => {});
  }, 2000);
  const pushReader = debounced(() => {
    if (started) void axios.put('/api/kv/reader', snapshotReaderState()).catch(() => {});
  }, 2000);

  let firstVocab = true;
  subscriptions.push(subscribeVocabBook(() => {
    if (firstVocab) {
      firstVocab = false;
      return;
    }
    if (!hydrating) pushVocab();
  }));

  let firstReader = true;
  subscriptions.push(subscribeReaderSession(() => {
    if (firstReader) {
      firstReader = false;
      return;
    }
    if (!hydrating) pushReader();
  }));
}
