#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_citation_gaps.py —— 引文缺口榜：把全库论文的参考文献汇总去重，
按「库内被引次数」排名，输出 <vault>/90_系统/_引文缺口榜.md。

- 未入库缺口榜：被 ≥min-count 篇库内论文共同引用、但还没入库的文献
  ——领域用脚投票选出的必修课 + 知识库的结构性漏洞，直接当阅读/下载队列用。
- 已入库被引榜：库内互引最多的论文（知识库的骨架节点）。

**主题范围模式（写综述用）**：--under "CFD-DEM方法/粗粒化" 只拿该文件夹的论文当种子，
或 --seeds "Example2024,Example2024"（pid 子串，逗号分隔）手点种子——
输出变成「这个主题的必引缺口」，写到 _引文缺口榜_<范围>.md（全库榜不受影响）。
范围模式下门槛常用 2（种子少）；全库默认 3。

复用 build_refs.py 的解析器直接从各篇 content/<pid>.txt 提取（不依赖正文是否已回填）；
DOI 只用条目自带的 + _引文DOI缓存.json（build_refs 跑批攒的），**不联网**。
条目身份：DOI 优先，无 DOI 用 (年份, 一作词, 4 个最长内容词) 模糊键，并做一轮
「模糊键 → 已知 DOI 组」折叠，减少同一文献因体裁差异被拆成两条。
库内已入库判定始终对全库匹配（主题外但已入库的不算缺口，会标出）。

榜单为自动生成的系统文件：**纯文本不加 [[ ]] 双链**（全双链的自动索引=关系图炸弹）。

用法：python build_citation_gaps.py --vault "G:/论文知识库"
      [--min-count 3] [--top 120] [--under 子路径] [--seeds pid1,pid2]
"""
import os
import re
import io
import sys
import glob
import argparse
import datetime
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'build_refs', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_refs.py'))
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)


def fuzzy_key(text):
    ym = br.YEAR_PAT.search(text)
    year = ym.group(0)[:4] if ym else ''
    toks = br.norm_tokens(text)
    first = toks[0] if toks else ''
    sig = tuple(sorted(sorted(toks, key=len, reverse=True)[:4]))
    return (year, first, sig)


def in_scope(article_path, vault, under=None, seeds=None):
    if under:
        rel = os.path.relpath(article_path, os.path.join(vault, 'Papers'))
        if not rel.replace('\\', '/').startswith(under.strip('/').replace('\\', '/')):
            return False
    if seeds:
        base = os.path.basename(article_path)
        if not any(s.strip() and s.strip() in base for s in seeds):
            return False
    return True


def collect(vault, under=None, seeds=None):
    papers = br.load_vault_papers(vault)
    cache = br.load_cache(os.path.join(vault, '90_系统', '_引文DOI缓存.json'))
    works = {}          # key -> dict(texts, dois, vault_pid, citers, year)
    doi_by_fuzzy = {}   # 模糊键 -> ('doi', doi)，用于折叠无 DOI 的同文献
    n_art, n_parsed, failed = 0, 0, []

    arts = sorted(glob.glob(os.path.join(vault, 'Papers', '**', '*.正文.md'), recursive=True))
    if under or seeds:
        arts = [a for a in arts if in_scope(a, vault, under, seeds)]
    parsed_entries = []     # (citer_pid, text, doi, vault_pid)
    for a in arts:
        n_art += 1
        pid = os.path.basename(a)[:-len('.正文.md')]
        txt_path = os.path.join(os.path.dirname(a), pid + '.txt')
        if not os.path.isfile(txt_path):
            failed.append((pid, '无 txt'))
            continue
        lines = br.locate_refs_segment(open(txt_path, encoding='utf-8').read())
        if lines is None:
            failed.append((pid, '找不到 References 段'))
            continue
        style, entries = br.clean_and_group(lines)
        if not entries:
            failed.append((pid, '解析不出条目'))
            continue
        n_parsed += 1
        for _, text in entries:
            if len(text) < 25:
                continue
            doi = br.extract_doi(text) or cache.get(br.cache_key(text))
            if not doi and not br.YEAR_PAT.search(text):
                continue
            vp = br.match_vault(text, doi, papers, pid)
            parsed_entries.append((pid, text, doi, vp['pid'] if vp else None))
            if doi:
                doi_by_fuzzy.setdefault(fuzzy_key(text), doi)

    for pid, text, doi, vpid in parsed_entries:
        if not doi:
            doi = doi_by_fuzzy.get(fuzzy_key(text))    # 折叠进已知 DOI 组
        key = ('vault', vpid) if vpid else (('doi', doi) if doi else ('fz',) + fuzzy_key(text))
        w = works.setdefault(key, dict(texts=[], dois=set(), vault_pid=vpid,
                                       citers=set(), year=''))
        w['texts'].append(text)
        if doi:
            w['dois'].add(doi)
        if vpid:
            w['vault_pid'] = vpid
        w['citers'].add(pid)
        if not w['year']:
            ym = br.YEAR_PAT.search(text)
            w['year'] = ym.group(0)[:4] if ym else ''

    return works, n_art, n_parsed, failed


def rep_text(w, limit=170):
    t = max(w['texts'], key=len)
    t = re.sub(r'https?://\S+', '', t).strip()      # 榜单里链接单独给，正文去 URL 噪声
    return (t[:limit] + '…') if len(t) > limit else t


def fmt_citers(citers, cap=8):
    lst = sorted(citers)
    s = '、'.join(lst[:cap])
    if len(lst) > cap:
        s += ' 等 %d 篇' % len(lst)
    return s


def scope_label(under=None, seeds=None):
    if under:
        return re.sub(r'[\\/:*?"<>|\s]+', '-', under.strip('/'))
    if seeds:
        return '种子%d篇' % len([s for s in seeds if s.strip()])
    return None


def build(vault, min_count=3, top=120, under=None, seeds=None):
    works, n_art, n_parsed, failed = collect(vault, under, seeds)
    gaps = [w for k, w in works.items() if not w['vault_pid'] and len(w['citers']) >= min_count]
    gaps.sort(key=lambda w: (-len(w['citers']), -(int(w['year']) if w['year'] else 0)))
    gaps = gaps[:top]
    invault = [w for k, w in works.items() if w['vault_pid'] and len(w['citers']) >= 1]
    invault.sort(key=lambda w: -len(w['citers']))

    label = scope_label(under, seeds)
    title = '🕳️ 引文缺口榜' + ('（%s）' % (under or '手选种子') if label else '')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    scope_line = ('> 范围：**%s** 的 %d 篇种子论文（写综述的必引缺口清单）。'
                  % (under or '、'.join(s.strip() for s in seeds), n_art)) if label else \
                 '> 范围：全库（知识库的结构性漏洞总榜）。'
    L = ['---', 'noteType: system', 'cssclasses:', '  - dashboard', '---',
         '# %s' % title,
         '',
         '> 参考文献汇总去重后，按**种子论文共引次数**排名（%s 由 build_citation_gaps.py 生成，勿手改）。' % now,
         scope_line,
         '> **被多篇共引却未入库的文献 = 必修课/必引项**——当阅读/下载队列用：',
         '> 挑中哪篇 → campus-lit-download 下载 → pdf-to-wenshu 入库 → 重跑本榜自动出队。',
         '> 统计：扫描 %d 篇正文，成功解析 %d 篇的参考文献；条目身份按 DOI/模糊键去重；纯文本无双链（防关系图炸弹）。'
         % (n_art, n_parsed),
         '',
         '## 📥 未入库缺口（被引 ≥%d 次）' % min_count,
         '']
    if not gaps:
        L.append('（暂无——要么都入库了，要么把 --min-count 降一档再看）')
    for i, w in enumerate(gaps, 1):
        doi = sorted(w['dois'])[0] if w['dois'] else None
        parts = ['**被引 %d 次**' % len(w['citers']), rep_text(w)]
        if doi:
            parts.append('[🔗 DOI](%s)' % br.doi_url(doi))
        L.append('%d. %s' % (i, ' ｜ '.join(parts)))
        L.append('    - 引用者：%s' % fmt_citers(w['citers']))
    L += ['', '## 🏛️ 已入库被引榜（%s互引的骨架节点）' % ('主题内' if label else '库内'), '']
    for w in invault[:40]:
        L.append('- **被引 %d 次** ｜ %s' % (len(w['citers']), w['vault_pid']))
    if failed:
        L += ['', '## ⚠️ 未纳入统计（txt 里解析不出参考文献）', '']
        for pid, why in failed:
            L.append('- %s（%s）' % (pid, why))
    fname = '_引文缺口榜%s.md' % (('_' + label) if label else '')
    out = os.path.join(vault, '90_系统', fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return dict(out=out, works=len(works), gaps=len(gaps), invault=len(invault),
                parsed=n_parsed, total=n_art, failed=len(failed))


if __name__ == '__main__':
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--min-count', type=int, default=3,
                    help='入榜门槛：被几篇种子论文共引（全库默认 3；主题范围建议 2）')
    ap.add_argument('--top', type=int, default=120)
    ap.add_argument('--under', default=None, help='主题范围：Papers/ 下的子路径，如 CFD-DEM方法/粗粒化')
    ap.add_argument('--seeds', default=None, help='主题范围：逗号分隔的 pid 子串，手点种子论文')
    a = ap.parse_args()
    seeds = a.seeds.split(',') if a.seeds else None
    st = build(a.vault, a.min_count, a.top, a.under, seeds)
    print('种子 %d 篇（解析成功 %d，失败 %d）· 去重后 %d 个被引文献 · 缺口榜 %d 条 · 已入库被引 %d 篇'
          % (st['total'], st['parsed'], st['failed'], st['works'], st['gaps'], st['invault']))
    print('输出：%s' % st['out'])
