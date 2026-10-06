import DOMPurify from 'dompurify';
import { paths } from 'src/routes/paths';

import { joinAssetUrl } from 'src/utils/vault-url';

import { VAULT_CONTRACT } from 'src/data/vault';
import { appAssetUrl, appRouteUrl } from 'src/lib/app-env';
import { resolveTermByName } from 'src/data/terms';
import { resolvePaperByPid } from 'src/data/papers';
import {
  type CiteEntry,
  citeLabelOrNumber,
  linkBodyCitations,
  parseBibliography,
  linkNumericCitations,
  restoreCitePlaceholders,
} from 'src/lib/citations';

export type MarkdownHeading = {
  id: string;
  text: string;
  level: 2 | 3;
};

declare global {
  interface Window {
    marked?: {
      parse: (src: string, options?: Record<string, unknown>) => string;
    };
    renderMathInElement?: (
      el: HTMLElement,
      options: {
        delimiters: { left: string; right: string; display: boolean }[];
        throwOnError: boolean;
      }
    ) => void;
  }
}

const EMOJI_PREFIX = /^[\p{Extended_Pictographic}\uFE0F\u200D]+\s*/u;
const EMOJI_ALL = /[\p{Extended_Pictographic}\uFE0F\u200D]/gu;

// 内部占位符（私用区字符，marked 会原样透传）
const SEP = '\uE31F';

function slugify(text: string, index: number) {
  const compact = text.trim().slice(0, 32).replace(/\s+/g, '-');
  return `h${index}-${compact || 'section'}`;
}

function stripFrontmatter(source: string) {
  return source.replace(/^---[\s\S]*?\n---\s*/, '');
}

function stripHeadingEmoji(text: string) {
  return text.replace(EMOJI_PREFIX, '').replace(EMOJI_ALL, '').replace(/\s+/g, ' ').trim();
}

export function stripVaultChrome(source: string) {
  let text = stripFrontmatter(source);
  text = text.replace(/<!--[\s\S]*?-->/g, '');
  text = text.replace(/^>\s*返回索引：.*(?:\n|$)/gm, '');
  text = text.replace(/^>\s*.*build_refs\.py.*(?:\n|$)/gm, '');
  text = text.replace(/^>\s*.*库内已入库.*(?:\n|$)/gm, '');
  text = text.replace(/^>\s*.*自动生成（条目保持原文.*(?:\n|$)/gm, '');
  text = text.replace(/^>\s*🤖.*(?:\n|$)/gm, '');
  text = expandDoiChips(text);
  return text.replace(/\n{3,}/g, '\n\n').trim();
}

/** 参考文献的 [🔗 DOI](url) 在网页上展开成完整可点 URL；行里已有同一地址则去掉重复芯片。 */
function expandDoiChips(text: string) {
  return text.replace(
    /(?:｜\s*)?\[(?:🔗\s*)?DOI\]\((https?:\/\/[^)\s]+)\)/gi,
    (_all, rawUrl: string, offset: number, src: string) => {
      const url = rawUrl.trim();
      let decoded = url;
      try {
        decoded = decodeURIComponent(url);
      } catch {
        /* keep encoded */
      }
      const lineStart = src.lastIndexOf('\n', offset) + 1;
      const before = src.slice(lineStart, offset);
      const compact = (value: string) =>
        value.replace(/https?:\/\//gi, '').replace(/[\s‐–—-]/g, '').toLowerCase();
      if (compact(before).includes(compact(decoded)) || compact(before).includes(compact(url))) {
        return '';
      }
      return `[${decoded}](${url})`;
    }
  );
}

/**
 * CommonMark 强调坑：`**图 5：**河道…` 里收尾 `**` 前是全角标点、后紧贴汉字，
 * 不构成右侧定界符，加粗解析失败、星号裸奔。给图注前缀的 `**` 后补一个空格即可合法。
 */
function fixCjkBoldCaptions(text: string) {
  return text.replace(/^(\*{2}(?:图|表|Fig|Figure|Table|Graphical)[^*\n]{0,80}\*{2})(?=\S)/gm, '$1 ');
}

function rewriteWikiImages(text: string, imagesDir?: string) {
  return text.replace(/!\s*\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]/g, (_all, raw: string) => {
    const name = raw.trim();
    const dir = imagesDir || crossPaperImagesDir(name);
    if (!dir) return `![${name}](${name})`;
    return `![${name}](${joinAssetUrl(dir, name)})`;
  });
}

/** 专题文档等无固定图片目录的场景：按图名 `<pid>_pageX_figY` 的 pid 前缀定位所属论文的 images/。 */
function crossPaperImagesDir(name: string) {
  const matched = /^(.+?)_page\d+/i.exec(name);
  return (matched && resolvePaperByPid(matched[1])?.files.imagesDir) || undefined;
}

/** 论文/术语/导航链接的占位构造（HTML 阶段还原为可点击元素）。 */
function paperPlaceholder(slug: string, pid: string, kind: '' | 'cite' | 'source', label: string) {
  return `\uE310${slug}${SEP}${pid}${SEP}${kind}${SEP}${label}\uE311`;
}

function termPlaceholder(key: string, label: string) {
  return `\uE300${key}${SEP}${label}\uE301`;
}

function navPlaceholder(url: string, label: string) {
  return `\uE320${url}${SEP}${label}\uE321`;
}

function mocTarget(target: string): { url: string; label: string } {
  const clean = stripHeadingEmoji(target.replace(/^_+/, '').trim());
  if (clean.includes('术语库')) {
    return { url: paths.dashboard.terms, label: '术语库' };
  }
  if (clean.includes('论文地图')) {
    return { url: paths.dashboard.papers.root, label: '论文库' };
  }
  return {
    url: `${paths.dashboard.papers.root}?domain=${encodeURIComponent(clean)}`,
    label: clean,
  };
}

/**
 * notes 章节重排：把「# 深度分析」整块移到「## 问答」之前（研究价值先看，问答后置）。
 */
export function reorderNoteSections(source: string) {
  const qaMatch = /^##\s+[^\n]*问答[^\n]*$/m.exec(source);
  const analysisMatch = /^#\s+[^\n]*深度分析[^\n]*$/m.exec(source);
  if (!qaMatch || !analysisMatch || analysisMatch.index < qaMatch.index) return source;

  const afterAnalysisHeading = analysisMatch.index + analysisMatch[0].length;
  const nextH1 = /^#\s+/m.exec(source.slice(afterAnalysisHeading));
  const analysisEnd = nextH1 ? afterAnalysisHeading + nextH1.index : source.length;
  const analysisBlock = source.slice(analysisMatch.index, analysisEnd).trimEnd();

  const withoutAnalysis = source.slice(0, analysisMatch.index) + source.slice(analysisEnd);
  const qaInNew = /^##\s+[^\n]*问答[^\n]*$/m.exec(withoutAnalysis);
  if (!qaInNew) return source;
  return (
    `${withoutAnalysis.slice(0, qaInNew.index).trimEnd()}\n\n${analysisBlock}\n\n` +
    withoutAnalysis.slice(qaInNew.index)
  );
}

/** 从中文正文抽参考文献，为尚未补齐英文参考表的存量条目提供阅读回退。 */
export function extractRefsSection(source: string) {
  const match = /^##\s+[^\n]*参考文献[^\n]*$/m.exec(source);
  if (!match) return '';
  const rest = source.slice(match.index);
  const next = /\n##\s+/.exec(rest.slice(match[0].length));
  return (next ? rest.slice(0, match[0].length + next.index) : rest).trim();
}

/** 英文优先使用自身完整 References；存量缺表时复用中文清单，避免重复显示。 */
export function englishArticleNeedsReferences(enSource: string) {
  return Boolean(enSource.trim()) && !/^##\s+References\s*$/im.test(enSource);
}

export function prepareEnglishArticle(enSource: string, chineseSource: string) {
  if (/^##\s+References\s*$/im.test(enSource)) return linkNumericCitations(enSource);
  const refs = extractRefsSection(chineseSource);
  if (!refs) return enSource;
  return `${linkNumericCitations(enSource).trim()}\n\n${refs.replace(/^##[^\n]*/, '## References')}\n`;
}

function rewriteWikiLinks(text: string, forHtml: boolean, cites: CiteEntry[] = []) {
  let next = text.replace(/式\[\[#\^ref-(\d+)\|[^\]]*\]\]/g, '式（$1）');
  if (forHtml) {
    next = next.replace(/\[\[#\^ref-(\d+)\|[^\]]*\]\]/g, (_all, n: string) => `\uE100${n}\uE101`);
    next = next.replace(/[ \t]*\^ref-(\d+)\b/g, (_all, n: string) => `\uE200${n}\uE201`);
  } else {
    next = next.replace(/\[\[#\^ref-(\d+)\|[^\]]*\]\]/g, (_all, n: string) => `(${citeLabelOrNumber(n, cites)})`);
    next = next.replace(/[ \t]*\^ref-(\d+)\b/g, '');
  }

  // 📥（引用互链）/ 📄（出处）前缀的论文链接
  next = next.replace(
    /(📥|📄)\s*\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/gu,
    (_all, mark: string, target: string, alias?: string) => {
      const pid = target.trim();
      const label = stripHeadingEmoji((alias || pid).trim());
      const paper = resolvePaperByPid(pid);
      if (!forHtml || !paper) return label;
      return paperPlaceholder(paper.slug, pid, mark === '📥' ? 'cite' : 'source', label);
    }
  );

  next = next.replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/g, (_all, rawTarget: string, alias?: string) => {
    const target = rawTarget.trim();
    const label = stripHeadingEmoji((alias || target).trim());
    if (!forHtml) return label;

    if (target.startsWith('_')) {
      const moc = mocTarget(target);
      return navPlaceholder(moc.url, alias ? label : moc.label);
    }

    const paper = resolvePaperByPid(target);
    if (paper) {
      return paperPlaceholder(paper.slug, target, '', label);
    }

    const term = resolveTermByName(target);
    if (term) {
      return termPlaceholder(term.key, alias ? label : term.term);
    }

    return forHtml ? `**${label}**` : label;
  });
  return next;
}

export function preprocessVaultMarkdown(source: string, imagesDir?: string) {
  let text = stripVaultChrome(source);
  const cites = parseBibliography(text);
  text = linkBodyCitations(text, cites);
  text = fixCjkBoldCaptions(text);
  text = rewriteWikiImages(text, imagesDir);
  text = rewriteWikiLinks(text, true, cites);
  return { text: text.trim(), cites };
}

export function toCopyMarkdown(source: string, imagesDir?: string) {
  let text = stripVaultChrome(source);
  const cites = parseBibliography(text);
  text = linkBodyCitations(text, cites);
  text = text.replace(/[📥📄]\s*/gu, '');
  text = rewriteWikiImages(text, imagesDir);
  text = rewriteWikiLinks(text, false, cites);
  text = text.replace(/\*\*【说明】\*\*\s*/g, '说明：');
  text = text.replace(/【说明】\s*/g, '说明：');
  return text.trim();
}

/** 按标题和空行切块，只保留包含查询词的段。 */
export function filterMarkdownBlocks(source: string, query: string) {
  const q = query.trim();
  if (!q) return { text: source, count: 0 };
  const needle = q.toLowerCase();
  const blocks: string[] = [];
  source.split(/(?=^#{1,6}\s)/m).forEach((part) => {
    part.split(/\n{2,}/).forEach((chunk) => {
      const trimmed = chunk.trim();
      if (trimmed) blocks.push(trimmed);
    });
  });
  const matched = blocks.filter((block) => block.toLowerCase().includes(needle));
  return { text: matched.join('\n\n'), count: matched.length };
}

export function extractHeadings(html: string): MarkdownHeading[] {
  const headings: MarkdownHeading[] = [];
  const matcher = /<h([23])([^>]*)>([\s\S]*?)<\/h\1>/gi;
  let index = 0;
  let match = matcher.exec(html);
  while (match) {
    const text = stripHeadingEmoji(match[3].replace(/<[^>]+>/g, '').trim());
    headings.push({
      id: slugify(text, index),
      text,
      level: Number(match[1]) as 2 | 3,
    });
    index += 1;
    match = matcher.exec(html);
  }
  return headings;
}

export function injectHeadingIds(html: string, headings: MarkdownHeading[]) {
  let cursor = 0;
  return html.replace(/<h([23])([^>]*)>/gi, (full, level: string, attrs: string) => {
    const heading = headings[cursor];
    cursor += 1;
    if (!heading) return full;
    if (/\sid=/.test(attrs)) return `<h${level}${attrs}>`;
    return `<h${level}${attrs} id="${heading.id}">`;
  });
}

export function wrapTables(html: string) {
  return html.replace(/<table[\s\S]*?<\/table>/gi, (table) => `<div class="tbl-wrap">${table}</div>`);
}

function restoreCitations(html: string, cites: CiteEntry[]) {
  return restoreCitePlaceholders(html, cites);
}

function restoreRefAnchors(html: string) {
  return html.replace(/<li>([\s\S]*?)<\/li>/gi, (full, inner: string) => {
    const ids = [...new Set([...inner.matchAll(/\uE200(\d+)\uE201/g)].map((match) => match[1]))];
    if (!ids.length) return full;
    const cleaned = inner.replace(/\uE200\d+\uE201/g, '').trim();
    const aliases = ids.slice(1).map((id) => `<span id="ref-${id}"></span>`).join('');
    return `<li id="ref-${ids[0]}" class="paper-ref">${aliases}${cleaned}</li>`;
  });
}

function restoreTermLinks(html: string) {
  return html.replace(
    new RegExp(`\uE300([^${SEP}\uE301]*)${SEP}([\\s\\S]*?)\uE301`, 'g'),
    (_all, key: string, label: string) => `<a class="term-link" data-term="${key}">${label}</a>`
  );
}

function restorePaperLinks(html: string) {
  return html.replace(
    new RegExp(`\uE310([\\s\\S]*?)\uE311`, 'g'),
    (_all, payload: string) => {
      const [slug, pid, kind, ...rest] = payload.split(SEP);
      const label = rest.join(SEP);
      const href = `${paths.dashboard.papers.root}/${slug}`;
      const tag = kind === 'cite' ? '<span class="paper-link-tag">引用</span>' : kind === 'source' ? '<span class="paper-link-tag">出处</span>' : '';
      const classes = kind ? 'paper-link paper-link-chip' : 'paper-link';
      return `<a class="${classes}" href="${appRouteUrl(href)}" data-nav="${href}" data-pid="${pid}">${tag}${label}</a>`;
    }
  );
}

function restoreNavLinks(html: string) {
  return html.replace(
    new RegExp(`\uE320([\\s\\S]*?)\uE321`, 'g'),
    (_all, payload: string) => {
      const [url, ...rest] = payload.split(SEP);
      const label = rest.join(SEP);
      return `<a class="nav-link" href="${appRouteUrl(url)}" data-nav="${url}">${label}</a>`;
    }
  );
}

/**
 * 「说明」引用块 → 公式注解卡片。
 * 内层用 tempered greedy token 挡住 `</blockquote>`：否则当文中第一个引用块不含【说明】时，
 * 惰性量词会跨过它的闭合标签一路吞到下一个说明块，把中间整段正文卷进注解卡里。
 */
function wrapFormulaNotes(html: string) {
  const NOT_CLOSE = '(?:(?!</?blockquote>)[\\s\\S])*?';
  return html.replace(
    new RegExp(`<blockquote>(\\s*<p>${NOT_CLOSE}【说明】${NOT_CLOSE})</blockquote>`, 'gi'),
    (_all, inner: string) => {
      const body = String(inner)
        .replace(/<strong>\s*【说明】\s*<\/strong>\s*/g, '')
        .replace(/【说明】\s*/g, '');
      return `<aside class="formula-note"><div class="formula-note-title">${ICONS.info}说明</div>${body}</aside>`;
    }
  );
}

/**
 * 章节 emoji → 线性图标（Feather 风格，stroke=currentColor），未收录的 emoji 剥离兜底。
 */
const ICON_SVG = (inner: string) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;

const ICONS: Record<string, string> = {
  pin: ICON_SVG('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>'),
  book: ICON_SVG('<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'),
  question: ICON_SVG('<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
  search: ICON_SVG('<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'),
  pen: ICON_SVG('<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>'),
  award: ICON_SVG('<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>'),
  folder: ICON_SVG('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'),
  card: ICON_SVG('<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>'),
  compass: ICON_SVG('<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>'),
  image: ICON_SVG('<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>'),
  zap: ICON_SVG('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
  chart: ICON_SVG('<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>'),
  link: ICON_SVG('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'),
  info: ICON_SVG('<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'),
};

const HEADING_EMOJI_ICON: Record<string, string> = {
  '📌': ICONS.pin,
  '📖': ICONS.book,
  '📚': ICONS.book,
  '❓': ICONS.question,
  '🔬': ICONS.search,
  '🔍': ICONS.search,
  '✍': ICONS.pen,
  '✍️': ICONS.pen,
  '🎓': ICONS.award,
  '🗂': ICONS.folder,
  '🗂️': ICONS.folder,
  '📇': ICONS.card,
  '🧭': ICONS.compass,
  '🖼': ICONS.image,
  '🖼️': ICONS.image,
  '💡': ICONS.zap,
  '⚡': ICONS.zap,
  '📊': ICONS.chart,
  '📈': ICONS.chart,
  '🔗': ICONS.link,
};

const H1_SUFFIXES = /（(?:中文翻译|方法原理精讲)）\s*$|\((?:中文翻译|方法原理精讲)\)\s*$/;

function decorateHeadings(html: string) {
  return html.replace(/<h([1-6])([^>]*)>([\s\S]*?)<\/h\1>/gi, (_all, level: string, attrs: string, inner: string) => {
    const plain = inner.replace(/<[^>]+>/g, '');
    const emojiMatch = plain.match(/^\s*([\p{Extended_Pictographic}\uFE0F\u200D]+)/u);
    let cleanText = stripHeadingEmoji(inner);
    if (level === '1') {
      cleanText = cleanText.replace(H1_SUFFIXES, '').trim();
    }
    if (!emojiMatch) {
      return `<h${level}${attrs}>${cleanText}</h${level}>`;
    }
    const emoji = emojiMatch[1].replace(/[\uFE0F\u200D]/g, '');
    const icon = HEADING_EMOJI_ICON[emoji] || HEADING_EMOJI_ICON[`${emoji}\uFE0F`];
    const prefix = icon ? `<span class="h-ico">${icon}</span>` : '';
    return `<h${level}${attrs}>${prefix}${cleanText}</h${level}>`;
  });
}

/** 图片行（或连续图组）+ 紧跟的「图 N：/表 N/Fig.」段落 → figure/figcaption（图注居中）。
 * 复合图 (a)(b) 拆成多张连续嵌入、整组共享一个图注也支持（与 web_lint 的图组规则一致）。 */
function wrapFigures(html: string) {
  const caption = '(?:<(?:strong|em)>\\s*)?(?:图|表|Fig|Figure|Table|Graphical)';
  return html
    .replace(
      // 图组：一个或多个段落、每段一张或多张 img（连续嵌入行会被合并进同一 <p>），共享其后的图注段
      new RegExp(`((?:<p>\\s*(?:<img[^>]*>\\s*)+</p>\\s*)+)<p>(${caption}[\\s\\S]*?)</p>`, 'gi'),
      (_all, imgGroup: string, cap: string) => {
        const imgs = imgGroup.replace(/<\/?p>/gi, '').trim();
        return `<figure class="md-fig">${imgs}<figcaption>${cap}</figcaption></figure>`;
      }
    )
    .replace(
      new RegExp(`<p>\\s*((?:<img[^>]*>\\s*)+)(${caption}[\\s\\S]*?)</p>`, 'gi'),
      (_all, imgs: string, cap: string) =>
        `<figure class="md-fig">${imgs.trim()}<figcaption>${cap}</figcaption></figure>`
    );
}

/** 紧跟标题的引导 blockquote → 视觉降权的 hint（Obsidian 侧的阅读提示，网页上弱化显示）。 */
function markHintBlockquotes(html: string) {
  return html.replace(/(<\/h[1-6]>\s*)<blockquote>/gi, '$1<blockquote class="md-hint">');
}

/**
 * 「亮点 / Highlights」小节的列表 → 高亮卡片样式（标题吸收进卡片）。
 *
 * 列表后若跟着「本节要点由 AI 通读全文提炼」的说明块，说明原刊没印 Highlights、
 * 这批要点是 AI 总结的：把说明块吸收成卡片标题旁的徽标，读者一眼分得清它和
 * 期刊自印要点的区别。徽标必须渲染在卡片里——单独留在下面的注解卡容易被跳过。
 */
function decorateHighlights(html: string) {
  const AI_NOTE =
    /(?:\s*<aside class="formula-note">[\s\S]*?本节要点由\s*AI\s*通读全文提炼[\s\S]*?<\/aside>|\s*<blockquote[^>]*>[\s\S]*?本节要点由\s*AI\s*通读全文提炼[\s\S]*?<\/blockquote>)/;
  return html.replace(
    new RegExp(
      '<h2[^>]*>(?:<span class="h-ico">[\\s\\S]*?</span>)?\\s*(亮点|Highlights|Key Points)\\s*</h2>\\s*<ul>([\\s\\S]*?)</ul>' +
        `(${AI_NOTE.source})?`
    ),
    (_all, label: string, items: string, aiNote?: string) => {
      const badge = aiNote
        ? '<span class="md-sec-badge" title="原刊未印 Highlights，本节要点由 AI 通读全文提炼">AI 提炼</span>'
        : '';
      return `<section class="md-highlights-card"><div class="md-sec-label">${ICONS.zap}${label}${badge}</div><ul class="md-highlights">${items}</ul></section>`;
    }
  );
}

/** 「摘要 / Abstract」小节 → 独立摘要卡片（标题吸收进卡片，直到下一个标题）。 */
function decorateAbstract(html: string) {
  return html.replace(
    /<h2[^>]*>(?:<span class="h-ico">[\s\S]*?<\/span>)?\s*(摘要|Abstract)\s*<\/h2>\s*([\s\S]*?)(?=<h[12][\s>]|$)/,
    (_all, label: string, body: string) =>
      `<section class="md-abstract"><div class="md-sec-label">${ICONS.book}${label}</div>${body}</section>`
  );
}

/** 「引言 / Introduction」首节加导读底色，和摘要区分开。 */
function decorateIntroduction(html: string) {
  return html.replace(
    /(<h2[^>]*>(?:<span class="h-ico">[\s\S]*?<\/span>)?\s*(?:\d+\.?\s*)?(引言|Introduction)\s*<\/h2>)([\s\S]*?)(?=<h2[\s>]|$)/,
    (_all, heading: string, _label: string, body: string) =>
      `<section class="md-intro">${heading}${body}</section>`
  );
}

function keywordChips(body: string, label: string) {
  const parts = body
    .replace(/<[^>]+>/g, '')
    .split(/[；;,，]/)
    .map((part) => part.replace(/[。.\s]+$/g, '').trim())
    .filter(Boolean);
  if (!parts.length) return '';
  const chips = parts.map((part) => `<span class="kw-chip">${part}</span>`).join('');
  return `<div class="md-keywords"><span class="md-keywords-label">${label}</span>${chips}</div>`;
}

/** 「**关键词：** a；b；c」段落 / 「## Keywords」小节 → 关键词 chips。 */
function decorateKeywords(html: string) {
  let next = html.replace(
    /<p><strong>\s*关键词[：:]\s*<\/strong>\s*([\s\S]*?)<\/p>/,
    (_all, body: string) => keywordChips(body, '关键词') || _all
  );
  next = next.replace(
    /<h2[^>]*>(?:<span class="h-ico">[\s\S]*?<\/span>)?\s*(关键词|Keywords)\s*<\/h2>\s*<p>([\s\S]*?)<\/p>/,
    (_all, label: string, body: string) =>
      keywordChips(body, label === 'Keywords' ? 'Keywords' : '关键词') || _all
  );
  return next;
}

/** H1 后紧跟的作者行 + 单位行 → 降权 byline（页头已有完整元信息）。 */
function decorateByline(html: string) {
  return html.replace(
    /(<\/h1>\s*)<p><strong>([\s\S]*?)<\/strong><\/p>(?:\s*<p>(?!<strong>)([\s\S]*?)<\/p>)?/,
    (_all, h1End: string, authors: string, affiliation?: string) => {
      const cleanAuthors = authors.replace(/<sup>[\s\S]*?<\/sup>/gi, '').replace(/\^\{[^}]+\}/g, '');
      const affiliationHtml = affiliation ? `<p class="md-byline">${affiliation}</p>` : '';
      return `${h1End}<p class="md-byline md-byline-authors">${cleanAuthors}</p>${affiliationHtml}`;
    }
  );
}

export function renderMarkdown(source: string, cites: CiteEntry[] = []) {
  if (!window.marked) {
    throw new Error('marked 尚未加载');
  }
  const store: string[] = [];
  const stash = (value: string) => {
    store.push(value);
    return `\uE000${store.length - 1}\uE001`;
  };
  const parts = source.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/);
  for (let i = 0; i < parts.length; i += 2) {
    parts[i] = parts[i]
      .replace(/\$\$([\s\S]+?)\$\$/g, stash)
      .replace(/\\\[([\s\S]+?)\\\]/g, stash)
      .replace(/\\\(([\s\S]+?)\\\)/g, stash)
      .replace(/\$(?!\s)([^$\n]+?)(?<!\s)\$/g, stash);
  }
  let html = window.marked.parse(parts.join(''), { gfm: true, mangle: false, headerIds: false });
  // 标准 Markdown/HTML 的图像和文件链接也须遵循部署目录及桌面协议。
  html = html.replace(/(\b(?:src|href|data-full-src)=["'])\/vault\//gi, `$1${VAULT_CONTRACT.publicRoot}/`);
  html = html.replace(/\uE000(\d+)\uE001/g, (_all, n: string) => {
    const raw = store[Number(n)] ?? '';
    return raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  });
  html = restoreCitations(html, cites);
  html = restoreRefAnchors(html);
  html = restoreTermLinks(html);
  html = restorePaperLinks(html);
  html = restoreNavLinks(html);
  html = wrapFormulaNotes(html);
  html = wrapFigures(html);
  html = decorateHeadings(html);
  html = markHintBlockquotes(html);
  html = decorateHighlights(html);
  html = decorateAbstract(html);
  html = decorateIntroduction(html);
  html = decorateKeywords(html);
  html = decorateByline(html);
  const headings = extractHeadings(html);
  html = injectHeadingIds(html, headings);
  html = wrapTables(html);
  return { html: DOMPurify.sanitize(html, { USE_PROFILES: { html: true, svg: true, mathMl: true }, ADD_ATTR: ['target', 'data-nav', 'data-term', 'data-ref', 'data-kind', 'data-full-src'] }), headings };
}

export function typesetMath(root: HTMLElement) {
  if (!window.renderMathInElement) return;
  window.renderMathInElement(root, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
      { left: '$', right: '$', display: false },
    ],
    throwOnError: false,
  });
}

function katexTex(node: Element) {
  return (
    node.querySelector('annotation')?.textContent?.trim() ||
    node.getAttribute('aria-label')?.trim() ||
    ''
  );
}

/** 把已渲染公式还原成可见的 $LaTeX$，复制时才能拿到源码。 */
export function revealLatexSource(root: HTMLElement) {
  root.querySelectorAll('.katex-display').forEach((node) => {
    const tex = katexTex(node);
    if (!tex) return;
    const code = document.createElement('code');
    code.className = 'ws-tex ws-tex-display';
    code.textContent = `$$${tex}$$`;
    node.replaceWith(code);
  });
  root.querySelectorAll('.katex').forEach((node) => {
    if (node.closest('.ws-tex')) return;
    const tex = katexTex(node);
    if (!tex) return;
    const code = document.createElement('code');
    code.className = 'ws-tex';
    code.textContent = `$${tex}$`;
    node.replaceWith(code);
  });
}

function loadScript(src: string) {
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-vendor="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`脚本加载失败: ${src}`)), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset.vendor = src;
    script.onload = () => {
      script.dataset.loaded = 'true';
      resolve();
    };
    script.onerror = () => reject(new Error(`脚本加载失败: ${src}`));
    document.body.appendChild(script);
  });
}

function loadStylesheet(href: string) {
  if (document.querySelector(`link[data-vendor="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  link.dataset.vendor = href;
  document.head.appendChild(link);
}

let vendorPromise: Promise<void> | null = null;

export function ensureMarkdownVendors() {
  if (!vendorPromise) {
    loadStylesheet(appAssetUrl('vendor/katex/katex.min.css'));
    vendorPromise = loadScript(appAssetUrl('vendor/marked.min.js'))
      .then(() => loadScript(appAssetUrl('vendor/katex/katex.min.js')))
      .then(() => loadScript(appAssetUrl('vendor/katex/auto-render.min.js')));
  }
  return vendorPromise;
}

function replaceNodeWithText(node: Element, value: string) {
  node.replaceWith(document.createTextNode(value));
}

export function selectionToCopyText() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return '';
  const contents = selection.getRangeAt(0).cloneContents();
  const wrap = document.createElement('div');
  wrap.appendChild(contents);
  wrap.querySelectorAll('.h-ico').forEach((node) => node.remove());
  wrap.querySelectorAll('.paper-link-tag').forEach((node) => node.remove());
  wrap.querySelectorAll('a.paper-cite, .paper-cite').forEach((node) => {
    replaceNodeWithText(node, node.textContent || '');
  });
  wrap.querySelectorAll('a.paper-link').forEach((node) => {
    const pid = (node as HTMLAnchorElement).dataset.pid;
    replaceNodeWithText(node, pid ? `[[${pid}]]` : node.textContent || '');
  });
  wrap.querySelectorAll('a.term-link, a.nav-link').forEach((node) => {
    replaceNodeWithText(node, node.textContent || '');
  });
  wrap.querySelectorAll('.katex-display, .katex, code.ws-tex').forEach((node) => {
    if (node.classList.contains('ws-tex')) {
      replaceNodeWithText(node, node.textContent || '');
      return;
    }
    if (node.closest('.katex-display') && !node.classList.contains('katex-display')) return;
    const tex = katexTex(node) || node.textContent || '';
    const display = node.classList.contains('katex-display') || Boolean(node.closest('.katex-display'));
    replaceNodeWithText(node, display ? `$$${tex}$$` : `$${tex}$`);
  });
  wrap.querySelectorAll('.formula-note-title').forEach((node) => {
    replaceNodeWithText(node, '说明：');
  });
  return (wrap.innerText || wrap.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
}
