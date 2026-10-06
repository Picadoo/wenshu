#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOI 驱动的元数据增强：从 PDF 抽 DOI -> 查 Crossref + OpenAlex -> 合并。

- Crossref 提供权威书目：标题/作者/期刊/卷期页/出版商/年份/摘要
- OpenAlex 提供被引数/开放获取链接/概念(concepts)/OpenAlex ID
- 全部免费、无需 API key（带 mailto 进 Crossref 礼貌池）

输出：合并后的元数据 JSON 到 stdout（仅 JSON，便于上层解析）；日志走 stderr。
失败优雅降级：拿不到 DOI 或查库失败时，metadataSources 标 ["pdf"]，
其余字段尽量从 PDF 首页猜测，标题/作者留给上层(读全文的子代理)补全。

用法：
    python doi_enrich.py --pdf "<path>"
    python doi_enrich.py --pdf "<path>" --doi 10.3390/s25154797 --out meta.json
    python doi_enrich.py --doi 10.3390/s25154797
"""

import os
import re
import sys
import json
import argparse
import logging

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

MAILTO = "amenthe432@gmail.com"   # Crossref 礼貌池，礼貌起见带上联系邮箱
UA = f"pdf-to-wenshu/1.0 (mailto:{MAILTO})"

DOI_RE = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', re.I)


def extract_pdf_head_text(pdf_path, pages=3, max_chars=8000):
    """抽取 PDF 前几页文本，用于找 DOI + 语种检测。"""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF(fitz) 不可用，无法从 PDF 抽文本")
        return ""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.warning("打开 PDF 失败 %s: %s", pdf_path, e)
        return ""
    parts = []
    try:
        for i in range(min(pages, len(doc))):
            parts.append(doc[i].get_text())
    finally:
        doc.close()
    return ("\n".join(parts))[:max_chars]


def find_doi(text):
    """从文本里找第一个看起来合理的 DOI（去掉尾部标点）。"""
    for m in DOI_RE.finditer(text or ""):
        doi = m.group(0)
        doi = doi.rstrip('.,;)】>」"\'')
        # 去掉常见误粘的尾巴
        doi = re.sub(r'(\.pdf|\.xml|\.full)$', '', doi, flags=re.I)
        if len(doi) > 7:
            return doi
    return None


def detect_language(text):
    """简单语种检测：CJK 字符占比高 -> zh，否则 en。"""
    if not text:
        return "en"
    cjk = len(re.findall(r'[一-鿿]', text))
    latin = len(re.findall(r'[A-Za-z]', text))
    if cjk == 0 and latin == 0:
        return "en"
    return "zh" if cjk > latin * 0.3 else "en"


def _get_json(url, timeout=30):
    if not HAS_REQUESTS:
        logger.warning("requests 不可用，跳过联网: %s", url)
        return None
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"},
                        timeout=timeout)
        if r.status_code == 200:
            return r.json()
        logger.warning("HTTP %d: %s", r.status_code, url)
    except Exception as e:
        logger.warning("请求失败 %s: %s", url, e)
    return None


def _strip_jats(s):
    """去掉 Crossref 摘要里的 JATS 标签。"""
    if not s:
        return ""
    s = re.sub(r'<[^>]+>', ' ', s)
    return ' '.join(s.split())


def query_crossref(doi):
    data = _get_json(f"https://api.crossref.org/works/{doi}?mailto={MAILTO}")
    if not data or 'message' not in data:
        return None
    m = data['message']
    authors = []
    for a in m.get('author', []) or []:
        name = " ".join(x for x in [a.get('given'), a.get('family')] if x).strip()
        if name:
            authors.append(name)
    year = None
    for key in ('published-print', 'published-online', 'published', 'issued', 'created'):
        dp = (m.get(key) or {}).get('date-parts')
        if dp and dp[0] and dp[0][0]:
            year = dp[0][0]
            break
    title = (m.get('title') or [''])[0]
    journal = (m.get('container-title') or [''])[0]
    return {
        'title': title,
        'authors': authors,
        'year': year,
        'journal': journal,
        'publisher': m.get('publisher', ''),
        'volume': m.get('volume', ''),
        'issue': m.get('issue', ''),
        'pages': m.get('page', ''),
        'doi': m.get('DOI', doi),
        'url': m.get('URL', f"https://doi.org/{doi}"),
        'abstract': _strip_jats(m.get('abstract', '')),
        'citationCount': m.get('is-referenced-by-count'),
    }


def _reconstruct_abstract(inv):
    """OpenAlex abstract_inverted_index -> 正常摘要文本。"""
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return ' '.join(w for _, w in positions)


def query_openalex(doi):
    data = _get_json(f"https://api.openalex.org/works/https://doi.org/{doi}?mailto={MAILTO}")
    if not data or 'id' in data and data.get('id') is None:
        pass
    if not data or 'id' not in data:
        return None
    oa = (data.get('open_access') or {})
    concepts = [c.get('display_name') for c in (data.get('concepts') or [])
                if c.get('display_name') and (c.get('score') or 0) >= 0.3][:6]
    loc = (data.get('primary_location') or {})
    src = (loc.get('source') or {})
    openalex_id = (data.get('id') or '').rsplit('/', 1)[-1]
    return {
        'openAlexId': openalex_id,
        'citationCount': data.get('cited_by_count'),
        'openAccessUrl': oa.get('oa_url') or '',
        'concepts': concepts,
        'year': data.get('publication_year'),
        'journal': src.get('display_name') or '',
        'publisher': src.get('host_organization_name') or '',
        'title': data.get('title') or '',
        'abstract': _reconstruct_abstract(data.get('abstract_inverted_index')),
    }


def _first_surname(meta):
    authors = meta.get('authors') or []
    surname = ''
    if authors:
        first = authors[0].strip()
        if re.search(r'[一-鿿]', first):
            surname = first[:3]           # 中文名取前两三字
        else:
            surname = first.split()[-1] if first.split() else first
    return re.sub(r'[^A-Za-z一-鿿]', '', surname) or 'Anon'


# 停用词（含介词/泛词，避免 slug 把 "around/the/method" 这类词夹进来形成残缺名）
_STOP = {'the', 'a', 'an', 'of', 'for', 'and', 'on', 'in', 'to', 'with', 'using',
         'based', 'from', 'by', 'via', 'study', 'studies', 'method', 'methods',
         'approach', 'analysis', 'around', 'into', 'under', 'over', 'between',
         'through', 'toward', 'towards', 'experimental', 'numerical', 'simulation',
         'investigation', 'novel', 'new', 'improved', 'effect', 'effects',
         'influence', 'influences', 'its', 'their', 'at', 'as', 'is', 'are'}


def suggest_id(meta):
    """paper-id：第一作者姓+年份 + 标题前几个**完整**关键词（不从词中间截断）。"""
    surname = _first_surname(meta)
    year = meta.get('year') or ''
    title = meta.get('title') or ''
    words = [w for w in re.findall(r'[A-Za-z0-9]+', title.lower())
             if w not in _STOP and len(w) > 2]
    slug = '-'.join(words[:3])
    base = f"{surname}{year}" if year else surname
    pid = base + (f"_{slug}" if slug else "")
    return re.sub(r'[ /\\:*?"<>|]+', '_', pid).strip('_') or 'paper'


def suggest_folder(meta):
    """论文文件夹名：第一作者姓+年份 + 完整原标题（严谨、可读，资源管理器里一眼看全）。"""
    surname = _first_surname(meta)
    year = meta.get('year') or ''
    title = (meta.get('title') or '').strip()
    base = f"{surname}{year}" if year else surname
    name = re.sub(r'[\\/:*?"<>|]+', ' ', f"{base} {title}".strip())
    name = re.sub(r'\s+', ' ', name).strip(' .')
    if len(name) > 120:
        name = name[:120].rsplit(' ', 1)[0].strip()
    return name or 'paper'


def merge(crossref, openalex, doi, lang):
    meta = {
        'title': '', 'translatedTitle': '', 'authors': [], 'year': None,
        'journal': '', 'publisher': '', 'volume': '', 'issue': '', 'pages': '',
        'doi': doi or '', 'url': f"https://doi.org/{doi}" if doi else '',
        'openAccessUrl': '', 'citationCount': None, 'openAlexId': '',
        'concepts': [], 'abstract': '',
        'metadataSources': [], 'detectedSourceLanguage': lang,
    }
    if crossref:
        meta['metadataSources'].append('crossref')
        for k in ('title', 'authors', 'year', 'journal', 'publisher', 'volume',
                  'issue', 'pages', 'doi', 'url', 'abstract', 'citationCount'):
            v = crossref.get(k)
            if v:
                meta[k] = v
    if openalex:
        meta['metadataSources'].append('openalex')
        # OpenAlex 优先补：被引/OA链接/概念/OpenAlexId
        for k in ('openAlexId', 'openAccessUrl', 'concepts'):
            if openalex.get(k):
                meta[k] = openalex[k]
        if openalex.get('citationCount') is not None:
            meta['citationCount'] = openalex['citationCount']
        # 兜底：Crossref 缺的用 OpenAlex 补
        for k in ('title', 'year', 'journal', 'publisher', 'abstract'):
            if not meta.get(k) and openalex.get(k):
                meta[k] = openalex[k]
    if not meta['metadataSources']:
        meta['metadataSources'] = ['pdf']
    meta['suggestedId'] = suggest_id(meta)
    meta['suggestedFolder'] = suggest_folder(meta)
    return meta


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S', stream=sys.stderr)

    ap = argparse.ArgumentParser(description='DOI 元数据增强 (Crossref + OpenAlex)')
    ap.add_argument('--pdf', default=None, help='PDF 路径（用于抽 DOI + 语种检测）')
    ap.add_argument('--doi', default=None, help='直接指定 DOI（跳过 PDF 抽取）')
    ap.add_argument('--out', default=None, help='把结果 JSON 也写到该文件')
    args = ap.parse_args()

    head = extract_pdf_head_text(args.pdf) if args.pdf else ""
    lang = detect_language(head) if head else "en"
    doi = args.doi or find_doi(head)

    if doi:
        logger.info("DOI: %s", doi)
    else:
        logger.warning("未找到 DOI，将降级为 PDF-only 元数据（标题/作者交由上层补全）")

    crossref = query_crossref(doi) if doi else None
    openalex = query_openalex(doi) if doi else None
    if doi and not crossref and not openalex:
        logger.warning("Crossref / OpenAlex 都没查到该 DOI")

    meta = merge(crossref, openalex, doi, lang)
    logger.info("元数据来源: %s | 建议ID: %s | 标题: %s",
                ",".join(meta['metadataSources']), meta['suggestedId'],
                (meta['title'] or '(待补)')[:60])

    out = json.dumps(meta, ensure_ascii=False, indent=2)
    if args.out:
        try:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(out)
            logger.info("已写入: %s", args.out)
        except IOError as e:
            logger.error("写入失败: %s", e)
    print(out)


if __name__ == '__main__':
    main()
