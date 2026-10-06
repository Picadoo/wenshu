import { webImageUrl } from 'src/lib/web-image';

import { withVaultOrigin } from './vault';

export type PaperStatus = 'reading' | 'notes' | 'ready' | 'shared';
export type PaperVisibility = 'private' | 'shared';
export type PaperKind = 'method' | 'experiment' | 'review';
export type PaperDocKey = 'index' | 'article' | 'articleEn' | 'notes' | 'cards' | 'pdf' | 'txt';

export type PaperImage = {
  name: string;
  url: string;
  size: number;
  caption?: string;
  order?: number;
};

export type TopicDoc = {
  slug: string;
  title: string;
  docType: string;
  domain: string;
  updatedAt: string;
  /** frontmatter papers: 覆盖账本（pid 列表），专题已纳入的库内论文 */
  papers?: string[];
  file: string;
};

export type PaperFiles = {
  index?: string;
  article?: string;
  articleEn?: string;
  notes?: string;
  cards?: string;
  pdf?: string;
  txt?: string;
  imagesDir?: string;
  indexHtml?: string;
  articleHtml?: string;
  articleEnHtml?: string;
  notesHtml?: string;
  cardsHtml?: string;
};

export type PaperVaultPaths = {
  folder: string;
  index: string;
  article: string;
  articleEn: string;
  notes: string;
  cards: string;
  pdf: string;
  txt: string;
};

export type Paper = {
  id: string;
  slug: string;
  pid: string;
  title: string;
  titleEn: string;
  /** 原文语言。中文刊不提供外文正文。 */
  lang?: 'zh' | 'en';
  authors: string;
  authorList: string[];
  year: number;
  venue: string;
  doi?: string;
  citekey?: string;
  kind: PaperKind;
  topic: string;
  domain: string;
  tags: string[];
  status: PaperStatus;
  visibility: PaperVisibility;
  reading?: string;
  vaultStatus?: string;
  qualityScore?: string;
  sciQuestion?: string;
  tldr?: string;
  updatedAt: string;
  coverUrl: string;
  excerpt: string;
  images?: PaperImage[];
  files: PaperFiles;
  hasTranslation: boolean;
  hasNotes: boolean;
  hasCards: boolean;
  hasPdf: boolean;
  hasTxt: boolean;
  vault: PaperVaultPaths;
};

export const STATUS_LABEL: Record<PaperStatus, string> = {
  reading: '精读中',
  notes: '写笔记',
  ready: '可分享',
  shared: '已公开',
};

export const VISIBILITY_LABEL: Record<PaperVisibility, string> = {
  private: '仅自己',
  shared: '可分享',
};

export const KIND_LABEL: Record<PaperKind, string> = {
  method: '方法',
  experiment: '实验',
  review: '综述',
};

export const DOC_LABEL: Record<PaperDocKey, string> = {
  index: '索引',
  article: '中文正文',
  articleEn: '英文正文',
  notes: '学习笔记',
  cards: '概念卡',
  pdf: '原文 PDF',
  txt: '英文原文',
};

/** 列表/封面位统一用 webp 压缩档（web 生产环境），原图留给大图查看。 */
function withWebCover(paper: Paper): Paper {
  const cover = webImageUrl(paper.coverUrl);
  return cover === paper.coverUrl ? paper : { ...paper, coverUrl: cover };
}

/**
 * 目录数据运行时从 /vault/catalog.json 水化（见 hydrate-vault.ts），
 * generated-catalog 只在初次拉取失败时动态加载，避免重复下载整份目录。
 * 数组保持同一引用、原地替换内容，所有同步消费方无需改动。
 */
export const papers: Paper[] = [];

export const topicDocs: TopicDoc[] = [];

let paperByPid = new Map<string, Paper>(papers.map((item) => [item.pid, item]));
let paperBySlug = new Map<string, Paper>();
let searchTextByPaper = new WeakMap<Paper, string>();

export function hydratePapers(nextPapers: Paper[], nextTopicDocs: TopicDoc[]) {
  papers.splice(0, papers.length, ...withVaultOrigin(nextPapers).map(withWebCover));
  topicDocs.splice(0, topicDocs.length, ...withVaultOrigin(nextTopicDocs));
  paperByPid = new Map(papers.map((item) => [item.pid, item]));
  paperBySlug = new Map(papers.map((item) => [item.slug, item]));
  searchTextByPaper = new WeakMap();
}

export function getPaper(slug: string) {
  return paperBySlug.get(slug);
}

/** 按 wiki 链接目标（pid = 「作者年份 中文短题」）解析论文。 */
export function resolvePaperByPid(pid: string) {
  return paperByPid.get(pid.trim());
}

/** 「第一作者 et al.」短格式（列表位展示用；全作者看详情页 Tooltip / 复制引用）。 */
export function shortAuthors(paper: Paper) {
  const first = paper.authorList[0] || paper.authors;
  return paper.authorList.length > 1 ? `${first} et al.` : first;
}

export function isChinesePaper(paper: Paper) {
  if (paper.lang === 'zh') return true;
  if (paper.lang === 'en') return false;
  const title = (paper.title || '').trim();
  const en = (paper.titleEn || '').trim();
  return /[\u4e00-\u9fff]/.test(title) && (!en || en === title);
}

/** 中英题名：语言切换决定主标题，另一语种仍保留，方便对照和检索。 */
export function paperTitles(paper: Paper, lang?: string) {
  const zh = (paper.title || '').trim();
  const en = (paper.titleEn || '').trim();
  const same = !zh || !en || zh === en;
  if (same) return { primary: zh || en, secondary: '' };
  const preferEn = (lang || '').toLowerCase().startsWith('en');
  return preferEn ? { primary: en, secondary: zh } : { primary: zh, secondary: en };
}

export function getTopicDoc(slug: string) {
  return topicDocs.find((item) => item.slug === slug);
}

/** domain 匹配：全等、大类前缀（"颗粒形态" 命中 "颗粒形态/深度学习"）或任一段相等。 */
export function domainMatches(paperDomain: string, filter: string) {
  if (!filter || filter === 'all') return true;
  if (paperDomain === filter) return true;
  if (paperDomain.startsWith(`${filter}/`)) return true;
  return paperDomain.split('/').includes(filter);
}

export function topicDocsForDomain(domain: string) {
  if (!domain || domain === 'all') return [];
  return topicDocs.filter(
    (doc) => domainMatches(doc.domain, domain) || domainMatches(domain, doc.domain) || doc.domain === ''
  );
}

/** 论文库主题筛选项：大类 + 完整 domain 两级。 */
export function domainOptions(list: Paper[] = papers) {
  const counts = new Map<string, number>();
  list.forEach((item) => {
    if (!item.domain) return;
    const major = item.domain.split('/')[0];
    counts.set(major, (counts.get(major) ?? 0) + 1);
    if (item.domain !== major) {
      counts.set(item.domain, (counts.get(item.domain) ?? 0) + 1);
    }
  });
  return [...counts.entries()].map(([label, count]) => ({ label, count }));
}

export function paperStats(list: Paper[] = papers) {
  return {
    total: list.length,
    reading: list.filter((item) => item.status === 'reading').length,
    notes: list.filter((item) => item.status === 'notes').length,
    shared: list.filter((item) => item.visibility === 'shared').length,
    withTranslation: list.filter((item) => item.hasTranslation).length,
    withAnalysis: list.filter((item) => item.hasNotes).length,
    withPdf: list.filter((item) => item.hasPdf).length,
  };
}

export type PaperDomainGroup = {
  key: string;
  major: string;
  sub: string;
  papers: Paper[];
};

/** 按 vault 主题路径分组，供论文库分节展示。 */
export function groupPapersByDomain(list: Paper[]): PaperDomainGroup[] {
  const map = new Map<string, PaperDomainGroup>();
  list.forEach((paper) => {
    const raw = paper.domain || paper.topic || '未分类';
    const [major, ...rest] = raw.split('/');
    const sub = rest.join('/');
    const key = sub ? `${major}/${sub}` : major;
    const group = map.get(key) ?? { key, major, sub, papers: [] };
    group.papers.push(paper);
    map.set(key, group);
  });
  return [...map.values()]
    .map((group) => ({
      ...group,
      papers: [...group.papers].sort(
        (a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.title.localeCompare(b.title, 'zh')
      ),
    }))
    .sort((a, b) => {
      const majorCmp = a.major.localeCompare(b.major, 'zh');
      return majorCmp || a.sub.localeCompare(b.sub, 'zh');
    });
}

export function topicSeries(list: Paper[] = papers) {
  const counts = new Map<string, number>();
  list.forEach((item) => {
    const label = (item.domain || item.topic || '未分类').split('/')[0];
    counts.set(label, (counts.get(label) ?? 0) + 1);
  });
  return [...counts.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, 'zh'));
}

/** 展示用标签：去掉「主题/」前缀和目录路径，只留词本身。 */
export function displayTags(paper: Paper) {
  const seen = new Set<string>();
  const labels: string[] = [];
  paper.tags.forEach((raw) => {
    const label = raw.startsWith('主题/') ? raw.slice(3) : raw;
    if (!label || label.includes('/') || seen.has(label)) return;
    seen.add(label);
    labels.push(label);
  });
  return labels;
}

export function paperScore(paper: Paper) {
  return (paper.qualityScore || '').replace(/\/10$/, '');
}

function normalizeSearchText(value: string) {
  return value.toLowerCase().replace(/[/\-_·,，。：:；;]+/g, ' ');
}

export function paperHaystack(item: Paper) {
  const cached = searchTextByPaper.get(item);
  if (cached !== undefined) return cached;
  const text = normalizeSearchText(
    [
      item.id,
      item.pid,
      item.slug,
      item.title,
      item.titleEn,
      item.authors,
      item.venue,
      item.doi,
      item.citekey,
      item.domain,
      item.topic,
      item.tldr,
      item.sciQuestion,
      item.excerpt,
      ...item.tags,
      ...displayTags(item),
    ]
      .filter(Boolean)
      .join(' ')
  );
  searchTextByPaper.set(item, text);
  return text;
}

export type PaperMarkFilter = 'all' | '在读' | '已读' | '重读' | '重点' | '待引用' | '已引用';

export function filterPapers(
  list: Paper[],
  query: string,
  extras?: {
    status?: 'all' | PaperStatus;
    visibility?: 'all' | PaperVisibility;
    kind?: 'all' | PaperKind;
    domain?: string;
    mark?: PaperMarkFilter;
    markOf?: (slug: string) => {
      reading?: string;
      starred?: boolean;
      cite?: string;
      cited?: boolean;
    };
  }
) {
  const tokens = normalizeSearchText(query)
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return list.filter((item) => {
    if (extras?.status && extras.status !== 'all' && item.status !== extras.status) return false;
    if (extras?.visibility && extras.visibility !== 'all' && item.visibility !== extras.visibility) {
      return false;
    }
    if (extras?.kind && extras.kind !== 'all' && item.kind !== extras.kind) return false;
    if (extras?.domain && !domainMatches(item.domain, extras.domain)) return false;
    if (extras?.mark && extras.mark !== 'all') {
      const flags = extras.markOf?.(item.slug);
      const reading =
        flags?.reading ||
        (['在读', '已读', '重读'].includes(item.reading || '') ? item.reading : '');
      if (extras.mark === '重点' && !flags?.starred) return false;
      const cite = flags?.cite || (flags?.cited ? '已引用' : '');
      if (extras.mark === '待引用' && cite !== '待引用') return false;
      if (extras.mark === '已引用' && cite !== '已引用') return false;
      if (
        extras.mark !== '重点' &&
        extras.mark !== '待引用' &&
        extras.mark !== '已引用' &&
        reading !== extras.mark
      ) {
        return false;
      }
    }
    if (!tokens.length) return true;
    const hay = paperHaystack(item);
    return tokens.every((token) => hay.includes(token));
  });
}
