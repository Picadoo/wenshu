import type { TermEntry } from 'src/data/terms';
import type { MarkdownHeading } from 'src/lib/markdown';
import type { Theme, SxProps } from '@mui/material/styles';
import type { VocabEntry, HighlightEntry } from 'src/lib/notes-store';

import DOMPurify from 'dompurify';

import { alpha as varAlpha } from '@mui/material/styles';
import { memo, useRef, useMemo, useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Paper from '@mui/material/Paper';
import Button from '@mui/material/Button';
import Popper from '@mui/material/Popper';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';

import { paths } from 'src/routes/paths';
import { useRouter } from 'src/routes/hooks';
import { RouterLink } from 'src/routes/components';

import { getTerm } from 'src/data/terms';
import { makeId } from 'src/lib/notes-store';
import { isHttpUrl, openExternal } from 'src/lib/open-external';
import { webImageUrl, hasWebVariant, USE_WEB_IMAGES } from 'src/lib/web-image';
import { lookupVocab, sameVocabSentence, subscribeVocabBook } from 'src/lib/vocab-book';
import { loadHoverTips, loadTermLinks, subscribeHoverTips, subscribeTermLinks } from 'src/lib/reader-prefs';
import {
  typesetMath,
  renderMarkdown,
  revealLatexSource,
  selectionToCopyText,
  ensureMarkdownVendors,
  preprocessVaultMarkdown,
} from 'src/lib/markdown';

import { Iconify } from 'src/components/iconify';
import { Lightbox } from 'src/components/lightbox';

// ----------------------------------------------------------------------

type Props = {
  source: string;
  empty: string;
  pid?: string;
  imagesDir?: string;
  copyMode?: boolean;
  onHeadings?: (headings: MarkdownHeading[]) => void;
  /** 高亮支持（阅读工作台） */
  highlightable?: boolean;
  tabKey?: string;
  highlights?: HighlightEntry[];
  onHighlightsChange?: (next: HighlightEntry[]) => void;
  onClip?: (text: string) => void;
  /** 生词标注（英文正文 tab）：双击标注生词、点击黄色标记删除 */
  vocab?: VocabEntry[];
  vocabMode?: boolean;
  onVocabChange?: (next: VocabEntry[]) => void;
  locateWord?: string;
  onLocated?: () => void;
  /** 段落筛选命中词标黄 */
  searchQuery?: string;
  /** 分享页：术语只悬浮/点开释义，不进术语库（访客无登录） */
  shareMode?: boolean;
};

type VocabGloss = {
  word: string;
  pos: string;
  en: string;
  zh: string;
  anchor: HTMLElement;
  pinned: boolean;
};

type SelectionInfo = {
  block: number;
  start: number;
  end: number;
  text: string;
  rect: DOMRect;
};

function citationText(root: HTMLElement, id: string) {
  const node = root.querySelector(`#ref-${id}`);
  if (!node) return '';
  return (node.textContent || '').replace(/\s+/g, ' ').trim();
}

const BLOCK_SELECTOR = 'p, li, figcaption';
const CONTEXT_SELECTOR = `${BLOCK_SELECTOR}, h1, h2, h3, h4, h5, h6`;

function sentenceForWord(paragraph: string, word: string) {
  const lower = word.toLowerCase();
  const parts = splitSentences(paragraph);
  const bounded = new RegExp(`\\b${escapeRegExp(lower)}\\b`, 'i');
  return (
    parts.find((item) => bounded.test(item)) ||
    parts.find((item) => item.toLowerCase().includes(lower)) ||
    ''
  ).trim();
}

function getBlocks(root: HTMLElement) {
  return [...root.querySelectorAll<HTMLElement>(BLOCK_SELECTOR)];
}

/** 块内文本偏移（含已渲染公式/标记的可见文本）。 */
function offsetWithin(block: HTMLElement, container: Node, offset: number) {
  const range = document.createRange();
  range.selectNodeContents(block);
  try {
    range.setEnd(container, offset);
  } catch {
    return -1;
  }
  return range.toString().length;
}

function escapeRegExp(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function splitSentences(paragraph: string) {
  return paragraph.split(/(?<=[.!?;])\s+/);
}

function unwrapSearchMarks(root: HTMLElement) {
  root.querySelectorAll('mark.ws-q').forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

function applySearchMarks(root: HTMLElement, query: string) {
  unwrapSearchMarks(root);
  const q = query.trim();
  if (!q) return;
  const pattern = new RegExp(escapeRegExp(q), 'gi');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const parent = (node as Text).parentElement;
      if (!parent || parent.closest('.katex, code, pre, mark, script, style')) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const textNodes: Text[] = [];
  let node = walker.nextNode() as Text | null;
  while (node) {
    textNodes.push(node);
    node = walker.nextNode() as Text | null;
  }
  textNodes.forEach((textNode) => {
    const text = textNode.textContent ?? '';
    pattern.lastIndex = 0;
    if (!pattern.test(text)) return;
    pattern.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text))) {
      if (match.index > last) {
        frag.appendChild(document.createTextNode(text.slice(last, match.index)));
      }
      const mark = document.createElement('mark');
      mark.className = 'ws-q';
      mark.textContent = match[0];
      frag.appendChild(mark);
      last = match.index + match[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode?.replaceChild(frag, textNode);
  });
}

function unwrapVocab(root: HTMLElement) {
  root.querySelectorAll('mark.ws-vocab').forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

/** 把生词标记重放到 DOM（跳过公式/代码/已有标记，不改变块内可见文本）。 */
function applyVocab(root: HTMLElement, vocab: VocabEntry[]) {
  unwrapVocab(root);
  if (!vocab.length) return;
  const seen = new Set<string>();
  const words = vocab
    .map((entry) => entry.word)
    .filter((word) => {
      const key = word.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map(escapeRegExp)
    .sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`\\b(${words.join('|')})\\b`, 'gi');

  getBlocks(root).forEach((block) => {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        const parent = (node as Text).parentElement;
        if (!parent || parent.closest('.katex, code, pre, mark, a')) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const textNodes: Text[] = [];
    let node = walker.nextNode() as Text | null;
    while (node) {
      textNodes.push(node);
      node = walker.nextNode() as Text | null;
    }
    textNodes.forEach((textNode) => {
      const text = textNode.textContent ?? '';
      pattern.lastIndex = 0;
      if (!pattern.test(text)) return;
      pattern.lastIndex = 0;
      const frag = document.createDocumentFragment();
      let last = 0;
      let match: RegExpExecArray | null;
      while ((match = pattern.exec(text))) {
        if (match.index > last) {
          frag.appendChild(document.createTextNode(text.slice(last, match.index)));
        }
        const mark = document.createElement('mark');
        mark.className = 'ws-vocab';
        mark.textContent = match[0];
        frag.appendChild(mark);
        last = match.index + match[0].length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      textNode.parentNode?.replaceChild(frag, textNode);
    });
  });
}

function applyVocabGloss(root: HTMLElement) {
  root.querySelectorAll<HTMLElement>('mark.ws-vocab').forEach((mark) => {
    const entry = lookupVocab(mark.textContent || '');
    if (!entry) {
      delete mark.dataset.pos;
      delete mark.dataset.en;
      delete mark.dataset.zh;
      return;
    }
    if (entry.pos) mark.dataset.pos = entry.pos;
    else delete mark.dataset.pos;
    if (entry.en) mark.dataset.en = entry.en;
    else delete mark.dataset.en;
    if (entry.zh) mark.dataset.zh = entry.zh;
    else delete mark.dataset.zh;
    mark.classList.toggle('ws-vocab-book', Boolean(entry.en || entry.zh));
  });
}

function unwrapHighlights(root: HTMLElement) {
  root.querySelectorAll('mark.ws-hl').forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    parent.normalize();
  });
}

/** 把高亮重放到 DOM；返回失配（原文已变）的条目数。 */
function applyHighlights(root: HTMLElement, highlights: HighlightEntry[], tabKey: string) {
  unwrapHighlights(root);
  const blocks = getBlocks(root);
  let failed = 0;

  highlights
    .filter((entry) => entry.tab === tabKey)
    .forEach((entry) => {
      const block = blocks[entry.block];
      const text = block?.textContent ?? '';
      if (!block || text.slice(entry.start, entry.end) !== entry.text) {
        failed += 1;
        return;
      }
      const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
      const targets: { node: Text; start: number; end: number }[] = [];
      let acc = 0;
      let node = walker.nextNode() as Text | null;
      while (node) {
        const len = node.textContent?.length ?? 0;
        const localStart = Math.max(0, entry.start - acc);
        const localEnd = Math.min(len, entry.end - acc);
        if (localStart < localEnd) {
          targets.push({ node, start: localStart, end: localEnd });
        }
        acc += len;
        if (acc >= entry.end) break;
        node = walker.nextNode() as Text | null;
      }
      targets.forEach(({ node: textNode, start, end }) => {
        let target = textNode;
        if (end < (target.textContent?.length ?? 0)) target.splitText(end);
        if (start > 0) target = target.splitText(start);
        const mark = document.createElement('mark');
        mark.className = 'ws-hl';
        mark.dataset.hlId = entry.id;
        target.parentNode?.insertBefore(mark, target);
        mark.appendChild(target);
      });
    });

  return failed;
}

// 静态样式提到模块级：组件因 hover 弹卡等频繁重渲时，不再重建这个大对象让 emotion 重新序列化
const MARKDOWN_SX: SxProps<Theme> = {
  color: 'text.primary',
  userSelect: 'text',
  overflowWrap: 'anywhere',
  '& h1': { typography: 'h4', mb: 2, mt: 0 },
  '& h2': {
    typography: 'h5',
    mt: 4,
    mb: 1.5,
    px: 1.5,
    py: 1,
    bgcolor: 'action.hover',
    borderLeft: (theme) => `4px solid ${theme.palette.primary.main}`,
    borderRadius: '0 8px 8px 0',
    scrollMarginTop: 96,
  },
  '& h3': { typography: 'h6', mt: 3, mb: 1, color: 'primary.main', scrollMarginTop: 96 },
  '& h4': { typography: 'subtitle1', mt: 2.5, mb: 1 },
  '& .h-ico': {
    mr: 0.75,
    display: 'inline-flex',
    alignItems: 'center',
    verticalAlign: 'text-bottom',
    color: 'text.secondary',
  },
  '& .h-ico svg': { width: 16, height: 16 },
  '& h1 .h-ico svg': { width: 18, height: 18 },
  '& mark.ws-q': {
    px: 0.15,
    borderRadius: 0.4,
    color: 'inherit',
    bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.28),
  },
  '& p': { typography: 'body2', lineHeight: 1.9, my: 1.25 },
  '& li': { typography: 'body2', lineHeight: 1.8, my: 0.5 },
  '& ul, & ol': { pl: 3, my: 1.25 },
  '& blockquote': {
    my: 2,
    px: 2,
    py: 1.5,
    bgcolor: 'action.hover',
    borderLeft: (theme) => `3px solid ${theme.palette.divider}`,
    borderRadius: '0 8px 8px 0',
    color: 'text.secondary',
  },
  '& blockquote.md-hint': {
    my: 1,
    px: 0,
    py: 0,
    pl: 1.5,
    bgcolor: 'transparent',
    borderLeft: (theme) => `2px solid ${theme.palette.divider}`,
    borderRadius: 0,
    color: 'text.disabled',
  },
  '& blockquote.md-hint p': { typography: 'caption', my: 0.25, lineHeight: 1.6 },
  '& p.md-byline': {
    typography: 'caption',
    color: 'text.disabled',
    my: 0.25,
    lineHeight: 1.6,
  },
  '& p.md-byline-authors': { color: 'text.secondary', fontWeight: 500 },
  '& section.md-highlights-card': {
    my: 2.5,
    px: 3,
    py: 2.5,
    borderRadius: 2,
    bgcolor: (theme) => varAlpha(theme.palette.primary.main, 0.05),
    border: (theme) => `1px solid ${varAlpha(theme.palette.primary.main, 0.16)}`,
  },
  '& section.md-abstract': {
    my: 2.5,
    px: 3,
    py: 2.5,
    borderRadius: 2,
    bgcolor: (theme) => varAlpha(theme.palette.grey[500], 0.06),
    border: (theme) => `1px solid ${theme.palette.divider}`,
  },
  '& section.md-abstract p': { my: 1, '&:last-of-type': { mb: 0 } },
  '& section.md-intro': {
    my: 2.5,
    px: 0,
    pt: 0.5,
    pb: 1,
    borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
  },
  '& section.md-intro > h2': { mt: 0 },
  '& .md-sec-label': {
    typography: 'overline',
    letterSpacing: 1,
    color: 'primary.main',
    display: 'flex',
    alignItems: 'center',
    gap: 0.75,
    mb: 1.25,
  },
  '& .md-sec-label svg': { width: 15, height: 15 },
  // 「AI 提炼」徽标：原刊没印 Highlights、这批要点是 AI 总结的，读者必须一眼看见
  '& .md-sec-badge': {
    ml: 0.75,
    px: 0.75,
    py: 0.125,
    borderRadius: 0.75,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.4,
    lineHeight: 1.6,
    color: 'warning.darker',
    bgcolor: (theme) => theme.palette.warning.light,
    border: (theme) => `1px solid ${theme.palette.warning.light}`,
  },
  '& section.md-abstract .md-sec-label': { color: 'text.secondary' },
  '& ul.md-highlights': { listStyle: 'none', pl: 0, my: 0 },
  '& ul.md-highlights li': {
    position: 'relative',
    pl: 3,
    my: 1,
    '&::before': {
      content: '"✦"',
      position: 'absolute',
      left: 4,
      color: 'primary.main',
      fontWeight: 700,
    },
  },
  '& .md-keywords': {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 1,
    mt: 2,
    pt: 1.75,
    borderTop: (theme) => `1px solid ${theme.palette.divider}`,
  },
  '& .md-keywords-label': {
    typography: 'subtitle2',
    fontWeight: 700,
    color: 'text.primary',
    mr: 0.25,
    flexShrink: 0,
  },
  '& .kw-chip': {
    px: 1.5,
    py: 0.75,
    borderRadius: 1,
    fontSize: 15,
    fontWeight: 700,
    lineHeight: 1.35,
    color: 'text.primary',
    bgcolor: 'background.paper',
    border: (theme) => `1px solid ${varAlpha(theme.palette.grey[500], 0.28)}`,
    boxShadow: (theme) => theme.shadows[1],
  },
  '& mark.ws-vocab': {
    px: 0.2,
    borderRadius: 0.5,
    color: 'inherit',
    cursor: 'pointer',
    bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.4),
  },
  '& mark.ws-vocab.ws-vocab-book': {
    px: 0,
    borderRadius: 0,
    bgcolor: 'transparent',
    color: 'info.dark',
    fontWeight: 600,
    boxShadow: (theme) => `inset 0 -2px 0 ${theme.palette.info.main}`,
  },
  '& mark.ws-hl': {
    px: 0.1,
    borderRadius: 0.5,
    cursor: 'pointer',
    color: 'inherit',
    bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.32),
    transition: (theme) => theme.transitions.create(['background-color']),
    '&:hover': {
      bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.48),
    },
  },
  '& .term-link': {
    px: 0.6,
    py: 0.1,
    mx: 0.1,
    borderRadius: 0.75,
    cursor: 'pointer',
    fontWeight: 500,
    textDecoration: 'none',
    color: 'info.dark',
    bgcolor: (theme) => varAlpha(theme.palette.info.main, 0.12),
    transition: (theme) => theme.transitions.create(['background-color']),
    '&:hover': {
      bgcolor: (theme) => varAlpha(theme.palette.info.main, 0.24),
    },
  },
  // 术语标注关闭时：术语退成普通文字（开关只切类名，不重渲 markdown）
  '&.no-term-links .term-link': {
    px: 0,
    py: 0,
    mx: 0,
    borderRadius: 0,
    cursor: 'text',
    fontWeight: 'inherit',
    color: 'inherit',
    bgcolor: 'transparent',
    '&:hover': { bgcolor: 'transparent' },
  },
  '&.share-mode .term-link': {
    cursor: 'help',
  },
  '& .paper-link': {
    color: 'primary.main',
    fontWeight: 600,
    cursor: 'pointer',
    textDecoration: 'none',
    '&:hover': { textDecoration: 'underline' },
  },
  '& .paper-link-chip': {
    px: 0.75,
    py: 0.2,
    borderRadius: 0.75,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 0.5,
    bgcolor: (theme) => varAlpha(theme.palette.primary.main, 0.08),
    '&:hover': {
      textDecoration: 'none',
      bgcolor: (theme) => varAlpha(theme.palette.primary.main, 0.18),
    },
  },
  '& .paper-link-tag': {
    px: 0.5,
    borderRadius: 0.5,
    fontSize: '0.72em',
    fontWeight: 700,
    lineHeight: 1.6,
    color: 'primary.dark',
    bgcolor: (theme) => varAlpha(theme.palette.primary.main, 0.16),
  },
  '& .nav-link': {
    color: 'primary.main',
    fontWeight: 600,
    cursor: 'pointer',
    textDecoration: 'none',
    '&:hover': { textDecoration: 'underline' },
  },
  '& .formula-note': {
    my: 2.5,
    px: 2.25,
    py: 2,
    bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.08),
    border: (theme) => `1px solid ${varAlpha(theme.palette.warning.main, 0.22)}`,
    borderRadius: 1.5,
    color: 'text.primary',
  },
  '& .formula-note-title': {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 0.6,
    mb: 1,
    px: 0.9,
    py: 0.2,
    borderRadius: 0.75,
    typography: 'caption',
    fontWeight: 700,
    letterSpacing: '0.06em',
    color: 'warning.darker',
    bgcolor: (theme) => varAlpha(theme.palette.warning.main, 0.16),
  },
  '& .formula-note-title svg': { width: 13, height: 13 },
  '& .formula-note p': {
    my: 0.75,
    typography: 'body2',
    color: 'text.secondary',
    lineHeight: 1.85,
  },
  '& code.ws-tex': {
    px: 0.75,
    py: 0.15,
    borderRadius: 0.5,
    bgcolor: (theme) => varAlpha(theme.palette.primary.main, 0.1),
    color: 'primary.dark',
    fontFamily: 'Consolas, Menlo, monospace',
    fontSize: '0.9em',
    whiteSpace: 'break-spaces',
  },
  '& code.ws-tex-display': {
    display: 'block',
    my: 1.5,
    px: 1.5,
    py: 1.25,
    lineHeight: 1.7,
  },
  '& img': {
    display: 'block',
    maxWidth: 1,
    height: 'auto',
    my: 2,
    borderRadius: 1,
    cursor: 'zoom-in',
  },
  '& img.img-flash': {
    outline: (theme) => `3px solid ${theme.palette.warning.main}`,
    outlineOffset: '3px',
  },
  '& figure.md-fig': { m: 0, my: 2.5 },
  '& figure.md-fig img': { mx: 'auto', my: 0 },
  '& figure.md-fig figcaption': {
    display: 'block',
    mt: 1,
    px: 2,
    typography: 'caption',
    color: 'text.secondary',
    lineHeight: 1.7,
    textAlign: 'center',
  },
  '& a': { color: 'primary.main' },
  '& a.paper-cite': {
    color: 'primary.main',
    textDecoration: 'none',
    fontWeight: 500,
    borderBottom: '1px dashed currentColor',
    px: 0.05,
  },
  '& .paper-ref': {
    scrollMarginTop: 96,
    borderRadius: 0.75,
    transition: (theme) => theme.transitions.create(['background-color']),
    '&:hover': { bgcolor: 'action.hover', cursor: 'pointer' },
    '& a': { overflowWrap: 'anywhere', wordBreak: 'break-word' },
  },
  '& code': {
    px: 0.75,
    py: 0.15,
    borderRadius: 0.5,
    bgcolor: 'action.hover',
    fontFamily: 'Consolas, Menlo, monospace',
    fontSize: '0.88em',
  },
  '& pre': {
    p: 2,
    overflow: 'auto',
    borderRadius: 1,
    bgcolor: 'action.hover',
    border: (theme) => `1px solid ${theme.palette.divider}`,
  },
  '& pre code': { p: 0, bgcolor: 'transparent' },
  '& .tbl-wrap': {
    overflowX: 'auto',
    my: 2,
    border: (theme) => `1px solid ${theme.palette.divider}`,
    borderRadius: 1,
  },
  '& table': { width: 1, borderCollapse: 'collapse', fontSize: '0.92em' },
  '& th, & td': {
    px: 1.5,
    py: 1,
    borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
    verticalAlign: 'top',
  },
  '& th': { bgcolor: 'action.hover', textAlign: 'left', whiteSpace: 'nowrap' },
  '& tbody tr:nth-of-type(even)': {
    bgcolor: (theme) => varAlpha(theme.palette.grey[500], 0.04),
  },
  '& .katex-display': { overflowX: 'auto', overflowY: 'hidden', py: 0.5 },
};

export const MarkdownNote = memo(function MarkdownNote({
  source,
  empty,
  pid,
  imagesDir,
  copyMode,
  onHeadings,
  highlightable,
  tabKey = 'article',
  highlights,
  onHighlightsChange,
  onClip,
  vocab,
  vocabMode,
  onVocabChange,
  locateWord,
  onLocated,
  searchQuery = '',
  shareMode = false,
}: Props) {
  const router = useRouter();
  const shareModeRef = useRef(shareMode);
  shareModeRef.current = shareMode;
  const rootRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState('');
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [cite, setCite] = useState<{ id: string; text: string; anchor: HTMLElement } | null>(null);
  const [termCard, setTermCard] = useState<{ entry: TermEntry; anchor: HTMLElement } | null>(null);
  const citeCardRef = useRef<HTMLDivElement>(null);
  const citeCloseTimer = useRef(0);
  const termCloseTimer = useRef(0);

  const cancelCiteClose = useCallback(() => {
    window.clearTimeout(citeCloseTimer.current);
  }, []);

  const scheduleCiteClose = useCallback(() => {
    window.clearTimeout(citeCloseTimer.current);
    citeCloseTimer.current = window.setTimeout(() => setCite(null), 240);
  }, []);

  const cancelTermClose = useCallback(() => {
    window.clearTimeout(termCloseTimer.current);
  }, []);

  const scheduleTermClose = useCallback(() => {
    window.clearTimeout(termCloseTimer.current);
    termCloseTimer.current = window.setTimeout(() => setTermCard(null), 240);
  }, []);

  const jumpToCite = useCallback((id: string) => {
    rootRef.current?.querySelector(`#ref-${id}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  }, []);
  const [slides, setSlides] = useState<{ src: string; title?: string }[]>([]);
  const [lightboxIndex, setLightboxIndex] = useState(-1);
  const [selInfo, setSelInfo] = useState<SelectionInfo | null>(null);
  const [removeHl, setRemoveHl] = useState<{ id: string; anchor: HTMLElement } | null>(null);
  const [failedCount, setFailedCount] = useState(0);
  const [gloss, setGloss] = useState<VocabGloss | null>(null);
  const [hoverTips, setHoverTips] = useState(loadHoverTips);
  const glossTimer = useRef(0);
  const glossPinned = useRef(false);
  // 事件处理器里经 ref 读取，开关悬浮提示不必重建 innerHTML / 重排公式
  const hoverTipsRef = useRef(hoverTips);
  hoverTipsRef.current = hoverTips;
  // 正文术语标注开关：关掉后术语显示为普通文字（纯 CSS 切换，不重渲 markdown）
  const [termLinks, setTermLinksState] = useState(loadTermLinks);
  const termLinksRef = useRef(termLinks);
  termLinksRef.current = termLinks;

  useEffect(() => subscribeHoverTips(setHoverTips), []);
  useEffect(() => subscribeTermLinks(setTermLinksState), []);

  useEffect(() => {
    if (!termLinks) setTermCard(null);
  }, [termLinks]);

  const openGloss = useCallback((mark: HTMLElement, pinned: boolean) => {
    const word = (mark.textContent || '').trim();
    const entry = lookupVocab(word);
    glossPinned.current = pinned;
    setGloss({
      word,
      pos: mark.dataset.pos || entry?.pos || '',
      en: mark.dataset.en || entry?.en || '',
      zh: mark.dataset.zh || entry?.zh || '',
      anchor: mark,
      pinned,
    });
  }, []);

  const prepared = useMemo(() => preprocessVaultMarkdown(source, imagesDir), [imagesDir, source]);

  useEffect(() => {
    let cancelled = false;
    if (!prepared.text) {
      setHtml('');
      setReady(true);
      onHeadings?.([]);
      return undefined;
    }

    setReady(false);
    setError('');
    ensureMarkdownVendors()
      .then(() => {
        if (cancelled) return;
        const result = renderMarkdown(prepared.text, prepared.cites);
        setHtml(result.html);
        onHeadings?.(result.headings);
        setReady(true);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [onHeadings, prepared]);

  useEffect(() => {
    if (!ready || !html || !rootRef.current) {
      return undefined;
    }
    const root = rootRef.current;
    root.innerHTML = html;
    typesetMath(root);
    if (copyMode) revealLatexSource(root);

    // 图片懒加载：滚到附近才下载，一篇十几张 400KB 级的图不再在打开正文时全量拉取
    root.querySelectorAll<HTMLImageElement>('img').forEach((img) => {
      img.loading = 'lazy';
      img.decoding = 'async';
      // web 生产环境正文用 webp 压缩档，原图 URL 存起来给大图查看/下载
      const original = img.getAttribute('src') || '';
      if (USE_WEB_IMAGES && hasWebVariant(original)) {
        img.dataset.fullSrc = original;
        img.src = webImageUrl(original);
        img.onerror = () => {
          img.onerror = null;
          img.src = original;
        };
      }
    });

    setSlides(
      [...root.querySelectorAll<HTMLImageElement>('img')].map((img) => ({
        src: img.dataset.fullSrc || img.src,
        title: img.alt,
      }))
    );

    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const httpLink = target.closest<HTMLAnchorElement>('a[href]');
      if (httpLink && isHttpUrl(httpLink.getAttribute('href') || '')) {
        event.preventDefault();
        event.stopPropagation();
        void openExternal(httpLink.getAttribute('href') || '');
        return;
      }
      if (target.tagName === 'IMG') {
        event.preventDefault();
        const index = [...root.querySelectorAll('img')].indexOf(target as HTMLImageElement);
        if (index >= 0) setLightboxIndex(index);
        return;
      }
      const hlMark = target.closest<HTMLElement>('mark.ws-hl');
      if (hlMark?.dataset.hlId) {
        setRemoveHl({ id: hlMark.dataset.hlId, anchor: hlMark });
        return;
      }
      const termLink = target.closest<HTMLAnchorElement>('a.term-link');
      if (termLink?.dataset.term) {
        if (!termLinksRef.current) return;
        event.preventDefault();
        // 分享页 / 触屏：只出释义，不进术语库（分享访客未登录）
        if (shareModeRef.current || window.matchMedia('(pointer: coarse)').matches) {
          const entry = getTerm(termLink.dataset.term);
          if (entry) {
            cancelTermClose();
            setTermCard({ entry, anchor: termLink });
          }
          return;
        }
        router.push(`${paths.dashboard.terms}?term=${termLink.dataset.term}`);
        return;
      }
      const navLink = target.closest<HTMLAnchorElement>('a[data-nav]');
      if (navLink?.dataset.nav) {
        event.preventDefault();
        if (shareModeRef.current) return;
        router.push(navLink.dataset.nav);
        return;
      }
      const citeLink = target.closest<HTMLAnchorElement>('a[data-ref]');
      if (citeLink?.dataset.ref) {
        event.preventDefault();
        jumpToCite(citeLink.dataset.ref);
        return;
      }
      const refItem = target.closest<HTMLLIElement>('li.paper-ref');
      if (refItem?.id) {
        const n = refItem.id.replace('ref-', '');
        root
          .querySelector(`a.paper-cite[data-ref="${n}"]`)
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    };

    const onOver = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const termLink = target.closest<HTMLAnchorElement>('a.term-link');
      if (termLink?.dataset.term && termLinksRef.current && (hoverTipsRef.current || shareModeRef.current)) {
        const entry = getTerm(termLink.dataset.term);
        if (entry) {
          cancelTermClose();
          setTermCard({ entry, anchor: termLink });
        }
        return;
      }
      if (!hoverTipsRef.current) return;
      const citeLink = target.closest<HTMLAnchorElement>('a[data-ref]');
      if (citeLink?.dataset.ref) {
        cancelCiteClose();
        setCite({
          id: citeLink.dataset.ref,
          text: citationText(root, citeLink.dataset.ref) || `文献 ${citeLink.dataset.ref}`,
          anchor: citeLink,
        });
      }
    };

    const onOut = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const next = event.relatedTarget as Node | null;
      const citeLink = target.closest('a[data-ref]');
      if (citeLink && (!next || !citeLink.contains(next))) {
        if (next && citeCardRef.current?.contains(next)) return;
        scheduleCiteClose();
        return;
      }
      const termLink = target.closest('a.term-link');
      if (termLink && (!next || !termLink.contains(next))) {
        scheduleTermClose();
      }
    };

    const onDragStart = (event: DragEvent) => {
      const target = event.target as HTMLElement;
      if (target.tagName === 'IMG' && event.dataTransfer) {
        const img = target as HTMLImageElement;
        const caption = img.closest('figure')?.querySelector('figcaption')?.textContent || img.alt;
        event.dataTransfer.setData('text/html', `<img src="${img.src}" alt="${caption}">`);
      }
    };

    root.addEventListener('click', onClick);
    root.addEventListener('mouseover', onOver);
    root.addEventListener('mouseout', onOut);
    root.addEventListener('dragstart', onDragStart);
    return () => {
      root.removeEventListener('click', onClick);
      root.removeEventListener('mouseover', onOver);
      root.removeEventListener('mouseout', onOut);
      root.removeEventListener('dragstart', onDragStart);
    };
  }, [cancelCiteClose, cancelTermClose, copyMode, html, jumpToCite, ready, router, scheduleCiteClose, scheduleTermClose]);

  useEffect(() => {
    if (hoverTips) return;
    setCite(null);
    setTermCard(null);
    if (!glossPinned.current) setGloss(null);
  }, [hoverTips]);

  useEffect(() => {
    if (!termCard) return undefined;
    const onDoc = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (termCard.anchor.contains(target)) return;
      const popper = document.querySelector('.ws-term-popper');
      if (popper?.contains(target)) return;
      setTermCard(null);
    };
    document.addEventListener('pointerdown', onDoc);
    return () => document.removeEventListener('pointerdown', onDoc);
  }, [termCard]);

  useEffect(() => {
    if (!cite) return undefined;
    const onDocDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (cite.anchor.contains(target) || citeCardRef.current?.contains(target)) return;
      setCite(null);
    };
    const onScroll = (event: Event) => {
      if (citeCardRef.current?.contains(event.target as Node)) return;
      setCite(null);
    };
    document.addEventListener('mousedown', onDocDown);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mousedown', onDocDown);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [cite]);

  useEffect(
    () => () => {
      window.clearTimeout(citeCloseTimer.current);
      window.clearTimeout(glossTimer.current);
    },
    []
  );

  // 高亮重放（在公式排版之后）
  useEffect(() => {
    if (!ready || !html || !rootRef.current) return;
    setFailedCount(applyHighlights(rootRef.current, highlights ?? [], tabKey));
  }, [copyMode, highlights, html, ready, tabKey]);

  useEffect(() => {
    if (!ready || !html || !rootRef.current) return;
    applySearchMarks(rootRef.current, searchQuery);
  }, [copyMode, html, ready, searchQuery]);

  // 生词标记重放（英文正文 tab）；书更新只改 dataset
  useEffect(() => {
    if (!ready || !html || !rootRef.current || !onVocabChange) return;
    applyVocab(rootRef.current, vocab ?? []);
    applyVocabGloss(rootRef.current);
  }, [copyMode, html, onVocabChange, ready, vocab]);

  useEffect(() => {
    if (!ready || !html || !rootRef.current || !onVocabChange) return undefined;
    return subscribeVocabBook(() => {
      if (rootRef.current) applyVocabGloss(rootRef.current);
    });
  }, [html, onVocabChange, ready]);

  // 生词标注模式：双击单词标注/追加原句；单击黄标删除（延迟，避免挡住双击）
  useEffect(() => {
    if (!vocabMode || !ready || !html || !rootRef.current || !onVocabChange) return undefined;
    const root = rootRef.current;
    const list = vocab ?? [];
    let clickTimer = 0;

    const onDblClick = (event: MouseEvent) => {
      window.clearTimeout(clickTimer);
      const mark = (event.target as HTMLElement).closest('mark.ws-vocab');
      const selection = window.getSelection();
      const word = (selection?.toString().trim() || mark?.textContent || '').trim();
      if (!/^[A-Za-z][A-Za-z'’-]{1,40}$/.test(word)) return;
      const lower = word.toLowerCase();
      const paragraph =
        (event.target as HTMLElement).closest(CONTEXT_SELECTOR)?.textContent ?? '';
      const context = sentenceForWord(paragraph, word).slice(0, 300);
      const same = list.find(
        (entry) => entry.word.toLowerCase() === lower && sameVocabSentence(entry.context, context)
      );
      if (same) {
        onVocabChange(list.filter((entry) => entry !== same));
      } else {
        onVocabChange([...list, { word, context, createdAt: new Date().toISOString() }]);
      }
      selection?.removeAllRanges();
      setSelInfo(null);
    };

    const onMarkClick = (event: MouseEvent) => {
      const mark = (event.target as HTMLElement).closest('mark.ws-vocab');
      if (!mark) return;
      window.clearTimeout(clickTimer);
      clickTimer = window.setTimeout(() => {
        const word = (mark.textContent || '').trim();
        const lower = word.toLowerCase();
        const paragraph = mark.closest(CONTEXT_SELECTOR)?.textContent ?? '';
        const sentence = sentenceForWord(paragraph, word);
        const same = list.find(
          (entry) => entry.word.toLowerCase() === lower && sameVocabSentence(entry.context, sentence)
        );
        onVocabChange(
          same
            ? list.filter((entry) => entry !== same)
            : list.filter((entry) => entry.word.toLowerCase() !== lower)
        );
      }, 280);
    };

    root.addEventListener('dblclick', onDblClick);
    root.addEventListener('click', onMarkClick);
    return () => {
      window.clearTimeout(clickTimer);
      root.removeEventListener('dblclick', onDblClick);
      root.removeEventListener('click', onMarkClick);
    };
  }, [html, onVocabChange, ready, vocab, vocabMode]);

  useEffect(() => {
    if (!ready || !html || !rootRef.current || !onVocabChange) return undefined;
    const root = rootRef.current;

    const onOver = (event: MouseEvent) => {
      if (!hoverTipsRef.current) return;
      const mark = (event.target as HTMLElement).closest<HTMLElement>('mark.ws-vocab');
      if (!mark || glossPinned.current) return;
      window.clearTimeout(glossTimer.current);
      glossTimer.current = window.setTimeout(() => openGloss(mark, false), 200);
    };

    const onOut = (event: MouseEvent) => {
      const mark = (event.target as HTMLElement).closest('mark.ws-vocab');
      if (!mark || glossPinned.current) return;
      window.clearTimeout(glossTimer.current);
      glossTimer.current = window.setTimeout(() => {
        if (!glossPinned.current) setGloss(null);
      }, 180);
    };

    const onClick = (event: MouseEvent) => {
      if (vocabMode) return;
      const mark = (event.target as HTMLElement).closest<HTMLElement>('mark.ws-vocab');
      if (!mark) return;
      event.preventDefault();
      openGloss(mark, true);
    };

    root.addEventListener('mouseover', onOver);
    root.addEventListener('mouseout', onOut);
    root.addEventListener('click', onClick);
    return () => {
      root.removeEventListener('mouseover', onOver);
      root.removeEventListener('mouseout', onOut);
      root.removeEventListener('click', onClick);
      window.clearTimeout(glossTimer.current);
    };
  }, [html, onVocabChange, openGloss, ready, vocabMode]);

  useEffect(() => {
    if (!gloss?.pinned) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      glossPinned.current = false;
      setGloss(null);
    };
    const onDoc = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('mark.ws-vocab') || target.closest('.ws-vocab-gloss')) return;
      glossPinned.current = false;
      setGloss(null);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDoc);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDoc);
    };
  }, [gloss?.pinned]);

  useEffect(() => {
    if (!locateWord || !ready || !html || !rootRef.current) return;
    const needle = locateWord.toLowerCase();
    const mark = [...rootRef.current.querySelectorAll<HTMLElement>('mark.ws-vocab')].find(
      (el) => (el.textContent || '').trim().toLowerCase() === needle
    );
    if (!mark) return;
    mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    openGloss(mark, true);
    onLocated?.();
  }, [html, locateWord, onLocated, openGloss, ready, vocab]);

  // 复制模式：划选复制时输出干净的 markdown（公式 LaTeX、[N] 引用、[[pid]] 出处）
  useEffect(() => {
    if (!copyMode) return undefined;
    const onCopy = (event: ClipboardEvent) => {
      const text = selectionToCopyText();
      if (!text) return;
      event.preventDefault();
      event.clipboardData?.setData('text/plain', text);
      void navigator.clipboard?.writeText(text);
    };
    document.addEventListener('copy', onCopy);
    return () => document.removeEventListener('copy', onCopy);
  }, [copyMode]);

  // 阅读高亮：选中文字弹浮动工具条
  useEffect(() => {
    if (!highlightable || copyMode || !ready || !rootRef.current) return undefined;
    const root = rootRef.current;

    const captureSelection = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        setSelInfo(null);
        return;
      }
      const range = selection.getRangeAt(0);
      if (!root.contains(range.commonAncestorContainer)) {
        setSelInfo(null);
        return;
      }
      const blocks = getBlocks(root);
      const startBlock = blocks.findIndex((block) => block.contains(range.startContainer));
      const endBlock = blocks.findIndex((block) => block.contains(range.endContainer));
      if (startBlock < 0 || startBlock !== endBlock) {
        setSelInfo(null);
        return;
      }
      const block = blocks[startBlock];
      const start = offsetWithin(block, range.startContainer, range.startOffset);
      const end = offsetWithin(block, range.endContainer, range.endOffset);
      if (start < 0 || end <= start) {
        setSelInfo(null);
        return;
      }
      const text = (block.textContent ?? '').slice(start, end);
      if (!text.trim()) {
        setSelInfo(null);
        return;
      }
      setSelInfo({ block: startBlock, start, end, text, rect: range.getBoundingClientRect() });
    };

    const onMouseUp = () => {
      window.setTimeout(captureSelection, 10);
    };
    const onTouchEnd = () => {
      window.setTimeout(captureSelection, 360);
    };

    root.addEventListener('mouseup', onMouseUp);
    root.addEventListener('touchend', onTouchEnd, { passive: true });
    return () => {
      root.removeEventListener('mouseup', onMouseUp);
      root.removeEventListener('touchend', onTouchEnd);
    };
  }, [copyMode, highlightable, html, ready]);

  const handleAddHighlight = useCallback(() => {
    if (!selInfo || !onHighlightsChange) return;
    onHighlightsChange([
      ...(highlights ?? []),
      {
        id: makeId(),
        tab: tabKey,
        block: selInfo.block,
        start: selInfo.start,
        end: selInfo.end,
        text: selInfo.text,
        createdAt: new Date().toISOString(),
      },
    ]);
    window.getSelection()?.removeAllRanges();
    setSelInfo(null);
  }, [highlights, onHighlightsChange, selInfo, tabKey]);

  const handleClip = useCallback(() => {
    if (!selInfo || !onClip) return;
    onClip(selectionToCopyText() || selInfo.text);
    window.getSelection()?.removeAllRanges();
    setSelInfo(null);
  }, [onClip, selInfo]);

  const selAnchor = useMemo(() => {
    if (!selInfo) return null;
    const { rect } = selInfo;
    return {
      getBoundingClientRect: () => rect,
    } as HTMLElement;
  }, [selInfo]);

  if (!source.trim()) {
    return (
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {empty}
      </Typography>
    );
  }

  if (!ready) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="warning">{error}</Alert>;
  }

  return (
    <>
      {failedCount > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          有 {failedCount} 条高亮因原文更新对不上位置（数据仍保存，不会丢）。
        </Alert>
      )}

      <Box
        ref={rootRef}
        className={['paper-md', termLinks ? '' : 'no-term-links', shareMode ? 'share-mode' : '']
          .filter(Boolean)
          .join(' ')}
        sx={MARKDOWN_SX}
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <Popper
        open={Boolean(cite)}
        anchorEl={cite?.anchor}
        placement="top-start"
        modifiers={[
          { name: 'offset', options: { offset: [0, 10] } },
          {
            name: 'flip',
            enabled: true,
            options: { fallbackPlacements: ['bottom-start', 'top-end', 'bottom-end', 'right', 'left'] },
          },
          {
            name: 'preventOverflow',
            enabled: true,
            options: { padding: 12, altAxis: true, tether: false },
          },
        ]}
        sx={{ zIndex: 1400 }}
      >
        <Paper
          ref={citeCardRef}
          onMouseEnter={cancelCiteClose}
          onMouseLeave={scheduleCiteClose}
          onClick={() => {
            if (cite) jumpToCite(cite.id);
          }}
          sx={{
            p: 1.5,
            width: 'max-content',
            maxWidth: 'min(560px, calc(100vw - 24px))',
            maxHeight: 'min(40vh, 360px)',
            overflow: 'auto',
            boxShadow: 8,
            cursor: 'pointer',
          }}
        >
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            文献 {cite?.id}
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
            {cite?.text}
          </Typography>
          <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'primary.main' }}>
            点击跳到文末
          </Typography>
        </Paper>
      </Popper>

      <Popper
        open={Boolean(termCard)}
        anchorEl={termCard?.anchor}
        placement="top-start"
        modifiers={[
          { name: 'offset', options: { offset: [0, 8] } },
          { name: 'flip', enabled: true, options: { fallbackPlacements: ['bottom-start'] } },
          { name: 'preventOverflow', enabled: true, options: { padding: 12, altAxis: true } },
        ]}
        className="ws-term-popper"
        sx={{ zIndex: 1400 }}
      >
        {termCard ? (
          <Box onMouseEnter={cancelTermClose} onMouseLeave={scheduleTermClose}>
            <TermPopoverCard entry={termCard.entry} pid={pid} showLibraryLink={!shareMode} />
          </Box>
        ) : (
          <span />
        )}
      </Popper>

      <Popper
        open={Boolean(gloss)}
        anchorEl={gloss?.anchor}
        placement="top-start"
        modifiers={[{ name: 'offset', options: { offset: [0, 8] } }]}
        sx={{ zIndex: 1300 }}
      >
        {gloss ? (
          <Paper className="ws-vocab-gloss" sx={{ p: 1.5, maxWidth: 320, boxShadow: 8 }}>
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 0.5 }}>
              <Typography variant="subtitle2">{gloss.word}</Typography>
              {gloss.pos ? (
                <Typography variant="caption" sx={{ color: 'text.disabled' }}>
                  {gloss.pos}
                </Typography>
              ) : null}
            </Box>
            {gloss.en ? (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                {gloss.en}
              </Typography>
            ) : null}
            {gloss.zh ? (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {gloss.zh}
              </Typography>
            ) : null}
            {!gloss.en && !gloss.zh ? (
              <Typography variant="caption" sx={{ color: 'text.disabled' }}>
                收入生词本后可补
              </Typography>
            ) : null}
          </Paper>
        ) : (
          <span />
        )}
      </Popper>

      <Popper
        open={Boolean(selInfo)}
        anchorEl={selAnchor}
        placement="top"
        modifiers={[
          { name: 'offset', options: { offset: [0, 8] } },
          { name: 'flip', enabled: true, options: { fallbackPlacements: ['bottom'] } },
          { name: 'preventOverflow', enabled: true, options: { padding: 12, altAxis: true } },
        ]}
        sx={{ zIndex: 1200 }}
      >
        <Paper sx={{ p: 0.5, boxShadow: 8, display: 'flex', gap: 0.5 }}>
          <Button
            size="small"
            color="warning"
            startIcon={<Iconify width={16} icon="solar:pen-bold" />}
            onClick={handleAddHighlight}
          >
            高亮
          </Button>
          {onClip ? (
            <Button
              size="small"
              color="inherit"
              startIcon={<Iconify width={16} icon="solar:clipboard-text-bold" />}
              onClick={handleClip}
            >
              摘到笔记
            </Button>
          ) : null}
        </Paper>
      </Popper>

      <Popper
        open={Boolean(removeHl)}
        anchorEl={removeHl?.anchor}
        placement="top"
        modifiers={[{ name: 'offset', options: { offset: [0, 6] } }]}
        sx={{ zIndex: 1200 }}
      >
        <Paper sx={{ p: 0.5, boxShadow: 8, display: 'flex', gap: 0.5 }}>
          <Button
            size="small"
            color="error"
            startIcon={<Iconify width={16} icon="solar:trash-bin-trash-bold" />}
            onClick={() => {
              if (removeHl && onHighlightsChange) {
                onHighlightsChange((highlights ?? []).filter((item) => item.id !== removeHl.id));
              }
              setRemoveHl(null);
            }}
          >
            删除高亮
          </Button>
          <Button size="small" color="inherit" onClick={() => setRemoveHl(null)}>
            取消
          </Button>
        </Paper>
      </Popper>

      <Lightbox
        open={lightboxIndex >= 0}
        close={() => setLightboxIndex(-1)}
        index={lightboxIndex}
        slides={slides}
        disableVideo
        disableThumbnails
        enableDownload
      />
    </>
  );
});

// ----------------------------------------------------------------------

type TermPopoverCardProps = {
  entry: TermEntry;
  pid?: string;
  showLibraryLink?: boolean;
};

function TermPopoverCard({ entry, pid, showLibraryLink = true }: TermPopoverCardProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  const usage = pid ? entry.usages.find((item) => item.paper === pid) : undefined;

  const definitionHtml = useMemo(() => {
    try {
      return renderMarkdown(entry.definition).html;
    } catch {
      return DOMPurify.sanitize(`<p>${entry.definition}</p>`);
    }
  }, [entry.definition]);

  const usageHtml = useMemo(() => {
    if (!usage) return '';
    try {
      return renderMarkdown(usage.context).html;
    } catch {
      return DOMPurify.sanitize(`<p>${usage.context}</p>`);
    }
  }, [usage]);

  useEffect(() => {
    if (contentRef.current) typesetMath(contentRef.current);
  }, [definitionHtml, usageHtml]);

  return (
    <Paper ref={contentRef} sx={{ p: 2, maxWidth: 440, boxShadow: 8 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
        <Typography variant="subtitle2">
          {entry.term}
          {entry.zhName ? `（${entry.zhName}）` : ''}
        </Typography>
      </Box>

      <Box
        dangerouslySetInnerHTML={{ __html: definitionHtml }}
        sx={{
          '& p': { typography: 'caption', color: 'text.secondary', lineHeight: 1.7, my: 0.25 },
        }}
      />

      {usage ? (
        <Box sx={{ mt: 1, pt: 1, borderTop: (theme) => `1px dashed ${theme.palette.divider}` }}>
          <Typography variant="caption" sx={{ color: 'info.dark', fontWeight: 600 }}>
            本文语境
          </Typography>
          <Box
            dangerouslySetInnerHTML={{ __html: usageHtml }}
            sx={{
              '& p': { typography: 'caption', color: 'text.secondary', lineHeight: 1.7, my: 0.25 },
            }}
          />
        </Box>
      ) : null}

      {showLibraryLink ? (
        <Typography
          component={RouterLink}
          href={`${paths.dashboard.terms}?term=${entry.key}`}
          variant="caption"
          sx={{ display: 'block', mt: 1, color: 'primary.main' }}
        >
          打开术语库
        </Typography>
      ) : null}
    </Paper>
  );
}

// 供图片定位使用：给正文里的目标图片加短暂高亮框
export function flashArticleImage(name: string, timeoutMs = 4000) {
  const deadline = Date.now() + timeoutMs;
  const timer = window.setInterval(() => {
    const img = [...document.querySelectorAll<HTMLImageElement>('.paper-md img')].find((el) => {
      try {
        return decodeURIComponent(el.src).includes(name);
      } catch {
        return el.src.includes(name);
      }
    });
    if (img) {
      window.clearInterval(timer);
      img.scrollIntoView({ behavior: 'smooth', block: 'center' });
      img.classList.add('img-flash');
      window.setTimeout(() => img.classList.remove('img-flash'), 2400);
    } else if (Date.now() > deadline) {
      window.clearInterval(timer);
    }
  }, 150);
}
