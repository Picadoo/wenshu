export const READING_TABS = ['article', 'articleEn', 'txt'] as const;

export type ReadingTab = (typeof READING_TABS)[number];

export type ReaderSession = {
  slug: string;
  title: string;
  /** 上次真正在读的正文页签，不会是图片 / PDF / 笔记。 */
  tab: ReadingTab;
  scroll: number;
  /** 各正文页签各自的滚动位置，互不覆盖。 */
  progress: Partial<Record<ReadingTab, number>>;
  split?: string;
  at: number;
};

type Listener = (session: ReaderSession | null) => void;

const SESSION_KEY = 'wenshu.reader-session';
const RECENT_KEY = 'wenshu.reader-recent';
const RECENT_MAX = 12;

const listeners = new Set<Listener>();
let cache: ReaderSession | null | undefined;
let lastEmitKey = '';
let recentMigrated = false;

export function isReadingTab(tab: string | null | undefined): tab is ReadingTab {
  return tab === 'article' || tab === 'articleEn' || tab === 'txt';
}

export function clampScroll(value: unknown) {
  const next = Math.round(Number(value));
  if (!Number.isFinite(next) || next < 0) return 0;
  return next;
}

function emptyProgress(): Partial<Record<ReadingTab, number>> {
  return {};
}

function sanitizeProgress(raw: unknown, fallbackTab: string, fallbackScroll: number) {
  const progress = emptyProgress();
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    Object.entries(raw as Record<string, unknown>).forEach(([tab, scroll]) => {
      if (isReadingTab(tab)) progress[tab] = clampScroll(scroll);
    });
  }
  if (isReadingTab(fallbackTab) && progress[fallbackTab] == null && fallbackScroll > 0) {
    progress[fallbackTab] = clampScroll(fallbackScroll);
  }
  return progress;
}

export function normalizeSession(raw: Partial<ReaderSession> | null | undefined): ReaderSession | null {
  if (!raw?.slug || typeof raw.slug !== 'string') return null;

  const progress = sanitizeProgress(raw.progress, String(raw.tab || ''), Number(raw.scroll) || 0);
  const tab: ReadingTab = isReadingTab(raw.tab)
    ? raw.tab
    : progress.articleEn != null
      ? 'articleEn'
      : progress.txt != null
        ? 'txt'
        : 'article';
  const scroll = progress[tab] ?? (isReadingTab(raw.tab) ? clampScroll(raw.scroll) : 0);
  progress[tab] = scroll;

  return {
    slug: raw.slug,
    title: typeof raw.title === 'string' ? raw.title : '',
    tab,
    scroll,
    progress,
    split: typeof raw.split === 'string' ? raw.split : '',
    at: Number(raw.at) || 0,
  };
}

function parseRecent(raw: unknown): ReaderSession[] {
  if (!Array.isArray(raw)) return [];
  if (typeof raw[0] === 'string') {
    return (raw as string[])
      .filter(Boolean)
      .map((slug) => normalizeSession({ slug, title: '', tab: 'article', scroll: 0, at: 0 }))
      .filter((item): item is ReaderSession => Boolean(item));
  }
  const seen = new Set<string>();
  const items: ReaderSession[] = [];
  (raw as Partial<ReaderSession>[]).forEach((item) => {
    const next = normalizeSession(item);
    if (!next || seen.has(next.slug)) return;
    seen.add(next.slug);
    items.push(next);
  });
  return items;
}

function emit(session: ReaderSession | null) {
  const key = session
    ? `${session.slug}|${session.tab}|${session.split || ''}|${session.title}|${session.scroll}`
    : '';
  if (key === lastEmitKey) return;
  lastEmitKey = key;
  listeners.forEach((fn) => fn(session));
}

function writeRecent(recent: ReaderSession[]) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, RECENT_MAX)));
  } catch {
    // 忽略配额
  }
}

function persistRecent(session: ReaderSession) {
  const list = loadRecentSessions();
  const prev = list.find((item) => item.slug === session.slug);
  const recent = list.filter((item) => item.slug !== session.slug);
  recent.unshift({
    ...session,
    progress: { ...prev?.progress, ...session.progress },
    scroll: session.progress[session.tab] ?? session.scroll,
  });
  writeRecent(recent);
}

export function loadReaderSession(): ReaderSession | null {
  if (cache !== undefined) return cache;
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<ReaderSession>) : null;
    cache = parsed ? normalizeSession(parsed) : null;
    if (cache && raw && JSON.stringify(parsed) !== JSON.stringify(cache)) {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(cache));
    }
  } catch {
    cache = null;
  }
  return cache;
}

export function loadRecentSessions(): ReaderSession[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const recent = raw ? parseRecent(JSON.parse(raw)) : [];
    if (!recentMigrated && raw) {
      recentMigrated = true;
      try {
        const original = JSON.parse(raw) as unknown;
        if (JSON.stringify(original) !== JSON.stringify(recent)) {
          writeRecent(recent);
        }
      } catch {
        writeRecent(recent);
      }
    }
    return recent;
  } catch {
    return [];
  }
}

export function loadRecentSlugs(): string[] {
  return loadRecentSessions().map((item) => item.slug);
}

export function loadPaperSession(slug: string): ReaderSession | null {
  if (!slug) return null;
  const last = loadReaderSession();
  if (last?.slug === slug) return last;
  return loadRecentSessions().find((item) => item.slug === slug) ?? null;
}

export function readingScroll(session: ReaderSession | null | undefined, tab: string) {
  if (!session || !isReadingTab(tab)) return 0;
  return session.progress[tab] ?? (session.tab === tab ? session.scroll : 0);
}

export function saveReaderSession(session: ReaderSession, options?: { quiet?: boolean }) {
  const next = normalizeSession(session);
  if (!next) return;
  cache = next;
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    persistRecent(next);
  } catch {
    // 忽略
  }
  if (!options?.quiet) emit(next);
}

/** 只在正文页签写入进度。图片 / PDF / 笔记不会进最近阅读，也不会覆盖已有滚动位置。 */
export function saveReadingProgress(
  input: {
    slug: string;
    title: string;
    tab: string;
    scroll: number;
    split?: string;
  },
  options?: { quiet?: boolean }
) {
  if (!input.slug || !isReadingTab(input.tab)) return;

  const prev = loadPaperSession(input.slug);
  const progress = { ...prev?.progress };
  progress[input.tab] = clampScroll(input.scroll);

  saveReaderSession(
    {
      slug: input.slug,
      title: input.title || prev?.title || '',
      tab: input.tab,
      scroll: progress[input.tab] ?? 0,
      progress,
      split: input.split || '',
      at: Date.now(),
    },
    options
  );
}

/** 云同步：当前会话 + 最近阅读快照。 */
export function snapshotReaderState() {
  return { session: loadReaderSession(), recent: loadRecentSessions() };
}

/** 云同步：合并远端阅读状态。recent 按 slug 取较新的 at；session 也取较新。 */
export function mergeRemoteReaderState(remote: {
  session?: Partial<ReaderSession> | null;
  recent?: Partial<ReaderSession>[] | null;
}) {
  const remoteRecent = parseRecent(remote.recent ?? []);
  if (remoteRecent.length) {
    const merged = new Map<string, ReaderSession>();
    [...loadRecentSessions(), ...remoteRecent].forEach((item) => {
      const prev = merged.get(item.slug);
      if (!prev || item.at > prev.at) {
        merged.set(item.slug, prev ? { ...item, progress: { ...prev.progress, ...item.progress } } : item);
      } else if (prev) {
        prev.progress = { ...item.progress, ...prev.progress };
      }
    });
    writeRecent([...merged.values()].sort((a, b) => b.at - a.at));
  }

  const remoteSession = remote.session ? normalizeSession(remote.session) : null;
  const local = loadReaderSession();
  if (remoteSession && (!local || remoteSession.at > local.at)) {
    cache = remoteSession;
    try {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(remoteSession));
    } catch {
      // 忽略
    }
    emit(remoteSession);
  }
}

export function subscribeReaderSession(fn: Listener) {
  listeners.add(fn);
  fn(loadReaderSession());
  return () => {
    listeners.delete(fn);
  };
}

export function paperReaderHref(session: { slug: string; tab?: string; split?: string }) {
  const search = new URLSearchParams();
  if (session.tab && isReadingTab(session.tab) && session.tab !== 'article') {
    search.set('tab', session.tab);
  }
  if (session.split) search.set('split', session.split);
  const qs = search.toString();
  return qs ? `/dashboard/papers/${session.slug}?${qs}` : `/dashboard/papers/${session.slug}`;
}

export function paperCompareHref(left: string, right: string, tab = '') {
  if (!right || right === left) return paperReaderHref({ slug: left, tab: isReadingTab(tab) ? tab : 'article', split: '' });
  return paperReaderHref({ slug: left, tab: isReadingTab(tab) ? tab : 'article', split: right });
}

export function isReaderPath(pathname: string, slug: string) {
  return pathname === `/dashboard/papers/${slug}` || pathname.startsWith(`/dashboard/papers/${slug}/`);
}

export function shortReaderTitle(title: string) {
  const text = title.replace(/\s+/g, ' ').trim();
  return text.length > 16 ? `${text.slice(0, 16)}…` : text;
}
