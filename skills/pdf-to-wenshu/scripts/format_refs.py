#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
format_refs.py —— 按期刊要求生成参考文献列表（pandoc citeproc + CSL 样式，零 token 确定性）。

数据 = 90_系统/_文献库.bib（build_bib 自动维护，verify_bib 补丁后为投稿级）；
样式 = CSL 官方仓库（约一万种期刊），首次使用自动下载并缓存到 90_系统/_csl样式/。

用法：
  python format_refs.py --vault "G:/论文知识库" --style gbt7714 --keys "holzer2008new,xu2025coarse"
  python format_refs.py --vault "G:/论文知识库" --style elsevier-num --all --out "引用清单.md"
  python format_refs.py --list-styles
  --style 可用别名（见 --list-styles）或 CSL 仓库里的任意样式文件名；--format plain|markdown（默认 plain，可直接粘 Word）。

长期写作建议走 Zotero 接管（见 90_系统/_Zotero对接说明.md）；本脚本适合快速出一版/核对格式。
"""
import os
import re
import io
import sys
import argparse
import subprocess
import tempfile

ALIASES = {
    'gbt7714':        ('china-national-standard-gb-t-7714-2015-numeric', 'GB/T 7714—2015 顺序编码（国内学报通用）'),
    'gbt7714-author': ('china-national-standard-gb-t-7714-2015-author-date', 'GB/T 7714—2015 著者-出版年'),
    'elsevier-num':   ('elsevier-vancouver', 'Elsevier 数字序号（Powder Technol./CES 等）'),
    'elsevier-author': ('elsevier-harvard', 'Elsevier 著者-年（Geomorphology 等）'),
    'apa':            ('apa', 'APA 7th'),
    'ieee':           ('ieee', 'IEEE'),
    'agu':            ('american-geophysical-union', 'AGU（JGR/WRR）'),
    'springer':       ('springer-basic-brackets', 'Springer 数字序号'),
    'nature':         ('nature', 'Nature 系'),
    'copernicus':     ('copernicus-publications', 'Copernicus（NHESS/ESurf）'),
    'taylor':         ('taylor-and-francis-national-library-of-medicine', 'Taylor & Francis 数字序号'),
}
CSL_SOURCES = [
    'https://raw.githubusercontent.com/citation-style-language/styles/master/%s.csl',
    'https://cdn.jsdelivr.net/gh/citation-style-language/styles@master/%s.csl',   # 国内可达镜像
]


def get_csl(vault, style):
    name = ALIASES.get(style, (style, ''))[0]
    cache_dir = os.path.join(vault, '90_系统', '_csl样式')
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, name + '.csl')
    if os.path.isfile(path) and os.path.getsize(path) > 500:
        return path
    import requests
    last_err = None
    for tpl in CSL_SOURCES:
        try:
            r = requests.get(tpl % name, timeout=25)
            if r.status_code == 200 and '<style' in r.text[:2000]:
                open(path, 'w', encoding='utf-8').write(r.text)
                return path
            last_err = 'HTTP %s' % r.status_code
        except Exception as e:
            last_err = str(e)
    raise SystemExit('下载 CSL 样式失败（%s）：%s——检查样式名或网络' % (name, last_err))


def bib_keys(bib_path):
    t = open(bib_path, encoding='utf-8').read()
    return set(re.findall(r'@\w+\{([^,\s]+),', t))


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault')
    ap.add_argument('--style', default='gbt7714')
    ap.add_argument('--keys', help='逗号分隔的 citekey（见各论文 index frontmatter）')
    ap.add_argument('--all', action='store_true', help='全库所有条目')
    ap.add_argument('--format', choices=['plain', 'markdown'], default='plain')
    ap.add_argument('--out', help='写入文件（缺省打印）')
    ap.add_argument('--list-styles', action='store_true')
    a = ap.parse_args()

    if a.list_styles:
        for k, (n, desc) in ALIASES.items():
            print('%-16s %s（%s）' % (k, desc, n))
        print('（也可直接传 CSL 仓库任意样式文件名，如 water-resources-research）')
        return
    if not a.vault:
        ap.error('--vault 必填')
    bib = os.path.join(a.vault, '90_系统', '_文献库.bib')
    if not os.path.isfile(bib):
        raise SystemExit('找不到 _文献库.bib，先跑 build_bib.py')

    if a.all:
        nocite = '@*'
    elif a.keys:
        keys = [k.strip().lstrip('@') for k in a.keys.split(',') if k.strip()]
        known = bib_keys(bib)
        bad = [k for k in keys if k not in known]
        if bad:
            print('⚠️ 这些 citekey 不在文献库里（跳过）：%s' % '、'.join(bad), file=sys.stderr)
        keys = [k for k in keys if k in known]
        if not keys:
            raise SystemExit('没有有效 citekey')
        nocite = ', '.join('@' + k for k in keys)
    else:
        ap.error('要么 --keys 要么 --all')

    csl = get_csl(a.vault, a.style)
    src = ('---\nbibliography: ["%s"]\ncsl: "%s"\nnocite: |\n  %s\n---\n'
           % (bib.replace('\\', '/'), csl.replace('\\', '/'), nocite))
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False,
                                     encoding='utf-8') as f:
        f.write(src)
        tmp = f.name
    try:
        fmt = 'plain' if a.format == 'plain' else 'markdown_strict'
        try:
            r = subprocess.run(['pandoc', '-f', 'markdown', '-t', fmt, '--citeproc',
                                '--wrap=none', tmp],
                               capture_output=True, encoding='utf-8', errors='replace')
        except FileNotFoundError:
            raise SystemExit('本脚本需要 pandoc（引用格式引擎）：https://pandoc.org/installing.html '
                             '（Windows: winget install pandoc）')
        if r.returncode != 0:
            raise SystemExit('pandoc 失败：%s' % (r.stderr or '')[-600:])
        out_text = r.stdout.strip()
    finally:
        os.unlink(tmp)

    if a.out:
        open(a.out, 'w', encoding='utf-8').write(out_text + '\n')
        print('已写入 %s（%d 行）' % (a.out, out_text.count('\n') + 1))
    else:
        print(out_text)


if __name__ == '__main__':
    main()
