export type CiteEntry = {
  n: string;
  label: string;
  keys: string[];
};

const YEAR_TOKEN = /\b((?:18|19|20)\d{2}[a-z]?)\b/g;
const PARTICLE = '(?:van|von|de|del|den|der|da|di|du|la|le|ten|ter|te|el|al)';

export function splitAtRefs(source: string) {
  const match = /^##\s+[^\n]*参考文献[^\n]*$/m.exec(source);
  if (!match) return { body: source, refs: '' };
  return { body: source.slice(0, match.index), refs: source.slice(match.index) };
}

function normalizeAuthorKey(name: string) {
  return name
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
}

function extractCiteYear(text: string) {
  const stripped = text.replace(/https?:\/\/\S+/gi, '').replace(/\bdoi:\s*\S+/gi, '').trim();
  const afterType = stripped.match(/\[(?:J|M|N|C|D|R)\][\s\S]{0,120}?((?:18|19|20)\d{2})/);
  if (afterType) return afterType[1];
  // Copernicus / 文末年份：「..., 2018.」优先于标题里的事件年份 (2012)
  const trailing = stripped.match(/[,，]\s*((?:18|19|20)\d{2}[a-z]?)\.?$/);
  if (trailing) return trailing[1];
  const springerYear = stripped.match(/^.{0,120}?\s\(((?:18|19|20)\d{2}[a-z]?)\)/);
  if (springerYear) return springerYear[1];
  const paren = [...stripped.matchAll(/\(((?:18|19|20)\d{2}[a-z]?)\)/g)].pop();
  if (paren) return paren[1];
  YEAR_TOKEN.lastIndex = 0;
  const all = [...stripped.matchAll(YEAR_TOKEN)];
  YEAR_TOKEN.lastIndex = 0;
  return all.at(-1)?.[1] || '';
}

const ALL_CAPS_AUTHORS =
  /^((?:[A-ZÀ-Þ][A-Za-zÀ-ÿ'’-]+(?:\s+[A-Z](?:[.\-\s][A-Z]){0,4}\.?)?[，,]?\s+)*(?:[A-ZÀ-Þ][A-Za-zÀ-ÿ'’-]+(?:\s+[A-Z](?:[.\-\s][A-Z]){0,4}\.?)?)(?:[，,]?\s*等)?)\.\s+\S/;

function authorSegment(text: string) {
  if (/^[\u4e00-\u9fff]/.test(text)) {
    return (
      text.match(/^([\u4e00-\u9fffA-Za-z\s、，,等]{2,80}?)(?:[.．]|\[J\]|\[M\]|\[N\]|\[C\])/)?.[1] || text.slice(0, 40)
    ).trim();
  }
  if (/^[A-ZÀ-Þ]{2,}\b/.test(text)) {
    const gbt = text.match(ALL_CAPS_AUTHORS);
    if (gbt) return gbt[1].trim();
  }
  const colonIdx = text.indexOf(':');
  // Copernicus「Author, A.: Title」；不要切到书章节的「GIS. In: Editor」
  if (
    colonIdx > 2 &&
    colonIdx <= 160 &&
    /^[A-ZÀ-Þ]/.test(text) &&
    !/\.\s+[A-ZÀ-Þ][a-zà-ÿ]{1,}$/.test(text.slice(0, colonIdx))
  ) {
    return text.slice(0, colonIdx).trim();
  }
  const parenYear = text.match(/\s\(((?:18|19|20)\d{2}[a-z]?)\)/);
  if (parenYear?.index != null) return text.slice(0, parenYear.index).slice(0, 180).trim();
  YEAR_TOKEN.lastIndex = 0;
  const yearMatch = YEAR_TOKEN.exec(text);
  YEAR_TOKEN.lastIndex = 0;
  return (yearMatch ? text.slice(0, yearMatch.index) : text).slice(0, 180).trim();
}

function prettySurname(value: string) {
  if (/[a-zà-ÿ]/.test(value.slice(1))) return value;
  return value.charAt(0) + value.slice(1).toLowerCase();
}

function westernMany(head: string, count: number) {
  return /等/.test(head) || /\bet\s*al\b/i.test(head) || count >= 3;
}

function parseAuthorHead(text: string) {
  const head = authorSegment(text);

  const zh = text.match(/^([\u4e00-\u9fff]{2,4})/);
  if (zh) {
    const names = [...head.matchAll(/[\u4e00-\u9fff]{2,4}/g)].map((m) => m[0]).filter((n) => n !== '等');
    const many = /等/.test(head) || names.length >= 3;
    if (many) return { first: names[0] || zh[1], second: names[1], count: 3 as const, chinese: true };
    if (names.length === 2) return { first: names[0], second: names[1], count: 2 as const, chinese: true };
    return { first: zh[1], count: 1 as const, chinese: true };
  }

  // 国标全大写：「PRAKASH N, MANCONI A, LOEW S. Mapping...」
  // 必须先于 initials，否则 `S. Mapping` 会被当成姓名。
  // 「GIS landslide...」这种残行不要当作者。
  if ((/^[A-ZÀ-Þ]{2,}\b/.test(head) || /^[A-ZÀ-Þ]{2,}\b/.test(text)) && !/^[A-Z]{2,}\s+[a-z]/.test(head)) {
    const names = [...new Set(
      [...head.matchAll(/\b([A-ZÀ-Þ]{2,})\b/g)]
        .map((m) => m[1])
        .filter((n) => n.length > 1 && !['AND', 'THE', 'FOR', 'OF', 'IN'].includes(n))
    )];
    if (names.length) {
      const first = prettySurname(names[0]);
      if (westernMany(head, names.length)) return { first, count: 3 as const, chinese: false };
      if (names.length === 2) return { first, second: prettySurname(names[1]), count: 2 as const, chinese: false };
      return { first, count: 1 as const, chinese: false };
    }
  }

  const ay = text.match(
    new RegExp(`^(?:(${PARTICLE}\\s+))?([A-ZÀ-Þ][A-Za-zà-ÿ'’]*(?:-[A-ZÀ-Þ][A-Za-zà-ÿ'’]*)*),`)
  );
  if (ay) {
    const first = `${ay[1] || ''}${ay[2]}`.trim();
    const etal = /\bet\s*al\b/i.test(head);
    const andM = head.match(new RegExp(`\\band\\s+(?:(${PARTICLE}\\s+))?([A-ZÀ-Þ][a-zà-ÿ'’-]+)`, 'i'));
    const surnameCount = (head.match(/[A-ZÀ-Þ][a-zà-ÿ'’-]+,/g) || []).length;
    if (etal || surnameCount >= 3) return { first, count: 3 as const, chinese: false };
    if (andM) return { first, second: `${andM[1] || ''}${andM[2]}`.trim(), count: 2 as const, chinese: false };
    return { first, count: 1 as const, chinese: false };
  }

  const initials = [
    ...head.matchAll(
      /(?:[A-ZÀ-Þ]\.(?:-[A-ZÀ-Þ]\.)?\s*)+([A-ZÀ-Þ][A-Za-zà-ÿ'’]*(?:-[A-ZÀ-Þ][A-Za-zà-ÿ'’]*)*)/g
    ),
  ];
  if (initials.length) {
    const first = initials[0][1];
    const etal = /\bet\s*al\b/i.test(head);
    if (etal || initials.length >= 3) {
      return { first, second: initials[1]?.[1], count: 3 as const, chinese: false };
    }
    if (initials.length === 2) {
      return { first, second: initials[1][1], count: 2 as const, chinese: false };
    }
    return { first, count: 1 as const, chinese: false };
  }

  // Springer：「Aksoy B, Ercanoglu M (2012)」
  const springer = [
    ...head.matchAll(
      new RegExp(`(?:(${PARTICLE})\\s+)?([A-ZÀ-Þ][a-zà-ÿ'’-]+)\\s+[A-Z]{1,4}(?:-[A-Z]{1,3})?\\b`, 'g')
    ),
  ].map((m) => `${m[1] ? `${m[1]} ` : ''}${m[2]}`);
  if (springer.length) {
    const first = springer[0];
    if (westernMany(head, springer.length)) return { first, count: 3 as const, chinese: false };
    if (springer.length === 2) return { first, second: springer[1], count: 2 as const, chinese: false };
    return { first, count: 1 as const, chinese: false };
  }

  return { first: '', count: 1 as const, chinese: false };
}

function formatCiteLabel(head: ReturnType<typeof parseAuthorHead>, year: string) {
  if (!head.first) return '';
  const who = head.chinese
    ? head.count === 1
      ? head.first
      : head.count === 2 && head.second
        ? `${head.first}和${head.second}`
        : `${head.first}等`
    : head.count === 1
      ? head.first
      : head.count === 2 && head.second
        ? `${head.first} and ${head.second}`
        : `${head.first} et al.`;
  return year ? `${who}, ${year}` : who;
}

export function parseBibliography(source: string): CiteEntry[] {
  const { refs } = splitAtRefs(source);
  if (!refs) return [];
  const entries: CiteEntry[] = [];
  for (const raw of refs.split('\n')) {
    const line = raw.trim();
    if (!line.startsWith('-')) continue;
    const num = line.match(/\^ref-(\d+)/)?.[1] || line.match(/\*\*\[(\d+)\]\*\*/)?.[1] || '';
    if (!num) continue;
    const text = line
      .replace(/^-\s*/, '')
      .replace(/^\*\*\[\d+\]\*\*\s*/, '')
      .replace(/\s*[｜|].*$/, '')
      .replace(/(?:\s*\^ref-\d+)+\s*$/, '')
      .replace(/\s*📥\s*\[\[[^\]]+\]\]\s*/g, '')
      .replace(/https?:\/\/\S+/gi, '')
      .trim();
    const year = extractCiteYear(text);
    const head = parseAuthorHead(text);
    const label = formatCiteLabel(head, year) || `文献 ${num}`;
    const keys = new Set<string>();
    if (head.first && year) {
      const key = normalizeAuthorKey(head.first);
      keys.add(`${key}|${year}`);
      keys.add(`${key}|${year.replace(/[a-z]$/, '')}`);
    }
    entries.push({ n: num, label, keys: [...keys] });
  }
  return entries;
}

export function citeMap(cites: CiteEntry[]) {
  return new Map(cites.map((entry) => [entry.n, entry]));
}

function protectChunks(source: string, rewrite: (plain: string) => string) {
  const parts = source.split(
    /(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]+?\$\$|\$[^$\n]+\$|!\[[^\]]*\]\([^)]*\)|\[\[#\^ref-[^\]]+\]\])/
  );
  for (let i = 0; i < parts.length; i += 2) {
    parts[i] = rewrite(parts[i]);
  }
  return parts.join('');
}

function expandCiteNums(body: string) {
  const nums: string[] = [];
  for (const chunk of body.split(/[,，]/)) {
    const range = chunk.match(/(\d{1,3})\s*[–—-]\s*(\d{1,3})/);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      if (start <= end && end - start <= 20) {
        for (let i = start; i <= end; i += 1) nums.push(String(i));
        continue;
      }
    }
    const single = chunk.match(/(\d{1,3})/);
    if (single) nums.push(single[1]);
  }
  return nums;
}

export function linkNumericCitations(source: string) {
  return protectChunks(source, (plain) =>
    plain.replace(
      /\[(\d{1,3}(?:\s*[,，]\s*\d{1,3})*(?:\s*[–—-]\s*\d{1,3})?)\](?!\()/g,
      (_all, body: string) => expandCiteNums(body).map((n) => `[[#^ref-${n}|${n}]]`).join(',')
    )
  );
}

function findCite(cites: CiteEntry[], author: string, year: string) {
  const key = `${normalizeAuthorKey(author)}|${year}`;
  const base = `${normalizeAuthorKey(author)}|${year.replace(/[a-z]$/, '')}`;
  return (
    cites.find((entry) => entry.keys.includes(key)) ||
    cites.find((entry) => entry.keys.includes(base)) ||
    cites.find((entry) =>
      entry.keys.some((item) => item.startsWith(`${normalizeAuthorKey(author)}|`) && item.startsWith(base))
    )
  );
}

function firstAuthorToken(part: string) {
  return part
    .replace(/\bet\s*al\.?/gi, '')
    .replace(/等/g, '')
    .split(/\s+(?:and|和|与|&)\s+|[,，]\s*/)[0]
    .replace(/[.\s]+$/g, '')
    .trim();
}

export function matchCitePart(part: string, cites: CiteEntry[]): CiteEntry[] | null {
  const trimmed = part.trim();
  if (!trimmed) return null;
  const years = [...trimmed.matchAll(/\b((?:18|19|20)\d{2})([a-z])?\b/g)];
  if (!years.length) return null;
  const authorPart = trimmed.slice(0, years[0].index).replace(/[,，.\s]+$/g, '');
  const first = firstAuthorToken(authorPart);
  if (!first || first.length < 2) return null;

  const baseYear = years[0][1];
  const yearList = [years[0][2] ? baseYear + years[0][2] : years[0][0]];
  const rest = trimmed.slice(years[0].index + years[0][0].length);
  for (const extra of rest.matchAll(/[,，]\s*([a-z])\b/g)) {
    yearList.push(baseYear + extra[1]);
  }
  for (const year of years.slice(1)) {
    yearList.push(year[0]);
  }

  const found: CiteEntry[] = [];
  const seen = new Set<string>();
  for (const year of yearList) {
    const hit = findCite(cites, first, year);
    if (!hit || seen.has(hit.n)) continue;
    seen.add(hit.n);
    found.push(hit);
  }
  return found.length ? found : null;
}

function toWiki(entries: CiteEntry[]) {
  return entries.map((entry) => `[[#^ref-${entry.n}|${entry.label}]]`).join(',');
}

function linkParenCitations(plain: string, cites: CiteEntry[]) {
  return plain.replace(/[（(]([^）)]{3,180})[）)]/g, (full, inner: string) => {
    const parts = inner
      .split(/[；;]/)
      .map((part) => part.trim())
      .filter(Boolean);
    if (!parts.length) return full;
    const resolved = parts.map((part) => matchCitePart(part, cites));
    if (resolved.some((item) => !item)) return full;
    return toWiki(resolved.flat().filter((item): item is CiteEntry => Boolean(item)));
  });
}

function linkBareCitations(plain: string, cites: CiteEntry[]) {
  let next = plain.replace(
    /([A-ZÀ-Þ][A-Za-zÀ-ÿ'’-]+(?:\s+and\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’-]+|\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’-]+)?)(?:\s+et\s+al\.?|\s*等)?(?:\s*[,，])?\s*(?:[（(]((?:18|19|20)\d{2}[a-z]?(?:\s*[,，]\s*(?:18|19|20)\d{2}[a-z]?)*)[）)]|((?:18|19|20)\d{2}[a-z]?))(?![a-zA-Z])/g,
    (full) => {
      const hits = matchCitePart(full, cites);
      return hits ? toWiki(hits) : full;
    }
  );
  next = next.replace(
    /([\u4e00-\u9fff]{2,4}(?:和[\u4e00-\u9fff]{2,4})?等|[\u4e00-\u9fff]{2,4})\s*[,，]\s*((?:18|19|20)\d{2}[a-z]?)/g,
    (full) => {
      const hits = matchCitePart(full, cites);
      return hits ? toWiki(hits) : full;
    }
  );
  return next;
}

export function linkAuthorYearCitations(body: string, cites: CiteEntry[]) {
  if (!cites.length) return body;
  // 先把括号引用收成 wiki，再在受保护文本上处理裸引用，避免匹配到已生成的标签。
  return protectChunks(protectChunks(body, (plain) => linkParenCitations(plain, cites)), (plain) =>
    linkBareCitations(plain, cites)
  );
}

export function linkBodyCitations(source: string, cites: CiteEntry[]) {
  const { body, refs } = splitAtRefs(source);
  if (!cites.length) return source;
  const linked = linkAuthorYearCitations(linkNumericCitations(body), cites);
  return `${linked}${refs}`;
}

export function restoreCitePlaceholders(html: string, cites: CiteEntry[]) {
  const map = citeMap(cites);
  return html.replace(/((?:\uE100\d+\uE101(?:[,，]\s*\uE100\d+\uE101)*))/g, (seq) => {
    const nums = [...seq.matchAll(/\uE100(\d+)\uE101/g)].map((m) => m[1]);
    const unique = [...new Set(nums)];
    const parts = unique.map((n) => {
      const label = map.get(n)?.label || n;
      return `<a class="paper-cite" href="#ref-${n}" data-ref="${n}">${label}</a>`;
    });
    return `(${parts.join('; ')})`;
  });
}

export function citeLabelOrNumber(n: string, cites: CiteEntry[]) {
  return cites.find((entry) => entry.n === n)?.label || n;
}
