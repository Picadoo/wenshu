import { hasAiKey, ensureAiModel, chatCompletions } from './ai-config';

import type { VocabEntry } from './notes-store';

export type VocabExample = {
  text: string;
  source: 'paper' | 'ai';
  slug?: string;
  title?: string;
};

export type VocabBookEntry = {
  word: string;
  pos: string;
  ipa: string;
  en: string;
  zh: string;
  examples: VocabExample[];
  updatedAt: string;
};

const STORAGE_KEY = 'wenshu.vocab-book';

type Listener = (book: VocabBookEntry[]) => void;

let cache: VocabBookEntry[] | null = null;
const listeners = new Set<Listener>();
const lookup = new Map<string, VocabBookEntry>();

function normalizeEntry(entry: Partial<VocabBookEntry> & { word?: string }): VocabBookEntry {
  return {
    word: entry.word || '',
    pos: entry.pos || '',
    ipa: entry.ipa || '',
    en: entry.en || '',
    zh: entry.zh || '',
    examples: Array.isArray(entry.examples) ? entry.examples : [],
    updatedAt: entry.updatedAt || '',
  };
}

function rebuildLookup(book: VocabBookEntry[]) {
  lookup.clear();
  book.forEach((entry) => lookup.set(entry.word.toLowerCase(), entry));
}

function emit() {
  const book = cache ?? [];
  listeners.forEach((fn) => fn(book));
}

function persist(book: VocabBookEntry[]) {
  cache = book;
  rebuildLookup(book);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(book));
  } catch {
    // 忽略
  }
  emit();
}

export function loadVocabBook(): VocabBookEntry[] {
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw
      ? (JSON.parse(raw) as VocabBookEntry[]).map((entry) => normalizeEntry(entry)).filter((entry) => entry.word)
      : [];
  } catch {
    cache = [];
  }
  rebuildLookup(cache);
  return cache;
}

export function lookupVocab(word: string) {
  if (!cache) loadVocabBook();
  return lookup.get(word.toLowerCase());
}

export function hasVocabGloss(word: string) {
  const entry = lookupVocab(word);
  return Boolean(entry && (entry.en || entry.zh));
}

/** 云同步：整本替换（服务器版本较新时调用）。 */
export function replaceVocabBook(book: VocabBookEntry[]) {
  persist(book.map((entry) => normalizeEntry(entry)).filter((entry) => entry.word));
}

/** 云同步：整本数据的最后修改时间（各词条 updatedAt 的最大值）。 */
export function vocabBookLatest(book: VocabBookEntry[] = loadVocabBook()) {
  return book.reduce((acc, entry) => (entry.updatedAt > acc ? entry.updatedAt : acc), '');
}

export function subscribeVocabBook(fn: Listener) {
  listeners.add(fn);
  fn(loadVocabBook());
  return () => {
    listeners.delete(fn);
  };
}

export function sameVocabSentence(a: string, b: string) {
  return a.replace(/\s+/g, ' ').trim().toLowerCase() === b.replace(/\s+/g, ' ').trim().toLowerCase();
}

export type ImportResult = {
  book: VocabBookEntry[];
  added: number;
  merged: number;
  pendingWords: string[];
};

export function needsVocabGloss(entry: Pick<VocabBookEntry, 'en' | 'zh'>) {
  return !entry.en || !entry.zh;
}

export function importPaperVocab(input: {
  slug: string;
  title: string;
  entries: VocabEntry[];
}): ImportResult {
  const book = [...loadVocabBook()];
  let added = 0;
  let merged = 0;
  const now = new Date().toISOString();

  input.entries.forEach((item) => {
    const word = item.word.trim();
    if (!word) return;
    const key = word.toLowerCase();
    const sentence = item.context.trim();
    const existing = book.find((entry) => entry.word.toLowerCase() === key);
    const example: VocabExample | null = sentence
      ? { text: sentence, source: 'paper', slug: input.slug, title: input.title }
      : null;

    if (!existing) {
      book.push({
        word,
        pos: '',
        ipa: '',
        en: '',
        zh: '',
        examples: example ? [example] : [],
        updatedAt: now,
      });
      added += 1;
      return;
    }

    if (example && !existing.examples.some((ex) => sameVocabSentence(ex.text, example.text))) {
      existing.examples.push(example);
      existing.updatedAt = now;
      merged += 1;
    }
  });

  persist(book);
  const pendingWords = book
    .filter(
      (entry) =>
        needsVocabGloss(entry) &&
        input.entries.some((item) => item.word.trim().toLowerCase() === entry.word.toLowerCase())
    )
    .map((entry) => entry.word);
  return { book, added, merged, pendingWords };
}

export function removeVocabWord(word: string) {
  persist(loadVocabBook().filter((entry) => entry.word.toLowerCase() !== word.toLowerCase()));
}

export function patchVocabEntry(word: string, patch: Partial<VocabBookEntry>) {
  const book = loadVocabBook().map((entry) =>
    entry.word.toLowerCase() === word.toLowerCase()
      ? { ...entry, ...patch, updatedAt: new Date().toISOString() }
      : entry
  );
  persist(book);
}

type AiGloss = { word?: string; pos?: string; ipa?: string; en?: string; zh?: string };

function parseGlossList(raw: string): AiGloss[] {
  const trimmed = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '');
  const start = trimmed.indexOf('[');
  const end = trimmed.lastIndexOf(']');
  if (start < 0 || end < 0) return [];
  try {
    return JSON.parse(trimmed.slice(start, end + 1)) as AiGloss[];
  } catch {
    return [];
  }
}

function collectPending(words?: string[]) {
  return loadVocabBook().filter((entry) => {
    if (words && !words.some((word) => word.toLowerCase() === entry.word.toLowerCase())) {
      return false;
    }
    return needsVocabGloss(entry);
  });
}

function matchGloss(entry: VocabBookEntry, glosses: AiGloss[], pending: VocabBookEntry[]) {
  const byWord = glosses.find((item) => item.word?.toLowerCase() === entry.word.toLowerCase());
  if (byWord) return byWord;
  const index = pending.findIndex((item) => item.word.toLowerCase() === entry.word.toLowerCase());
  return index >= 0 ? glosses[index] : undefined;
}

async function enrichOnce(words?: string[]): Promise<{ filled: number; error?: string }> {
  const pending = collectPending(words);
  if (!pending.length) return { filled: 0 };
  if (!hasAiKey()) return { filled: 0 };

  const prompt = `为下列英语论文生词补词典义。每个词给：pos（词性，如 n./v./adj.）、ipa（国际音标，用 /.../）、en（一句英文短义）、zh（中文释义）。只返回 JSON 数组。
${pending
  .map((entry, index) => {
    const sentence = entry.examples.find((ex) => ex.source === 'paper')?.text || '';
    return `${index + 1}. ${entry.word}${sentence ? `\n   原句：${sentence}` : ''}`;
  })
  .join('\n')}`;

  try {
    const raw = await chatCompletions(prompt, await ensureAiModel());
    const glosses = parseGlossList(raw);
    const now = new Date().toISOString();
    let filled = 0;
    const book = loadVocabBook();
    const next = book.map((entry) => {
      const hit = matchGloss(entry, glosses, pending);
      if (!hit) return entry;
      filled += 1;
      return {
        ...entry,
        pos: entry.pos || hit.pos || '',
        ipa: entry.ipa || hit.ipa || '',
        en: entry.en || hit.en || '',
        zh: entry.zh || hit.zh || '',
        updatedAt: now,
      };
    });
    persist(next);
    return { filled };
  } catch (error) {
    return { filled: 0, error: error instanceof Error ? error.message : '补释义失败' };
  }
}

let enrichTail: Promise<unknown> = Promise.resolve();

export function enrichVocabBook(words?: string[]): Promise<{ filled: number; error?: string }> {
  const job = enrichTail.then(() => enrichOnce(words));
  enrichTail = job.then(
    () => undefined,
    () => undefined
  );
  return job;
}

export function filterVocabBook(book: VocabBookEntry[], query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return book;
  return book.filter(
    (entry) =>
      entry.word.toLowerCase().includes(q) ||
      entry.zh.toLowerCase().includes(q) ||
      entry.en.toLowerCase().includes(q) ||
      (entry.ipa || '').toLowerCase().includes(q)
  );
}
