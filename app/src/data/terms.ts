// ----------------------------------------------------------------------

export type TermUsage = {
  paper: string;
  context: string;
};

export type TermEntry = {
  key: string;
  term: string;
  zhName: string;
  fullName: string;
  aliases: string[];
  type: string;
  domains: string[];
  definition: string;
  noteStem: string;
  usages: TermUsage[];
};

/** bootstrap 水化后才加载页面；请求失败时由 hydrate-vault 按需加载构建兜底。 */
export const terms: TermEntry[] = [];

/** 链接名归一：小写 + 只留字母/数字/汉字。与 scripts/sync-vault.py 的实现保持一致。 */
export function normalizeLinkKey(name: string) {
  return [...name.toLowerCase()].filter((ch) => /[a-z0-9\u4e00-\u9fff]/.test(ch)).join('');
}

let termByKey = new Map<string, TermEntry>();
let aliasToKey = new Map<string, string>();
let searchTextByEntry = new WeakMap<TermEntry, string>();

function rebuildTermIndexes() {
  searchTextByEntry = new WeakMap();
  termByKey = new Map(terms.map((entry) => [entry.key, entry]));
  aliasToKey = new Map();
  terms.forEach((entry) => {
    [entry.term, entry.zhName, entry.fullName, entry.noteStem, ...entry.aliases].forEach((name) => {
      const normalized = normalizeLinkKey(name);
      if (normalized && !aliasToKey.has(normalized)) {
        aliasToKey.set(normalized, entry.key);
      }
    });
  });
}

rebuildTermIndexes();

export function hydrateTerms(next: TermEntry[]) {
  terms.splice(0, terms.length, ...next);
  rebuildTermIndexes();
}

export function getTerm(key: string) {
  return termByKey.get(key);
}

/** 按 wiki 链接目标名解析术语（支持 term/中文名/全称/别名/笔记文件名）。 */
export function resolveTermByName(name: string) {
  const key = aliasToKey.get(normalizeLinkKey(name));
  return key ? termByKey.get(key) : undefined;
}

export type TermFacets = {
  /** 术语类型：概念 / 物理量 / 模型 / 方法 / 指标 / 算法 / 数据集 */
  type?: string;
  /** 一级领域，见 majorDomain */
  domain?: string;
};

/** 领域取一级：`CFD-DEM方法/非球颗粒` → `CFD-DEM方法`。二级太碎，做筛选芯片会铺满一屏。 */
export function majorDomain(domain: string) {
  return domain.split('/')[0];
}

function matchesFacets(entry: TermEntry, facets?: TermFacets) {
  if (!facets) return true;
  if (facets.type && entry.type !== facets.type) return false;
  if (facets.domain && !entry.domains.some((d) => majorDomain(d) === facets.domain)) return false;
  return true;
}

function termSearchText(entry: TermEntry) {
  let text = searchTextByEntry.get(entry);
  if (text === undefined) {
    text = [entry.term, entry.zhName, entry.fullName, entry.definition, ...entry.aliases]
      .join(' ')
      .toLowerCase();
    searchTextByEntry.set(entry, text);
  }
  return text;
}

export function filterTerms(list: TermEntry[], query: string, facets?: TermFacets) {
  const q = query.trim().toLowerCase();
  return list.filter((entry) => {
    if (!matchesFacets(entry, facets)) return false;
    if (!q) return true;
    return termSearchText(entry).includes(q);
  });
}

/** 统计各筛选值下的条目数。计数在「其余条件已生效」的集合上算，避免出现点了就空的死芯片。 */
export function searchTerms(list: TermEntry[], query: string, facets: TermFacets) {
  const q = query.trim().toLowerCase();
  const filtered: TermEntry[] = [];
  const types = new Map<string, number>();
  const domains = new Map<string, number>();
  const add = (counts: Map<string, number>, value: string) => {
    if (value) counts.set(value, (counts.get(value) ?? 0) + 1);
  };

  // 文本匹配只做一次，筛选计数各自忽略本维度，保持原有芯片语义。
  list.forEach((entry) => {
    if (q && !termSearchText(entry).includes(q)) return;
    const entryDomains = new Set(entry.domains.map(majorDomain));
    const typeMatches = !facets.type || entry.type === facets.type;
    const domainMatches = !facets.domain || entryDomains.has(facets.domain);
    if (typeMatches && domainMatches) filtered.push(entry);
    if (domainMatches) add(types, entry.type);
    if (typeMatches) entryDomains.forEach((value) => add(domains, value));
  });

  const sortedCounts = (counts: Map<string, number>): [string, number][] =>
    [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return { filtered, counts: { types: sortedCounts(types), domains: sortedCounts(domains) } };
}

export function termFacetCounts(list: TermEntry[], query: string, facets: TermFacets) {
  return searchTerms(list, query, facets).counts;
}
