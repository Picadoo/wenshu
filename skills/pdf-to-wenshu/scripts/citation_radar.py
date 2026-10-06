#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
citation_radar.py —— 引用雷达（前向追踪）：谁在引用我库里的论文？
参考文献只能往回看（它引了谁）；写综述最怕漏掉**最新进展**——本脚本用 OpenAlex 的
cited-by 接口（免费、无需 key）把方向反过来：

  库内种子论文 → 查"引用了它们的新论文" → 按「一篇新文命中几篇种子」排序
  ——引用了你 4 篇种子的 2025 年新文，几乎必然是你该看的最新进展。

与 build_citation_gaps.py（向后滚雪球）互为镜像，合称综述搜文献的两翼。

- 范围：--under "CFD-DEM方法/粗粒化" 按文件夹圈种子，或 --seeds "pid1,pid2" 手点；
  不给范围=全库（174 篇大约要几分钟，主题模式更常用）。
- 过滤：--since 年份（默认近 3 年）、--min-hits 命中种子数（默认 2）。
- 已入库的引用者自动排除（那些不是"新进展"，是你已经读过的东西）。
- DOI→OpenAlex ID 的解析结果缓存在 90_系统/_openalex缓存.json；引用列表不缓存（要新鲜度）。
- 输出 90_系统/_引用雷达[_<范围>].md，纯文本无 [[ ]] 双链（防关系图炸弹）。

用法：python citation_radar.py --vault "G:/论文知识库" --under "CFD-DEM方法/非球颗粒"
      [--since 2023] [--min-hits 2] [--top 80] [--max-pages 5]
"""
import os
import re
import io
import sys
import json
import time
import glob
import argparse
import datetime
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'build_refs', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_refs.py'))
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)

API = 'https://api.openalex.org'
MAILTO = 'p2o-skill@example.org'
SELECT = 'id,doi,title,publication_year,cited_by_count,primary_location,open_access'


def get_json(session, url, tries=2):
    for i in range(tries):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(2.5)
                continue
            return None
        except Exception:
            if i + 1 < tries:
                time.sleep(1.5)
                continue
            return None
    return None


def resolve_id(session, doi, cache):
    """DOI → OpenAlex work id（缓存；查不到缓存 null）。"""
    key = doi.lower()
    if key in cache:
        return cache[key]
    j = get_json(session, '%s/works/doi:%s?select=id&mailto=%s' % (API, key, MAILTO))
    wid = (j or {}).get('id')
    wid = wid.rsplit('/', 1)[-1] if wid else None
    cache[key] = wid
    time.sleep(0.12)
    return wid


def citing_works(session, wid, max_pages=5):
    """分页拉取引用了 wid 的论文。"""
    out, cursor = [], '*'
    for _ in range(max_pages):
        url = ('%s/works?filter=cites:%s&per-page=200&cursor=%s&select=%s&mailto=%s'
               % (API, wid, cursor, SELECT, MAILTO))
        j = get_json(session, url)
        if not j:
            break
        out.extend(j.get('results', []))
        cursor = (j.get('meta') or {}).get('next_cursor')
        time.sleep(0.12)
        if not cursor:
            break
    return out


def load_seeds(vault, under=None, seeds=None):
    """种子 = 范围内有 DOI 的 index。返回 [(pid, doi)] 与无 DOI 名单。"""
    items, no_doi = [], []
    for p in glob.glob(os.path.join(vault, 'Papers', '**', '*.md'), recursive=True):
        if os.sep + 'content' + os.sep in p:
            continue
        try:
            head = open(p, encoding='utf-8').read(2000)
        except Exception:
            continue
        if 'noteType: index' not in head and 'p2o/paper' not in head:
            continue
        pid = os.path.basename(p)[:-3]
        if under:
            rel = os.path.relpath(p, os.path.join(vault, 'Papers')).replace('\\', '/')
            if not rel.startswith(under.strip('/').replace('\\', '/')):
                continue
        if seeds and not any(s.strip() and s.strip() in pid for s in seeds):
            continue
        m = re.search(r'^doi:\s*"?([^"\n]+?)"?\s*$', head, re.M)
        doi = (m.group(1).strip() if m else '')
        if doi and doi.startswith('10.'):
            items.append((pid, doi.lower()))
        else:
            no_doi.append(pid)
    return items, no_doi


def scope_label(under=None, seeds=None):
    if under:
        return re.sub(r'[\\/:*?"<>|\s]+', '-', under.strip('/'))
    if seeds:
        return '种子%d篇' % len([s for s in seeds if s.strip()])
    return None


def build(vault, under=None, seeds=None, since=None, min_hits=2, top=80, max_pages=5):
    import requests
    session = requests.Session()
    session.headers['User-Agent'] = 'p2o-citation-radar/1.0 (mailto:%s)' % MAILTO

    since = since or (datetime.date.today().year - 2)
    seeds_list, no_doi = load_seeds(vault, under, seeds)
    all_vault_dois = {d for _, d in load_seeds(vault)[0]}     # 全库 DOI 用于排除已入库

    cache_path = os.path.join(vault, '90_系统', '_openalex缓存.json')
    cache = br.load_cache(cache_path)
    hits = {}       # citing_id -> dict(meta, seeds:set)
    unresolved = []
    for pid, doi in seeds_list:
        wid = resolve_id(session, doi, cache)
        if not wid:
            unresolved.append(pid)
            continue
        for w in citing_works(session, wid, max_pages):
            wdoi = (w.get('doi') or '').replace('https://doi.org/', '').lower()
            if wdoi and wdoi in all_vault_dois:
                continue                            # 已入库的引用者不算新进展
            year = w.get('publication_year') or 0
            if year < since:
                continue
            h = hits.setdefault(w['id'], dict(
                doi=wdoi, title=w.get('title') or '(无题)', year=year,
                cited=w.get('cited_by_count') or 0,
                venue=((w.get('primary_location') or {}).get('source') or {}).get('display_name') or '',
                oa=(w.get('open_access') or {}).get('oa_url') or '',
                seeds=set()))
            h['seeds'].add(pid)
    br.save_cache(cache_path, cache)

    rows = [h for h in hits.values() if len(h['seeds']) >= min_hits]
    rows.sort(key=lambda h: (-len(h['seeds']), -h['year'], -h['cited']))
    rows = rows[:top]

    label = scope_label(under, seeds)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    title = '📡 引用雷达' + ('（%s）' % (under or '手选种子') if label else '')
    L = ['---', 'noteType: system', 'cssclasses:', '  - dashboard', '---',
         '# %s' % title,
         '',
         '> 谁在引用我库里的论文？OpenAlex 前向追踪（%s 生成，勿手改）。' % now,
         '> 范围：%s 的 %d 篇种子 ｜ 只看 %d 年以来 ｜ 命中 ≥%d 篇种子才上榜 ｜ 已入库的引用者已排除。'
         % (under or ('手选' if seeds else '全库'), len(seeds_list), since, min_hits),
         '> **命中种子越多 = 和你的知识库越同频**——写综述的"最新进展"章节直接从这里取材；',
         '> 看中哪篇 → 点 DOI/OA → campus-lit-download 下载 → pdf-to-wenshu 入库。',
         '',
         '## 🛰️ 最新进展（按命中种子数排序）',
         '']
    if not rows:
        L.append('（无命中——把 --min-hits 降到 1 或 --since 再放宽试试）')
    for i, h in enumerate(rows, 1):
        parts = ['**命中 %d 篇种子**' % len(h['seeds']),
                 '(%d) %s' % (h['year'], h['title'][:110])]
        if h['venue']:
            parts.append(h['venue'][:40])
        parts.append('全球被引 %d' % h['cited'])
        if h['doi']:
            parts.append('[🔗 DOI](%s)' % br.doi_url(h['doi']))
        if h['oa']:
            parts.append('[📄 OA](%s)' % h['oa'])
        L.append('%d. %s' % (i, ' ｜ '.join(parts)))
        L.append('    - 引用了：%s' % '、'.join(sorted(h['seeds'])[:8] +
                                             (['等 %d 篇' % len(h['seeds'])] if len(h['seeds']) > 8 else [])))
    if unresolved or no_doi:
        L += ['', '## ⚠️ 未纳入的种子', '']
        for pid in unresolved:
            L.append('- %s（OpenAlex 查无此 DOI）' % pid)
        for pid in no_doi:
            L.append('- %s（index 无 DOI）' % pid)
    fname = '_引用雷达%s.md' % (('_' + label) if label else '')
    out = os.path.join(vault, '90_系统', fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return dict(out=out, seeds=len(seeds_list), rows=len(rows),
                unresolved=len(unresolved) + len(no_doi), candidates=len(hits))


if __name__ == '__main__':
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--under', default=None, help='主题范围：Papers/ 下子路径')
    ap.add_argument('--seeds', default=None, help='逗号分隔的 pid 子串')
    ap.add_argument('--since', type=int, default=None, help='只看该年以来（默认近 3 年）')
    ap.add_argument('--min-hits', type=int, default=2)
    ap.add_argument('--top', type=int, default=80)
    ap.add_argument('--max-pages', type=int, default=5, help='每篇种子最多翻几页引用(×200)')
    a = ap.parse_args()
    st = build(a.vault, a.under, a.seeds.split(',') if a.seeds else None,
               a.since, a.min_hits, a.top, a.max_pages)
    print('种子 %d 篇（未解析 %d）· 候选引用者 %d · 上榜 %d 条' %
          (st['seeds'], st['unresolved'], st['candidates'], st['rows']))
    print('输出：%s' % st['out'])
