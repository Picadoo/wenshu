#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_bib.py —— 文献库元数据核对（投稿级质检）：拿每篇的 DOI 去 Crossref
逐条比对权威元数据，产出：
  1. 90_系统/_bib补丁.json —— 可安全自动修的字段（条目类型/卷/期/页码），
     build_bib.py 生成 bib 时自动套用（补丁按 DOI 键控，幂等）。
  2. 90_系统/_bib核对报告.md —— 三档：✅一致 / 🔧已补丁 / ⚠️需人工
     （无 DOI、Crossref 查无、标题对不上=DOI 可能挂错——这些**不自动改**，人工/AI 逐条看）。

条目类型映射（决定引用格式里的 [J]/[C]/[M]/斜体等）：
  journal-article→article · proceedings-article→inproceedings · book-chapter→incollection
  book/monograph/edited-book→book · posted-content→misc(预印本) · dissertation→phdthesis · report→techreport

用法：python verify_bib.py --vault "G:/论文知识库"
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

TYPE_MAP = {
    'journal-article': 'article', 'proceedings-article': 'inproceedings',
    'book-chapter': 'incollection', 'book': 'book', 'monograph': 'book',
    'edited-book': 'book', 'reference-book': 'book', 'posted-content': 'misc',
    'dissertation': 'phdthesis', 'report': 'techreport',
}


def norm_tokens(s):
    return [w for w in re.split(r'[^a-z0-9]+', (s or '').lower())
            if len(w) >= 4 and not w.isdigit()]


def containment(a, b):
    """a 的内容词有多大比例出现在 b 里。"""
    ta = norm_tokens(a)
    if not ta:
        return 1.0      # 中文题名无英文词，放行（走人工档）
    tb = set(norm_tokens(b))
    return sum(1 for w in ta if w in tb) / len(ta)


def collect(vault):
    items = []
    for p in glob.glob(os.path.join(vault, 'Papers', '**', '*.md'), recursive=True):
        if os.sep + 'content' + os.sep in p or os.sep + 'images' + os.sep in p:
            continue
        try:
            txt = open(p, encoding='utf-8').read()
        except Exception:
            continue
        if 'noteType: index' not in txt[:2400] and 'p2o/paper' not in txt[:2400]:
            continue
        fm = txt.split('---', 2)[1] if txt.startswith('---') else ''

        def f1(pat):
            m = re.search(pat, fm, re.M)
            return m.group(1).strip().strip('"') if m else ''
        m = re.search(r'\*\*原题\*\*[：:]\s*(.*?)(?=\n[-*] \*\*|\n##|\Z)', txt, re.S)
        en_title = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
        items.append(dict(pid=os.path.basename(p)[:-3], doi=f1(r'^doi:\s*"?([^"\n]*)"?').lower(),
                          year=f1(r'^year:\s*"?([^"\n]*)"?'), title=en_title))
    return items


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    a = ap.parse_args()

    import requests
    s = requests.Session()
    s.headers['User-Agent'] = 'p2o-verify-bib/1.0 (mailto:p2o-skill@example.org)'

    items = collect(a.vault)
    ok, patched, manual = [], [], []
    patches = {}
    for it in items:
        pid, doi = it['pid'], it['doi']
        if not doi or not doi.startswith('10.'):
            manual.append((pid, '无 DOI——格式化引用前需人工补书目'))
            continue
        try:
            r = s.get('https://api.crossref.org/works/' + doi, timeout=20)
            time.sleep(0.1)
        except Exception:
            r = None
        if r is None or r.status_code != 200:
            manual.append((pid, 'Crossref 查无此 DOI（%s）——中文刊/预印本常见，需人工核' % doi))
            continue
        w = r.json()['message']
        # 标题一致性——防 DOI 挂错篇
        cr_title = (w.get('title') or [''])[0]
        t = containment(cr_title, it['title'] or pid)
        if t < 0.55:
            manual.append((pid, '标题对不上（DOI 可能挂错）：Crossref=「%s…」' % cr_title[:60]))
            continue
        # 收集补丁字段
        p = {}
        et = TYPE_MAP.get(w.get('type') or '', '')
        if et and et != 'article':
            p['entrytype'] = et
        for src, dst in (('volume', 'volume'), ('issue', 'number'), ('page', 'pages')):
            v = (w.get(src) or '').strip()
            if v:
                p[dst] = v.replace('-', '--') if dst == 'pages' else v
        dp = (w.get('issued') or {}).get('date-parts') or [[None]]
        if dp[0][0] and it['year'] and str(dp[0][0]) != it['year']:
            p['year'] = str(dp[0][0])
        ct = (w.get('container-title') or [''])[0]
        if ct:
            p['journal_full'] = ct
        if p:
            patches[doi] = p
            patched.append((pid, '、'.join(sorted(p.keys()))))
        else:
            ok.append(pid)

    sysdir = os.path.join(a.vault, '90_系统')
    os.makedirs(sysdir, exist_ok=True)
    json.dump(patches, open(os.path.join(sysdir, '_bib补丁.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    L = ['# 🧾 文献库元数据核对报告', '',
         '> %s 由 verify_bib.py 生成（Crossref 权威元数据逐条比对）。' % now,
         '> 🔧 档的字段已写入 `_bib补丁.json`，build_bib.py 生成 bib 时自动套用；⚠️ 档**不自动改**，逐条人工/AI 核。',
         '',
         '共 %d 篇：✅ 完全一致 %d ｜ 🔧 已补丁 %d ｜ ⚠️ 需人工 %d' % (len(items), len(ok), len(patched), len(manual)),
         '', '## ⚠️ 需人工核对', '']
    for pid, why in manual:
        L.append('- **%s**：%s' % (pid, why))
    L += ['', '## 🔧 已自动补丁（字段）', '']
    for pid, fields in patched:
        L.append('- %s：%s' % (pid, fields))
    open(os.path.join(sysdir, '_bib核对报告.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('共 %d 篇：一致 %d · 补丁 %d · 需人工 %d' % (len(items), len(ok), len(patched), len(manual)))
    print('补丁：_bib补丁.json ｜ 报告：_bib核对报告.md（都在 90_系统/）')


if __name__ == '__main__':
    main()
